"""Build a Dragon-lands Grand Prix release from the sheets.

usage: python -I build.py <version>
Steps: preflight (must be clean) -> compile + scrub scripts -> generate plugin -> our assets and placeholders ->
importer bundle (signed python.org embeddable + open-source wheels + our importer) -> release zip.
Ships nothing from F1 2021 or Bethesda: F1 content is converted on the player's PC by the importer.
"""
import glob
import json
import os
import shutil
import subprocess
import sys
import wave
import zipfile

ROOT = os.path.dirname(os.path.abspath(__file__))
SKYRIM_ESM = os.environ.get("DLGP_SKYRIM_ESM", "Skyrim.esm")   # path to your own Skyrim.esm (build input only)
PYEMBED = os.path.join(ROOT, "tools", "dl", "pyembed", "py")
PAPYRUS = os.path.join(ROOT, "tools", "dl", "papyrus-compiler", "papyrus-compiler", "papyrus.exe")
WHEELS = ["numpy", "pillow", "lz4", "zstandard"]


def run(*cmd):
    print(">", " ".join(str(c) for c in cmd))
    subprocess.run([str(c) for c in cmd], check=True, cwd=ROOT)


def main():
    version = sys.argv[1]
    out = os.path.join(ROOT, "build", "release", version)
    shutil.rmtree(out, ignore_errors=True)
    data, imp = os.path.join(out, "Data"), os.path.join(out, "Importer")
    py = sys.executable

    run(py, "-I", "tools/scripts/preflight.py", "sheets", SKYRIM_ESM)

    pex = os.path.join(ROOT, "build", "pex")
    shutil.rmtree(pex, ignore_errors=True)
    os.makedirs(pex)
    run(PAPYRUS, "compile", "-h", "src/papyrus/headers", "-i", "src/papyrus/scripts", "-o", pex, "-nocache")
    run(py, "-I", "tools/scripts/pexscrub.py", *glob.glob(os.path.join(pex, "*.pex")))
    os.makedirs(os.path.join(data, "Scripts"))
    for f in glob.glob(os.path.join(pex, "*.pex")):
        shutil.copy2(f, os.path.join(data, "Scripts"))

    run(py, "-I", "src/plugin/build_esp.py", "sheets", SKYRIM_ESM, os.path.join(data, "DragonlandsGP.esp"))
    run(py, "-I", "tools/scripts/espcheck.py", os.path.join(data, "DragonlandsGP.esp"))

    # our own textures + placeholders the importer overwrites (listed in the package so Melty tracks them)
    sys.path.insert(0, os.path.join(ROOT, "src", "importer"))
    from PIL import Image
    from skynif import build_skinned
    common = os.path.join(data, "textures", "dlgp", "common")
    os.makedirs(common)
    Image.new("RGBA", (64, 64), (22, 22, 24, 255)).save(os.path.join(common, "carbon.dds"), "DDS", pixel_format="DXT1")
    Image.new("RGBA", (64, 64), (128, 128, 255, 255)).save(os.path.join(common, "flat_n.dds"), "DDS", pixel_format="DXT1")
    cars = json.load(open(os.path.join(ROOT, "sheets", "cars.json")))
    for car in cars["rows"]:
        mesh = os.path.join(data, car["skyrim_skinned_mesh"])
        os.makedirs(os.path.dirname(mesh), exist_ok=True)
        build_skinned(mesh, [], "NPC Root [Root]")                     # empty until the importer runs
        tdir = os.path.join(data, car["skyrim_textures"])
        os.makedirs(tdir, exist_ok=True)
        for key in sorted({v for v in car["material_textures"].values() if v != "carbon"}):
            Image.new("RGBA", (4, 4), (90, 90, 90, 255)).save(os.path.join(tdir, key + ".dds"), "DDS", pixel_format="DXT5")
        wav = os.path.join(data, car["skyrim_engine_wav"])
        os.makedirs(os.path.dirname(wav), exist_ok=True)
        with wave.open(wav, "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(48000); w.writeframes(b"\0\0" * 4800)

    # importer bundle
    shutil.copytree(PYEMBED, imp)
    site = os.path.join(imp, "Lib", "site-packages")
    run(py, "-m", "pip", "install", "--quiet", "--target", site, "--only-binary=:all:", "--platform", "win_amd64",
        "--python-version", "3.12", "--implementation", "cp", *WHEELS)
    for junk in glob.glob(os.path.join(site, "**", "tests"), recursive=True) + glob.glob(os.path.join(site, "bin")):
        shutil.rmtree(junk, ignore_errors=True)
    for junk in glob.glob(os.path.join(site, "**", "__pycache__"), recursive=True):
        shutil.rmtree(junk, ignore_errors=True)
    with open(os.path.join(imp, "python312._pth"), "w") as f:
        f.write("python312.zip\n.\nLib\\site-packages\n")
    for f in ("importer.py", "carconv.py", "engine.py", "perf.py", "egoerp.py", "egopkg.py", "skynif.py"):
        shutil.copy2(os.path.join(ROOT, "src", "importer", f), imp)
    shutil.copy2(os.path.join(ROOT, "sheets", "cars.json"), imp)
    lic = os.path.join(imp, "licenses")
    os.makedirs(lic)
    shutil.copy2(os.path.join(PYEMBED, "LICENSE.txt"), os.path.join(lic, "Python-LICENSE.txt"))
    for d in glob.glob(os.path.join(site, "*.dist-info")):
        for name in ("LICENSE", "LICENSE.txt", "LICENSE.rst", "COPYING"):
            for p in glob.glob(os.path.join(d, "**", name), recursive=True):
                shutil.copy2(p, os.path.join(lic, os.path.basename(d).split("-")[0] + "-" + os.path.basename(p)))
    shutil.copy2(os.path.join(ROOT, "CREDITS.txt"), out)

    zpath = os.path.join(ROOT, "build", "release", f"DragonlandsGP-{version}.zip")
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for base, _, files in os.walk(out):
            for f in files:
                full = os.path.join(base, f)
                z.write(full, os.path.relpath(full, out).replace("\\", "/"))
    n = sum(len(f) for _, _, f in os.walk(out))
    print(f"release {zpath}: {n} files, {os.path.getsize(zpath) / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
