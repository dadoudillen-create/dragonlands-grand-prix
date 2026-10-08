"""Replace the compiling user's name and machine name stored in compiled Papyrus (.pex) headers.

Skyrim pex header: magic u32 (0xFA57C0DE, big-endian), major u8, minor u8, game id u16, compile time u64,
then source file name, user name, machine name as u16-length strings (big-endian). Nothing later holds offsets.
usage: python -I pexscrub.py <file.pex> ... [--user X] [--machine Y]
"""
import struct
import sys


def scrub(path, user="DragonlandsGP", machine="build"):
    b = open(path, "rb").read()
    assert struct.unpack_from(">I", b, 0)[0] == 0xFA57C0DE, "not a Skyrim pex"
    o = 4 + 1 + 1 + 2 + 8
    strs = []
    for _ in range(3):
        n = struct.unpack_from(">H", b, o)[0]; strs.append(b[o + 2:o + 2 + n]); o += 2 + n
    new = [strs[0], user.encode(), machine.encode()]
    head = b[:16] + b"".join(struct.pack(">H", len(s)) + s for s in new)
    open(path, "wb").write(head + b[o:])
    return strs[1].decode(), strs[2].decode()


if __name__ == "__main__":
    files = [a for a in sys.argv[1:] if a.endswith(".pex")]
    for f in files:
        print(f, "was", scrub(f))
