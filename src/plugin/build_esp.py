"""Generate DragonlandsGP.esp from the sheets (sheets/*.json are the source of truth).

usage: python -I build_esp.py <sheets dir> <Skyrim.esm> <out.esp> [--test-near x,y,z,cellId]
F1-derived values (speed curves) ship as zeros; the importer fills them from the player's own F1 2021.
"""
import json
import math
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from esm import Esm  # noqa: E402
from esp import Plugin, drop, set_sub, u32, zstr  # noqa: E402

CURVE_SAMPLES = 16  # importer resamples each F1 curve to this many points


def fid_of(cell):
    return int(cell.split()[0], 16)


# --- VMAD (script attachment), Skyrim LE version 5 / object format 2 ---------------------------------------
def wstr(s):
    b = s.encode("cp1252")
    return struct.pack("<H", len(b)) + b


def prop(name, kind, value):
    head = wstr(name)
    if kind == "object":
        return head + struct.pack("<BB", 1, 1) + struct.pack("<HhI", 0, -1, value)
    if kind == "float":
        return head + struct.pack("<BBf", 4, 1, value)
    if kind == "object[]":
        return head + struct.pack("<BBI", 11, 1, len(value)) + b"".join(struct.pack("<HhI", 0, -1, v) for v in value)
    if kind == "float[]":
        return head + struct.pack("<BBI", 14, 1, len(value)) + b"".join(struct.pack("<f", v) for v in value)
    raise ValueError(kind)


def vmad(script, props):
    body = struct.pack("<hhH", 5, 2, 1) + wstr(script) + struct.pack("<BH", 0, len(props))
    return body + b"".join(props)


def glob(p, edid, value=0.0):
    return p.add("GLOB", [["EDID", zstr(edid)], ["FNAM", b"f"], ["FLTV", struct.pack("<f", value)]])


