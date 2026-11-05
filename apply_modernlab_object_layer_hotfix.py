#!/usr/bin/env python3
from pathlib import Path
import sys

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()


def replace_once(path: Path, old: str, new: str, label: str):
    text = path.read_text(encoding='utf-8')
    if new in text:
        print(f'[ok] {label}: already applied')
        return
    if old not in text:
        raise SystemExit(f'[error] {label}: anchor not found in {path}')
    path.write_text(text.replace(old, new, 1), encoding='utf-8')
    print(f'[ok] {label}')

scumm_h = ROOT / 'engines/scumm/scumm.h'
scumm_cpp = ROOT / 'engines/scumm/scumm.cpp'
gfx_cpp = ROOT / 'engines/scumm/gfx.cpp'
for p in (scumm_h, scumm_cpp, gfx_cpp):
    if not p.exists():
        raise SystemExit(f'[error] missing {p}; run this after apply_modernlab_hd_patch.py on a ScummVM checkout')

replace_once(
    scumm_h,
    '''\tbyte *_modernLabHDPixels = nullptr;\n\tbyte *_modernLabHDOutput = nullptr;\n\n\tbool modernLabLoadHDRoom();\n\tvoid modernLabDrawHDFrame(VirtScreen *vs);\n''',
    '''\tbyte *_modernLabHDPixels = nullptr;\n\tbyte *_modernLabHDOutput = nullptr;\n\n\t// Snapshot of the pristine SCUMM room background before OBIM room objects\n\t// are drawn into backBuf. This lets the HD compositor distinguish true\n\t// background pixels from interactive/static room objects (doors, props, etc.).\n\tbyte *_modernLabHDBase = nullptr;\n\tuint32 _modernLabHDBaseBytes = 0;\n\tint _modernLabHDBaseRoom = -1;\n\n\tbool modernLabLoadHDRoom();\n\tvoid modernLabCaptureBaseStrip(VirtScreen *vs, int x, int width);\n\tvoid modernLabDrawHDFrame(VirtScreen *vs);\n''',
    'scumm.h room-object preservation state'
)

replace_once(
    scumm_cpp,
    '''\tfree(_modernLabHDPixels);\n\tfree(_modernLabHDOutput);\n\t_modernLabHDPixels = nullptr;\n\t_modernLabHDOutput = nullptr;\n''',
    '''\tfree(_modernLabHDPixels);\n\tfree(_modernLabHDOutput);\n\tfree(_modernLabHDBase);\n\t_modernLabHDPixels = nullptr;\n\t_modernLabHDOutput = nullptr;\n\t_modernLabHDBase = nullptr;\n\t_modernLabHDBaseBytes = 0;\n\t_modernLabHDBaseRoom = -1;\n''',
    'scumm.cpp room-object preservation cleanup'
)

helper_anchor = 'bool ScummEngine::modernLabLoadHDRoom() {\n'
helper = r'''void ScummEngine::modernLabCaptureBaseStrip(VirtScreen *vs, int x, int width) {
	if (!_modernLabHD || !vs || !vs->backBuf || vs->format.bytesPerPixel != 1)
		return;

	if (x < 0) {
		width += x;
		x = 0;
	}
	if (x >= vs->w || width <= 0)
		return;
	if (x + width > vs->w)
		width = vs->w - x;

	const uint32 bytes = (uint32)vs->pitch * (uint32)vs->h;
	if (!_modernLabHDBase || _modernLabHDBaseBytes != bytes || _modernLabHDBaseRoom != _currentRoom) {
		free(_modernLabHDBase);
		_modernLabHDBase = (byte *)malloc(bytes);
		if (!_modernLabHDBase) {
			_modernLabHDBaseBytes = 0;
			_modernLabHDBaseRoom = -1;
			return;
		}
		memset(_modernLabHDBase, 0, bytes);
		_modernLabHDBaseBytes = bytes;
		_modernLabHDBaseRoom = _currentRoom;
	}

	for (int y = 0; y < vs->h; ++y) {
		const byte *src = vs->getBackPixels(x, y);
		byte *dst = _modernLabHDBase + y * vs->pitch + vs->xstart + x;
		memcpy(dst, src, width);
	}
}

'''
text = gfx_cpp.read_text(encoding='utf-8')
if 'void ScummEngine::modernLabCaptureBaseStrip' not in text:
    if helper_anchor not in text:
        raise SystemExit('[error] gfx.cpp Modern Lab helper anchor not found; apply base v0.11 patch first')
    gfx_cpp.write_text(text.replace(helper_anchor, helper + helper_anchor, 1), encoding='utf-8')
    print('[ok] gfx.cpp base-background capture helper')
