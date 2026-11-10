#!/usr/bin/env python3
'''COMI Modern Lab v0.13.2 Room Test Harness.

Apply after:
  apply_modernlab_hd_patch.py
  apply_modernlab_object_layer_hotfix.py
  apply_modernlab_truecolor_v012.py
  apply_modernlab_truecolor_palette_hotfix_v0121.py
  apply_modernlab_v013_multroom_hotfix.py

Adds renderer-validation room jumping:
  F9        -> next test room
  Shift+F9  -> previous test room
  Ctrl+F9   -> return to room 9 (cannon)
  F10       -> original/remastered background toggle (existing)
'''
from pathlib import Path
import sys

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()


def replace_once(path: Path, old: str, new: str, label: str):
    text = path.read_text(encoding="utf-8")
    if new in text:
        print(f"[ok] {label}: already applied")
        return
    if old not in text:
        raise SystemExit(f"[error] {label}: anchor not found in {path}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    print(f"[ok] {label}")


input_cpp = ROOT / "engines/scumm/input.cpp"
scumm_cpp = ROOT / "engines/scumm/scumm.cpp"
for p in (input_cpp, scumm_cpp):
    if not p.exists():
        raise SystemExit(f"[error] missing {p}")

old_branch = '''\t\t} else if (_modernLabHD && event.kbd.keycode == Common::KEYCODE_F10) {
\t\t\t_modernLabHDUseBackground = !_modernLabHDUseBackground;
\t\t\t_modernLabHDRoom = -1;
\t\t\tfree(_modernLabHDPixels);
\t\t\t_modernLabHDPixels = nullptr;
\t\t\t_fullRedraw = true;
\t\t\twarning("COMI Modern Lab HD background: %s", _modernLabHDUseBackground ? "ON" : "OFF");
'''

new_branch = '''\t\t} else if (_modernLabHD && event.kbd.keycode == Common::KEYCODE_F9) {
\t\t\t// Modern Lab renderer validation harness. This deliberately mirrors
\t\t\t// ScummDebugger::Cmd_Room(): move the ego to the target room, stop
\t\t\t// sounds, then use the normal startScene() path.
\t\t\tif (_smushActive) {
\t\t\t\twarning("COMI Modern Lab tester: finish/skip the SMUSH cutscene before room-jumping");
\t\t\t} else {
\t\t\t\tstatic const int testRooms[] = { 9, 15, 79, 62, 91, 93 };
\t\t\t\tstatic const char *const testNames[] = {
\t\t\t\t\t"cannon", "town", "clifface", "recipes", "credits", "endcred"
\t\t\t\t};
\t\t\t\tconst int count = ARRAYSIZE(testRooms);
\t\t\t\tint current = -1;
\t\t\t\tfor (int i = 0; i < count; ++i) {
\t\t\t\t\tif (testRooms[i] == _currentRoom) {
\t\t\t\t\t\tcurrent = i;
\t\t\t\t\t\tbreak;
\t\t\t\t\t}
\t\t\t\t}

\t\t\t\tint next = 0;
\t\t\t\tif (event.kbd.hasFlags(Common::KBD_CTRL)) {
\t\t\t\t\tnext = 0;
\t\t\t\t} else if (current >= 0) {
\t\t\t\t\tconst int delta = event.kbd.hasFlags(Common::KBD_SHIFT) ? -1 : 1;
\t\t\t\t\tnext = (current + delta + count) % count;
\t\t\t\t}

\t\t\t\tconst int room = testRooms[next];
\t\t\t\tif (VAR_EGO != 0xFF) {
\t\t\t\t\tconst int ego = VAR(VAR_EGO);
\t\t\t\t\tif (ego >= 0 && ego < _numActors && _actors[ego])
\t\t\t\t\t\t_actors[ego]->_room = room;
\t\t\t\t}

\t\t\t\tif (_sound)
\t\t\t\t\t_sound->stopAllSounds();

\t\t\t\t// Drop the previous room sidecar cache before startScene().
\t\t\t\t_modernLabHDRoom = -1;
\t\t\t\tfree(_modernLabHDPixels);
\t\t\t\t_modernLabHDPixels = nullptr;

\t\t\t\tstartScene(room, nullptr, 0);
\t\t\t\t_fullRedraw = true;
\t\t\t\twarning("COMI Modern Lab tester: room %d (%s) | F9 next | Shift+F9 previous | Ctrl+F9 cannon | F10 HD toggle",
\t\t\t\t\troom, testNames[next]);
\t\t\t}
\t\t} else if (_modernLabHD && event.kbd.keycode == Common::KEYCODE_F10) {
\t\t\t_modernLabHDUseBackground = !_modernLabHDUseBackground;
\t\t\t_modernLabHDRoom = -1;
\t\t\tfree(_modernLabHDPixels);
\t\t\t_modernLabHDPixels = nullptr;
\t\t\t_fullRedraw = true;
\t\t\twarning("COMI Modern Lab HD background: %s", _modernLabHDUseBackground ? "ON" : "OFF");
'''

replace_once(
    input_cpp,
    old_branch,
    new_branch,
    "input.cpp F9 room-test harness"
)

replace_once(
    scumm_cpp,
    'COMI Modern Lab HD v0.13 compositor enabled (F10 toggles remastered background)',
    'COMI Modern Lab HD v0.13.2 compositor enabled (F9 room tester, F10 remastered toggle)',
    "scumm.cpp v0.13.2 startup banner"
)

replace_once(
    scumm_cpp,
    'COMI Modern Lab v0.13: true-colour output ON for room %d',
    'COMI Modern Lab v0.13.2: true-colour output ON for room %d',
    "scumm.cpp v0.13.2 true-colour banner"
)

replace_once(
    scumm_cpp,
    'COMI Modern Lab v0.13: backend rejected 32-bit output for room %d',
    'COMI Modern Lab v0.13.2: backend rejected 32-bit output for room %d',
    "scumm.cpp v0.13.2 backend warning"
)

replace_once(
    scumm_cpp,
    'COMI Modern Lab v0.13: returned to CLUT8 output for room %d',
    'COMI Modern Lab v0.13.2: returned to CLUT8 output for room %d',
    "scumm.cpp v0.13.2 CLUT8 banner"
)

print("\nCOMI Modern Lab v0.13.2 room test harness applied successfully.")
