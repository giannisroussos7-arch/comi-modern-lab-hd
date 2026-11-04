#!/usr/bin/env python3
"""Build a Modern Lab .mlhd 2x indexed background sidecar from a PNG.

No third-party Python packages are required. The replacement PNG is quantized to
the room's original 256-colour palette so the first HD compositor can remain
CLUT8 while breaking the native spatial-resolution limit.
"""
from pathlib import Path
import argparse, struct, hashlib
import background_replace as bg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--bundle', required=True, help='Original COMI.LA1 or COMI.LA2')
    ap.add_argument('--room', required=True, type=int, help='Numeric SCUMM room id')
    ap.add_argument('--image', required=True, help='2x RGB PNG')
    ap.add_argument('--out', required=True, help='Output room_XX.mlhd')
    args = ap.parse_args()

    bundle = Path(args.bundle).read_bytes()
    loff = bg.parse_loff_bytes(bundle)
    if args.room not in loff:
        raise SystemExit(f'Room {args.room} not found in {args.bundle}')
    parts = bg.get_background_parts(bundle, loff[args.room])
    if not parts or parts.get('error'):
        raise SystemExit(f'Room {args.room} has no conventional background: {parts}')

    native_w = parts['meta']['width']
    native_h = parts['meta']['height']
    target = (native_w * 2, native_h * 2)
    pal_start = parts['palette_start'] + 8
    palraw = bundle[pal_start:pal_start+768]
    if len(palraw) != 768:
        raise SystemExit('Could not read 256-colour room palette')

    iw, ih, rgb = bg.read_png_rgb(Path(args.image))
    if (iw, ih) != target:
        raise SystemExit(f'Expected {target[0]}x{target[1]} image, got {iw}x{ih}')
    indexed = bg.quantize_rgb_to_palette(rgb, palraw, target, (iw, ih))

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = b'MLHD' + struct.pack('<HHII', 1, args.room, iw, ih) + indexed
    out.write_bytes(payload)
    print(f'Wrote {out} ({iw}x{ih}, {len(payload):,} bytes)')
    print('SHA256', hashlib.sha256(payload).hexdigest())

if __name__ == '__main__':
    main()
