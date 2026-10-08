# Dragon-lands Grand Prix

A mashup of **The Elder Scrolls V: Skyrim Special Edition** and **F1 2021**: a solo time trial in which you drive
the real F1 2021 car along Skyrim's roads, from the Whiterun crossroads down to the Riverwood bridge and back.

Nothing from either game is in this repository or in the download. The F1 2021 car (model, livery, tyres), its engine
sound and its handling data are converted on the player's PC, from the player's own F1 2021 install, the first time
the mashup starts.

## What's in it

| Part | Folder | What it does |
|---|---|---|
| Driving plugin | `src/sseplugin` | Native Skyrim SE plugin (`.asi`, loaded by Ultimate ASI Loader): moves the car every frame with F1 2021's acceleration, braking, coasting and cornering-grip tables; countdown, checkpoints, lap timer, best lap |
| Importer | `src/importer` | Finds F1 2021 through Steam and converts the car, tyres, textures, engine loop and performance tables into Skyrim files (Python) |
| Plugin generator | `src/plugin` | Builds `DragonlandsGP.esp` (car object, grid, checkpoint banners) from the design sheets |
| Design sheets | `sheets` | Source of truth for cars, track, assets, systems and engine hooks; `tools/scripts/preflight.py` checks every cell and reference |

Controls: **View/Back** on an Xbox controller (or **F8**) goes to the grid. Right trigger / **W** throttle, left
trigger / **S** brake, left stick / **A D** steer.

## Building the plugin

Windows, Visual Studio 2022 Build Tools (C++), CMake, Ninja and vcpkg:

```
git clone --recursive https://github.com/dadoudillen-create/dragonlands-grand-prix
cmake -S src/sseplugin -B build -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_TOOLCHAIN_FILE=<vcpkg>/scripts/buildsystems/vcpkg.cmake -DVCPKG_TARGET_TRIPLET=x64-windows-static
cmake --build build --target DragonlandsGP
```

The GitHub Actions workflow builds the same thing; release builds are code-signed through SignPath Foundation.

## Credits

- [CommonLibSSE NG / CommonLibVR](https://github.com/alandtse/CommonLibVR) (GPL-3.0-or-later), pinned as a submodule
- [Ego Engine Modding](https://github.com/EgoEngineModding/Ego-Engine-Modding) (MIT): ERP, mesh, pkg and engine-sound formats, ported to Python
- [Address Library for SKSE Plugins](https://www.nexusmods.com/skyrimspecialedition/mods/32444) by meh321 (bundled in releases with credit, per its page)
- [Ultimate ASI Loader](https://github.com/ThirteenAG/Ultimate-ASI-Loader) (installed by Melty)
- [niftools nif.xml](https://github.com/niftools/nifxml) (NIF format reference)
- Python, NumPy, Pillow, python-lz4, python-zstandard (importer runtime; licences shipped with releases)

Made with the help of an AI coding assistant (Claude).

The Elder Scrolls V: Skyrim is a trademark of Bethesda Softworks / ZeniMax Media. F1 2021 is a game by Codemasters /
Electronic Arts; F1 and FORMULA 1 are trademarks of Formula One Licensing B.V. This is an unofficial fan project, not
endorsed by any of them. You need your own copies of both games.

## Licence

GPL-3.0-or-later (see `LICENSE.txt`), because the plugin links CommonLibSSE NG.
