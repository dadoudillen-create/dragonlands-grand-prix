"""Parse Skyrim LE NIFs with the same field layout skynif.py writes, and check every block is consumed exactly.

Run it on vanilla meshes (proves the layout) and on our output (proves the writer).
usage: python -I nifcheck.py <file.nif> ...
"""
import struct
import sys


class R:
    def __init__(self, b, o=0):
        self.b, self.o = b, o

    def u(self, f):
        v = struct.unpack_from("<" + f, self.b, self.o); self.o += struct.calcsize("<" + f)
        return v if len(v) > 1 else v[0]


def header(b):
    end = b.index(b"\n") + 1
    r = R(b, end)
    ver, endian, user, nblocks, bsver = r.u("IBIII")
    for _ in range(3):
        n = r.u("B"); r.o += n
    ntypes = r.u("H")
    types = []
    for _ in range(ntypes):
        n = r.u("I"); types.append(b[r.o:r.o + n].decode()); r.o += n
    idx = [r.u("H") for _ in range(nblocks)]
    sizes = [r.u("I") for _ in range(nblocks)]
    nstr, _ = r.u("II")
    strings = []
    for _ in range(nstr):
        n = r.u("I"); strings.append(b[r.o:r.o + n].decode("latin1")); r.o += n
    ngroups = r.u("I"); r.o += 4 * ngroups
    return dict(ver=ver, user=user, bsver=bsver, types=[types[i] for i in idx], sizes=sizes, strings=strings, start=r.o)


def net(r, shader_type=False):
    if shader_type:
        r.u("I")
    r.u("i")
    n = r.u("I"); r.o += 4 * n
    r.u("i")


def av(r):
    net(r)
    r.u("I"); r.o += 12 + 36 + 4; r.u("i")


def parse_block(t, r, info):
    if t in ("NiNode", "BSFadeNode", "BSLeafAnimNode", "BSMultiBoundNode"):
        av(r)
        n = r.u("I"); r.o += 4 * n
        n = r.u("I"); r.o += 4 * n
        if t == "BSMultiBoundNode":
            r.u("i")
            r.u("I")
    elif t == "NiTriShape":
        av(r)
        r.u("ii")
        nm = r.u("I"); r.o += 8 * nm
        r.u("iB")
        r.u("ii")
    elif t == "NiTriShapeData":
        r.u("i")
        nv = r.u("H"); r.u("BB")
        if r.u("B"):
            r.o += 12 * nv
        flags = r.u("H")
        r.u("I")  # material CRC
        if r.u("B"):
            r.o += 12 * nv
            if flags & 4096:
                r.o += 24 * nv
        r.o += 16
        if r.u("B"):
            r.o += 16 * nv
        r.o += 8 * nv * (flags & 1)
        r.u("H"); r.u("i")
        nt = r.u("H")
        r.u("I")
        if r.u("B"):
            r.o += 6 * nt
        nmg = r.u("H")
        for _ in range(nmg):
            k = r.u("H"); r.o += 2 * k
        info.append(f"verts={nv} tris={nt} flags={flags:#x}")
    elif t == "BSLightingShaderProperty":
        st = struct.unpack_from("<I", r.b, r.o)[0]
        net(r, shader_type=True)
        sf1, sf2 = r.u("II")
        r.o += 16
        r.u("i")
        r.o += 16
        r.u("I")
        r.o += 4 * 3 + 16 + 8
        extra = {1: 4, 5: 12, 6: 12, 7: 8, 11: 20, 14: 16, 16: 28}.get(st, 0)
        r.o += extra
        info.append(f"shaderType={st} sf1={sf1:#x} sf2={sf2:#x}")
    elif t == "BSDismemberSkinInstance":
        r.u("iii"); nb = r.u("I"); r.o += 4 * nb
        n = r.u("I"); r.o += 4 * n
        info.append(f"bones={nb} partitions={n}")
    elif t == "NiSkinData":
        r.o += 52
        nb = r.u("I"); hw = r.u("B")
        for _ in range(nb):
            r.o += 52 + 16
            nv = r.u("H")
            if hw:
                r.o += 6 * nv
    elif t == "NiSkinPartition":
        n = r.u("I")
        for _ in range(n):
            nv, nt, nb, ns, nw = r.u("5H")
            r.o += 2 * nb
            if r.u("B"):
                r.o += 2 * nv
            if r.u("B"):
                r.o += 4 * nv * nw
            lens = [r.u("H") for _ in range(ns)]
            if r.u("B"):
                if ns:
                    r.o += 2 * sum(lens)
                else:
                    r.o += 6 * nt
            if r.u("B"):
                r.o += nv * nw
            r.u("BB")
            info.append(f"part verts={nv} tris={nt} bones={nb} w/v={nw}")
    elif t == "BSShaderTextureSet":
        n = r.u("i")
        for _ in range(n):
            k = r.u("I"); r.o += k
    else:
        return False
    return True


def check(path):
    b = open(path, "rb").read()
    h = header(b)
    o = h["start"]
    ok = bad = skipped = 0
    for i, (t, size) in enumerate(zip(h["types"], h["sizes"])):
        r = R(b, o); info = []
        try:
            known = parse_block(t, r, info)
        except Exception as e:
            known, info = True, [f"EXC {e}"]
            r.o = -1
        if not known:
            skipped += 1
        elif r.o - o == size:
            ok += 1
        else:
            bad += 1
            print(f"  MISMATCH block {i} {t}: parsed {r.o - o} of {size} bytes {info}")
        o += size
    foot = R(b, o); nroots = foot.u("I")
    tail_ok = foot.o + 4 * nroots == len(b)
    print(f"{path.split(chr(92))[-1][:70]}: ver={h['ver']:#x} user={h['user']} bsver={h['bsver']} "
          f"blocks ok={ok} bad={bad} other={skipped} footer={'ok' if tail_ok else 'BAD'}")


if __name__ == "__main__":
    for p in sys.argv[1:]:
        check(p)
