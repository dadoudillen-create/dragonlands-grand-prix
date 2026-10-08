"""Read records from Skyrim.esm (LE) by formID or EditorID, as editable subrecord lists."""
import struct
import zlib


def subrecords(data):
    out, o, big = [], 0, None
    while o < len(data):
        sig = data[o:o + 4].decode("latin1"); size = struct.unpack_from("<H", data, o + 4)[0]; o += 6
        if sig == "XXXX":
            big = struct.unpack_from("<I", data, o)[0]; o += size; continue
        if big is not None:
            size, big = big, None
        out.append([sig, bytes(data[o:o + size])])
        o += size
    return out


class Esm:
    def __init__(self, path):
        self.b = open(path, "rb").read()
        self.index = {}        # formID -> (sig, offset)
        self.edids = {}
        self.cell_blocks = {}  # Tamriel exterior cell formID -> (block label, sub-block label)
        self.persistent_cell = None  # Tamriel's persistent cell (holds persistent exterior references)
        stack, o = [], 0
        while o < len(self.b):
            while stack and o >= stack[-1][0]:
                stack.pop()
            sig = self.b[o:o + 4]
            if sig == b"GRUP":
                gsize, label, gtype = struct.unpack_from("<IIi", self.b, o + 4)
                stack.append((o + gsize, gtype, label))
                o += 24; continue
            size, flags, fid = struct.unpack_from("<III", self.b, o + 4)
            self.index[fid] = (sig.decode(), o)
            if sig == b"CELL" and any(t == 1 and l == 0x3C for _, t, l in stack):
                labels = {t: l for _, t, l in stack if t in (4, 5)}
                if 4 in labels and 5 in labels:
                    self.cell_blocks[fid] = (labels[4], labels[5])
                else:  # the persistent worldspace cell sits directly in the world children group
                    self.persistent_cell = fid
            o += 24 + size

    def record(self, fid):
        """-> (sig, flags, [ [subsig, bytes], ... ]) with compression undone."""
        sig, o = self.index[fid]
        size, flags = struct.unpack_from("<II", self.b, o + 4)
        data = self.b[o + 24:o + 24 + size]
        if flags & 0x40000:
            data = zlib.decompress(data[4:])
            flags &= ~0x40000
        return sig, flags, subrecords(data)

    def raw(self, fid):
        sig, o = self.index[fid]
        size = struct.unpack_from("<I", self.b, o + 4)[0]
        return self.b[o:o + 24 + size]

    def find_edid(self, edid, sig=None):
        if not self.edids:
            for fid, (s, _) in self.index.items():
                if s in ("GRUP",):
                    continue
                try:
                    subs = self.record(fid)[2]
                except Exception:
                    continue
                for ss, v in subs:
                    if ss == "EDID":
                        self.edids[(s, v.rstrip(b"\0").decode("cp1252"))] = fid
                        break
        return self.edids[(sig, edid)] if sig else next(f for (s, e), f in self.edids.items() if e == edid)
