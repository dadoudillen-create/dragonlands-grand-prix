"""Read Codemasters EGO .erp archives (F1 2021: version 4).

Port of EgoEngineLibrary Archive/Erp (ErpFile, ErpResource, ErpFragment), MIT licence, by Petar Tasev and
contributors (https://github.com/EgoEngineModding/Ego-Engine-Modding). Read-only.
"""
import struct
import zlib

import zstandard

MAGIC = 1263555141  # "ERFK"
ZLIB = {0x01}
ZSTD = {0x03, 0x10, 0x11}
RAW = {0x00, 0x81, 0x90, 0x91}


class Fragment:
    __slots__ = ("name", "size", "flags", "compression", "packed")

    def data(self):
        if self.compression in ZLIB:
            return zlib.decompress(self.packed)
        if self.compression in ZSTD:
            return zstandard.ZstdDecompressor().decompress(self.packed, max_output_size=self.size)
        if self.compression in RAW:
            return self.packed
        raise ValueError(f"erp compression {self.compression:#x} not supported")


class Resource:
    __slots__ = ("identifier", "type", "fragments")

    @property
    def name(self):
        """Identifier without the eaid://package/ prefix, e.g. teams/ferrari/idf/ferrari.idf?lod=all&vb=0"""
        i = self.identifier
        return i.split("/", 3)[3] if i.lower().startswith("eaid://") else i

    def frag(self, n):
        return self.fragments[n].data()


def read_erp(path):
    b = open(path, "rb").read()
    magic, version = struct.unpack_from("<Ii", b, 0)
    if magic != MAGIC or not 0 <= version <= 4:
        raise ValueError(f"{path}: not an ERP v0-4 file")
    res_offset = struct.unpack_from("<Q", b, 32)[0]
    nfiles = struct.unpack_from("<i", b, 48)[0]
    o = 56
    resources = []
    for _ in range(nfiles):
        o += 4
        n = struct.unpack_from("<h", b, o)[0]; o += 2
        r = Resource()
        r.identifier = b[o:o + n].split(b"\0")[0].decode("utf-8", "replace"); o += n
        r.type = b[o:o + 16].split(b"\0")[0].decode(); o += 16
        o += 4
        if version >= 4:
            o += 2
        count = b[o]; o += 1
        r.fragments = []
        for _ in range(count):
            f = Fragment()
            f.name = b[o:o + 4].split(b"\0")[0].decode(); o += 4
            offset, f.size, f.flags = struct.unpack_from("<QQi", b, o); o += 20
            if version > 2:
                f.compression = b[o]; o += 1
                packed = struct.unpack_from("<Q", b, o)[0]; o += 8
            else:
                f.compression, packed = 0, f.size
            start = res_offset + offset
            f.packed = b[start:start + packed]
            r.fragments.append(f)
        if version > 2:
            o += 16
        resources.append(r)
    return resources


if __name__ == "__main__":
    import sys
    from collections import Counter
    rs = read_erp(sys.argv[1])
    print(len(rs), "resources;", Counter(r.type for r in rs).most_common())
    for r in rs[:int(sys.argv[2]) if len(sys.argv) > 2 else 12]:
        print(f"  {r.type:16s} {r.name}  frags={[(f.name, f.size, hex(f.compression)) for f in r.fragments]}")
