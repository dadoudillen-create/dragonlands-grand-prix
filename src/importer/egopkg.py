"""Read Codemasters EGO "!pkg" binary data files into Python dicts/lists.

Port of the read side of EgoEngineLibrary Data/Pkg (MIT, https://github.com/EgoEngineModding/Ego-Engine-Modding).
Values come back as Python numbers/strings ("stri foo" -> "foo", "fp32 1.5" -> 1.5).
"""
import struct

MAGIC = 1735094305  # "!pkg"
SCALAR = {"fp32": "<f", "ui32": "<I", "si32": "<i", "ui64": "<Q", "si64": "<q", "ui16": "<H", "ui08": "<B"}


def _offtype(b, o):
    v = struct.unpack_from("<I", b, o)[0]
    return v >> 24, v & 0x00FFFFFF


class _Pool:
    """The '!vca' data array: one typed list per element; values are addressed by (type index, offset)."""

    def __init__(self):
        self.lists = []

    def get(self, t, off):
        kind, data = self.lists[t]
        if kind == "stri":
            n = data[off]
            return data[off + 1:off + 1 + n].decode("utf-8", "replace")
        return data[off]


def read_pkg(path_or_bytes):
    b = path_or_bytes if isinstance(path_or_bytes, (bytes, bytearray)) else open(path_or_bytes, "rb").read()
    if struct.unpack_from("<I", b, 0)[0] != MAGIC:
        raise ValueError("not a !pkg file")
    name = b[4:8].split(b"\0")[0].decode()
    pool = _Pool()

    def chunk(off):
        kind = b[off:off + 4].decode()
        o = off + 4
        if kind == "!vbi":
            typ = b[o:o + 4].decode(); o += 4
            n, size = struct.unpack_from("<II", b, o); o += 8
            if typ in SCALAR:
                fmt = SCALAR[typ]
                return typ, [struct.unpack_from(fmt, b, o + i * size)[0] for i in range(n)]
            if typ == "bool":
                return typ, [bool(b[o + i * size]) for i in range(n)]
            if typ in ("vec3", "vec4", "quat", "mat4", "bbox"):
                k = size // 4
                return typ, [list(struct.unpack_from(f"<{k}f", b, o + i * size)) for i in range(n)]
            return typ, [b[o + i * size:o + (i + 1) * size] for i in range(n)]
        if kind == "!sbi":
            length = struct.unpack_from("<I", b, o)[0]
            return "stri", b[o + 4:o + 4 + length]
        if kind == "!vca":
            n = struct.unpack_from("<I", b, o)[0]
            return [value(o + 4 + 4 * i) for i in range(n)]
        if kind == "!idi":
            ver, n = _offtype(b, o); o += 4
            obj = {}
            step = 8 if ver == 0 else 12
            for i in range(n):
                p = o + i * step
                key = pool.get(*_offtype(b, p))
                obj[key] = value(p + 4)
            return obj
        if kind == "!ili":
            n = struct.unpack_from("<I", b, o)[0]
            return [value(o + 4 + 4 * i) for i in range(n)]
        if kind == "!iar":
            return {"$ref": b[o:o + 8].split(b"\0")[0].decode()}
        raise ValueError(f"pkg chunk {kind!r} not supported")

    def value(off):
        t, o = _offtype(b, off)
        if t == 128:
            return chunk(o)
        return pool.get(t, o)

    # element 1 is the data pool; read it before the tree that references it
    pool.lists = value(12)
    return {name: value(8)}


if __name__ == "__main__":
    import json
    import sys
    d = read_pkg(sys.argv[1])
    print(json.dumps(d, default=str)[:1500])
