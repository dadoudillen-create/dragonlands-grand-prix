"""F1 2021 engine sound bundles (.bdl) -> a loopable WAV for Skyrim.

Layout per EgoEngineModding's 010 template bdl.bt (MIT). Reads the throttle sound's source samples (int16 PCM),
its zero-crossing table and named loop points, and cuts the loop nearest the requested RPM.
"""
import struct
import wave


class _R:
    def __init__(self, b, o=0):
        self.b, self.o = b, o

    def u(self, fmt):
        v = struct.unpack_from("<" + fmt, self.b, self.o); self.o += struct.calcsize("<" + fmt)
        return v if len(v) > 1 else v[0]


def _engine_sound(r):
    r.o += 4                                   # magic "egoe"
    ver = r.u("I"); r.u("i"); firings = r.u("i"); r.u("4f")
    fmt, rate = 0, 48000
    if ver >= 101:
        if ver >= 108:
            if ver >= 113:
                r.u("4i")
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
                    n = ((12 if ver >= 114 else 4 if ver >= 111 else 0) + 9) if ver >= 107 else (3 if ver == 104 else 6)
                    for _ in range(n):
                        r.u("i")
                        if ver >= 105:
                            r.u("i")
                        r.o += 4 * 256
                    if ver >= 106:
                        r.o += 4 * (16 if ver >= 114 else 8)
    src_len = r.u("i")
    samples = r.b[r.o:r.o + 2 * max(src_len, 0)]; r.o += 2 * max(src_len, 0)
    n = r.u("i"); r.o += 4 * n                 # source RPM table
    n = r.u("i"); zcs = struct.unpack_from(f"<{n}d", r.b, r.o); r.o += 8 * n
    if fmt == 0:
        length = r.u("i"); r.o += 4 * 32 + 4 * 256 + 19 * ((length - 1152) // 19); r.u("if3i")
    elif fmt == 1:
        length = r.u("i"); r.o += length; r.u("if3i")
    else:
        r.o += 24
    loops = []
    for _ in range(r.u("i")):
        rpm, s_zc, e_zc, s_xf, e_xf, power, style = r.u("f6i")
        name = r.b[r.o:r.o + 64].split(b"\0")[0].decode("ascii", "replace"); r.o += 64
        loops.append(dict(rpm=rpm, start=s_zc, end=e_zc, name=name))
    return dict(rate=rate, samples=samples, zcs=zcs, loops=loops, firings=firings)


def read_bdl(path):
    b = open(path, "rb").read()
    r = _R(b, 4)
    ver = r.u("i")
    nxt = 8
    if ver >= 101:
        r.u("2f"); nxt = 16
        if ver >= 102:
            nxt = 20 + r.u("i")
    r.o = nxt
    rpm_range = r.u("8i")
    if ver >= 105:
        r.u("2f")
    return dict(version=ver, rpm_range=rpm_range, throttle=_engine_sound(r))


def write_loop_wav(bdl, out_path, target_rpm=None, min_seconds=2.0):
    """Cut the throttle loop closest to target_rpm (default: 80% of the bundle's range) and repeat it to
    at least min_seconds so Skyrim's looping descriptor has a steady note."""
    s = bdl["throttle"]
    if target_rpm is None:
        lo, hi = bdl["rpm_range"][0], bdl["rpm_range"][1]
        target_rpm = lo + 0.8 * (hi - lo)
    pcm = s["samples"]
    if s["loops"] and s["zcs"]:
        loop = min(s["loops"], key=lambda l: abs(l["rpm"] - target_rpm))
        a, b = int(s["zcs"][loop["start"]]), int(s["zcs"][loop["end"]])
        if 0 <= a < b <= len(pcm) // 2:
            pcm = pcm[2 * a:2 * b]
            rpm = loop["rpm"]
        else:
            rpm = None
    else:
        rpm = None
    reps = max(1, int(min_seconds * s["rate"] * 2 / max(len(pcm), 1)) + 1)
    with wave.open(out_path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(s["rate"]); w.writeframes(pcm * reps)
    return dict(rpm=rpm, seconds=len(pcm) * reps / 2 / s["rate"], loops=len(s["loops"]))
