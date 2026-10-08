"""Convert one F1 2021 car from the player's install into Skyrim LE files (mesh, textures).

Formats worked out in this project (see MODLOG.md) on top of EgoEngineLibrary's ERP/mesh templates (MIT).
"""
import io
import os
import re
import struct

import lz4.block
import numpy as np
import zstandard
from PIL import Image

from egoerp import read_erp
from skynif import build_skinned

UNITS_PER_METRE = 1 / 0.0142875
MAX_PER_SHAPE = 16000
HEADER = 0x4C


# --- F1 2021 mesh/model resources -----------------------------------------------------------------------------
def _cstrs(b, off, n):
    out = []
    for _ in range(n):
        end = b.index(0, off); out.append(b[off:end].decode("ascii", "replace")); off = end + 1
    return out


def parse_mesh(b):
    h = struct.unpack_from("<19I", b, 0)
    sub_n, vb_n, ib_n = h[:3]
    subs = []
    for i in range(sub_n):
        v = struct.unpack_from("<6I4f4I8I", b, HEADER + i * 88)
        subs.append(dict(start=v[3], count=v[4], base=v[5], prim=v[1], mat=v[12], ib=v[13], vbs=list(v[14:14 + v[0]])))
    return subs, _cstrs(b, h[5] + HEADER, vb_n), _cstrs(b, h[6] + HEADER, ib_n), b[h[7] + HEADER:]


def parse_model_nodes(b):
    mesh_n, node_n, skin_n, name_n, _pad, lod_n = struct.unpack_from("<I4HI", b, 0)
    o = 16 + 16 + 4 + 24 + 8 * lod_n + 4      # sphere, mirror bits, AABB (F1 2021), LOD table, LOD strategy
    nodes = []
    for _ in range(node_n):
        v = struct.unpack_from("<Ii3f4f3f16fii", b, o); o += 120
        nodes.append(dict(nameIndex=v[0], parent=v[1], t=v[2:5], r=v[5:9], s=v[9:12]))
    o += 2 * skin_n
    for _ in range(mesh_n):
        o = b.index(0, o) + 1
    names = b[o:]
    for n in nodes:
        n["name"] = names[n["nameIndex"]:names.index(0, n["nameIndex"])].decode()
    return nodes


def _quat(q):
    x, y, z, w = q
    if x == y == z == w == 0:
        return np.eye(3)
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def part_transforms(nodes):
    local = []
    for n in nodes:
        M = np.eye(4); M[:3, :3] = _quat(n["r"]) * np.array(n["s"]); M[:3, 3] = n["t"]; local.append(M)
    world, out = {}, {}

    def w(i):
        if i not in world:
            p = nodes[i]["parent"]
            world[i] = local[i] if p < 0 else w(p) @ local[i]
        return world[i]

    for i, n in enumerate(nodes):
        out.setdefault(n["name"], w(i))
    return out


def _unit(v):
    return v / (np.linalg.norm(v, axis=1, keepdims=True) + 1e-12)


def _to_skyrim(v):
    """F1: metres, X right, Y up, Z forward -> Skyrim: units, X right, Y forward, Z up."""
    return np.stack([v[:, 0], v[:, 2], v[:, 1]], axis=1) * UNITS_PER_METRE


def _split(attrs, tri, limit):
    step = limit // 3 if len(tri) > limit else max(len(tri), 1)
    for start in range(0, len(tri), step):
        used, local = np.unique(tri[start:start + step], return_inverse=True)
        yield tuple(a[used] for a in attrs), local.reshape(-1, 3)


