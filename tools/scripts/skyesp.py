"""Minimal Skyrim LE plugin writer: TES4 header + one STAT (static) record per model.

usage: python -I skyesp.py <out.esp> <EditorID>=<mesh path relative to Data/meshes> ...
"""
import struct
import sys

FORM_VERSION = 43  # Skyrim LE
HEDR_VERSION = 0.94


def sub(sig, data):
    return sig.encode() + struct.pack("<H", len(data)) + data


def zstr(s):
    return s.encode("ascii") + b"\0"


def record(sig, form_id, payload, flags=0):
    return sig.encode() + struct.pack("<IIIIHH", len(payload), flags, form_id, 0, FORM_VERSION, 0) + payload


def group(label, records):
    body = b"".join(records)
    return b"GRUP" + struct.pack("<I", 24 + len(body)) + label.encode() + struct.pack("<iII", 0, 0, 0) + body


def write_esp(path, statics, author="DragonlandsGP"):
    first = 0x800
    stats = []
    for i, (edid, model, bounds) in enumerate(statics):
        payload = sub("EDID", zstr(edid))
        payload += sub("OBND", struct.pack("<6h", *bounds))
        payload += sub("MODL", zstr(model))
        payload += sub("DNAM", struct.pack("<fI", 90.0, 0))  # max angle, no directional material
        stats.append(record("STAT", 0x01000000 | (first + i), payload))
    hdr = sub("HEDR", struct.pack("<fII", HEDR_VERSION, len(stats), first + len(stats)))
    hdr += sub("CNAM", zstr(author))
    hdr += sub("MAST", zstr("Skyrim.esm")) + sub("DATA", struct.pack("<Q", 0))
    out = record("TES4", 0, hdr) + group("STAT", stats)
    with open(path, "wb") as f:
        f.write(out)


if __name__ == "__main__":
    items = []
    for arg in sys.argv[2:]:
        edid, model = arg.split("=", 1)
        items.append((edid, model, (-70, -182, -27, 70, 213, 59)))
    write_esp(sys.argv[1], items)
    print("wrote", sys.argv[1], "records:", [hex(0x01000800 + i) for i in range(len(items))])
