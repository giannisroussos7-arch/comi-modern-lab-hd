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

palette_cpp = ROOT / 'engines/scumm/palette.cpp'
if not palette_cpp.exists():
    raise SystemExit(f'[error] missing {palette_cpp}; point this script at the patched ScummVM checkout')

# COMI remains an indexed-color SCUMM game internally. In v0.12 we only make
# the backend/display true-color. _currentPalette must therefore continue to
# evolve normally, but uploading that palette to a 32-bit OpenGL game surface
# is invalid (and asserts in OpenGLGraphicsManager::setPalette()).
#
# While true-color output is active:
#   * keep all normal software palette bookkeeping above this block
#   * DO NOT call the backend PaletteManager
#   * dirty the virtual screens so palette fades/cycles are re-rendered through
#     the CLUT8 -> RGBA32 converter on the next drawDirtyScreenParts().
replace_once(
    palette_cpp,
    '''\t_palDirtyMax = -1;\n\t_palDirtyMin = 256;\n\n#ifdef USE_RGB_COLOR\n''',
    '''\t_palDirtyMax = -1;\n\t_palDirtyMin = 256;\n\n\tif (_modernLabHD && _modernLabHDTrueColor) {\n\t\t// The backend surface is RGBA32 and has no hardware palette. Keep\n\t\t// _currentPalette as the authoritative SCUMM software palette and\n\t\t// redraw indexed virtual screens through the Modern Lab converter.\n\t\tfor (int i = 0; i < kNumVirtScreens; ++i) {\n\t\t\tVirtScreen &vs = _virtscr[i];\n\t\t\tif (vs.h > 0)\n\t\t\t\tvs.setDirtyRange(0, vs.h);\n\t\t}\n\t\t_fullRedraw = true;\n\t\treturn;\n\t}\n\n#ifdef USE_RGB_COLOR\n''',
    'palette.cpp software-only palette updates in RGBA32 mode'
)

print('\nCOMI Modern Lab v0.12.1 true-colour palette hotfix applied successfully.')