def car_shapes(resources, team, lod, skip, material_textures, tex_dir):
    by_name = {r.name: r for r in resources}
    model = next(r for r in resources if r.type == "GfxModelRes" and re.search(rf"/{team}\.idf\?model$", r.name))
    xf = part_transforms(parse_model_nodes(model.frag(0)))
    car_shapes.wheels = {w: xf[w] for w in ("wheel_fl", "wheel_fr", "wheel_bl", "wheel_br") if w in xf}
    buffers = {}

    def stream(eaid):
        key = eaid.split("//", 1)[-1].split("/", 1)[-1]
        if key not in buffers:
            r = by_name[key]
            hdr = r.frag(0)
            buffers[key] = (struct.unpack_from("<3I", hdr)[1], r.frag(1))
        return buffers[key]

    groups = {}
    meshes = sorted(r for r in by_name if re.search(rf"\.idf\?lod={lod}(&[a-z0-9_]+)?&mesh$", r))
    for mn in meshes:
        part = re.search(r"lod=\d+(?:&([a-z0-9_]+))?&mesh", mn).group(1) or "body"
        subs, vbs, ibs, mats = parse_mesh(by_name[mn].frag(0))
        M = None if part == "body" else next((m for k, m in xf.items() if k.startswith(part)), None)
        for s in subs:
            mat = mats[s["mat"]:mats.index(0, s["mat"])].decode()
            if s["prim"] != 4 or s["count"] == 0 or mat in skip:
                continue
            _, ibd = stream(ibs[s["ib"]])
            ib = np.frombuffer(ibd, "<u2")[s["start"]:s["start"] + s["count"]].astype(np.int64) + s["base"]
            used, local = np.unique(ib, return_inverse=True)
            st = [stream(vbs[i]) for i in s["vbs"]]
            sizes = [z for z, _ in st]
            pos = np.frombuffer(st[0][1], np.uint8).reshape(-1, sizes[0])[used, :12].copy().view("<f4").reshape(-1, 3)
            if sizes[:4] == [12, 8, 8, 8]:
                nrm = np.frombuffer(st[1][1], "<f2").reshape(-1, 4)[used, :3].astype(np.float32)
                tg4 = np.frombuffer(st[2][1], "<f2").reshape(-1, 4)[used].astype(np.float32)
                uv = np.frombuffer(st[3][1], "<f2").reshape(-1, 4)[used, :2].astype(np.float32)
                tan, sign = tg4[:, :3], np.where(tg4[:, 3] < 0, -1.0, 1.0)[:, None]
            else:
                n = len(used)
                nrm = np.tile([0, 1, 0], (n, 1)).astype(np.float32); uv = np.zeros((n, 2), np.float32)
                tan, sign = np.tile([1, 0, 0], (n, 1)).astype(np.float32), np.ones((n, 1))
            if M is not None:
                pos = pos @ M[:3, :3].T + M[:3, 3]; nrm = nrm @ M[:3, :3].T; tan = tan @ M[:3, :3].T
            tri = local.reshape(-1, 3)[:, ::-1]
            n_s, t_s = _unit(_to_skyrim(nrm)), _unit(_to_skyrim(tan))
            b_s = -np.cross(n_s, t_s) * sign
            key = next((v for k, v in material_textures.items() if mat.lower().startswith(k)), material_textures["other"])
            for piece in _split((_to_skyrim(pos), n_s, t_s, b_s, uv), tri, MAX_PER_SHAPE):
                groups.setdefault(key, []).append(piece)

    shapes = []
    for tex, parts in groups.items():
        cur = dict(a=[], f=[], count=0, tris=0)

        def flush():
            if cur["a"]:
                v, n, t, b, uv = (np.concatenate([a[i] for a in cur["a"]]) for i in range(5))
                folder = tex_dir if tex != "carbon" else "textures/dlgp/common"
                shapes.append(dict(name=f"{tex}_{len(shapes)}", verts=v, normals=n, tangents=t, bitangents=b, uvs=uv,
                                   tris=np.concatenate(cur["f"]),
                                   textures=[f"{folder}/{tex}.dds".replace("/", "\\"),
                                             "textures\\dlgp\\common\\flat_n.dds"]))
            cur.update(a=[], f=[], count=0, tris=0)

        for attrs, f in parts:
            if cur["count"] + len(attrs[0]) > MAX_PER_SHAPE or cur["tris"] + len(f) > MAX_PER_SHAPE:
                flush()
            cur["a"].append(attrs); cur["f"].append(f + cur["count"])
            cur["count"] += len(attrs[0]); cur["tris"] += len(f)
        flush()
    return shapes


def write_mount_mesh(shapes, out_path):
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    lift = -float(min(s["verts"][:, 2].min() for s in shapes))   # actor origin is at ground level
    build_skinned(out_path, shapes, "NPC Root [Root]", z_offset=lift)
    return lift


# --- textures -------------------------------------------------------------------------------------------------
FORMATS = {52: (b"DXT1", 8), 54: (b"DXT1", 8), 55: (b"DXT5", 16), 57: (b"DXT5", 16), 62: (b"DXT3", 16),
           63: (b"ATI1", 8), 65: (b"ATI2", 16), 69: (None, 16), 70: (None, 16)}
DXGI = {69: 98, 70: 99}


def _dds(w, h, mips, fmt, top, body):
    fourcc = FORMATS[fmt][0]
    flags = 0x1 | 0x2 | 0x4 | 0x1000 | 0x80000 | (0x20000 if mips > 1 else 0)
    caps = 0x1000 | ((0x8 | 0x400000) if mips > 1 else 0)
    pf = struct.pack("<II4sIIIII", 32, 0x4, fourcc or b"DX10", 0, 0, 0, 0, 0)
    hdr = b"DDS " + struct.pack("<IIIIIII", 124, flags, h, w, top, 0, mips) + b"\0" * 44 + pf
    hdr += struct.pack("<IIIII", caps, 0, 0, 0, 0)
    if fourcc is None:
        hdr += struct.pack("<IIIII", DXGI[fmt], 3, 0, 1, 0)
    return hdr + body


