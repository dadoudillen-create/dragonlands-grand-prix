"""Preflight: lay every sheet's rows and columns over each other and list what will fail or is unimplemented.

usage: python -I preflight.py <sheets dir> <Skyrim.esm>
Blocking: unfilled cells (None, "", "TBD..."), references that do not resolve, Skyrim.esm formIDs that do not exist.
Reported, not blocking: rows with verified=false (they need the in-game test to tick).
Exit code 1 when anything is blocking.
"""
import json
import os
import re
import struct
import sys
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from esmscan import subrecords  # noqa: E402

REF = re.compile(r"\b(cars|records|checkpoints|assets|hooks|systems)\.([A-Za-z0-9_*]+)")
FORMID = re.compile(r"\b([0-9A-F]{8}) ([A-Za-z0-9_]+)")
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def esm_index(esm):
    cache = os.path.join(ROOT, "build", "esm_index.json")
    if os.path.exists(cache):
        return json.load(open(cache))
    b, o, idx = open(esm, "rb").read(), 0, {}
    while o < len(b):
        if b[o:o + 4] == b"GRUP":
            o += 24; continue
        size, flags, fid = struct.unpack_from("<III", b, o + 4)
        data = b[o + 24:o + 24 + size]
        if flags & 0x40000:
            data = zlib.decompress(data[4:])
        for sig, val in subrecords(data):
            if sig == b"EDID":
                idx[f"{fid:08X}"] = val.rstrip(b"\0").decode("cp1252"); break
        o += 24 + size
    os.makedirs(os.path.dirname(cache), exist_ok=True)
    json.dump(idx, open(cache, "w"))
    return idx


def walk(v, path):
    if isinstance(v, dict):
        for k, x in v.items():
            yield from walk(x, path + [k])
    elif isinstance(v, list):
        for i, x in enumerate(v):
            yield from walk(x, path + [str(i)])
    else:
        yield path, v


def main():
    sdir, esm = sys.argv[1], sys.argv[2]
    sheets = {f[:-5]: json.load(open(os.path.join(sdir, f))) for f in sorted(os.listdir(sdir)) if f.endswith(".json")}
    ids = {name: {r["id"] for r in s["rows"]} for name, s in sheets.items()}
    cols = {name: set().union(*(r.keys() for r in s["rows"])) for name, s in sheets.items()}
    idx = esm_index(esm)
    unfilled, broken, badform, pending, cells = [], [], [], [], 0
    for name, s in sheets.items():
        for r in s["rows"]:
            where = f"{name}[{r['id']}]"
            if r.get("verified") is False:
                pending.append(where)
            for path, v in walk(r, []):
                cells += 1
                col = ".".join(path)
                if v is None or (isinstance(v, str) and (v.strip() == "" or v.upper().startswith("TBD"))):
                    unfilled.append(f"{where}.{col} = {v!r}")
                if not isinstance(v, str):
                    continue
                for sheet, key in REF.findall(v):
                    if key == "*" or key in ids[sheet] or key in cols[sheet]:
                        continue
                    broken.append(f"{where}.{col}: '{sheet}.{key}' not found")
                for fid, edid in FORMID.findall(v):
                    if idx.get(fid) != edid:
                        badform.append(f"{where}.{col}: {fid} {edid} (Skyrim.esm has {idx.get(fid)!r})")
            for u in r.get("uses", []):
                if u not in ids["hooks"] and u not in ids["records"]:
                    broken.append(f"{where}.uses: '{u}' is not a hooks/records id")
    print(f"preflight: {len(sheets)} sheets, {sum(len(s['rows']) for s in sheets.values())} rows, {cells} cells")
    for title, items in (("UNFILLED", unfilled), ("UNRESOLVED REFERENCES", broken), ("BAD FORMIDS", badform)):
        print(f"\n{title}: {len(items)}")
        for i in items:
            print("  -", i)
    print(f"\nAWAITING IN-GAME TEST (verified=false): {len(pending)}")
    print("  " + ", ".join(pending))
    sys.exit(1 if unfilled or broken or badform else 0)


if __name__ == "__main__":
    main()
