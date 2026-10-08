"""Scan Skyrim LE Skyrim.esm: find an exterior cell in Tamriel and list nearby references with their base EditorIDs.

usage: python -I esmscan.py <Skyrim.esm> <cellX> <cellY>
Prints the CELL formID, its group path (for overriding it in a plugin) and references near the cell centre.
"""
import struct
import sys
import zlib

TAMRIEL = 0x3C


def subrecords(data):
    o, big = 0, None
    while o < len(data):
        sig = data[o:o + 4]; size = struct.unpack_from("<H", data, o + 4)[0]; o += 6
        if sig == b"XXXX":
            big = struct.unpack_from("<I", data, o)[0]; o += size; continue
        if big is not None:
            size, big = big, None
        yield sig, data[o:o + size]
        o += size


def payload(b, o, size, flags):
    data = b[o + 24:o + 24 + size]
    if flags & 0x40000:
        data = zlib.decompress(data[4:])
    return data


def main():
    path, cx, cy = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
    b = open(path, "rb").read()
    edids = {}      # base formID -> (sig, edid)
    target = None   # (cell formID, offset)
    refs = []
    stack = []      # (end offset, group type, label)
    o = 0
    in_target_children = False
    while o < len(b):
        while stack and o >= stack[-1][0]:
            stack.pop()
        sig = b[o:o + 4]
        if sig == b"GRUP":
            gsize, label, gtype = struct.unpack_from("<IIi", b, o + 4)
            stack.append((o + gsize, gtype, label))
            in_target_children = target is not None and any(t in (6, 8, 9) and l == target[0] for _, t, l in stack)
            o += 24
            continue
        size, flags, fid = struct.unpack_from("<III", b, o + 4)
        if sig in (b"STAT", b"MSTT", b"FURN", b"ACTI", b"TREE", b"CELL", b"REFR", b"LAND"):
            data = payload(b, o, size, flags)
            subs = dict(subrecords(data)) if sig != b"REFR" else None
            if sig == b"CELL":
                in_world = any(t == 1 and l == TAMRIEL for _, t, l in stack)
                xclc = subs.get(b"XCLC")
                if in_world and xclc and struct.unpack_from("<ii", xclc)[:2] == (cx, cy):
                    target = (fid, o)
                    print(f"CELL {fid:08X} at offset {o} edid={subs.get(b'EDID', b'').rstrip(bytes(1)).decode()} "
                          f"groups={[(t, hex(l)) for _, t, l in stack]}")
            elif sig == b"REFR" and in_target_children:
                s = dict(subrecords(data))
                base = struct.unpack_from("<I", s[b"NAME"])[0]
                pos = struct.unpack_from("<6f", s[b"DATA"])
                refs.append((fid, base, pos))
            elif sig == b"LAND" and in_target_children:
                vhgt = subs.get(b"VHGT")
                if vhgt:
                    print("LAND base height", struct.unpack_from("<f", vhgt)[0] * 8)
            elif sig != b"REFR":
                e = subs.get(b"EDID")
                if e:
                    edids[fid] = (sig.decode(), e.rstrip(bytes(1)).decode())
        o += 24 + size
    cxw, cyw = (float(sys.argv[4]), float(sys.argv[5])) if len(sys.argv) > 5 else (cx * 4096 + 2048, cy * 4096 + 2048)
    print(f"{len(refs)} refs in cell; centre ({cxw},{cyw})")
    near = sorted(refs, key=lambda r: (r[2][0] - cxw) ** 2 + (r[2][1] - cyw) ** 2)
    for fid, base, p in near[:60]:
        sig, e = edids.get(base, ("?", "?"))
        print(f"{fid:08X} {sig} {e:40s} pos=({p[0]:.0f},{p[1]:.0f},{p[2]:.0f}) rotZ={p[5]:.2f}")


if __name__ == "__main__":
    main()
