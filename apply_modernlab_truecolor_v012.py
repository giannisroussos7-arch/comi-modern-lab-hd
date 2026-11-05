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


scumm_h = ROOT / 'engines/scumm/scumm.h'
scumm_cpp = ROOT / 'engines/scumm/scumm.cpp'
gfx_cpp = ROOT / 'engines/scumm/gfx.cpp'
room_cpp = ROOT / 'engines/scumm/room.cpp'
for p in (scumm_h, scumm_cpp, gfx_cpp, room_cpp):
    if not p.exists():
        raise SystemExit(f'[error] missing {p}; run this after the v0.11 + v0.11.1 patches')

# --- state / declarations -------------------------------------------------
replace_once(
    scumm_h,
    '''\tbyte *_modernLabHDPixels = nullptr;\n\tbyte *_modernLabHDOutput = nullptr;\n\n\t// Snapshot of the pristine SCUMM room background before OBIM room objects\n''',
    '''\tbyte *_modernLabHDPixels = nullptr;\n\tbyte *_modernLabHDOutput = nullptr;\n\tuint32 _modernLabHDOutputBytes = 0;\n\tbool _modernLabHDTrueColor = false;\n\n\t// Snapshot of the pristine SCUMM room background before OBIM room objects\n''',
    'scumm.h true-colour state'
)

replace_once(
    scumm_h,
    '''\tbool modernLabLoadHDRoom();\n\tvoid modernLabCaptureBaseStrip(VirtScreen *vs, int x, int width);\n\tvoid modernLabDrawHDFrame(VirtScreen *vs);\n''',
    '''\tvoid modernLabPrepareRoomOutput();\n\tbool modernLabLoadHDRoom();\n\tvoid modernLabCaptureBaseStrip(VirtScreen *vs, int x, int width);\n\tvoid modernLabDrawTrueColorStrip(VirtScreen *vs, int x, int width, int top, int bottom);\n\tvoid modernLabDrawHDFrame(VirtScreen *vs);\n''',
    'scumm.h true-colour methods'
)

# --- cleanup --------------------------------------------------------------
replace_once(
    scumm_cpp,
    '''\t_modernLabHDPixels = nullptr;\n\t_modernLabHDOutput = nullptr;\n\t_modernLabHDBase = nullptr;\n\t_modernLabHDBaseBytes = 0;\n''',
    '''\t_modernLabHDPixels = nullptr;\n\t_modernLabHDOutput = nullptr;\n\t_modernLabHDOutputBytes = 0;\n\t_modernLabHDTrueColor = false;\n\t_modernLabHDBase = nullptr;\n\t_modernLabHDBaseBytes = 0;\n''',
    'scumm.cpp true-colour cleanup state'
)

# The initial backend remains CLUT8. We only switch to RGBA32 when a room
# actually has a .mltc sidecar, so intro movies and untouched rooms remain on
# ScummVM's normal rendering path.
replace_once(
    scumm_cpp,
    '''\tif (_modernLabHD) {\n\t\tinitGraphics(_screenWidth * 2, _screenHeight * 2);\n\t\twarning("COMI Modern Lab HD compositor enabled (F10 toggles remastered background)");\n''',
    '''\tif (_modernLabHD) {\n\t\tinitGraphics(_screenWidth * 2, _screenHeight * 2);\n\t\t_modernLabHDTrueColor = false;\n\t\twarning("COMI Modern Lab HD v0.12 compositor enabled (F10 toggles remastered background)");\n''',
    'scumm.cpp v0.12 startup mode'
)

