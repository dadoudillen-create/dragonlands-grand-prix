"""Read Skyrim LE BSA (version 104): list files and extract by name pattern.

usage: python -I bsa104.py <archive.bsa> <regex> <out folder> [max]
"""
import os
import re
import struct
import sys
import zlib


def read_bsa(path):
    f = open(path, "rb")
    magic, ver, off, flags, nfold, nfile, foldlen, filelen, ftypes = struct.unpack("<4sIIIIIIII", f.read(36))
    assert magic == b"BSA\0" and ver in (104, 105), (magic, ver)
    compressed = bool(flags & 0x4)
    embed_names = bool(flags & 0x100)
    rec = "<QII" if ver == 104 else "<QIIQ"     # SE (105): 24-byte folder records with a 64-bit offset
    folders = [struct.unpack(rec, f.read(struct.calcsize(rec)))[:3] for _ in range(nfold)]
    entries = []
    for _, count, _ in folders:
        n = f.read(1)[0]; folder = f.read(n)[:-1].decode("cp1252")
        for _ in range(count):
            _, size, offset = struct.unpack("<QII", f.read(16))
            entries.append([folder, None, size, offset])
    names = f.read(filelen).split(b"\0")
    for e, n in zip(entries, names):
        e[1] = n.decode("cp1252")
    return f, entries, compressed, embed_names


def extract(f, entry, compressed, embed_names):
    folder, name, size, offset = entry
    comp = compressed ^ bool(size & 0x40000000)
    size &= 0x3FFFFFFF
    f.seek(offset)
    data = f.read(size)
    if embed_names:
        data = data[1 + data[0]:]
    if comp:
        data = data[4:]
        if data[:4] == bytes.fromhex("04224d18"):  # SE: LZ4 frame
            import lz4.frame
            data = lz4.frame.decompress(data)
        else:
            data = zlib.decompress(data)
    return data


if __name__ == "__main__":
    path, pat, out = sys.argv[1], re.compile(sys.argv[2], re.I), sys.argv[3]
    limit = int(sys.argv[4]) if len(sys.argv) > 4 else 10
    f, entries, comp, emb = read_bsa(path)
    os.makedirs(out, exist_ok=True)
    n = 0
    for e in entries:
        full = e[0] + "\\" + e[1]
        if pat.search(full):
            open(os.path.join(out, full.replace("\\", "__")), "wb").write(extract(f, e, comp, emb))
            print(full); n += 1
            if n >= limit:
                break
