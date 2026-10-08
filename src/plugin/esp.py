"""Write Skyrim LE plugins: records from subrecord lists, groups, and world/cell overrides for placed references."""
import struct
import zlib

FORM_VERSION = 43   # Skyrim LE
HEDR_VERSION = 0.94
TAMRIEL = 0x3C


def zstr(s):
    return s.encode("cp1252") + b"\0"


def sub(sig, data):
    if len(data) > 0xFFFF:
        return b"XXXX" + struct.pack("<HI", 4, len(data)) + sig.encode() + struct.pack("<H", 0) + data
    return sig.encode() + struct.pack("<H", len(data)) + data


def record(sig, fid, subs, flags=0):
    payload = b"".join(sub(s, v) for s, v in subs)
    return sig.encode() + struct.pack("<IIIIHH", len(payload), flags, fid, 0, FORM_VERSION, 0) + payload


def group(label, gtype, body):
    if isinstance(label, str):
        label = struct.unpack("<I", label.encode())[0]
    return b"GRUP" + struct.pack("<IIiII", 24 + len(body), label, gtype, 0, 0) + body


def u32(v):
    return struct.pack("<I", v)


def set_sub(subs, sig, value):
    for s in subs:
        if s[0] == sig:
            s[1] = value
            return subs
    subs.append([sig, value])
    return subs


def drop(subs, *sigs):
    return [s for s in subs if s[0] not in sigs]


class Plugin:
    """Collects top-level records by type and exterior placements per cell, then writes a valid LE plugin."""

    ORDER = ["GLOB", "KYWD", "SPEL", "MGEF", "SNDR", "SOUN", "ARMO", "ARMA", "BOOK", "STAT", "NPC_", "MESG", "QUST", "WRLD"]

    def __init__(self, esm, author="DragonlandsGP", masters=("Skyrim.esm",)):
        self.esm, self.author, self.masters = esm, author, masters
        self.next_id = 0x800
        self.records = {}          # sig -> [bytes]
        self.placements = {}       # cell formID -> [record bytes] (temporary children)
        self.persistent = []       # persistent references (Tamriel persistent cell)
        self.count = 0

    def new_id(self):
        fid = (len(self.masters) << 24) | self.next_id
        self.next_id += 1
        return fid

    def add(self, sig, subs, fid=None, flags=0):
        fid = fid or self.new_id()
        self.records.setdefault(sig, []).append(record(sig, fid, subs, flags))
        self.count += 1
        return fid

    def place(self, cell_id, sig, subs):
        fid = self.new_id()
        self.placements.setdefault(cell_id, []).append(record(sig, fid, subs))
        self.count += 1
        return fid

    def place_persistent(self, sig, subs):
        """A reference scripts can point at: lives in Tamriel's persistent cell with the persistent flag."""
        fid = self.new_id()
        self.persistent.append(record(sig, fid, subs, flags=0x400))
        self.count += 1
        return fid

    def _world(self):
        if not self.placements and not self.persistent:
            return b""
        # group exterior cells by their block/sub-block labels in Skyrim.esm
        tree = {}
        for cell_id, refs in self.placements.items():
            blk, sblk = self.esm.cell_blocks[cell_id]
            tree.setdefault(blk, {}).setdefault(sblk, []).append((cell_id, refs))
        body = b""
        for blk, subs_ in tree.items():
            sb = b""
            for sblk, cells in subs_.items():
                sb += group(sblk, 5, b"".join(self._cell_raw(cid) + group(cid, 6, group(cid, 9, b"".join(refs)))
                                              for cid, refs in cells))
            body += group(blk, 4, sb)
        if self.persistent:
            pc = self.esm.persistent_cell
            body = self._cell_raw(pc) + group(pc, 6, group(pc, 8, b"".join(self.persistent))) + body
            self.count += 1
        sig, flags, subs_w = self.esm.record(TAMRIEL)
        wrld = record("WRLD", TAMRIEL, [s for s in subs_w if s[0] != "OFST"], flags)  # OFST points into Skyrim.esm
        self.count += 1 + len(self.placements)
        return group("WRLD", 0, wrld + group(TAMRIEL, 1, body))

    def _cell_raw(self, cid):
        sig, flags, subs = self.esm.record(cid)
        return record("CELL", cid, subs, flags)

    def write(self, path):
        body = b""
        for sig in self.ORDER:
            if sig == "WRLD":
                body += self._world()
            elif sig in self.records:
                body += group(sig, 0, b"".join(self.records[sig]))
        hdr = [["HEDR", struct.pack("<fII", HEDR_VERSION, self.count, (len(self.masters) << 24 | self.next_id) & 0xFFFFFF)],
               ["CNAM", zstr(self.author)]]
        for m in self.masters:
            hdr += [["MAST", zstr(m)], ["DATA", struct.pack("<Q", 0)]]
        with open(path, "wb") as f:
            f.write(record("TES4", 0, hdr) + body)
