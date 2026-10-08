"""Parse F1 2021 GfxModelRes (<car>.idf&<part>?model) per the 010 template GfxModelRes.bt."""
import os
import re
import struct
import sys


def parse_model(b):
    mesh_n, node_n, skin_n, name_n, _pad, lod_n = struct.unpack_from("<I4HI", b, 0)
    o = 16
    sphere = struct.unpack_from("<4f", b, o); o += 16
    o += 4  # mirrorControlBitfield
    aabb = struct.unpack_from("<6f", b, o); o += 24  # F1 2021: AABB min/max, not in the 010 template
    lods = [struct.unpack_from("<2f", b, o + 8 * i) for i in range(lod_n)]; o += 8 * lod_n
    o += 4  # lodStrategy
    nodes = []
    for _ in range(node_n):
        v = struct.unpack_from("<Ii3f4f3f16fii", b, o); o += 120
        nodes.append(dict(nameIndex=v[0], parent=v[1], t=v[2:5], r=v[5:9], s=v[9:12]))
    o += 2 * skin_n
    files = []
    for _ in range(mesh_n):
        e = b.index(0, o); files.append(b[o:e].decode()); o = e + 1
    names_blob = b[o:]
    for n in nodes:
        e = names_blob.index(0, n["nameIndex"])
        n["name"] = names_blob[n["nameIndex"]:e].decode()
    return dict(sphere=sphere, aabb=aabb, lods=lods, nodes=nodes, files=files)


def all_models(folder):
    out = {}
    for n in sorted(os.listdir(folder)):
        m = re.search(r"\.idf(?:&([a-z0-9_]+))?%3Fmodel$", n)
        if m:
            out[m.group(1) or "body"] = parse_model(open(os.path.join(folder, n), "rb").read())
    return out


if __name__ == "__main__":
    for part, m in all_models(sys.argv[1]).items():
        for nd in m["nodes"]:
            print(f"{part:28s} node={nd['name']:24s} parent={nd['parent']:3d} "
                  f"t=({nd['t'][0]:+.3f},{nd['t'][1]:+.3f},{nd['t'][2]:+.3f}) "
                  f"r=({nd['r'][0]:+.2f},{nd['r'][1]:+.2f},{nd['r'][2]:+.2f},{nd['r'][3]:+.2f})")
