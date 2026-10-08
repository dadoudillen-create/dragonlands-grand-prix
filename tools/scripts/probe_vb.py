import struct, sys, glob, os
import numpy as np
d = sys.argv[1]
def f(name): return os.path.join(d, "ferrari!!!temp001.idf%3Flod=all&" + name)
for vb in range(0, 7):
    p = f("vb=%d" % vb)
    raw = open(p, "rb").read()
    n = 310410
    stride = len(raw) // n
    print("vb", vb, "bytes", len(raw), "stride", stride, "rem", len(raw) - stride * n)
    a = np.frombuffer(raw[:stride * 2000], dtype=np.uint8).reshape(2000, stride)
    if stride % 4 == 0:
        fl = a.view("<f4").reshape(2000, stride // 4)
        print("  as f32 min", fl.min(0).round(3), "max", fl.max(0).round(3))
    if stride % 2 == 0:
        h = a.view("<f2").reshape(2000, stride // 2).astype(np.float32)
        print("  as f16 min", h.min(0).round(3), "max", h.max(0).round(3))
        s = a.view("<i2").reshape(2000, stride // 2) / 32767.0
        print("  as snorm16 min", s.min(0).round(3), "max", s.max(0).round(3))
    print("  as u8 min", a.min(0), "max", a.max(0))
ib = open(f("ib=0"), "rb").read()
print("ib bytes", len(ib), "u16 max", np.frombuffer(ib, "<u2").max(), "u32 max", np.frombuffer(ib[: len(ib)//4*4], "<u4").max())
