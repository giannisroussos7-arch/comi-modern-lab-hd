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
input_cpp = ROOT / 'engines/scumm/input.cpp'
for p in (scumm_h, scumm_cpp, gfx_cpp, input_cpp):
    if not p.exists():
        raise SystemExit(f'[error] missing {p}; point this script at a ScummVM source checkout')

replace_once(
    scumm_h,
    '\tbool _needsSoundUnpause = false;\n',
    '''\tbool _needsSoundUnpause = false;\n\n\t// COMI Modern Lab HD sidecar renderer. SCUMM logic stays native-res;\n\t// only final presentation is doubled and an optional 2x background is composited.\n\tbool _modernLabHD = false;\n\tbool _modernLabHDUseBackground = true;\n\tint _modernLabHDRoom = -1;\n\tint _modernLabHDWidth = 0;\n\tint _modernLabHDHeight = 0;\n\tbyte *_modernLabHDPixels = nullptr;\n\tbyte *_modernLabHDOutput = nullptr;\n\n\tbool modernLabLoadHDRoom();\n\tvoid modernLabDrawHDFrame(VirtScreen *vs);\n''',
    'scumm.h HD state'
)

replace_once(
    scumm_cpp,
    '\tdelete _musicEngine;\n',
    '''\tfree(_modernLabHDPixels);\n\tfree(_modernLabHDOutput);\n\t_modernLabHDPixels = nullptr;\n\t_modernLabHDOutput = nullptr;\n\n\tdelete _musicEngine;\n''',
    'scumm.cpp HD cleanup'
)

replace_once(
    scumm_cpp,
    '''\t// Initialize backend\n\tif (_renderMode == Common::kRenderHercA || _renderMode == Common::kRenderHercG) {\n\t\tinitGraphics(kHercWidth, kHercHeight);\n''',
    '''\t// Initialize backend\n\t_modernLabHD = (_game.id == GID_CMI && Common::File::exists(Common::Path("modernlab_hd/enabled.flag")));\n\tif (_modernLabHD) {\n\t\tinitGraphics(_screenWidth * 2, _screenHeight * 2);\n\t\twarning("COMI Modern Lab HD compositor enabled (F10 toggles remastered background)");\n\t} else if (_renderMode == Common::kRenderHercA || _renderMode == Common::kRenderHercG) {\n\t\tinitGraphics(kHercWidth, kHercHeight);\n''',
    'scumm.cpp 2x output init'
)

replace_once(
    input_cpp,
    '''\t\t} else if (event.kbd.hasFlags(Common::KBD_CTRL) && event.kbd.keycode == Common::KEYCODE_g) {\n\t\t\t_fastMode ^= 2;\n''',
    '''\t\t} else if (event.kbd.hasFlags(Common::KBD_CTRL) && event.kbd.keycode == Common::KEYCODE_g) {\n\t\t\t_fastMode ^= 2;\n\t\t} else if (_modernLabHD && event.kbd.keycode == Common::KEYCODE_F10) {\n\t\t\t_modernLabHDUseBackground = !_modernLabHDUseBackground;\n\t\t\t_modernLabHDRoom = -1;\n\t\t\tfree(_modernLabHDPixels);\n\t\t\t_modernLabHDPixels = nullptr;\n\t\t\t_fullRedraw = true;\n\t\t\twarning("COMI Modern Lab HD background: %s", _modernLabHDUseBackground ? "ON" : "OFF");\n''',
    'input.cpp F10 toggle'
)

replace_once(
    input_cpp,
    '''\t\t_mouse.x = event.mouse.x;\n\t\t_mouse.y = event.mouse.y;\n\n\t\tif (_renderMode == Common::kRenderHercA || _renderMode == Common::kRenderHercG) {\n''',
    '''\t\t_mouse.x = event.mouse.x;\n\t\t_mouse.y = event.mouse.y;\n\n\t\tif (_modernLabHD) {\n\t\t\t_mouse.x >>= 1;\n\t\t\t_mouse.y >>= 1;\n\t\t} else if (_renderMode == Common::kRenderHercA || _renderMode == Common::kRenderHercG) {\n''',
    'input.cpp 2x mouse mapping'
)

