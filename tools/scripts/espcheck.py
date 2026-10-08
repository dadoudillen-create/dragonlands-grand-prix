"""Re-read a generated plugin: group/record sizes must nest exactly, subrecords must parse, VMADs must decode.

usage: python -I espcheck.py <plugin.esp>
"""
import struct
import sys
import zlib
from collections import Counter

sys.path.insert(0, __file__.rsplit("\\", 1)[0])
from esmscan import subrecords  # noqa: E402


def wstr(v, p):
    n = struct.unpack_from("<H", v, p)[0]
    return v[p + 2:p + 2 + n].decode("cp1252"), p + 2 + n


def decode_vmad(v):
    ver, fmt, n = struct.unpack_from("<hhH", v, 0)
    p, out = 6, []
    for _ in range(n):
        name, p = wstr(v, p); p += 1
        pc = struct.unpack_from("<H", v, p)[0]; p += 2
        props = []
        for _ in range(pc):
            pn, p = wstr(v, p); t = v[p]; p += 2
            if t == 1:
                props.append((pn, f"{struct.unpack_from('<I', v, p + 4)[0]:08X}")); p += 8
            elif t == 4:
                props.append((pn, round(struct.unpack_from("<f", v, p)[0], 2))); p += 4
            elif t in (11, 14):
                c = struct.unpack_from("<I", v, p)[0]; p += 4 + c * (8 if t == 11 else 4)
                props.append((pn, f"[{c}]"))
            else:
                raise ValueError(f"prop type {t}")
        out.append((name, props))
    assert p == len(v), f"VMAD has {len(v) - p} trailing bytes"
    return ver, fmt, out


def walk(b, o, end, depth, stats):
    while o < end:
        sig = b[o:o + 4].decode("latin1")
        if sig == "GRUP":
            size = struct.unpack_from("<I", b, o + 4)[0]
            assert o + size <= end, f"group at {o} overruns parent"
            walk(b, o + 24, o + size, depth + 1, stats)
            stats["groups"] += 1
            o += size
            continue
        size, flags, fid = struct.unpack_from("<III", b, o + 4)
        data = b[o + 24:o + 24 + size]
        if flags & 0x40000:
            data = zlib.decompress(data[4:])
        subs = list(subrecords(data))
        stats["records"] += 1; stats[sig] += 1
        for s, v in subs:
            if s == b"VMAD":
                ver, fmt, scripts = decode_vmad(v)
                for name, props in scripts:
                    print(f"  {sig} {fid:08X} VMAD v{ver}/{fmt} {name}: {props}")
        o += 24 + size
    assert o == end, f"misaligned: {o} != {end}"


def main():
    b = open(sys.argv[1], "rb").read()
    stats = Counter()
    walk(b, 0, len(b), 0, stats)
    hedr = struct.unpack_from("<fII", b, 24 + 6)
    print(f"OK: {stats['records']} records, {stats['groups']} groups; HEDR version {hedr[0]:.2f}, count {hedr[1]}")
    print("   ", {k: v for k, v in stats.items() if k not in ("records", "groups")})


if __name__ == "__main__":
    main()