def main():
    sdir, esm_path, out = sys.argv[1], sys.argv[2], sys.argv[3]
    test_near = sys.argv[sys.argv.index("--test-near") + 1] if "--test-near" in sys.argv else None
    S = {f[:-5]: json.load(open(os.path.join(sdir, f))) for f in os.listdir(sdir) if f.endswith(".json")}
    rows = {name: {r["id"]: r for r in s["rows"]} for name, s in S.items()}
    rec, car, cps = rows["records"], rows["cars"]["ferrari"], S["checkpoints"]["rows"]
    esm = Esm(esm_path)
    p = Plugin(esm)

    # globals: best lap, import flag, tuning, and the F1 curves (zeros until the importer runs)
    g_best = glob(p, rec["best_lap_global"]["edid"])
    g_imported = glob(p, "DLGP_F1Imported")
    g_scale = glob(p, "DLGP_SpeedScale", car["speed_scale"])
    g_grip = glob(p, "DLGP_GripPerLap", 0.1)
    g_diag = glob(p, "DLGP_Diag", 1.0 if "--diag" in sys.argv else 0.0)
    curves = {name: [glob(p, f"DLGP_{name}{i:02d}") for i in range(CURVE_SAMPLES)]
              for name in ("AccelT", "AccelV", "CoastT", "CoastV")}

    # engine sound: SNDR copied from a vanilla looping descriptor, pointing at the imported F1 engine wav
    _, fl, sd = esm.record(0x0F58)                   # OBJWindmillSolitudeLPSD
    set_sub(sd, "EDID", zstr(rec["engine_sndr"]["edid"]))
    set_sub(sd, "ANAM", zstr("Data\\" + car["skyrim_engine_wav"].replace("/", "\\")))
    sndr = p.add("SNDR", sd, flags=fl)
    soun = p.add("SOUN", [["EDID", zstr(rec["engine_soun"]["edid"])], ["OBND", bytes(12)], ["SDSC", u32(sndr)]])

    # the rideable car: ARMA/ARMO/NPC_ as verified in game (test_mount.py)
    _, _, aa = esm.record(0x36EA7)                   # NakedHorseAA
    aa = drop(aa, "MO2T", "SNDD")
    set_sub(aa, "EDID", zstr(rec["car_skin_aa"]["edid"]))
    set_sub(aa, "MOD2", zstr(car["skyrim_skinned_mesh"].replace("meshes/", "", 1).replace("/", "\\")))
    arma = p.add("ARMA", aa)
    _, _, sk = esm.record(0x60715)                   # SkinHorse
    sk = [s for s in sk if s[0] != "MODL"]
    sk.insert(next(k for k, s in enumerate(sk) if s[0] == "DATA"), ["MODL", u32(arma)])
    set_sub(sk, "EDID", zstr(rec["car_skin"]["edid"]))
    armo = p.add("ARMO", sk)

    # entry pass (book) + grid prompt (message box): no magic - casting crashed this Skyrim LE install
    qid = p.new_id()                                 # scripts below point at the quest
    _, fl_b, bk = esm.record(fid_of(rec["entry_pass"]["base"]))     # MQ105Note: plain readable note
    bk = drop(bk, "KSIZ", "KWDA", "VMAD")
    set_sub(bk, "EDID", zstr(rec["entry_pass"]["edid"]))
    set_sub(bk, "FULL", zstr(rec["entry_pass"]["fields"]["name"]))
    set_sub(bk, "DESC", zstr("<p align='center'><font size='40'>DRAGON-LANDS GRAND PRIX</font></p>"
                             "<p align='center'>Entry pass</p><br><p>Whiterun crossroads to the Riverwood bridge "
                             "and back. One car, one lap, one clock.</p><br><p>Close this pass to be asked whether "
                             "to go to the grid.</p>"))
    set_sub(bk, "CNAM", zstr(""))
    bk.insert(1, ["VMAD", vmad("DLGP_PassScript", [prop("Race", "object", qid)])])
    entry_pass = p.add("BOOK", bk, flags=fl_b)
    _, fl_m, ms = esm.record(fid_of(rec["grid_prompt"]["base"]))    # MQ203PuzzleActivatorMessage: box, 2 buttons
    set_sub(ms, "EDID", zstr(rec["grid_prompt"]["edid"]))
    set_sub(ms, "DESC", zstr(rec["grid_prompt"]["fields"]["text"]))
    buttons = iter(rec["grid_prompt"]["fields"]["buttons"])
    ms = [[s_, zstr(next(buttons))] if s_ == "ITXT" else [s_, v] for s_, v in ms]
    grid_prompt = p.add("MESG", ms, flags=fl_m)

    # NPC_ (car) with the handling script
    _, fl_n, npc = esm.record(0x109E3D)              # WhiterunPlayerHorse
    npc = drop(npc, "TPLT", "DOFT", "VMAD")
    acbs = bytearray(dict(npc)["ACBS"]); struct.pack_into("<H", acbs, 18, 0)
    set_sub(npc, "ACBS", bytes(acbs))
    set_sub(npc, "EDID", zstr(rec["car_npc"]["edid"]))
    set_sub(npc, "WNAM", u32(armo))
    npc.insert(next(k for k, s in enumerate(npc) if s[0] == "OBND") + 1, ["FULL", zstr(car["display_name"])])
    npc.insert(1, ["VMAD", vmad("DLGP_CarScript", [
        prop("AccelT", "object[]", curves["AccelT"]), prop("AccelV", "object[]", curves["AccelV"]),
        prop("CoastT", "object[]", curves["CoastT"]), prop("CoastV", "object[]", curves["CoastV"]),
        prop("SpeedScale", "object", g_scale), prop("GripPerLap", "object", g_grip),
        prop("EngineSound", "object", soun)])])
    car_npc = p.add("NPC_", npc, flags=fl_n)

    # track: persistent grid marker + car, banner posts and braziers in their cells
    cp0 = cps[0]
    gx, gy, gz = cp0["pos"]
    head = cp0["heading"]
    grid = p.place_persistent("REFR", [["EDID", zstr(rec["grid_marker"]["edid"])], ["NAME", u32(0x34)],
                                       ["DATA", struct.pack("<6f", gx, gy, gz + 20, 0, 0, head)]])
    if test_near:
        tx, ty, tz, _ = test_near.split(",")
        car_pos = (float(tx) + 250, float(ty) - 120, float(tz))
    else:
        car_pos = (gx, gy, gz + 20)
    car_ref = p.place_persistent("ACHR", [["EDID", zstr("DLGP_FerrariCarRef")], ["NAME", u32(car_npc)],
                                          ["DATA", struct.pack("<6f", *car_pos, 0, 0, head)]])
    side = (math.cos(head), -math.sin(head))          # right-hand side of the road for heading (0 = +Y)
    for c in cps:
        x, y, z = c["pos"]
        post = fid_of(rec["checkpoint_marker"]["base"])
        for sgn in (1, -1) if c["role"] != "checkpoint" else (1,):
            p.place(int(c["cell"], 16), "REFR", [["NAME", u32(post)], ["DATA", struct.pack(
                "<6f", x + sgn * side[0] * 420, y + sgn * side[1] * 420, z, 0, 0, c["heading"])]])
    braz = fid_of(rec["start_brazier"]["base"])
    for sgn in (1, -1):
        p.place(int(cp0["cell"], 16), "REFR", [["NAME", u32(braz)], ["DATA", struct.pack(
            "<6f", gx + sgn * side[0] * 350 - math.sin(head) * 120, gy + sgn * side[1] * 350 - math.cos(head) * 120, gz, 0, 0, head)]])

    # quest (start game enabled) with the race controller
    p.add("QUST", [
        ["EDID", zstr(rec["race_quest"]["edid"])],
        ["VMAD", vmad("DLGP_RaceQuestScript", [
            prop("Car", "object", car_ref), prop("GridMarker", "object", grid),
            prop("EntryPass", "object", entry_pass), prop("GridPrompt", "object", grid_prompt),
            prop("BestLap", "object", g_best),
            prop("F1Imported", "object", g_imported), prop("CarControl", "object", car_ref), prop("Diag", "object", g_diag),
            prop("CheckX", "float[]", [c["pos"][0] for c in cps]), prop("CheckY", "float[]", [c["pos"][1] for c in cps]),
            prop("CheckRadius", "float", float(cps[0]["radius_units"]))]
            + ([prop("DiagProbe", "float", 1.0)] if test_near else []))],   # unknown property -> Papyrus logs a binding warning
        ["FULL", zstr("Dragon-lands Grand Prix")],
        ["DNAM", struct.pack("<HBBII", 0x0011, 50, 0, 0, 0)],    # flags as vanilla VoicePowers (start game enabled); priority 50
        ["NEXT", b""], ["ANAM", u32(0)]], fid=qid)
    p.write(out)
    print(f"wrote {out}: quest {qid:08X} car {car_npc:08X} carRef {car_ref:08X} grid {grid:08X} pass {entry_pass:08X} prompt {grid_prompt:08X} "
          f"checkpoints {len(cps)} records {p.count}")


if __name__ == "__main__":
    main()
