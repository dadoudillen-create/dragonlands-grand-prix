"""Feasibility test: convert one F1 2021 car (exported .erp + DDS textures) into a Skyrim LE static NIF.

usage: python -I car2nif.py <idf folder> <dds folder> <team> <lod> <skyrim Data folder>
Writes Data/meshes/dlgp/<team>.nif and Data/textures/dlgp/<team>/*.dds
"""
import os
import re
import struct
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ego2obj import Streams, parse_mesh, part_transforms  # noqa: E402
from egomodel import all_models  # noqa: E402
from skynif import build_skinned, build_static  # noqa: E402

UNITS_PER_METRE = 1 / 0.0142875  # game_info: one Skyrim unit is 0.0142875 m
SKIP = {"rainbeads"}
MAX_PER_SHAPE = 16000  # vanilla shapes are small; keep ours well under the 16-bit limits


def unit(v):
    return v / (np.linalg.norm(v, axis=1, keepdims=True) + 1e-12)


def split(attrs, tri, limit):
    """Yield (attrs, tris) pieces with at most `limit` vertices and triangles each."""
    for start in range(0, len(tri), limit // 3 if len(tri) > limit else len(tri) or 1):
        chunk = tri[start:start + (limit // 3 if len(tri) > limit else len(tri))]
        used, local = np.unique(chunk, return_inverse=True)
        yield tuple(a[used] for a in attrs), local.reshape(-1, 3)


def tex_for(material, team):
    m = material.lower()
    if m == "body":
        return f"{team}_paint_d"
    if m.startswith("wheel") or m == "disc":
        return f"{team}_wheel_d"
    if m.startswith("steering"):
        return f"{team}_steering_wheel_d"
    return "carbon"


def to_skyrim(v):
    """F1: metres, X right, Y up, Z forward -> Skyrim: units, X right, Y forward, Z up."""
    return np.stack([v[:, 0], v[:, 2], v[:, 1]], axis=1) * UNITS_PER_METRE


def convert_textures(dds_dir, team, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    made = {}
    for key in (f"{team}_paint_d", f"{team}_wheel_d", f"{team}_steering_wheel_d"):
        im = Image.open(os.path.join(dds_dir, key + ".dds")); im.load()
        im = im.convert("RGBA").resize((1024, 1024), Image.LANCZOS)
        dst = os.path.join(out_dir, key + ".dds")
        im.save(dst, "DDS", pixel_format="DXT5")  # Skyrim LE (DX9) cannot read BC7
        made[key] = dst
    Image.new("RGBA", (64, 64), (22, 22, 24, 255)).save(os.path.join(out_dir, "carbon.dds"), "DDS", pixel_format="DXT1")
    Image.new("RGBA", (64, 64), (128, 128, 255, 255)).save(os.path.join(out_dir, "flat_n.dds"), "DDS", pixel_format="DXT1")
    return made


def main():
    idf, dds_dir, team, lod, data = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5]
    tex_out = os.path.join(data, "textures", "dlgp", team)
    convert_textures(dds_dir, team, tex_out)

    names = os.listdir(idf)
    prefix = max((n for n in names if n.endswith("lod=all&ib=0")),
                 key=lambda n: os.path.getsize(os.path.join(idf, n))).split("%3F")[0]
    st = Streams(idf, prefix)
    xf = part_transforms(all_models(idf)["body"]["nodes"])
    groups = {}  # texture -> lists
    for mn in sorted(n for n in names if re.search(r"%3Flod=" + lod + r"(&[a-z0-9_]+)?&mesh$", n)):
        part = re.search(r"lod=\d+(?:&([a-z0-9_]+))?&mesh", mn).group(1) or "body"
        subs, vbs, ibs, mats = parse_mesh(open(os.path.join(idf, mn), "rb").read())
        M = None if part == "body" else next((m for k, m in xf.items() if k.startswith(part)), None)
        for s in subs:
            mat = mats[s["mat"]:mats.index(0, s["mat"])].decode()
            if s["prim"] != 4 or s["count"] == 0 or mat in SKIP:
                continue
            ib = np.frombuffer(st.get(ibs[s["ib"]]), "<u2")[s["start"]:s["start"] + s["count"]].astype(np.int64) + s["base"]
            # keep only the vertices this submesh uses (LODs share buffers, so ranges have gaps)
            used, local = np.unique(ib, return_inverse=True)
            streams = [st.get(vbs[i]) for i in s["vbs"]]
            sizes = [st.elem_size(vbs[i]) for i in s["vbs"]]
            pos = np.frombuffer(streams[0], np.uint8).reshape(-1, sizes[0])[used, :12].copy().view("<f4").reshape(-1, 3)
            if sizes[:4] == [12, 8, 8, 8]:
                nrm = np.frombuffer(streams[1], "<f2").reshape(-1, 4)[used, :3].astype(np.float32)
                uv = np.frombuffer(streams[3], "<f2").reshape(-1, 4)[used, :2].astype(np.float32)
                tg4 = np.frombuffer(streams[2], "<f2").reshape(-1, 4)[used].astype(np.float32)
                tan, sign = tg4[:, :3], np.where(tg4[:, 3] < 0, -1.0, 1.0)[:, None]
            else:
                nrm = np.tile([0, 1, 0], (len(used), 1)).astype(np.float32)
                uv = np.zeros((len(used), 2), np.float32)
                tan, sign = np.tile([1, 0, 0], (len(used), 1)).astype(np.float32), np.ones((len(used), 1))
            if M is not None:
                pos = pos @ M[:3, :3].T + M[:3, 3]
                nrm = nrm @ M[:3, :3].T
                tan = tan @ M[:3, :3].T
            tri = local.reshape(-1, 3)[:, ::-1]  # axis swap flips handedness: reverse winding
            n_s, t_s = unit(to_skyrim(nrm)), unit(to_skyrim(tan))
            b_s = -np.cross(n_s, t_s) * sign  # handedness flips with the axis swap
            g = groups.setdefault(tex_for(mat, team), [])
            for piece in split((to_skyrim(pos), n_s, t_s, b_s, uv), tri, MAX_PER_SHAPE):
                g.append(piece)

    shapes = []
    for tex, parts in groups.items():
        # pack submeshes into shapes under the 16-bit vertex/triangle limits
        cur = dict(a=[], f=[], count=0, tris=0)

        def flush():
            if cur["a"]:
                v, n, t, b, uv = (np.concatenate([a[i] for a in cur["a"]]) for i in range(5))
                shapes.append(dict(name=f"{tex}_{len(shapes)}", verts=v, normals=n, tangents=t, bitangents=b,
                                   uvs=uv, tris=np.concatenate(cur["f"]),
                                   textures=[f"textures\\dlgp\\{team}\\{tex}.dds", f"textures\\dlgp\\{team}\\flat_n.dds"]))
            cur.update(a=[], f=[], count=0, tris=0)

        for attrs, f in parts:
            if cur["count"] + len(attrs[0]) > MAX_PER_SHAPE or cur["tris"] + len(f) > MAX_PER_SHAPE:
                flush()
            cur["a"].append(attrs); cur["f"].append(f + cur["count"])
            cur["count"] += len(attrs[0]); cur["tris"] += len(f)
        flush()

    mesh_out = os.path.join(data, "meshes", "dlgp")
    os.makedirs(mesh_out, exist_ok=True)
    build_static(os.path.join(mesh_out, f"{team}.nif"), shapes)
    lift = -float(min(s["verts"][:, 2].min() for s in shapes))  # actor origin is at ground level
    build_skinned(os.path.join(mesh_out, f"{team}_mount.nif"), shapes, "NPC Root [Root]", z_offset=lift)
    print(f"mount mesh lifted {lift:.1f} units onto the ground")
    allv = np.concatenate([s["verts"] for s in shapes])
    print(f"shapes={len(shapes)} verts={len(allv)} tris={sum(len(s['tris']) for s in shapes)}")
    print("bounds (Skyrim units) min", allv.min(0).round(1), "max", allv.max(0).round(1))


if __name__ == "__main__":
    main()