prepare_impl = r'''void ScummEngine::modernLabPrepareRoomOutput() {
	if (!_modernLabHD)
		return;

	const Common::String name = Common::String::format("modernlab_hd/room_%02d.mltc", _currentRoom);
	const bool wantTrueColor = Common::File::exists(Common::Path(name));
	if (wantTrueColor == _modernLabHDTrueColor)
		return;

	if (wantTrueColor) {
		Graphics::PixelFormat rgba = Graphics::PixelFormat::createFormatRGBA32();
		initGraphics(_screenWidth * 2, _screenHeight * 2, &rgba);
		_modernLabHDTrueColor = (_system->getScreenFormat().bytesPerPixel == 4);
		if (_modernLabHDTrueColor)
			warning("COMI Modern Lab v0.12: true-colour output ON for room %d", _currentRoom);
		else
			warning("COMI Modern Lab v0.12: backend rejected 32-bit output for room %d", _currentRoom);
	} else {
		initGraphics(_screenWidth * 2, _screenHeight * 2);
		_modernLabHDTrueColor = false;
		warning("COMI Modern Lab v0.12: returned to CLUT8 output for room %d", _currentRoom);
	}

	free(_modernLabHDPixels);
	_modernLabHDPixels = nullptr;
	_modernLabHDRoom = -1;
	_fullRedraw = true;
}

'''
text = scumm_cpp.read_text(encoding='utf-8')
if 'void ScummEngine::modernLabPrepareRoomOutput()' not in text:
    anchor = 'ScummEngine::~ScummEngine() {'
    if anchor not in text:
        raise SystemExit('[error] scumm.cpp destructor anchor not found')
    scumm_cpp.write_text(text.replace(anchor, prepare_impl + anchor, 1), encoding='utf-8')
    print('[ok] scumm.cpp per-room output format switch')
else:
    print('[ok] scumm.cpp per-room output format switch: already applied')

# Switch the backend after _currentRoom changes but before the room palette and
# graphics are initialized. This means room 9 enters RGBA32, while rooms with no
# MLTC sidecar (including movies / normal rooms) remain CLUT8.
replace_once(
    room_cpp,
    '''\t_currentRoom = room;\n\tVAR(VAR_ROOM) = room;\n''',
    '''\t_currentRoom = room;\n\tVAR(VAR_ROOM) = room;\n\tif (_modernLabHD)\n\t\tmodernLabPrepareRoomOutput();\n''',
    'room.cpp select CLUT8/RGBA32 per room'
)

# --- true-colour sidecar loader ------------------------------------------
load_impl = r'''bool ScummEngine::modernLabLoadHDRoom() {
	if (!_modernLabHD || !_modernLabHDTrueColor || !_modernLabHDUseBackground)
		return false;
	if (_modernLabHDRoom == _currentRoom && _modernLabHDPixels)
		return true;

	free(_modernLabHDPixels);
	_modernLabHDPixels = nullptr;
	_modernLabHDWidth = _modernLabHDHeight = 0;
	_modernLabHDRoom = _currentRoom;

	Common::String name = Common::String::format("modernlab_hd/room_%02d.mltc", _currentRoom);
	Common::File f;
	if (!f.open(Common::Path(name)))
		return false;

	char magic[4];
	if (f.read(magic, 4) != 4 || memcmp(magic, "MLTC", 4) != 0)
		return false;
	const uint16 version = f.readUint16LE();
	const uint16 room = f.readUint16LE();
	const uint32 width = f.readUint32LE();
	const uint32 height = f.readUint32LE();
	const byte channels = f.readByte();
	f.skip(3);
	if (version != 1 || room != (uint16)_currentRoom || channels != 3 ||
		!width || !height || width > 16384 || height > 4096)
		return false;

	const uint64 pixels64 = (uint64)width * (uint64)height;
	const uint64 rgbBytes64 = pixels64 * 3;
	const uint64 packedBytes64 = pixels64 * 4;
	if (rgbBytes64 > 96 * 1024 * 1024 || packedBytes64 > 128 * 1024 * 1024)
		return false;

	const uint32 rgbBytes = (uint32)rgbBytes64;
	byte *rgb = (byte *)malloc(rgbBytes);
	if (!rgb)
		return false;
	if (f.read(rgb, rgbBytes) != rgbBytes) {
		free(rgb);
		return false;
	}

	_modernLabHDPixels = (byte *)malloc((uint32)packedBytes64);
	if (!_modernLabHDPixels) {
		free(rgb);
		return false;
	}

	const Graphics::PixelFormat fmt = _system->getScreenFormat();
	if (fmt.bytesPerPixel != 4) {
		free(rgb);
		free(_modernLabHDPixels);
		_modernLabHDPixels = nullptr;
		return false;
	}

	uint32 *dst = (uint32 *)_modernLabHDPixels;
	for (uint64 i = 0; i < pixels64; ++i) {
		const byte *p = rgb + i * 3;
		dst[i] = fmt.RGBToColor(p[0], p[1], p[2]);
	}
	free(rgb);

	_modernLabHDWidth = (int)width;
	_modernLabHDHeight = (int)height;
	debug(1, "ModernLab v0.12: loaded true-colour room %d sidecar %dx%d", _currentRoom, _modernLabHDWidth, _modernLabHDHeight);
	return true;
}

'''
replace_region(
    gfx_cpp,
    'bool ScummEngine::modernLabLoadHDRoom() {\n',
    'void ScummEngine::modernLabDrawHDFrame(VirtScreen *vs) {\n',
    load_impl,
    'gfx.cpp MLTC true-colour loader'
)

