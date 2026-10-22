# UE4SS for the cabin game

> 🛟 **Need help or found a bug?** Get support at [support.doodesch.de/ue4ss](https://support.doodesch.de/ue4ss).

[![Check distribution](https://github.com/DooDesch-Mods/TheCabinGame-UE4SS/actions/workflows/ci.yml/badge.svg)](https://github.com/DooDesch-Mods/TheCabinGame-UE4SS/actions/workflows/ci.yml)

The original [UE4SS](https://github.com/UE4SS-RE/RE-UE4SS) loader for the Steam
Windows version of **the cabin game**, required by Lua mods such as ChairMarker.
This distribution preserves the upstream ZIP without changes. UE4SS is by
Narknon and the UE4SS-RE contributors; DooDesch maintains this unofficial mirror.

## Download

Selected version: **v3.0.1-1164-g5e627997**. The loader was used for ChairMarker
checks on Steam build `25553694`, Unreal Engine `5.5`. Follow your gameplay mod's
version requirements. Other mods and game updates may need a different build.

- [Original upstream ZIP](https://github.com/UE4SS-RE/RE-UE4SS/releases/download/experimental-latest/UE4SS_v3.0.1-1164-g5e627997.zip).
- [Checked distribution builds](https://github.com/DooDesch-Mods/TheCabinGame-UE4SS/actions/workflows/ci.yml): open a successful run, download **ue4ss-package**, then extract the outer artifact ZIP.
- [Distribution releases](https://github.com/DooDesch-Mods/TheCabinGame-UE4SS/releases). A Nexus loader page is being prepared.

Original ZIP SHA-256:

```text
3c72142a383e25e9f9553ac9e4d5677aa572e98cb369cac57200efb2e381e603
```

## Install

1. Close the game and open `the_cabin_game/Binaries/Win64` in its installation folder.
2. Preserve existing UE4SS mods and settings before replacing files.
3. Extract the loader ZIP next to `the_cabin_game-Win64-Shipping.exe`; keep `dwmapi.dll` and the `ue4ss` folder together.
4. Install Lua mods under `ue4ss/Mods` and follow each mod's instructions.

The original ZIP includes upstream example mods and settings. For Vortex, import
the ZIP as a mod using the [game extension](https://github.com/DooDesch-Mods/TheCabinGame-Vortex).
Extension 0.1.1 in Vortex 2.8.0 installed this loader and Chair Marker 0.1.2,
which worked in game. Disable, re-enable and purge checks also passed.
The Nexus Mod Manager download button uses the game's `thecabingame` mapping.

To uninstall, close the game, preserve your mods/settings, then remove this
loader's `dwmapi.dll` and `ue4ss` folder. Mods that require UE4SS will stop working.

## Updates and licenses

The daily **Check upstream** Action prepares newer basic builds as unapproved
candidates. After game/mod checks, a selected version can be released and sent
to an existing Nexus Main File. See [publishing](docs/publishing.md).

The [exact upstream source](https://github.com/UE4SS-RE/RE-UE4SS/tree/5e627997bf265ae6fc89d23357543d8c8ac05a6f)
and its [MIT license](licenses/UE4SS-MIT.txt) remain unchanged. Our distribution
tools and documents use the [DooDesch license](LICENSE.md), following
ServerPasswordOnce. It does not cover UE4SS. See [credits](CREDITS.md) and the
selected package in [distribution.json](distribution.json).
