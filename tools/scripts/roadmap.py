"""Dump road pieces (STAT EditorID starting 'Road') in a block of Tamriel cells from Skyrim.esm, and plot them.

usage: python -I roadmap.py <Skyrim.esm> <x0> <x1> <y0> <y1> <out.json> <out.png>
Each road ref: cell grid, cell formID, ref formID, base EditorID, position, rotation.
"""
import json
import struct
import sys
import zlib

sys.path.insert(0, __file__.rsplit("\\", 1)[0])
from esmscan import subrecords, TAMRIEL  # noqa: E402


def main():
    esm, x0, x1, y0, y1, out_json, out_png = sys.argv[1], *map(int, sys.argv[2:6]), sys.argv[6], sys.argv[7]
    b = open(esm, "rb").read()
    edids, cells, refs = {}, {}, []
    stack, o, cur_cell = [], 0, None
    while o < len(b):
        while stack and o >= stack[-1][0]:
            stack.pop()
        sig = b[o:o + 4]
        if sig == b"GRUP":
            gsize, label, gtype = struct.unpack_from("<IIi", b, o + 4)
            stack.append((o + gsize, gtype, label)); o += 24; continue
        size, flags, fid = struct.unpack_from("<III", b, o + 4)
        if sig in (b"STAT", b"CELL", b"REFR"):
            data = b[o + 24:o + 24 + size]
            if flags & 0x40000:
                data = zlib.decompress(data[4:])
            s = dict(subrecords(data))
            if sig == b"STAT" and b"EDID" in s:
                edids[fid] = s[b"EDID"].rstrip(b"\0").decode()
            elif sig == b"CELL" and any(t == 1 and l == TAMRIEL for _, t, l in stack) and b"XCLC" in s:
                gx, gy = struct.unpack_from("<ii", s[b"XCLC"])
                cur_cell = (gx, gy, fid) if x0 <= gx <= x1 and y0 <= gy <= y1 else None
                if cur_cell:
                    cells[fid] = (gx, gy, s.get(b"EDID", b"").rstrip(b"\0").decode())
            elif sig == b"REFR" and cur_cell and any(t in (8, 9) and l == cur_cell[2] for _, t, l in stack):
                base = struct.unpack_from("<I", s[b"NAME"])[0]
                pos = struct.unpack_from("<6f", s[b"DATA"])
                refs.append(dict(cell=[cur_cell[0], cur_cell[1]], cellId=f"{cur_cell[2]:08X}", refId=f"{fid:08X}",
                                 base=base, pos=[round(v, 1) for v in pos[:3]], rot=[round(v, 4) for v in pos[3:]]))
        o += 24 + size
    roads = []
    for r in refs:
        e = edids.get(r.pop("base"), "")
        if e.lower().startswith("road"):
            r["edid"] = e
            roads.append(r)
    json.dump(dict(cells={f"{k:08X}": v for k, v in cells.items()}, roads=roads), open(out_json, "w"), indent=1)
    print(f"{len(cells)} cells, {len(roads)} road pieces")

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(12, 12), dpi=90)
    for r in roads:
        ax.plot(r["pos"][0], r["pos"][1], "s", ms=3, color="saddlebrown")
    for fid, (gx, gy, e) in cells.items():
        ax.text(gx * 4096 + 200, gy * 4096 + 200, f"{gx},{gy}\n{e}", fontsize=6, color="gray")
    ax.set_xticks([x * 4096 for x in range(x0, x1 + 2)]); ax.set_yticks([y * 4096 for y in range(y0, y1 + 2)])
    ax.grid(True, lw=0.3); ax.set_aspect("equal"); ax.set_title("Road pieces around Whiterun (Skyrim.esm)")
    fig.savefig(out_png, bbox_inches="tight")


if __name__ == "__main__":
    main()
