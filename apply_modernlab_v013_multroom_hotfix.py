#!/usr/bin/env python3
"""COMI Modern Lab v0.13 multi-room viewport/buffer hotfix.

Apply after:
  apply_modernlab_hd_patch.py
  apply_modernlab_object_layer_hotfix.py
  apply_modernlab_truecolor_v012.py
  apply_modernlab_truecolor_palette_hotfix_v0121.py

Fixes two issues that room 9 could not expose:
  * vertically scrolling rooms now composite the camera-visible slice using _screenTop
  * the pristine background snapshot mirrors SCUMM v7/v8's extra scroll buffer allocation
"""
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


def replace_region(path: Path, start: str, end: str, replacement: str, label: str):
    text = path.read_text(encoding='utf-8')
    if replacement in text:
        print(f'[ok] {label}: already applied')
        return
    a = text.find(start)
    if a < 0:
        raise SystemExit(f'[error] {label}: start anchor not found in {path}')
    b = text.find(end, a + len(start))
    if b < 0:
        raise SystemExit(f'[error] {label}: end anchor not found in {path}')
    path.write_text(text[:a] + replacement + text[b:], encoding='utf-8')
    print(f'[ok] {label}')

scumm_cpp = ROOT / 'engines/scumm/scumm.cpp'
gfx_cpp = ROOT / 'engines/scumm/gfx.cpp'
for p in (scumm_cpp, gfx_cpp):
    if not p.exists():
        raise SystemExit(f'[error] missing {p}')

# SCUMM v7/v8 allocates an additional pitch*8 bytes for horizontally scrollable
# main virtual screens. The v0.11.1 snapshot mirrored only pitch*h, which is safe
# in room 9 but can overflow in wide rooms once xstart becomes large.
replace_once(
    gfx_cpp,
    '''\tconst uint32 bytes = (uint32)vs->pitch * (uint32)vs->h;\n''',
    '''\t// Mirror SCUMM v7/v8's horizontally-scrollable main-buffer allocation.\n\t// initVirtScreen() reserves pitch*h plus pitch*8 bytes for smooth scrolling.\n\tconst uint32 bytes = (uint32)vs->pitch * (uint32)(vs->h + 8);\n''',
    'gfx.cpp safe wide-room base snapshot allocation'
)

