"""Read F1 2021 engine sound bundles (.bdl) per the 010 template bdl.bt and dump each sound's source samples as WAV.

usage: python -I egobdl.py <bundle.bdl> <out folder>
"""
import os
import struct
import sys
import wave


class R:
    def __init__(self, b, o=0):
        self.b, self.o = b, o

    def u(self, fmt):
        v = struct.unpack_from("<" + fmt, self.b, self.o)
        self.o += struct.calcsize("<" + fmt)
        return v if len(v) > 1 else v[0]


def header(r):
    magic = r.b[0:4]; r.o = 4
    ver = r.u("i")
    nxt = 8
    if ver >= 101:
        r.u("2f"); nxt = 16
        if ver >= 102:
            extra = r.u("i"); nxt = 20 + extra
    r.o = nxt
    rpm = r.u("8i")
    if ver >= 105:
        r.u("2f")
    return dict(magic=magic, ver=ver, rpm=rpm)


def engine_sound(r):
    start = r.o
    magic = r.b[r.o:r.o + 4]; r.o += 4
    ver = r.u("I")
    r.u("i")
    firings = r.u("i")
    r.u("4f")
    fmt, rate = 0, 48000
    if ver >= 101:
        if ver >= 108:
            if ver >= 113:
                r.u("3i"); r.u("i")
            fmt = r.u("i")
            if ver >= 109:
                rate = r.u("i")
        r.u("2f")
        if ver >= 102:
            r.u("i")
            if ver >= 103:
                r.u("3i")
                if ver >= 104:
                    r.o += 16
                    n = (12 if ver >= 114 else 4 if ver >= 111 else 0) + 9 if ver >= 107 else (3 if ver == 104 else 6)
                    for _ in range(n):
                        r.u("i")
                        if ver >= 105:
                            r.u("i")
                        r.o += 4 * 256
                    if ver >= 106:
                        r.o += 4 * (16 if ver >= 114 else 8)
    src_len = r.u("i")
    samples = r.b[r.o:r.o + 2 * max(src_len, 0)]; r.o += 2 * max(src_len, 0)
    tbl = r.u("i"); rpm_table = struct.unpack_from(f"<{tbl}f", r.b, r.o); r.o += 4 * tbl
    zc = r.u("i"); r.o += 8 * zc
    return dict(start=start, magic=magic, ver=ver, firings=firings, fmt=fmt, rate=rate, src_len=src_len,
                samples=samples, rpm_table=rpm_table[:4] + (("...",) if tbl > 4 else ()), next=r.o)


def main():
    path, out = sys.argv[1], sys.argv[2]
    os.makedirs(out, exist_ok=True)
    b = open(path, "rb").read()
    r = R(b)
    h = header(r)
    print("bundle", h["magic"], "ver", h["ver"], "rpm", h["rpm"])
    s = engine_sound(r)
    print({k: v for k, v in s.items() if k != "samples"})
    if s["src_len"] > 0:
        dst = os.path.join(out, os.path.basename(path).replace(".bdl", "_throttle_source.wav"))
        with wave.open(dst, "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(s["rate"]); w.writeframes(s["samples"])
        print("wrote", dst, f"{s['src_len'] / s['rate']:.2f}s")


if __name__ == "__main__":
    main()
