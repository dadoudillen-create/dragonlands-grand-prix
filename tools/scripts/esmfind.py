"""Look up records in Skyrim.esm by EditorID regex (optionally limited to record types).

usage: python -I esmfind.py <Skyrim.esm> <regex> [TYPE,TYPE,...]
Prints type, formID, EditorID and the model path (MODL) when there is one.
"""
import re
import struct
import sys
import zlib

sys.path.insert(0, __file__.rsplit("\\", 1)[0])
from esmscan import subrecords  # noqa: E402


def main():
    b = open(sys.argv[1], "rb").read()
    pat = re.compile(sys.argv[2], re.I)
    types = set(sys.argv[3].encode().split(b",")) if len(sys.argv) > 3 else None
    o = 0
    while o < len(b):
        sig = b[o:o + 4]
        if sig == b"GRUP":
            o += 24; continue
        size, flags, fid = struct.unpack_from("<III", b, o + 4)
        if types is None or sig in types:
            data = b[o + 24:o + 24 + size]
            if flags & 0x40000:
                data = zlib.decompress(data[4:])
            s = dict(subrecords(data))
            e = s.get(b"EDID", b"").rstrip(b"\0").decode("cp1252")
            if e and pat.search(e):
                model = s.get(b"MODL", b"").rstrip(b"\0").decode("cp1252")
                print(f"{sig.decode()} {fid:08X} {e} {model}")
        o += 24 + size


if __name__ == "__main__":
    main()