else:
    print('[ok] gfx.cpp base-background capture helper: already applied')

replace_once(
    gfx_cpp,
    '''\t_gdi->drawBitmap(room + _IM00_offs, &_virtscr[kMainVirtScreen], s, 0, _roomWidth, _virtscr[kMainVirtScreen].h, s, num, 0);\n}\n''',
    '''\t_gdi->drawBitmap(room + _IM00_offs, &_virtscr[kMainVirtScreen], s, 0, _roomWidth, _virtscr[kMainVirtScreen].h, s, num, 0);\n\n\t// Capture only the freshly redrawn pristine background strips, before\n\t// drawRoomObjects() composites OBIM objects into the SCUMM back buffer.\n\tif (_modernLabHD)\n\t\tmodernLabCaptureBaseStrip(&_virtscr[kMainVirtScreen], start * 8, num * 8);\n}\n''',
    'gfx.cpp capture pristine background strips'
)

replace_once(
    gfx_cpp,
    '''\tconst byte *front = (const byte *)vs->getPixels(0, 0);\n\tconst byte *back = (vs->hasTwoBuffers && vs->backBuf) ? (const byte *)vs->getBackPixels(0, 0) : nullptr;\n\tconst int pitch = vs->pitch;\n\tconst bool haveHD = modernLabLoadHDRoom();\n\n\tfor (int y = 0; y < srcH; ++y) {\n\t\tfor (int x = 0; x < srcW; ++x) {\n\t\t\tbool foreground = !haveHD || !back;\n\t\t\tif (!foreground) {\n\t\t\t\tfor (int yy = MAX(0, y - 1); yy <= MIN(srcH - 1, y + 1) && !foreground; ++yy) {\n\t\t\t\t\tfor (int xx = MAX(0, x - 1); xx <= MIN(srcW - 1, x + 1); ++xx) {\n\t\t\t\t\t\tif (front[yy * pitch + xx] != back[yy * pitch + xx]) {\n\t\t\t\t\t\t\tforeground = true;\n\t\t\t\t\t\t\tbreak;\n\t\t\t\t\t\t}\n\t\t\t\t\t}\n\t\t\t\t}\n\t\t\t}\n''',
    '''\tconst byte *front = (const byte *)vs->getPixels(0, 0);\n\tconst byte *back = (vs->hasTwoBuffers && vs->backBuf) ? (const byte *)vs->getBackPixels(0, 0) : nullptr;\n\tconst byte *base = (_modernLabHDBase && _modernLabHDBaseRoom == _currentRoom)\n\t\t? _modernLabHDBase + vs->xstart : nullptr;\n\tconst int pitch = vs->pitch;\n\tconst bool haveHD = modernLabLoadHDRoom();\n\n\tfor (int y = 0; y < srcH; ++y) {\n\t\tfor (int x = 0; x < srcW; ++x) {\n\t\t\tbool foreground = !haveHD || !back || !base;\n\t\t\tif (!foreground) {\n\t\t\t\tfor (int yy = MAX(0, y - 1); yy <= MIN(srcH - 1, y + 1) && !foreground; ++yy) {\n\t\t\t\t\tfor (int xx = MAX(0, x - 1); xx <= MIN(srcW - 1, x + 1); ++xx) {\n\t\t\t\t\t\tconst int p = yy * pitch + xx;\n\t\t\t\t\t\t// front != back  -> actor / text / other dynamic foreground\n\t\t\t\t\t\t// back  != base  -> SCUMM room object (door, prop, stateful OBIM)\n\t\t\t\t\t\tif (front[p] != back[p] || back[p] != base[p]) {\n\t\t\t\t\t\t\tforeground = true;\n\t\t\t\t\t\t\tbreak;\n\t\t\t\t\t\t}\n\t\t\t\t\t}\n\t\t\t\t}\n\t\t\t}\n''',
    'gfx.cpp preserve room objects as foreground'
)

print('\nModern Lab HD v0.11.1 object-layer hotfix applied successfully.')
