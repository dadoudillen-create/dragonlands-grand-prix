"""Read the player's cell and position from a Skyrim LE save (.ess).

usage: python -I esspos.py <save.ess>
Layout: UESP "Skyrim Mod:Save File Format" (LE). Reads the player reference change form (FormID 0x14).
"""
import struct
import sys
import zlib


def main():
    b = open(sys.argv[1], "rb").read()
    assert b[:13] == b"TESV_SAVEGAME"
    hsize = struct.unpack_from("<I", b, 13)[0]
    o = 17
    o += 8  # version, save number

    def ws():
        nonlocal o
        n = struct.unpack_from("<H", b, o)[0]; s = b[o + 2:o + 2 + n].decode("cp1252"); o += 2 + n
        return s

    name = ws(); o += 4; loc = ws(); date = ws(); race = ws()
    o += 2 + 4 + 4 + 8
    w, h = struct.unpack_from("<II", b, o); o += 8
    assert o == 17 + hsize, (o, hsize)
    o += w * h * 3                       # LE screenshot is RGB
    o += 1                               # form version
    plen = struct.unpack_from("<I", b, o)[0]; o += 4
    pinfo = b[o:o + plen]; o += plen
    n = pinfo[0]; p, plugins = 1, []
    for _ in range(n):
        k = struct.unpack_from("<H", pinfo, p)[0]; plugins.append(pinfo[p + 2:p + 2 + k].decode()); p += 2 + k
    tbl = struct.unpack_from("<10I", b, o)
    formid_off, change_off, change_count = tbl[0], tbl[4], tbl[9]
    fcount = struct.unpack_from("<I", b, formid_off)[0]
    formids = struct.unpack_from(f"<{fcount}I", b, formid_off + 4)

    def refid(x):
        v = (x[0] << 16) | (x[1] << 8) | x[2]
        kind, val = v >> 22, v & 0x3FFFFF
        if kind == 0:
            return formids[val - 1] if val else 0
        if kind == 1:
            return val
        return 0xFF000000 | val

    # Global data table 1, type 1 = Player Location: nextObjectId, worldspace, coorX, coorY, worldspace2, pos[3]
    g, gcount = tbl[2], tbl[6]
    for _ in range(gcount):
        gtype, glen = struct.unpack_from("<II", b, g)
        if gtype == 1:
            d = b[g + 8:g + 8 + glen]
            world = refid(d[4:7]); cx, cy = struct.unpack_from("<ii", d, 7)
            pos = struct.unpack_from("<3f", d, 18)  # 4+3+4+4+3
            print(f"player={name} location={loc} plugins={plugins}")
            print(f"world={world:08X} grid=({cx}, {cy}) pos=({pos[0]:.1f}, {pos[1]:.1f}, {pos[2]:.1f})")
            return
        g += 8 + glen

    o = change_off
    for _ in range(change_count):
        rid = refid(b[o:o + 3]); flags = struct.unpack_from("<I", b, o + 3)[0]; typ = b[o + 7]
        lw = typ >> 6; fmt = {0: "B", 1: "H", 2: "I"}[lw]; sz = struct.calcsize(fmt)
        l1, l2 = struct.unpack_from("<" + fmt * 2, b, o + 9)
        data = b[o + 9 + 2 * sz:o + 9 + 2 * sz + l1]
        o += 9 + 2 * sz + l1
        if rid == 0x14 and (typ & 0x3F) == 0:
            if l2:
                data = zlib.decompress(data)
            cell = refid(data[0:3])
            pos = struct.unpack_from("<3f", data, 3); rot = struct.unpack_from("<3f", data, 15)
            print(f"player={name} location={loc} plugins={plugins}")
            print(f"changeFlags={flags:#x} cell/world={cell:08X}")
            print(f"pos=({pos[0]:.1f}, {pos[1]:.1f}, {pos[2]:.1f}) rot=({rot[0]:.3f}, {rot[1]:.3f}, {rot[2]:.3f})")
            print(f"grid=({int(pos[0] // 4096)}, {int(pos[1] // 4096)})")
            return
    print("player change form not found")


if __name__ == "__main__":
    main()