# --- generic CLUT8 -> RGBA32 converter -----------------------------------
convert_impl = r'''void ScummEngine::modernLabDrawTrueColorStrip(VirtScreen *vs, int x, int width, int top, int bottom) {
	if (!vs || bottom <= top || top >= vs->h || x < 0 || x >= vs->w)
		return;
	if (width > vs->w - x)
		width = vs->w - x;
	if (top < 0)
		top = 0;
	if (bottom > vs->h)
		bottom = vs->h;
	if (width <= 0 || bottom <= top)
		return;

	const int height = bottom - top;
	const int outW = width * 2;
	const int outH = height * 2;
	const uint32 bytes = (uint32)outW * (uint32)outH * 4;
	if (!_modernLabHDOutput || _modernLabHDOutputBytes < bytes) {
		byte *newBuf = (byte *)realloc(_modernLabHDOutput, bytes);
		if (!newBuf)
			return;
		_modernLabHDOutput = newBuf;
		_modernLabHDOutputBytes = bytes;
	}

	const Graphics::PixelFormat fmt = _system->getScreenFormat();
	if (fmt.bytesPerPixel != 4)
		return;

	uint32 palette32[256];
	for (int c = 0; c < 256; ++c)
		palette32[c] = fmt.RGBToColor(_currentPalette[c * 3], _currentPalette[c * 3 + 1], _currentPalette[c * 3 + 2]);

	uint32 *out = (uint32 *)_modernLabHDOutput;
	for (int sy = 0; sy < height; ++sy) {
		const byte *src = (const byte *)vs->getPixels(x, top + sy);
		uint32 *row0 = out + (sy * 2 + 0) * outW;
		uint32 *row1 = out + (sy * 2 + 1) * outW;
		for (int sx = 0; sx < width; ++sx) {
			const uint32 color = palette32[src[sx]];
			row0[sx * 2 + 0] = color;
			row0[sx * 2 + 1] = color;
			row1[sx * 2 + 0] = color;
			row1[sx * 2 + 1] = color;
		}
	}

	const int screenY = vs->topline + top - _screenTop;
	_system->copyRectToScreen(_modernLabHDOutput, outW * 4, x * 2, screenY * 2, outW, outH);
}

'''
text = gfx_cpp.read_text(encoding='utf-8')
if 'void ScummEngine::modernLabDrawTrueColorStrip' not in text:
    anchor = 'void ScummEngine::modernLabDrawHDFrame(VirtScreen *vs) {\n'
    if anchor not in text:
        raise SystemExit('[error] gfx.cpp HD frame anchor not found')
    gfx_cpp.write_text(text.replace(anchor, convert_impl + anchor, 1), encoding='utf-8')
    print('[ok] gfx.cpp CLUT8 -> RGBA32 converter')
