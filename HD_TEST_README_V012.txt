COMI MODERN LAB v0.12 - TRUE-COLOUR HD PROTOTYPE
=================================================

What changed from v0.11.1
-------------------------
* The proven three-layer compositor remains intact:
    base room background + room objects + actors/dynamic foreground.
* Rooms with an MLTC sidecar switch the ScummVM backend to 32-bit RGBA output.
* The MLTC sidecar stores portable 24-bit RGB pixels (no 256-colour quantization).
* Original actors, room objects, text and UI remain native CLUT8 internally and
  are palette-converted to the 32-bit output at render time.
* Rooms without an MLTC sidecar stay on stock CLUT8 output. This deliberately
  keeps intro movies and untouched rooms on ScummVM's normal path.
* F10 still toggles Original / Remastered background in a true-colour room.

Room 9 prototype
----------------
The included room_09.mltc is 1280x960 RGB24 and is generated from the current
Modern Lab cannon-room restoration master.

Expected test
-------------
1. Run INSTALL_V012_TRUECOLOR_ASSETS_WINDOWS.bat and select the extracted COMI
   data folder containing COMI.LA0 / COMI.LA1 / COMI.LA2.
2. Start the custom v0.12 scummvm.exe from the GitHub Actions artifact.
3. Add the same extracted COMI folder and start a New Game.
4. Reach the first cannon-hold room.
5. Press F10 repeatedly.

Expected:
  F10 OFF = original 640x480 indexed background expanded to 1280x960 RGBA.
  F10 ON  = 1280x960 true-colour Modern Lab background.

The locked door and all other SCUMM room objects must remain visible in both
modes. Actors and hotspots must remain aligned.

Known prototype limits
----------------------
* Actors/objects are still original-resolution art, nearest-neighbour doubled.
* The HD background currently does not emulate every palette fade/cycle effect.
* Only room 9 has a true-colour sidecar in this milestone.
