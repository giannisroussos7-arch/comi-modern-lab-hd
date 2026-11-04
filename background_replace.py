#!/usr/bin/env python3
"""
COMI Modern Lab v0.8.3 - dependency-free background replacement patcher.

Replaces one SCUMM v8 room background in COMI.LA1 or COMI.LA2 from a PNG,
while preserving the room palette and rebuilding the affected bundle tables.

No third-party Python packages are required. Tested with Python 3.9+.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import struct
import zlib
import binascii
from pathlib import Path

CONTAINERS = {
    "LECF","LFLF","ROOM","PALS","WRAP","IMAG","BSTR","ZPLN","RMSC","AKOS","ANIM",
    "OBCD","IM00","IM01","IM02","IM03","IM04","IM05","IM06","IM07","IM08","IM09",
    "RMIM","OBIM","SOUN","SBL","TLKB","TALK","SONG","DIGI","RMDA","SMAP"
}
READ_RES_DIR_TAGS = {"DROO", "DRSC", "DSCR", "DSOU", "DCOS", "DCHR"}
PNG_SIG = b"\x89PNG\r\n\x1a\n"


def be32(v: int) -> bytes:
    return int(v).to_bytes(4, "big")


def le32(v: int) -> bytes:
    return int(v).to_bytes(4, "little")


def read_be32(data: bytes, off: int) -> int:
    return int.from_bytes(data[off:off+4], "big")


def read_le32(data: bytes, off: int) -> int:
    return int.from_bytes(data[off:off+4], "little")


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def chunk(tag: bytes, payload: bytes) -> bytes:
    return tag + be32(len(payload) + 8) + payload


# ------------------------- Minimal PNG I/O -------------------------

def _paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa = abs(p - a)
    pb = abs(p - b)
    pc = abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    if pb <= pc:
        return b
    return c


def read_png_rgb(path: Path) -> tuple[int, int, bytes]:
    data = path.read_bytes()
    if not data.startswith(PNG_SIG):
        raise ValueError(f"Not a PNG file: {path}")

    pos = 8
    width = height = bit_depth = color_type = interlace = None
    palette = None
    idat = bytearray()

    while pos + 12 <= len(data):
        length = int.from_bytes(data[pos:pos+4], "big")
        tag = data[pos+4:pos+8]
        payload = data[pos+8:pos+8+length]
        if pos + 12 + length > len(data):
            raise ValueError("Truncated PNG chunk")
        if tag == b"IHDR":
            if length != 13:
                raise ValueError("Invalid IHDR")
            width, height, bit_depth, color_type, comp, filt, interlace = struct.unpack(">IIBBBBB", payload)
            if comp != 0 or filt != 0:
                raise ValueError("Unsupported PNG compression/filter method")
        elif tag == b"PLTE":
            if len(payload) % 3:
                raise ValueError("Invalid PNG palette")
            palette = [tuple(payload[i:i+3]) for i in range(0, len(payload), 3)]
        elif tag == b"IDAT":
            idat.extend(payload)
        elif tag == b"IEND":
            break
        pos += 12 + length

    if None in (width, height, bit_depth, color_type, interlace):
        raise ValueError("PNG has no IHDR")
    if bit_depth != 8:
        raise ValueError(f"Only 8-bit PNGs are supported (got {bit_depth}-bit)")
    if interlace != 0:
        raise ValueError("Interlaced PNGs are not supported; save/export as non-interlaced PNG")

    channels_by_type = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}
    if color_type not in channels_by_type:
        raise ValueError(f"Unsupported PNG colour type {color_type}")
    if color_type == 3 and not palette:
        raise ValueError("Indexed PNG is missing PLTE")

    channels = channels_by_type[color_type]
    bpp = channels
    stride = width * channels
    raw = zlib.decompress(bytes(idat))
    expected = height * (stride + 1)
    if len(raw) != expected:
        raise ValueError(f"Unexpected PNG data size: {len(raw)} bytes, expected {expected}")

    rows = []
    prev = bytearray(stride)
    p = 0
    for _y in range(height):
        f = raw[p]
        p += 1
        scan = bytearray(raw[p:p+stride])
        p += stride
        if f == 1:  # Sub
            for x in range(stride):
                scan[x] = (scan[x] + (scan[x-bpp] if x >= bpp else 0)) & 0xFF
        elif f == 2:  # Up
            for x in range(stride):
                scan[x] = (scan[x] + prev[x]) & 0xFF
        elif f == 3:  # Average
            for x in range(stride):
                left = scan[x-bpp] if x >= bpp else 0
                scan[x] = (scan[x] + ((left + prev[x]) >> 1)) & 0xFF
        elif f == 4:  # Paeth
            for x in range(stride):
                left = scan[x-bpp] if x >= bpp else 0
                up = prev[x]
                ul = prev[x-bpp] if x >= bpp else 0
                scan[x] = (scan[x] + _paeth(left, up, ul)) & 0xFF
        elif f != 0:
            raise ValueError(f"Unsupported PNG filter {f}")
        rows.append(bytes(scan))
        prev = scan

    rgb = bytearray(width * height * 3)
    dst = 0
    for row in rows:
        if color_type == 2:  # RGB
            rgb[dst:dst+width*3] = row
            dst += width * 3
        elif color_type == 6:  # RGBA
            for x in range(0, len(row), 4):
                rgb[dst:dst+3] = row[x:x+3]
                dst += 3
        elif color_type == 0:  # grayscale
            for v in row:
                rgb[dst:dst+3] = bytes((v, v, v))
                dst += 3
        elif color_type == 4:  # grayscale + alpha
            for x in range(0, len(row), 2):
                v = row[x]
                rgb[dst:dst+3] = bytes((v, v, v))
                dst += 3
        elif color_type == 3:  # indexed
            for idx in row:
                if idx >= len(palette):
                    raise ValueError("PNG palette index out of range")
                rgb[dst:dst+3] = bytes(palette[idx])
                dst += 3
    return width, height, bytes(rgb)


def _png_chunk(tag: bytes, payload: bytes) -> bytes:
    return (
        len(payload).to_bytes(4, "big") + tag + payload +
        (binascii.crc32(tag + payload) & 0xFFFFFFFF).to_bytes(4, "big")
    )


def write_png_rgb(path: Path, width: int, height: int, rgb: bytes) -> None:
    if len(rgb) != width * height * 3:
        raise ValueError("RGB buffer size mismatch")
    raw = bytearray()
    stride = width * 3
    for y in range(height):
        raw.append(0)  # filter: None
        s = y * stride
        raw.extend(rgb[s:s+stride])
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    payload = zlib.compress(bytes(raw), 6)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(PNG_SIG + _png_chunk(b"IHDR", ihdr) + _png_chunk(b"IDAT", payload) + _png_chunk(b"IEND", b""))


# ------------------------- SCUMM parsing -------------------------

def parse_children(data: bytes, start: int) -> list[dict]:
    size = read_be32(data, start + 4)
    end = start + size
    pos = start + 8
    children = []
    while pos + 8 <= end:
        tagb = data[pos:pos+4]
        size = read_be32(data, pos + 4)
        if not all(32 <= c < 127 for c in tagb):
            break
        if size < 8 or pos + size > end:
            break
        children.append({"tag": tagb.decode("latin-1"), "start": pos, "size": size})
        pos += size
    return children


def walk_nodes(data: bytes, start: int, max_depth: int = 20):
    def rec(st: int, depth: int):
        tag = data[st:st+4].decode("latin-1")
        size = read_be32(data, st + 4)
        yield {"tag": tag, "start": st, "size": size, "depth": depth}
        if depth >= max_depth or tag not in CONTAINERS:
            return
        for child in parse_children(data, st):
            yield from rec(child["start"], depth + 1)
    yield from rec(start, 0)


def find_nodes(data: bytes, start: int, tag: str) -> list[int]:
    return [n["start"] for n in walk_nodes(data, start) if n["tag"] == tag]


def parse_rmhd(data: bytes, rmhd: int) -> dict:
    p = rmhd + 8
    marker = read_le32(data, p)
    if marker == 800:
        return {"version_marker": 800, "width": read_le32(data, p+4), "height": read_le32(data, p+8), "local_objects": read_le32(data, p+12)}
    if marker == 730:
        return {"version_marker": 730, "width": int.from_bytes(data[p+4:p+6], "little"), "height": int.from_bytes(data[p+6:p+8], "little"), "local_objects": int.from_bytes(data[p+8:p+10], "little")}
    return {"version_marker": None, "width": int.from_bytes(data[p:p+2], "little"), "height": int.from_bytes(data[p+2:p+4], "little"), "local_objects": int.from_bytes(data[p+4:p+6], "little")}


def parse_loff_bytes(data: bytes) -> dict[int, int]:
    if data[:4] != b"LECF":
        raise ValueError("Bundle does not begin with LECF")
    pos = 8
    if data[pos:pos+4] != b"LOFF":
        raise ValueError("Bundle has no LOFF after LECF")
    size = read_be32(data, pos + 4)
    payload = data[pos+8:pos+size]
    count = payload[0]
    out = {}
    for i in range(count):
        rid = payload[1+i*5]
        out[rid] = int.from_bytes(payload[2+i*5:6+i*5], "little")
    return out


def get_background_parts(data: bytes, lflf_start: int) -> dict | None:
    direct = parse_children(data, lflf_start)
    room = next((x for x in direct if x["tag"] == "ROOM"), None)
    if room is None:
        return None
    rmhds = find_nodes(data, room["start"], "RMHD")
    imags = find_nodes(data, room["start"], "IMAG")
    if not rmhds or not imags:
        return None
    meta = parse_rmhd(data, rmhds[0])
    width, height = meta["width"], meta["height"]
    if width <= 0 or height <= 0 or width % 8:
        return {"meta": meta, "error": "No conventional room background"}
    palettes = find_nodes(data, room["start"], "APAL") or find_nodes(data, room["start"], "CLUT") or find_nodes(data, room["start"], "NPAL")
    if not palettes:
        return {"meta": meta, "error": "No palette found"}
    imag = imags[0]
    offs_candidates = find_nodes(data, imag, "OFFS")
    target_offs = None
    expected = width // 8
    for off in offs_candidates:
        count = (read_be32(data, off+4) - 8) // 4
        if count == expected:
            target_offs = off
            break
    if target_offs is None:
        return {"meta": meta, "error": "No matching background OFFS table"}
    offs_size = read_be32(data, target_offs+4)
    offsets = [read_le32(data, target_offs+8+i*4) for i in range((offs_size-8)//4)]
    codes = [data[target_offs + rel] for rel in offsets]
    return {"meta": meta, "palette_start": palettes[0], "offs_start": target_offs, "offsets": offsets, "code_counts": dict(collections.Counter(codes))}


def find_path_to_tag(data: bytes, root: int, target_start: int):
    path = []
    def rec(st: int, cur):
        if st == target_start:
            path.extend(cur + [st])
            return True
        tag = data[st:st+4].decode("latin-1")
        if tag not in CONTAINERS:
            return False
        for ch in parse_children(data, st):
            if ch["start"] <= target_start < ch["start"] + ch["size"]:
                if rec(ch["start"], cur + [st]):
                    return True
        return False
    if not rec(root, []):
        raise ValueError("Could not resolve chunk ancestor path")
    return path


def locate_background_details(bundle: bytes, room_start: int, parts: dict):
    target_offs = parts["offs_start"]
    containing_bstr = None
    for n in walk_nodes(bundle, room_start):
        if n["tag"] == "BSTR" and n["start"] < target_offs < n["start"] + n["size"]:
            containing_bstr = n
            break
    if not containing_bstr:
        raise ValueError("Could not locate background BSTR")
    out = dict(parts)
    out["bstr_start"] = containing_bstr["start"]
    return out


# ------------------------- Image quantization / encoding -------------------------

def quantize_rgb_to_palette(rgb: bytes, palraw: bytes, size: tuple[int, int], actual_size: tuple[int, int]) -> bytearray:
    if actual_size != size:
        raise ValueError(f"Replacement image must be exactly {size[0]}x{size[1]}, got {actual_size[0]}x{actual_size[1]}")
    palette = [tuple(palraw[i:i+3]) for i in range(0, 768, 3)]
    exact = {}
    for i, c in enumerate(palette):
        exact.setdefault(c, i)
    cache = dict(exact)
    out = bytearray(len(rgb) // 3)
    o = 0
    for p in range(0, len(rgb), 3):
        c = (rgb[p], rgb[p+1], rgb[p+2])
        idx = cache.get(c)
        if idx is None:
            r, g, b = c
            best_i = 0
            best_d = 1 << 62
            for i, (pr, pg, pb) in enumerate(palette):
                dr, dg, db = r-pr, g-pg, b-pb
                d = dr*dr + dg*dg + db*db
                if d < best_d:
                    best_d = d
                    best_i = i
                    if d == 0:
                        break
            cache[c] = best_i
            idx = best_i
        out[o] = idx
        o += 1
    return out


def build_raw_bstr(indexed: bytearray, width: int, height: int) -> tuple[bytes, list[int]]:
    if width % 8:
        raise ValueError("Background width is not divisible by 8")
    if len(indexed) != width * height:
        raise ValueError("Indexed image buffer size mismatch")
    strips = []
    for x in range(0, width, 8):
        # SCUMM BMCOMP_RAW256 is scanline-major inside each 8-pixel strip:
        # row 0: pixels x..x+7, row 1: pixels x..x+7, etc.
        # Gdi::drawStripRaw() memcpy()s 8 bytes per destination scanline.
        raw = bytearray(8 * height)
        q = 0
        for y in range(height):
            row = y * width + x
            raw[q:q+8] = indexed[row:row+8]
            q += 8
        strips.append(b"\x01" + bytes(raw))
    offs_size = 8 + 4 * len(strips)
    offsets = []
    cursor = offs_size
    for s in strips:
        offsets.append(cursor)
        cursor += len(s)
    offs = chunk(b"OFFS", b"".join(le32(x) for x in offsets))
    wrap = chunk(b"WRAP", offs + b"".join(strips))
    return chunk(b"BSTR", wrap), offsets


def decode_raw_background(data: bytes, parts: dict) -> bytearray:
    width = parts["meta"]["width"]
    height = parts["meta"]["height"]
    canvas = bytearray(width * height)
    offst = parts["offs_start"]
    offsets = parts["offsets"]
    for i, rel in enumerate(offsets):
        p = offst + rel
        if data[p] != 1:
            raise ValueError(f"Validation expected raw codec 1, got codec {data[p]} at strip {i}")
        p += 1
        need = 8 * height
        if p + need > len(data):
            raise EOFError("Raw strip too short")
        q = p
        x0 = i * 8
        # Mirror ScummVM Gdi::drawStripRaw(): 8 contiguous pixels per scanline.
        for y in range(height):
            dst = y * width + x0
            canvas[dst:dst+8] = data[q:q+8]
            q += 8
    return canvas


def indexed_to_rgb(indexed: bytearray, palraw: bytes) -> bytes:
    out = bytearray(len(indexed) * 3)
    d = 0
    for idx in indexed:
        s = idx * 3
        out[d:d+3] = palraw[s:s+3]
        d += 3
    return bytes(out)


# ------------------------- Archive patching -------------------------

def patch_la0(la0: bytes, room_id: int, splice_rel: int, delta: int):
    data = bytearray(la0)
    pos = 0
    changed = []
    while pos + 8 <= len(data):
        tag = bytes(data[pos:pos+4]).decode("latin-1")
        size = int.from_bytes(data[pos+4:pos+8], "big")
        if size < 8 or pos + size > len(data):
            raise ValueError(f"Invalid LA0 chunk {tag} at {pos}")
        if tag in READ_RES_DIR_TAGS:
            p = pos + 8
            n = int.from_bytes(data[p:p+4], "little")
            p += 4
            roomnos_pos = p
            offs_pos = p + n
            expected = 8 + 4 + n + 4*n
            if expected != size:
                raise ValueError(f"Unexpected {tag} directory size: {size}, expected {expected}")
            for i in range(n):
                rn = data[roomnos_pos+i]
                old = int.from_bytes(data[offs_pos+i*4:offs_pos+i*4+4], "little")
                if rn == room_id and old > splice_rel and old != 0xFFFFFFFF:
                    new = old + delta
                    data[offs_pos+i*4:offs_pos+i*4+4] = le32(new)
                    changed.append({"directory": tag, "index": i, "before": old, "after": new})
        pos += size
    return bytes(data), changed


def patch_bundle(bundle: bytes, room_id: int, room_start: int, parts: dict, new_bstr: bytes):
    old_bstr_start = parts["bstr_start"]
    old_bstr_size = int.from_bytes(bundle[old_bstr_start+4:old_bstr_start+8], "big")
    old_bstr_end = old_bstr_start + old_bstr_size
    old = bundle[old_bstr_start:old_bstr_end]
    delta = len(new_bstr) - len(old)
    path = find_path_to_tag(bundle, room_start, old_bstr_start)
    ancestors = path[:-1]
    out = bytearray(bundle[:old_bstr_start] + new_bstr + bundle[old_bstr_end:])
    for st in ancestors:
        oldsz = int.from_bytes(bundle[st+4:st+8], "big")
        out[st+4:st+8] = be32(oldsz + delta)
    if bundle[:4] != b"LECF":
        raise ValueError("Expected LECF bundle")
    out[4:8] = be32(int.from_bytes(bundle[4:8], "big") + delta)
    loff = 8
    if bundle[loff:loff+4] != b"LOFF":
        raise ValueError("Expected LOFF at offset 8")
    payload = loff + 8
    count = out[payload]
    for i in range(count):
        rid_pos = payload + 1 + i*5
        off_pos = rid_pos + 1
        old_off = int.from_bytes(bundle[off_pos:off_pos+4], "little")
        if old_off > room_start:
            out[off_pos:off_pos+4] = le32(old_off + delta)
    return bytes(out), delta, old_bstr_size


def validate(original_bundle: bytes, patched_bundle: bytes, room_id: int, source_room_offsets: dict[int,int], target_indexed: bytearray, out_png: Path):
    new_offsets = parse_loff_bytes(patched_bundle)
    if room_id not in new_offsets:
        raise ValueError("Patched room missing from LOFF")
    new_parts = get_background_parts(patched_bundle, new_offsets[room_id])
    if not new_parts or "error" in new_parts:
        raise ValueError(f"Patched background cannot be parsed: {new_parts}")
    canvas = decode_raw_background(patched_bundle, new_parts)
    if canvas != target_indexed:
        mismatch = sum(1 for a, b in zip(canvas, target_indexed) if a != b)
        raise ValueError(f"Round-trip pixel mismatch: {mismatch} pixels")

    ps = new_parts["palette_start"] + 8
    palraw = patched_bundle[ps:ps+768]
    write_png_rgb(out_png, new_parts["meta"]["width"], new_parts["meta"]["height"], indexed_to_rgb(canvas, palraw))

    for rid, old_start in source_room_offsets.items():
        if rid == room_id or rid not in new_offsets:
            continue
        old_size = int.from_bytes(original_bundle[old_start+4:old_start+8], "big")
        ns = new_offsets[rid]
        new_size = int.from_bytes(patched_bundle[ns+4:ns+8], "big")
        if old_size != new_size:
            raise ValueError(f"Room {rid} size changed unexpectedly")
        if original_bundle[old_start:old_start+old_size] != patched_bundle[ns:ns+new_size]:
            raise ValueError(f"Room {rid} data changed unexpectedly")
    return new_offsets


def main():
    ap = argparse.ArgumentParser(description="Replace a COMI room background in a copied LA1/LA2 bundle (stdlib-only).")
    ap.add_argument("--la0", type=Path, required=True)
    ap.add_argument("--bundle", type=Path, required=True, help="COMI.LA1 or COMI.LA2")
    ap.add_argument("--room", type=int, required=True)
    ap.add_argument("--image", type=Path, required=True)
    ap.add_argument("--out-la0", type=Path, required=True)
    ap.add_argument("--out-bundle", type=Path, required=True)
    ap.add_argument("--manifest", type=Path)
    ap.add_argument("--proof-png", type=Path)
    args = ap.parse_args()

    if args.out_la0.resolve() == args.la0.resolve() or args.out_bundle.resolve() == args.bundle.resolve():
        raise SystemExit("Refusing in-place modification. Choose new output file names.")
    if not args.image.exists():
        raise SystemExit(f"Replacement image not found: {args.image}")

    original_la0 = args.la0.read_bytes()
    original_bundle = args.bundle.read_bytes()
    room_offsets = parse_loff_bytes(original_bundle)
    if args.room not in room_offsets:
        raise SystemExit(f"Room {args.room} is not present in {args.bundle.name}")

    room_start = room_offsets[args.room]
    parts = get_background_parts(original_bundle, room_start)
    if not parts or "error" in parts:
        raise SystemExit(f"Room has no replaceable background: {parts}")
    parts = locate_background_details(original_bundle, room_start, parts)

    w, h = parts["meta"]["width"], parts["meta"]["height"]
    ps = parts["palette_start"] + 8
    palraw = original_bundle[ps:ps+768]
    if len(palraw) != 768:
        raise SystemExit("Room palette is incomplete")

    iw, ih, rgb = read_png_rgb(args.image)
    print(f"Replacement PNG: {iw}x{ih}")
    print("Quantizing to the room's original 256-colour palette...")
    indexed = quantize_rgb_to_palette(rgb, palraw, (w, h), (iw, ih))
    new_bstr, _strip_offsets = build_raw_bstr(indexed, w, h)

    patched_bundle, delta, old_bstr_size = patch_bundle(original_bundle, args.room, room_start, parts, new_bstr)
    splice_rel = parts["bstr_start"] - room_start
    patched_la0, la0_changes = patch_la0(original_la0, args.room, splice_rel, delta)

    proof = args.proof_png or args.out_bundle.with_suffix(".background-proof.png")
    print("Validating rebuilt archive and round-trip pixels...")
    validate(original_bundle, patched_bundle, args.room, room_offsets, indexed, proof)

    # Only publish final archive files after all validation has passed.
    args.out_bundle.parent.mkdir(parents=True, exist_ok=True)
    args.out_la0.parent.mkdir(parents=True, exist_ok=True)
    args.out_bundle.write_bytes(patched_bundle)
    args.out_la0.write_bytes(patched_la0)

    manifest = {
        "format": "COMI Modern Lab Background Patch v1.2",
        "patcher": "stdlib-only (no NumPy/Pillow required)",
        "room_id": args.room,
        "bundle": args.bundle.name,
        "native_size": [w, h],
        "raw_strip_codec": 1,
        "strip_count": w // 8,
        "old_bstr_size": old_bstr_size,
        "new_bstr_size": len(new_bstr),
        "bundle_size_delta": delta,
        "la0_resource_offsets_updated": len(la0_changes),
        "source_la0_sha256": sha256_bytes(original_la0),
        "patched_la0_sha256": sha256_bytes(patched_la0),
        "source_bundle_sha256": sha256_bytes(original_bundle),
        "patched_bundle_sha256": sha256_bytes(patched_bundle),
        "replacement_image": args.image.name,
        "proof_image": proof.name,
        "la0_changes": la0_changes,
    }
    mp = args.manifest or args.out_bundle.with_suffix(args.out_bundle.suffix + ".patch.json")
    mp.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in manifest.items() if k != "la0_changes"}, indent=2))
    print("\nSUCCESS: patched files validated and written.")


if __name__ == "__main__":
    main()
