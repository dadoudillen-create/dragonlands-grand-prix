"""Test plugin: rideable Ferrari (horse actor with the F1 car as its skin) beside the static car below Solitude.

usage: python -I test_mount.py <Skyrim.esm> <out.esp>
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from esm import Esm  # noqa: E402
from esp import Plugin, drop, set_sub, u32, zstr  # noqa: E402

SOLITUDE_CELL = 0x927B          # SolitudeExterior01, where the static car already stands
STATIC_POS = (-66844.0, 103909.0, -8507.0)


def main():
    esm = Esm(sys.argv[1])
    p = Plugin(esm)

    stat = p.add("STAT", [["EDID", zstr("DLGP_FerrariStatic")], ["OBND", struct.pack("<6h", -70, -182, -27, 70, 213, 59)],
                          ["MODL", zstr(r"dlgp\ferrari.nif")], ["DNAM", struct.pack("<fI", 90.0, 0)]])

    # ARMA: copy of NakedHorseAA with the Ferrari mount mesh, no texture hashes, no hoof footsteps
    _, _, aa = esm.record(0x36EA7)
    aa = drop(aa, "MO2T", "SNDD")
    set_sub(aa, "EDID", zstr("DLGP_FerrariSkinAA"))
    set_sub(aa, "MOD2", zstr(r"dlgp\ferrari_mount.nif"))
    arma = p.add("ARMA", aa)

    # ARMO: copy of SkinHorse listing only the Ferrari addon
    _, _, sk = esm.record(0x60715)
    sk = [s for s in sk if s[0] != "MODL"]
    i = next(k for k, s in enumerate(sk) if s[0] == "DATA")
    sk.insert(i, ["MODL", u32(arma)])
    set_sub(sk, "EDID", zstr("DLGP_FerrariSkin"))
    armo = p.add("ARMO", sk)

    # NPC_: copy of WhiterunPlayerHorse, own traits (no template), our skin, no saddle outfit
    _, flags, npc = esm.record(0x109E3D)
    npc = drop(npc, "TPLT", "DOFT")
    acbs = bytearray(dict(npc)["ACBS"])
    struct.pack_into("<H", acbs, 18, 0)                       # template data flags off
    set_sub(npc, "ACBS", bytes(acbs))
    set_sub(npc, "EDID", zstr("DLGP_FerrariCar"))
    set_sub(npc, "WNAM", u32(armo))
    i = next(k for k, s in enumerate(npc) if s[0] == "OBND") + 1
    npc.insert(i, ["FULL", zstr("Ferrari")])
    car = p.add("NPC_", npc, flags=flags)

    x, y, z = STATIC_POS
    p.place(SOLITUDE_CELL, "REFR", [["NAME", u32(stat)], ["DATA", struct.pack("<6f", x, y, z, 0, 0, 1.04)]])
    p.place(SOLITUDE_CELL, "ACHR", [["NAME", u32(car)], ["DATA", struct.pack("<6f", x + 250, y - 120, z - 20, 0, 0, 1.04)]])
    p.write(sys.argv[2])
    print(f"STAT {stat:08X} ARMA {arma:08X} ARMO {armo:08X} NPC_ {car:08X} -> {sys.argv[2]}")


if __name__ == "__main__":
    main()
