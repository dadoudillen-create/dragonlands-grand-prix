"""Export an F1 2021 car (exported .erp folder) at one LOD to OBJ, and render a preview PNG.

usage: python -I ego2obj.py <idf folder> <car name> <lod> <out.obj> <preview.png>
"""
import os
import re
import struct
import sys
from urllib.parse import unquote

import numpy as np

HEADER = 0x4C  # 19 uint32; string-table offsets are relative to the end of it
SUB = 88


def cstrs(b, off, n):
    out = []
    for _ in range(n):
        end = b.index(0, off)
        out.append(b[off:end].decode("ascii", "replace"))
        off = end + 1
    return out


def parse_mesh(b):
    h = struct.unpack_from("<19I", b, 0)
    sub_n, vb_n, ib_n, mat_n = h[:4]
    vb_off, ib_off, mat_off = h[5] + HEADER, h[6] + HEADER, h[7] + HEADER
    subs = []
    for i in range(sub_n):
        v = struct.unpack_from("<6I4f4I8I", b, HEADER + i * SUB)
        subs.append(dict(start=v[3], count=v[4], base=v[5], prim=v[1],
                         mat=v[12], ib=v[13], vbs=list(v[14:14 + v[0]])))
    vbs = cstrs(b, vb_off, vb_n)
    ibs = cstrs(b, ib_off, ib_n)
    mat_blob = b[mat_off:]
    return subs, vbs, ibs, mat_blob


class Streams:
    def __init__(self, folder, prefix):
        self.folder, self.prefix, self.cache = folder, prefix, {}

    def get(self, eaid):
        q = eaid.split("?", 1)[1]  # lod=all&vb=0
        if q not in self.cache:
            self.cache[q] = open(os.path.join(self.folder, self.prefix + "%3F" + q), "rb").read()
        return self.cache[q]

    def elem_size(self, eaid):
        q = eaid.split("?", 1)[1]
        hdr = self.prefix.replace("temp001", "temp000") + "%3F" + q
        return struct.unpack_from("<3I", open(os.path.join(self.folder, hdr), "rb").read())[1]


def main():
    folder, car, lod, out_obj, out_png = sys.argv[1:6]
    names = os.listdir(folder)
    # The archive exports each buffer twice: a 16-byte GfxBufferRes header (temp000) and the data (temp001).
    stream_prefix = max((n for n in names if n.endswith("lod=all&ib=0")),
                        key=lambda n: os.path.getsize(os.path.join(folder, n))).split("%3F")[0]
    meshes = sorted(n for n in names if re.search(r"%3Flod=" + lod + r"(&[a-z0-9_]+)?&mesh$", n))
    st = Streams(folder, stream_prefix)
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from egomodel import all_models
    xforms = part_transforms(all_models(folder)["body"]["nodes"])
    P, UV, F, groups = [], [], [], []
    nverts = 0
    for mn in meshes:
        part = re.search(r"lod=\d+(?:&([a-z0-9_]+))?&mesh", mn).group(1) or "body"
        b = open(os.path.join(folder, mn), "rb").read()
        subs, vbs, ibs, mats = parse_mesh(b)
        for s in subs:
            if s["prim"] != 4 or s["count"] == 0:
                continue
            mat = mats[s["mat"]:mats.index(0, s["mat"])].decode()
            ib = np.frombuffer(st.get(ibs[s["ib"]]), "<u2")[s["start"]:s["start"] + s["count"]].astype(np.int64)
            ib = ib + s["base"]
            lo, hi = int(ib.min()), int(ib.max()) + 1
            streams = [st.get(vbs[i]) for i in s["vbs"]]
            sizes = [st.elem_size(vbs[i]) for i in s["vbs"]]
            # position: float3 at the start of the first stream (12-byte stream, or interleaved)
            p0 = np.frombuffer(streams[0], np.uint8).reshape(-1, sizes[0])[lo:hi, :12]
            pos = p0.copy().view("<f4").reshape(-1, 3)
            if part != "body":
                M = next((m for name, m in xforms.items() if name.startswith(part)), None)
                if M is None:
                    print("no node for part", part)
                else:
                    pos = pos @ M[:3, :3].T + M[:3, 3]
            # uv: separated layout is pos, normal, tangent, uv(half4) ...; otherwise unknown for now
            if len(streams) > 3 and sizes[:4] == [12, 8, 8, 8]:
                uv = np.frombuffer(streams[3], "<f2").reshape(-1, 4)[lo:hi, :2].astype(np.float32)
            else:
                uv = np.zeros((hi - lo, 2), np.float32)
            P.append(pos); UV.append(uv)
            F.append((ib - lo + nverts).reshape(-1, 3))
            groups.append((f"{part}:{mat}", len(F) - 1))
            nverts += hi - lo
    P = np.concatenate(P); UV = np.concatenate(UV)
    with open(out_obj, "w") as o:
        o.write(f"# {car} LOD{lod} from the player's own F1 2021 install\n")
        for p in P:
            o.write("v %.5f %.5f %.5f\n" % tuple(p))
        for t in UV:
            o.write("vt %.5f %.5f\n" % (t[0], 1 - t[1]))
        for g, fi in groups:
            o.write(f"g {g}\n")
            for a, b2, c in F[fi] + 1:
                o.write(f"f {a}/{a} {b2}/{b2} {c}/{c}\n")
    tris = np.concatenate(F)
    print(f"parts={len(meshes)} submeshes={len(groups)} verts={len(P)} tris={len(tris)}")
    print("bounds min", P.min(0).round(3), "max", P.max(0).round(3))
    render(P, tris, out_png, car)


