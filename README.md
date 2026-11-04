# COMI Modern Lab v0.11 — HD Compositor Prototype

This build kit is the first renderer-side experiment. It does **not** patch the COMI archives.
Instead, a small ScummVM modification keeps the SCUMM VM at its original coordinate system and
composites an external 2× background beneath the native actors and dynamic objects.

## Proof target

- Game: The Curse of Monkey Island
- Room: 9 (`cannon`), first playable hold
- Engine logic: 640×480/native
- Presentation: 1280×960
- Sidecar: `modernlab_hd/room_09.mlhd`
- Toggle: **F10** Original ↔ HD

## Files

- `apply_modernlab_hd_patch.py` — patches the pinned ScummVM source
- `.github/workflows/build-hd-scummvm-windows.yml` — Windows x64 cloud build
- `modernlab_hd/room_09.mlhd` — indexed 1280×960 first-room HD sidecar
- `modernlab_hd/enabled.flag` — enables the compositor
- `INSTALL_HD_ASSETS_WINDOWS.bat` — copies sidecars into your game-data folder
- `HD_TEST_README.txt` — test instructions

The original COMI data files remain untouched.

## Building more HD room sidecars

`make_hd_sidecar.py` takes an original COMI bundle plus a 2× PNG and creates the indexed sidecar:

```text
python make_hd_sidecar.py --bundle COMI.LA1 --room 9 --image cannon_remastered_2x_master.png --out modernlab_hd/room_09.mlhd
```

The generator is dependency-free and validates the exact 2× room dimensions.
