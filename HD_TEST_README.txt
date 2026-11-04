COMI MODERN LAB v0.11 - HD COMPOSITOR PROTOTYPE
================================================

Target ScummVM revision:
  f909c9d882248fe25b4aff96ccb48b33cf2d8f42

What this prototype changes
---------------------------
* SCUMM logic, room coordinates, walkboxes, scripts and savegame state remain native.
* Output presentation becomes 1280x960 (2x).
* Room 9 (the first cannon hold) can use a separate 1280x960 CLUT8 sidecar background.
* Actors / dynamic objects remain original artwork and are nearest-neighbor doubled.
* A one-pixel-dilated foreground mask protects actor/object edges from the HD background.
* Mouse coordinates are mapped back to the original 640x480 coordinate system.
* F10 toggles Original / HD background while the game is running.

Important
---------
This is deliberately an indexed-colour HD prototype. It breaks the 640x480 spatial
resolution limit first, while retaining COMI's original room palette. True-colour HD
is the next renderer milestone after this compositor is runtime-verified.

Game-data installation
----------------------
Run INSTALL_HD_ASSETS_WINDOWS.bat and point it at your normal extracted COMI game
folder. It adds only:

  modernlab_hd/enabled.flag
  modernlab_hd/room_09.mlhd

It does NOT modify COMI.LA0, COMI.LA1 or COMI.LA2.

Building the custom Windows executable
--------------------------------------
The included GitHub Actions workflow builds a pinned Windows x64 ScummVM executable.
Put the contents of this build kit in a GitHub repository, then run:

  Actions -> Build COMI Modern Lab HD ScummVM (Windows x64) -> Run workflow

Download the COMI-Modern-Lab-HD-v0.11-Windows-x64 artifact when the run completes.

Testing
-------
1. Install the modernlab_hd folder into your COMI data folder.
2. Start the custom scummvm.exe.
3. Add your ORIGINAL COMI data folder. No LA0/LA1 patch is needed for HD mode.
4. Start a new game.
5. In the first cannon-hold room, press F10 repeatedly.

Expected result:
  F10 OFF = original background enlarged 2x
  F10 ON  = 1280x960 Modern Lab sidecar background

The actors and pirate should remain aligned and interactive in both modes.