def texture_image(resources, name_suffix, f1_dir, exact=None):
    """Decode an F1 texture (full resolution from its .mipmaps file) to a PIL image."""
    r = next(x for x in resources if x.type == "GfxSurfaceRes" and
             (x.name == exact if exact else x.name.endswith(name_suffix + ".tif.image")))
    f0 = r.frag(0)
    _, _, fmt, w, h, _, mips, arr, _ = struct.unpack_from("<iiiIIiIIi", f0, 0)
    data = r.frag(1)
    body, top = b"", len(data)
    if len(r.fragments) > 2:
        f2 = r.frag(2)
        n = f2[0]; mipfile = f2[1:1 + n].decode(); o = 1 + n
        count = struct.unpack_from("<I", f2, o)[0]
        f123 = len(f2) == n + 6 + 26 * count + 8
        if f123:
            o += 1; count = struct.unpack_from("<I", f2, o)[0]
        o += 4
        entries = []
        for _ in range(count):
            if f123:
                o += 1
            comp = f2[o]; _, packed, size = struct.unpack_from("<QQQ", f2, o + 1); o += 25
            entries.append((comp, packed, size))
        mp = os.path.join(f1_dir, mipfile)
        if entries and os.path.exists(mp):
            with open(mp, "rb") as mf:
                for comp, packed, size in entries:
                    raw = mf.read(packed)
                    body += (raw if comp == 0 else lz4.block.decompress(raw, uncompressed_size=size) if comp == 3
                             else zstandard.ZstdDecompressor().decompress(raw, max_output_size=size))
            top = entries[0][2]
            w, h, mips = w << len(entries), h << len(entries), mips + len(entries)
    if arr > 1:
        data = data[: len(data) // arr]
    im = Image.open(io.BytesIO(_dds(w, h, mips, fmt, top, body + data)))
    im.load()
    return im.convert("RGBA")


def write_textures(resources, team, f1_dir, out_dir, keys, size=1024):
    os.makedirs(out_dir, exist_ok=True)
    for key in keys:
        im = texture_image(resources, f"{team}_{key}", f1_dir).resize((size, size), Image.LANCZOS)
        im.save(os.path.join(out_dir, key + ".dds"), "DDS", pixel_format="DXT5")   # Skyrim LE (DX9): no BC7


def load_car(f1_dir, car_erp):
    return read_erp(os.path.join(f1_dir, car_erp))


# --- tyres: shared F1 2021 tyre model (teams/common.erp), placed on this car's wheel nodes ---------------------
TYRE_ORDER = ["wheel_fl", "wheel_fl", "wheel_fr", "wheel_fr", "wheel_bl", "wheel_bl", "wheel_br", "wheel_br"]


def tyre_shapes(common, wheels, lod, tex_dir):
    by = {r.name: r for r in common}

    def stream(eaid):
        r = by[eaid.split("//", 1)[-1].split("/", 1)[-1]]
        return struct.unpack_from("<3I", r.frag(0))[1], r.frag(1)

    subs, vbs, ibs, mats = parse_mesh(by[f"shared/tyres/idf/tyres.idf?lod={lod}&mesh"].frag(0))
    _, ibd = stream(ibs[0])
    shapes = []
    for i, s in enumerate(subs):
        mat = mats[s["mat"]:mats.index(0, s["mat"])].decode()
        M = wheels[TYRE_ORDER[i]]
        ib = np.frombuffer(ibd, "<u2")[s["start"]:s["start"] + s["count"]].astype(np.int64) + s["base"]
        used, local = np.unique(ib, return_inverse=True)
        st = [stream(vbs[k]) for k in s["vbs"]]
        pos = np.frombuffer(st[0][1], np.uint8).reshape(-1, st[0][0])[used, :12].copy().view("<f4").reshape(-1, 3)
        nrm = np.frombuffer(st[1][1], "<f2").reshape(-1, 4)[used, :3].astype(np.float32)
        tg4 = np.frombuffer(st[2][1], "<f2").reshape(-1, 4)[used].astype(np.float32)
        uv = np.frombuffer(st[3][1], "<f2").reshape(-1, 4)[used, :2].astype(np.float32)
        pos = pos @ M[:3, :3].T + M[:3, 3]; nrm = nrm @ M[:3, :3].T; tan = tg4[:, :3] @ M[:3, :3].T
        sign = np.where(tg4[:, 3] < 0, -1.0, 1.0)[:, None]
        n_s, t_s = _unit(_to_skyrim(nrm)), _unit(_to_skyrim(tan))
        tex = "tyre_tread" if mat == "tread" else "tyre_wall"
        shapes.append(dict(name=f"{tex}_{i}", verts=_to_skyrim(pos), normals=n_s, tangents=t_s,
                           bitangents=-np.cross(n_s, t_s) * sign, uvs=uv, tris=local.reshape(-1, 3)[:, ::-1],
                           textures=[f"{tex_dir}/{tex}.dds".replace("/", "\\"), "textures\\dlgp\\common\\flat_n.dds"]))
    return shapes


def write_tyre_textures(common, f1_dir, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    tread = texture_image(common, None, f1_dir, exact="shared/tyres/texture_arrays/slick_diffuse.tif.image")
    tread.resize((256, 1024), Image.LANCZOS).save(os.path.join(out_dir, "tyre_tread.dds"), "DDS", pixel_format="DXT5")
    wall = texture_image(common, None, f1_dir, exact="shared/tyres/texture_arrays/sidewall_diffuse.texarray.image")
    wall.resize((1024, 1024), Image.LANCZOS).save(os.path.join(out_dir, "tyre_wall.dds"), "DDS", pixel_format="DXT5")