def quat_mat(q):
    x, y, z, w = q
    if x == y == z == w == 0:
        return np.eye(3)
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def part_transforms(nodes):
    """World matrix of each named node, following parent links (first occurrence of a name wins)."""
    local = []
    for n in nodes:
        M = np.eye(4); M[:3, :3] = quat_mat(n["r"]) * np.array(n["s"]); M[:3, 3] = n["t"]
        local.append(M)
    world, out = {}, {}

    def w(i):
        if i not in world:
            p = nodes[i]["parent"]
            world[i] = local[i] if p < 0 else w(p) @ local[i]
        return world[i]

    for i, n in enumerate(nodes):
        out.setdefault(n["name"], w(i))
    return out


def render(P, tris, out_png, title):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.collections import PolyCollection
    fig, axes = plt.subplots(1, 2, figsize=(16, 6), dpi=110)
    light = np.array([0.4, 0.8, 0.45]); light /= np.linalg.norm(light)
    # EGO: assume y up; views: side (z,y) and three-quarter
    yaw, pitch = np.radians(35), np.radians(-20)
    Ry = np.array([[np.cos(yaw), 0, np.sin(yaw)], [0, 1, 0], [-np.sin(yaw), 0, np.cos(yaw)]])
    Rx = np.array([[1, 0, 0], [0, np.cos(pitch), -np.sin(pitch)], [0, np.sin(pitch), np.cos(pitch)]])
    for ax, R, name in [(axes[0], np.eye(3)[[2, 1, 0]], "side"), (axes[1], Rx @ Ry, "3/4")]:
        V = P @ R.T
        T = V[tris]
        n = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0])
        n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-12
        shade = np.clip(np.abs(n @ light), 0.15, 1)
        order = np.argsort(T[:, :, 2].mean(1))
        pc = PolyCollection(T[order][:, :, :2], facecolors=plt.cm.gray(shade[order]), edgecolors="none")
        ax.add_collection(pc); ax.autoscale(); ax.set_aspect("equal"); ax.axis("off"); ax.set_title(f"{title} - {name}")
    fig.savefig(out_png, bbox_inches="tight", facecolor="white")


if __name__ == "__main__":
    main()