else:
    print('[ok] gfx.cpp CLUT8 -> RGBA32 converter: already applied')

# --- main-room true-colour compositor ------------------------------------
draw_impl = r'''void ScummEngine::modernLabDrawHDFrame(VirtScreen *vs) {
	const int scale = 2;
	const int srcW = vs->w;
	const int srcH = vs->h;
	const int outW = srcW * scale;
	const int outH = srcH * scale;
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

	const byte *front = (const byte *)vs->getPixels(0, 0);
	const byte *back = (vs->hasTwoBuffers && vs->backBuf) ? (const byte *)vs->getBackPixels(0, 0) : nullptr;
	const byte *base = (_modernLabHDBase && _modernLabHDBaseRoom == _currentRoom)
		? _modernLabHDBase + vs->xstart : nullptr;
	const int pitch = vs->pitch;
	const bool haveHD = modernLabLoadHDRoom();
	const uint32 *hd = (const uint32 *)_modernLabHDPixels;
	uint32 *out = (uint32 *)_modernLabHDOutput;

	for (int y = 0; y < srcH; ++y) {
		for (int x = 0; x < srcW; ++x) {
			bool foreground = !haveHD || !back || !base;
			if (!foreground) {
				for (int yy = MAX(0, y - 1); yy <= MIN(srcH - 1, y + 1) && !foreground; ++yy) {
					for (int xx = MAX(0, x - 1); xx <= MIN(srcW - 1, x + 1); ++xx) {
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
				const int hy = y * scale;
				if (hx + 1 < _modernLabHDWidth && hy + 1 < _modernLabHDHeight) {
					out[(oy + 0) * outW + ox + 0] = hd[(hy + 0) * _modernLabHDWidth + hx + 0];
					out[(oy + 0) * outW + ox + 1] = hd[(hy + 0) * _modernLabHDWidth + hx + 1];
					out[(oy + 1) * outW + ox + 0] = hd[(hy + 1) * _modernLabHDWidth + hx + 0];
					out[(oy + 1) * outW + ox + 1] = hd[(hy + 1) * _modernLabHDWidth + hx + 1];
					continue;
				}
			}

			const uint32 color = palette32[front[y * pitch + x]];
			out[(oy + 0) * outW + ox + 0] = color;
			out[(oy + 0) * outW + ox + 1] = color;
			out[(oy + 1) * outW + ox + 0] = color;
			out[(oy + 1) * outW + ox + 1] = color;
		}
	}

	_system->copyRectToScreen(_modernLabHDOutput, outW * 4, 0, 0, outW, outH);
}

'''
replace_region(
    gfx_cpp,
    'void ScummEngine::modernLabDrawHDFrame(VirtScreen *vs) {\n',
    'void ScummEngine::drawStripToScreen(VirtScreen *vs, int x, int width, int top, int bottom) {\n',
    draw_impl,
    'gfx.cpp true-colour main compositor'
)

# Route all SCUMM virtual-screen blits through our palette converter while the
# current room is using a 32-bit backend. In normal rooms this block is skipped
# and stock ScummVM rendering remains untouched.
replace_once(
    gfx_cpp,
    '''void ScummEngine::drawStripToScreen(VirtScreen *vs, int x, int width, int top, int bottom) {\n\tif (_modernLabHD && vs->number == kMainVirtScreen) {\n\t\tmodernLabDrawHDFrame(vs);\n\t\treturn;\n\t}\n\n''',
    '''void ScummEngine::drawStripToScreen(VirtScreen *vs, int x, int width, int top, int bottom) {\n\tif (_modernLabHD && _modernLabHDTrueColor) {\n\t\tif (vs->number == kMainVirtScreen)\n\t\t\tmodernLabDrawHDFrame(vs);\n\t\telse\n\t\t\tmodernLabDrawTrueColorStrip(vs, x, width, top, bottom);\n\t\treturn;\n\t}\n\n''',
    'gfx.cpp true-colour blit routing'
)

print('\nCOMI Modern Lab v0.12 true-colour patch applied successfully.')
