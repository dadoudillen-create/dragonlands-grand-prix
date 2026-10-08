"""Feasibility test plugin: the car STAT plus one placed reference in a Tamriel exterior cell.

usage: python -I placecar.py <Skyrim.esm> <out.esp> <cellX> <cellY> <x> <y> <z> <rotZ radians> <mesh>
Copies the WRLD Tamriel and CELL records verbatim from Skyrim.esm (an override needs its parents),
then adds a temporary-children group holding the REFR.
"""
import struct
import sys
import zlib

sys.path.insert(0, __file__.rsplit("\\", 1)[0])
from esmscan import subrecords  # noqa: E402
from skyesp import FORM_VERSION, HEDR_VERSION, record, sub, zstr  # noqa: E402

TAMRIEL = 0x3C


def grp(label, gtype, body):
    return b"GRUP" + struct.pack("<IIiII", 24 + len(body), label, gtype, 0, 0) + body


def find(esm, cx, cy):
    b = open(esm, "rb").read()
    wrld = cell = None
    labels = {}
    stack, o = [], 0
    while o < len(b):
        while stack and o >= stack[-1][0]:
            stack.pop()
        sig = b[o:o + 4]
        if sig == b"GRUP":
            gsize, label, gtype = struct.unpack_from("<IIi", b, o + 4)
            stack.append((o + gsize, gtype, label)); o += 24; continue
        size, flags, fid = struct.unpack_from("<III", b, o + 4)
        raw = b[o:o + 24 + size]
        if sig == b"WRLD" and fid == TAMRIEL:
            wrld = raw
        elif sig == b"CELL" and any(t == 1 and l == TAMRIEL for _, t, l in stack):
            data = b[o + 24:o + 24 + size]
            if flags & 0x40000:
                data = zlib.decompress(data[4:])
            xclc = dict(subrecords(data)).get(b"XCLC")
            if xclc and struct.unpack_from("<ii", xclc)[:2] == (cx, cy):
                cell = (fid, raw)
                labels = {t: l for _, t, l in stack if t in (4, 5)}
                break
        o += 24 + size
    return wrld, cell, labels


def strip_ofst(raw):
    """Return the record without its OFST (cell offset table into Skyrim.esm), uncompressed."""
    sig, size, flags, fid, vc, fv, v2 = struct.unpack_from("<4sIIIIHH", raw, 0)
    data = raw[24:24 + size]
    if flags & 0x40000:
        data = zlib.decompress(data[4:])
    out, o, big = b"", 0, None
    while o < len(data):
        ssig = data[o:o + 4]; ssize = struct.unpack_from("<H", data, o + 4)[0]
        if ssig == b"XXXX":
            big = struct.unpack_from("<I", data, o + 6)[0]; o += 6 + ssize; continue
        hdr_len = 6
        real = big if big is not None else ssize
        chunk = data[o:o + hdr_len + real]
        o += hdr_len + real
        if ssig == b"OFST":
            big = None; continue
        if big is not None:
            out += b"XXXX" + struct.pack("<HI", 4, big)
            big = None
        out += chunk
    return struct.pack("<4sIIIIHH", sig, len(out), flags & ~0x40000, fid, vc, fv, v2) + out


def main():
    """usage: placecar.py <Skyrim.esm> <out.esp> <mesh> cx,cy,x,y,z,rotZ [...]"""
    esm, out, mesh = sys.argv[1], sys.argv[2], sys.argv[3]
    places = [tuple(float(v) for v in a.split(",")) for a in sys.argv[4:]]
    stat_id = 0x01000800
    stat = record("STAT", stat_id, sub("EDID", zstr("DLGP_FerrariStatic")) +
                  sub("OBND", struct.pack("<6h", -70, -182, -27, 70, 213, 59)) +
                  sub("MODL", zstr(mesh)) + sub("DNAM", struct.pack("<fI", 90.0, 0)))
    blocks = {}  # block label -> subblock label -> [(cell_raw, cell_id, [refr])]
    wrld = None
    for i, (cx, cy, x, y, z, rz) in enumerate(places):
        wrld, (cell_id, cell_raw), labels = find(esm, int(cx), int(cy))
        refr = record("REFR", stat_id + 1 + i, sub("EDID", zstr(f"DLGP_FerrariRef{i}")) +
                      sub("NAME", struct.pack("<I", stat_id)) +
                      sub("DATA", struct.pack("<6f", x, y, z, 0.0, 0.0, rz)))
        blocks.setdefault(labels[4], {}).setdefault(labels[5], []).append((cell_raw, cell_id, refr))
        print(f"place {i}: cell {cell_id:08X} grid ({int(cx)},{int(cy)}) at ({x:.0f},{y:.0f},{z:.0f})")
    world = b""
    for bl, subs_ in blocks.items():
        sb_bytes = b""
        for sl, cells in subs_.items():
            sb_bytes += grp(sl, 5, b"".join(raw + grp(cid, 6, grp(cid, 9, refr)) for raw, cid, refr in cells))
        world += grp(bl, 4, sb_bytes)
    wrld_top = grp(struct.unpack("<I", b"WRLD")[0], 0, strip_ofst(wrld) + grp(TAMRIEL, 1, world))
    stat_top = grp(struct.unpack("<I", b"STAT")[0], 0, stat)
    n = 1 + 1 + 2 * len(places)
    hdr = sub("HEDR", struct.pack("<fII", HEDR_VERSION, n, stat_id + 1 + len(places)))
    hdr += sub("CNAM", zstr("DragonlandsGP")) + sub("MAST", zstr("Skyrim.esm")) + sub("DATA", struct.pack("<Q", 0))
    with open(out, "wb") as f:
        f.write(record("TES4", 0, hdr) + stat_top + wrld_top)
    print("wrote", out)


if __name__ == "__main__":
    main()
