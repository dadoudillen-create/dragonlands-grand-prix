"""Generate the Skyrim SE plugin and track file from the sheets.

usage: python -I build_esp_se.py <sheets dir> <SE Skyrim.esm> <out Data folder>
Writes <Data>/DragonlandsGP.esp (car object at the grid + track dressing) and
<Data>/SKSE/Plugins/DragonlandsGP/track.json (checkpoints for the native driving plugin).
The driving plugin finds the car by its plugin-local formID 0x801.
"""
import json
import math
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import esp  # noqa: E402
from esm import Esm  # noqa: E402
from esp import Plugin, u32, zstr  # noqa: E402

esp.FORM_VERSION = 44       # Skyrim SE
esp.HEDR_VERSION = 1.71
CAR_REF_LOCAL_ID = 0x801


def fid_of(cell):
    return int(cell.split()[0], 16)


def main():
    sdir, esm_path, data = sys.argv[1], sys.argv[2], sys.argv[3]
    S = {f[:-5]: json.load(open(os.path.join(sdir, f))) for f in os.listdir(sdir) if f.endswith(".json")}
    rows = {name: {r["id"]: r for r in s["rows"]} for name, s in S.items()}
    rec, car, cps = rows["records"], rows["cars"]["ferrari"], S["checkpoints"]["rows"]
    p = Plugin(Esm(esm_path))

    model = car["skyrim_mesh"].replace("meshes/", "", 1).replace("/", "\\")
    stat = p.add("STAT", [["EDID", zstr(rec["car_static"]["edid"])], ["OBND", struct.pack("<6h", -70, -182, 0, 70, 213, 86)],
                          ["MODL", zstr(model)], ["DNAM", struct.pack("<fI", 90.0, 0)]])
    cp0 = cps[0]
    gx, gy, gz = cp0["pos"]
    car_ref = p.place_persistent("REFR", [["EDID", zstr("DLGP_FerrariCarRef")], ["NAME", u32(stat)],
                                          ["DATA", struct.pack("<6f", gx, gy, gz, 0, 0, cp0["heading"])]])
    assert car_ref & 0xFFFFFF == CAR_REF_LOCAL_ID, hex(car_ref)

    side = (math.cos(cp0["heading"]), -math.sin(cp0["heading"]))
    post = fid_of(rec["checkpoint_marker"]["base"])
    for c in cps:
        x, y, z = c["pos"]
        s = (math.cos(c["heading"]), -math.sin(c["heading"]))
        for sgn in (1, -1) if c["role"] != "checkpoint" else (1,):
            p.place(int(c["cell"], 16), "REFR", [["NAME", u32(post)], ["DATA", struct.pack(
                "<6f", x + sgn * s[0] * 420, y + sgn * s[1] * 420, z, 0, 0, c["heading"])]])
    braz = fid_of(rec["start_brazier"]["base"])
    for sgn in (1, -1):
        p.place(int(cp0["cell"], 16), "REFR", [["NAME", u32(braz)], ["DATA", struct.pack(
            "<6f", gx + sgn * side[0] * 350, gy + sgn * side[1] * 350, gz, 0, 0, cp0["heading"])]])
    os.makedirs(data, exist_ok=True)
    out = os.path.join(data, "DragonlandsGP.esp")
    p.write(out)

    tdir = os.path.join(data, "SKSE", "Plugins", "DragonlandsGP")
    os.makedirs(tdir, exist_ok=True)
    json.dump({"track": S["checkpoints"]["track"], "radius": cps[0]["radius_units"], "grid_heading": cp0["heading"],
               "points": [c["pos"] for c in cps]}, open(os.path.join(tdir, "track.json"), "w"), indent=1)
    print(f"wrote {out}: car STAT {stat:08X}, car ref {car_ref:08X}, {len(cps)} checkpoints; track.json")


if __name__ == "__main__":
    main()