helper_anchor = 'void ScummEngine::drawStripToScreen(VirtScreen *vs, int x, int width, int top, int bottom) {\n'
helper = r'''bool ScummEngine::modernLabLoadHDRoom() {
	if (!_modernLabHD || !_modernLabHDUseBackground)
		return false;
	if (_modernLabHDRoom == _currentRoom && _modernLabHDPixels)
		return true;

	free(_modernLabHDPixels);
	_modernLabHDPixels = nullptr;
	_modernLabHDWidth = _modernLabHDHeight = 0;
	_modernLabHDRoom = _currentRoom;

	Common::String name = Common::String::format("modernlab_hd/room_%02d.mlhd", _currentRoom);
	Common::File f;
	if (!f.open(Common::Path(name)))
		return false;

	char magic[4];
	if (f.read(magic, 4) != 4 || memcmp(magic, "MLHD", 4) != 0)
		return false;
	const uint16 version = f.readUint16LE();
	const uint16 room = f.readUint16LE();
	const uint32 width = f.readUint32LE();
	const uint32 height = f.readUint32LE();
	if (version != 1 || room != (uint16)_currentRoom || !width || !height || width > 16384 || height > 4096)
		return false;

	const uint64 bytes64 = (uint64)width * (uint64)height;
	if (bytes64 > 64 * 1024 * 1024)
		return false;
	const uint32 bytes = (uint32)bytes64;
	_modernLabHDPixels = (byte *)malloc(bytes);
	if (!_modernLabHDPixels)
		return false;
	if (f.read(_modernLabHDPixels, bytes) != bytes) {
		free(_modernLabHDPixels);
		_modernLabHDPixels = nullptr;
		return false;
	}
	_modernLabHDWidth = (int)width;
	_modernLabHDHeight = (int)height;
	debug(1, "ModernLab HD: loaded room %d sidecar %dx%d", _currentRoom, _modernLabHDWidth, _modernLabHDHeight);
	return true;
}

void ScummEngine::modernLabDrawHDFrame(VirtScreen *vs) {
	const int scale = 2;
	const int srcW = vs->w;
	const int srcH = vs->h;
	const int outW = srcW * scale;
	const int outH = srcH * scale;
	const uint32 outBytes = (uint32)(outW * outH);

	if (!_modernLabHDOutput)
		_modernLabHDOutput = (byte *)malloc(outBytes);
	if (!_modernLabHDOutput)
		return;

	const byte *front = (const byte *)vs->getPixels(0, 0);
	const byte *back = (vs->hasTwoBuffers && vs->backBuf) ? (const byte *)vs->getBackPixels(0, 0) : nullptr;
	const int pitch = vs->pitch;
	const bool haveHD = modernLabLoadHDRoom();

	for (int y = 0; y < srcH; ++y) {
		for (int x = 0; x < srcW; ++x) {
			bool foreground = !haveHD || !back;
			if (!foreground) {
				for (int yy = MAX(0, y - 1); yy <= MIN(srcH - 1, y + 1) && !foreground; ++yy) {
					for (int xx = MAX(0, x - 1); xx <= MIN(srcW - 1, x + 1); ++xx) {
						if (front[yy * pitch + xx] != back[yy * pitch + xx]) {
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
					_modernLabHDOutput[(oy + 0) * outW + ox + 0] = _modernLabHDPixels[(hy + 0) * _modernLabHDWidth + hx + 0];
					_modernLabHDOutput[(oy + 0) * outW + ox + 1] = _modernLabHDPixels[(hy + 0) * _modernLabHDWidth + hx + 1];
					_modernLabHDOutput[(oy + 1) * outW + ox + 0] = _modernLabHDPixels[(hy + 1) * _modernLabHDWidth + hx + 0];
					_modernLabHDOutput[(oy + 1) * outW + ox + 1] = _modernLabHDPixels[(hy + 1) * _modernLabHDWidth + hx + 1];
					continue;
				}
			}

			const byte c = front[y * pitch + x];
			_modernLabHDOutput[(oy + 0) * outW + ox + 0] = c;
			_modernLabHDOutput[(oy + 0) * outW + ox + 1] = c;
			_modernLabHDOutput[(oy + 1) * outW + ox + 0] = c;
			_modernLabHDOutput[(oy + 1) * outW + ox + 1] = c;
		}
	}
	_system->copyRectToScreen(_modernLabHDOutput, outW, 0, 0, outW, outH);
}

'''
text = gfx_cpp.read_text(encoding='utf-8')
if 'bool ScummEngine::modernLabLoadHDRoom()' not in text:
    if helper_anchor not in text:
        raise SystemExit('[error] gfx.cpp helper anchor not found')
    gfx_cpp.write_text(text.replace(helper_anchor, helper + helper_anchor, 1), encoding='utf-8')
    print('[ok] gfx.cpp compositor helper')
else:
    print('[ok] gfx.cpp compositor helper: already applied')

replace_once(
    gfx_cpp,
    helper_anchor,
    helper_anchor + '''\tif (_modernLabHD && vs->number == kMainVirtScreen) {\n\t\tmodernLabDrawHDFrame(vs);\n\t\treturn;\n\t}\n\n''',
    'gfx.cpp HD blit route'
)

print('\nModern Lab HD patch applied successfully.')
