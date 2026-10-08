"""Dragon-lands Grand Prix importer: runs once before Skyrim starts (Melty recipe.setup).

Finds the player's own F1 2021 through Steam, converts the car(s) in cars.json into Skyrim files and writes
F1's speed curves into DragonlandsGP.esp. Nothing from F1 2021 ships with the mod; it is read here, on the
player's PC, from their install. Without F1 2021 the placeholders stay and the game says how to fix it.

usage: python importer.py --skyrim <Skyrim folder> [--force]
"""
import argparse
import json
import os
import re
import shutil
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

F1_APPID = "1134570"
STATE_DIR = os.path.join(os.environ.get("LOCALAPPDATA", HERE), "DragonlandsGP")
DONE = os.path.join(STATE_DIR, "import_done.txt")
LOG = os.path.join(STATE_DIR, "import.log")
PLUGIN = "DragonlandsGP.esp"


def log(msg):
    os.makedirs(STATE_DIR, exist_ok=True)
    line = time.strftime("%Y-%m-%d %H:%M:%S ") + msg
    print(line)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def steam_root():
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as k:
            return winreg.QueryValueEx(k, "SteamPath")[0].replace("/", "\\")
    except OSError:
        return r"C:\Program Files (x86)\Steam"


def find_f1():
    """Steam library folders -> appmanifest_1134570.acf -> installdir containing F1_2021_dx12.exe."""
    root = steam_root()
    libs = [root]
    vdf = os.path.join(root, "steamapps", "libraryfolders.vdf")
    if os.path.exists(vdf):
        libs += [p.replace("\\\\", "\\") for p in re.findall(r'"path"\s+"([^"]+)"', open(vdf, encoding="utf-8", errors="replace").read())]
    for lib in dict.fromkeys(libs):
        acf = os.path.join(lib, "steamapps", f"appmanifest_{F1_APPID}.acf")
        if os.path.exists(acf):
            m = re.search(r'"installdir"\s+"([^"]+)"', open(acf, encoding="utf-8", errors="replace").read())
            if m:
                d = os.path.join(lib, "steamapps", "common", m.group(1))
                if os.path.exists(os.path.join(d, "F1_2021_dx12.exe")):
                    return d
    return None


def activate_plugin():
    """Original Skyrim reads the active plugin list from %LOCALAPPDATA%\\Skyrim\\plugins.txt."""
    folder = os.path.join(os.environ["LOCALAPPDATA"], "Skyrim")
    path = os.path.join(folder, "plugins.txt")
    os.makedirs(folder, exist_ok=True)
    lines = open(path, encoding="cp1252").read().splitlines() if os.path.exists(path) else []
    if any(l.strip().lower() == PLUGIN.lower() for l in lines):
        return False
    if os.path.exists(path):
        shutil.copy2(path, os.path.join(STATE_DIR, "plugins.txt.before-dragonlandsgp"))
    if not any(l.strip().lower() == "skyrim.esm" for l in lines):
        lines = ["Skyrim.esm", "Update.esm"] + lines
    lines.append(PLUGIN)
    with open(path, "w", encoding="cp1252", newline="\r\n") as f:
        f.write("\n".join(lines) + "\n")
    return True


def import_car(car, f1, data):
    import carconv
    import engine
    import perf
    t0 = time.time()
    res = carconv.load_car(f1, car["f1_car_erp"])
    shapes = carconv.car_shapes(res, car["f1_team_folder"].split("/")[-1], car["lod"], set(car["skip_materials"]),
                                car["material_textures"], car["skyrim_textures"])
    from egoerp import read_erp
    common = read_erp(os.path.join(f1, car["f1_tyre_erp"]))
    shapes += carconv.tyre_shapes(common, carconv.car_shapes.wheels, car["lod"], car["skyrim_textures"])
    carconv.write_tyre_textures(common, f1, os.path.join(data, car["skyrim_textures"]))
    lift = carconv.write_mount_mesh(shapes, os.path.join(data, car["skyrim_skinned_mesh"]))
    log(f"{car['id']}: mesh {len(shapes)} shapes, lifted {lift:.1f} ({time.time() - t0:.1f}s)")
    keys = sorted({v for v in car["material_textures"].values() if v != "carbon"})
    carconv.write_textures(res, car["f1_team_folder"].split("/")[-1], f1, os.path.join(data, car["skyrim_textures"]), keys)
    log(f"{car['id']}: textures {keys}")
    wav = os.path.join(data, car["skyrim_engine_wav"])
    os.makedirs(os.path.dirname(wav), exist_ok=True)
    info = engine.write_loop_wav(engine.read_bdl(os.path.join(f1, car["f1_engine_bdl"])), wav)
    log(f"{car['id']}: engine loop {info}")
    c = perf.curves(os.path.join(f1, car["f1_perf_erp"]), car["f1_perf_set"]["ers_mode"], car["f1_perf_set"]["index"])
    vals = perf.curve_globals(c)
    vals["DLGP_F1Imported"] = 1.0
    written = perf.patch_globals(os.path.join(data, PLUGIN), vals)
    log(f"{car['id']}: speed curves -> {len(written)} plugin values (top {max(c['AccelV']) * 3.6:.0f} km/h)")
    if len(written) != len(vals):
        raise RuntimeError(f"plugin is missing values: {sorted(set(vals) - written)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skyrim", required=True)
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    data = os.path.join(a.skyrim, "Data")
    os.makedirs(STATE_DIR, exist_ok=True)
    log(f"importer start; Skyrim at {a.skyrim}")
    try:
        if activate_plugin():
            log(f"activated {PLUGIN} in plugins.txt (backup kept in {STATE_DIR})")
        f1 = find_f1()
        status = {"f1_found": bool(f1), "f1_dir": f1, "cars": {}}
        if not f1:
            log("F1 2021 not found in any Steam library: keeping the placeholder; the game will say how to fix it")
        else:
            log(f"F1 2021 at {f1}")
            cars = json.load(open(os.path.join(HERE, "cars.json"), encoding="utf-8"))["rows"]
            for car in cars:
                import_car(car, f1, data)
                status["cars"][car["id"]] = "ok"
        json.dump(status, open(os.path.join(STATE_DIR, "status.json"), "w"), indent=1)
        with open(DONE, "w", encoding="utf-8") as f:
            f.write(f"done {time.strftime('%Y-%m-%d %H:%M:%S')} f1={'yes' if f1 else 'no'}\n")
        log("importer done")
        return 0
    except Exception:
        log("importer FAILED:\n" + traceback.format_exc())
        # still release the game so the player is not stuck; the in-game message explains the missing car
        with open(DONE, "w", encoding="utf-8") as f:
            f.write("done with errors; see import.log\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
