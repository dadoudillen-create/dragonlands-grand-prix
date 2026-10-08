"""Decode an F1 2021 (EGO engine) GfxMeshRes exported by Ego ERP Archiver.

Layout worked out from F1 2021 data (see MODLOG.md):
  header: 19 x uint32 (first 9 as in the 010 template GfxMeshRes.bt)
  submesh (88 bytes): vbCount, primType, cmdType, start, count, baseVertex,
                      sphere[4], nodeOff, nodeCount, matIdx, ibIdx, vbIdx[8]
  string tables at vbIdOffset / ibIdOffset / materialIdOffset.
"""
import struct
import sys
from pathlib import Path


def cstr(b, off):
    end = b.index(0, off)
    return b[off:end].decode("ascii", "replace"), end + 1


def read_strings(b, off, n):
    out = []
    for _ in range(n):
        s, off = cstr(b, off)
        out.append(s)
    return out


def parse_mesh(path):
    b = Path(path).read_bytes()
    h = struct.unpack_from("<19I", b, 0)
    sub_n, vb_n, ib_n, mat_n, bind_n, vb_off, ib_off, mat_off, node_off = h[:9]
    subs = []
    for i in range(sub_n):
        o = 0x4C + i * 88
        v = struct.unpack_from("<6I4f4I8I", b, o)
        subs.append(dict(vbCount=v[0], prim=v[1], cmd=v[2], start=v[3], count=v[4],
                         base=v[5], sphere=v[6:10], matIdx=v[12], ibIdx=v[13],
                         vbIdx=list(v[14:14 + v[0]])))
    return dict(header=h, subs=subs,
                vbs=read_strings(b, vb_off, vb_n),
                ibs=read_strings(b, ib_off, ib_n),
                mats=read_strings(b, mat_off, mat_n))


if __name__ == "__main__":
    m = parse_mesh(sys.argv[1])
    print("header", m["header"])
    for i, s in enumerate(m["subs"]):
        print(i, s)
    print("vbs", m["vbs"])
    print("ibs", m["ibs"])
    print("mats", m["mats"])
