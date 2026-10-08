"""Turn F1 2021 textures (exported by Ego ERP Archiver Console) into DDS, reading mipmaps from the player's F1 2021.

Port of EgoEngineLibrary GraphicsExtensions.ToDdsFile (ErpGfxSurfaceRes0/1/2), F1 2021 subset.
Writes legacy DXT1/DXT5/ATI1/ATI2 headers (what Skyrim LE's DX9 renderer loads); BC7 keeps a DX10 header.

usage: python -I egotex.py <textures folder> <F1 2021 folder> <out folder> [name filter]
"""
import os
import re
import struct
import sys

import lz4.block
import zstandard

# ErpGfxSurfaceFormat -> (fourCC or None for DX10, dxgi format, bytes per 4x4 block)
FORMATS = {
    52: (b"DXT1", 71, 8), 54: (b"DXT1", 72, 8),  # DXT1 / DXT1_SRGB (same blocks)
    55: (b"DXT5", 77, 16), 57: (b"DXT5", 78, 16),  # DXT5 / DXT5_SRGB
    62: (b"DXT3", 75, 16),  # BC2_SRGB
    63: (b"ATI1", 80, 8), 65: (b"ATI2", 83, 16),
    69: (None, 98, 16), 70: (None, 99, 16),  # BC7 / BC7_SRGB
}


def frag0(b):
    _u, _u2, fmt, w, h, _u3, mips, arr, _u4 = struct.unpack_from("<iiiIIiIIi", b, 0)
    return dict(fmt=fmt, w=w, h=h, mips=mips, arr=arr)


def frag2(b):
    n = b[0]
    name = b[1:1 + n].decode()
    o = 1 + n
    count = struct.unpack_from("<I", b, o)[0]
    f123 = len(b) == n + 6 + 26 * count + 8
    if f123:
        o += 1
        count = struct.unpack_from("<I", b, o)[0]
    o += 4
    mips = []
    for _ in range(count):
        if f123:
            o += 1
        comp = b[o]; off, packed, size = struct.unpack_from("<QQQ", b, o + 1); o += 25
        mips.append(dict(comp=comp, off=off, packed=packed, size=size))
    return name, mips


def dds_header(w, h, mip_count, fmt, top_size):
    fourcc, dxgi, _ = FORMATS[fmt]
    flags = 0x1 | 0x2 | 0x4 | 0x1000 | 0x80000 | (0x20000 if mip_count > 1 else 0)
    caps = 0x1000 | ((0x8 | 0x400000) if mip_count > 1 else 0)
    pf = struct.pack("<II4sIIIII", 32, 0x4, fourcc or b"DX10", 0, 0, 0, 0, 0)
    hdr = b"DDS " + struct.pack("<IIIIIII", 124, flags, h, w, top_size, 0, mip_count) + b"\0" * 44 + pf
    hdr += struct.pack("<IIIII", caps, 0, 0, 0, 0)
    if fourcc is None:
        hdr += struct.pack("<IIIII", dxgi, 3, 0, 1, 0)
    return hdr


def export(tex_dir, f1_dir, out_dir, filt=""):
    os.makedirs(out_dir, exist_ok=True)
    names = sorted({m.group(1) for n in os.listdir(tex_dir)
                    if (m := re.match(r"(.+)\.tif!!!temp000\.image$", n))})
    ok = fail = 0
    for name in names:
        if filt and filt not in name:
            continue
        try:
            rd = lambda i: open(os.path.join(tex_dir, f"{name}.tif!!!temp00{i}.image"), "rb").read()
            f0, data, (mipfile, mips) = frag0(rd(0)), rd(1), frag2(rd(2))
            if f0["fmt"] not in FORMATS:
                raise ValueError(f"format {f0['fmt']}")
            w, h, count = f0["w"], f0["h"], f0["mips"]
            top = len(data) if not mips else mips[0]["size"]
            body = b""
            mip_path = os.path.join(f1_dir, mipfile)
            if mips and os.path.exists(mip_path):
                with open(mip_path, "rb") as mf:
                    for m in mips:
                        packed = mf.read(m["packed"])
                        if m["comp"] == 0:
                            body += packed
                        elif m["comp"] == 3:
                            body += lz4.block.decompress(packed, uncompressed_size=m["size"])
                        elif m["comp"] == 4:
                            body += zstandard.ZstdDecompressor().decompress(packed, max_output_size=m["size"])
                        else:
                            raise ValueError(f"mip compression {m['comp']}")
                w, h, count = w << len(mips), h << len(mips), count + len(mips)
            else:
                top = len(data)  # no high-res mips: use what the erp holds
            if f0["arr"] > 1:
                data = data[: len(data) // f0["arr"]]
            with open(os.path.join(out_dir, name + ".dds"), "wb") as o:
                o.write(dds_header(w, h, count, f0["fmt"], top) + body + data)
            print(f"OK   {name:48s} {w}x{h} fmt={f0['fmt']} mips={count} hires={'yes' if body else 'no'}")
            ok += 1
        except Exception as e:  # keep going: report every texture
            print(f"FAIL {name}: {e}")
            fail += 1
    print(f"done: {ok} exported, {fail} failed")


if __name__ == "__main__":
    export(*sys.argv[1:4], *(sys.argv[4:5] or [""]))