new_draw = r'''void ScummEngine::modernLabDrawHDFrame(VirtScreen *vs) {
	const int scale = 2;
	const int srcW = vs->w;
	// SCUMM v7/v8 keeps the main VirtScreen as tall as the room. Only the
	// [_screenTop, _screenTop + _screenHeight) camera slice is visible.
	const int viewTop = MAX<int>(0, (int)_screenTop);
	const int viewBottom = MIN<int>((int)vs->h, (int)_screenTop + (int)_screenHeight);
	const int viewH = viewBottom - viewTop;
	if (viewH <= 0)
		return;

	const int outW = srcW * scale;
	const int outH = viewH * scale;
	const uint32 outBytes = (uint32)outW * (uint32)outH * 4;

	if (!_modernLabHDOutput || _modernLabHDOutputBytes < outBytes) {
		byte *newBuf = (byte *)realloc(_modernLabHDOutput, outBytes);
		if (!newBuf)
			return;
		_modernLabHDOutput = newBuf;
		_modernLabHDOutputBytes = outBytes;
	}

	const Graphics::PixelFormat fmt = _system->getScreenFormat();
	if (fmt.bytesPerPixel != 4)
		return;

	uint32 palette32[256];
	for (int c = 0; c < 256; ++c)
		palette32[c] = fmt.RGBToColor(_currentPalette[c * 3], _currentPalette[c * 3 + 1], _currentPalette[c * 3 + 2]);

	// getPixels(0,0) / getBackPixels(0,0) already include VirtScreen::xstart,
	// which in SCUMM v7/v8 is the full horizontal camera-left coordinate.
	const byte *front = (const byte *)vs->getPixels(0, 0);
	const byte *back = (vs->hasTwoBuffers && vs->backBuf) ? (const byte *)vs->getBackPixels(0, 0) : nullptr;
	const byte *base = (_modernLabHDBase && _modernLabHDBaseRoom == _currentRoom)
		? _modernLabHDBase + vs->xstart : nullptr;
	const int pitch = vs->pitch;
	const bool haveHD = modernLabLoadHDRoom();
	const uint32 *hd = (const uint32 *)_modernLabHDPixels;
	uint32 *out = (uint32 *)_modernLabHDOutput;

	for (int y = 0; y < viewH; ++y) {
		const int sy = viewTop + y;
		for (int x = 0; x < srcW; ++x) {
			bool foreground = !haveHD || !back || !base;
			if (!foreground) {
				// Expand the preserved foreground/object mask by one native pixel.
				// This avoids HD background colour leaking around antialiased sprites.
				for (int yy = MAX<int>(0, sy - 1); yy <= MIN<int>((int)vs->h - 1, sy + 1) && !foreground; ++yy) {
					for (int xx = MAX<int>(0, x - 1); xx <= MIN<int>(srcW - 1, x + 1); ++xx) {
						const int p = yy * pitch + xx;
						// front != back  -> actors/text/dynamic foreground
						// back  != base  -> stateful room object (door, prop, etc.)
						if (front[p] != back[p] || back[p] != base[p]) {
							foreground = true;
							break;
						}
					}
				}
			}

			const int ox = x * scale;
			const int oy = y * scale;
			if (!foreground) {
				const int hx = (vs->xstart + x) * scale;
				const int hy = sy * scale;
				if (hx >= 0 && hy >= 0 && hx + 1 < _modernLabHDWidth && hy + 1 < _modernLabHDHeight) {
					out[(oy + 0) * outW + ox + 0] = hd[(hy + 0) * _modernLabHDWidth + hx + 0];
					out[(oy + 0) * outW + ox + 1] = hd[(hy + 0) * _modernLabHDWidth + hx + 1];
					out[(oy + 1) * outW + ox + 0] = hd[(hy + 1) * _modernLabHDWidth + hx + 0];
					out[(oy + 1) * outW + ox + 1] = hd[(hy + 1) * _modernLabHDWidth + hx + 1];
					continue;
				}
			}

			const uint32 color = palette32[front[sy * pitch + x]];
			out[(oy + 0) * outW + ox + 0] = color;
			out[(oy + 0) * outW + ox + 1] = color;
			out[(oy + 1) * outW + ox + 0] = color;
			out[(oy + 1) * outW + ox + 1] = color;
		}
	}

	const int destY = vs->topline * scale;
	_system->copyRectToScreen(_modernLabHDOutput, outW * 4, 0, destY, outW, outH);
}

'''
replace_region(
    gfx_cpp,
    'void ScummEngine::modernLabDrawHDFrame(VirtScreen *vs) {\n',
    'void ScummEngine::drawStripToScreen(VirtScreen *vs, int x, int width, int top, int bottom) {\n',
    new_draw,
    'gfx.cpp v0.13 scrolling-room compositor'
)

# Make runtime identification unambiguous in screenshots/logs.
replace_once(
    scumm_cpp,
    'COMI Modern Lab HD v0.12 compositor enabled (F10 toggles remastered background)',
    'COMI Modern Lab HD v0.13 compositor enabled (F10 toggles remastered background)',
    'scumm.cpp v0.13 startup banner'
)
replace_once(
    scumm_cpp,
    'COMI Modern Lab v0.12: true-colour output ON for room %d',
    'COMI Modern Lab v0.13: true-colour output ON for room %d',
    'scumm.cpp v0.13 true-colour banner'
)
replace_once(
    scumm_cpp,
    'COMI Modern Lab v0.12: backend rejected 32-bit output for room %d',
    'COMI Modern Lab v0.13: backend rejected 32-bit output for room %d',
    'scumm.cpp v0.13 backend warning'
)
replace_once(
    scumm_cpp,
    'COMI Modern Lab v0.12: returned to CLUT8 output for room %d',
    'COMI Modern Lab v0.13: returned to CLUT8 output for room %d',
    'scumm.cpp v0.13 CLUT8 banner'
)

print('\nCOMI Modern Lab v0.13 multi-room viewport/buffer hotfix applied successfully.')
