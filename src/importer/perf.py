"""F1 2021 AI performance tables -> speed curves the Skyrim car script reads, written into DragonlandsGP.esp.

The plugin ships with DLGP_AccelT00..15 / AccelV / CoastT / CoastV globals at 0; this fills them in place
(same record sizes, so the file layout does not change) and sets DLGP_F1Imported to 1.
"""
import struct
import zlib

import numpy as np

from egoerp import read_erp
from egopkg import read_pkg

SAMPLES = 16


def curves(perf_erp_path, ers_mode="none", index=0):
    res = {r.name.rsplit("/", 1)[-1]: r for r in read_erp(perf_erp_path)}
    acc = read_pkg(res["acceleration.acpd"].frag(0))["AIAC"]["sampleSetList"]
    acc = [s for s in acc if s.get("ers_mode") == ers_mode][index]
    coast = read_pkg(res["cruising.crpd"].frag(0))["AICR"]["sampleSetList"][0]
    out = {}
    for name, s in (("Accel", acc), ("Coast", coast)):
        t, v = np.array(s["timeList"], float), np.array(s["speedList"], float)
        ts = np.linspace(t[0], t[-1], SAMPLES)
        out[name + "T"] = ts
        out[name + "V"] = np.interp(ts, t, v)
    return out


def patch_globals(esp_path, values):
    """values: {EditorID: float}. Rewrites FLTV of matching GLOB records in place; returns the EditorIDs written."""
    b = bytearray(open(esp_path, "rb").read())
    done, o = set(), 0
    while o < len(b):
        sig = bytes(b[o:o + 4])
        if sig == b"GRUP":
            o += 24; continue
        size, flags = struct.unpack_from("<II", b, o + 4)
        if sig == b"GLOB" and not flags & 0x40000:
            p, end, edid = o + 24, o + 24 + size, None
            while p < end:
                ssig = bytes(b[p:p + 4]); ssize = struct.unpack_from("<H", b, p + 4)[0]
                if ssig == b"EDID":
                    edid = bytes(b[p + 6:p + 6 + ssize]).rstrip(b"\0").decode()
                elif ssig == b"FLTV" and edid in values:
                    struct.pack_into("<f", b, p + 6, float(values[edid])); done.add(edid)
                p += 6 + ssize
        o += 24 + size
    open(esp_path, "wb").write(bytes(b))
    return done


def curve_globals(c):
    vals = {}
    for key, arr in c.items():
        for i, v in enumerate(arr):
            vals[f"DLGP_{key}{i:02d}"] = v
    return vals


# --- Skyrim SE: physics tables for the native driving plugin (Data/SKSE/Plugins/DragonlandsGP/car.json) ---------
def _rate(t, v):
    """dv/dt along a speed-time curve, as (speed, |rate|) pairs sorted by speed."""
    t, v = np.asarray(t, float), np.asarray(v, float)
    dv, dt = np.diff(v), np.maximum(np.diff(t), 1e-6)
    vm, a = (v[1:] + v[:-1]) / 2, np.abs(dv / dt)
    o = np.argsort(vm)
    return [round(float(x), 3) for x in vm[o]], [round(float(x), 3) for x in a[o]]


def _lateral(sets, grip, mass_index=0):
    """F1 cornering table: max speed through each corner radius -> lateral grip v^2/r vs speed."""
    at = sorted([s for s in sets if abs(s["grip"] - grip) < 1e-3], key=lambda s: s["mass"])[mass_index]
    v, r = np.array(at["speedList"], float), np.array(at["distanceList"], float)
    o = np.argsort(v)
    return [round(float(x), 3) for x in v[o]], [round(float(x), 3) for x in (v * v / r)[o]]


def car_physics(perf_erp_path, name, ers_mode="none", index=0, speed_scale=0.5):
    res = {r.name.rsplit("/", 1)[-1]: r for r in read_erp(perf_erp_path)}
    acc = [s for s in read_pkg(res["acceleration.acpd"].frag(0))["AIAC"]["sampleSetList"] if s.get("ers_mode") == ers_mode][index]
    brk = next(s for s in read_pkg(res["braking.brpd"].frag(0))["AIBR"]["sampleSetList"] if s["radius"] == 0.0)
    cst = read_pkg(res["cruising.crpd"].frag(0))["AICR"]["sampleSetList"][0]
    cor = read_pkg(res["cornering.copd"].frag(0))
    cor = cor[next(iter(cor))]["sampleSetList"]
    out = {"name": name, "speed_scale": speed_scale, "source": "F1 2021 AI performance tables from the player's install"}
    for key, s in (("accel", acc), ("brake", brk), ("coast", cst)):
        x, y = _rate(s["timeList"], s["speedList"])
        out[key] = {"x": x, "y": y}
    out["cornering"] = dict(zip(("x", "y"), _lateral(cor, 1.0)))
    out["cornering_worn"] = dict(zip(("x", "y"), _lateral(cor, 0.6)))
    out["top_speed"] = round(float(max(max(acc["speedList"]), max(brk["speedList"]))), 2)
    out["grip_loss_per_lap"] = 0.1          # F1 grip levels run 1.0 -> 0.6; one level per lap
    out["grip_min"] = 0.6
    return out
