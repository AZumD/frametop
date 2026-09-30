#!/usr/bin/env python3
"""Generate a clearly marked equirectangular 360° test background (pure Python PNG).

Layout (yaw around +Y, SteamVR latlong skybox):
  - Top band (north pole): cyan
  - Bottom band (south pole): yellow
  - Azimuth bands: FRONT (green), RIGHT (magenta), BACK (blue), LEFT (orange)
  - Left edge = right edge (no seam color break) with white tick marks every 45°
  - Asymmetric chevron near FRONT to detect mirroring
"""
from __future__ import annotations

import argparse
import struct
import zlib
from pathlib import Path


def _png_rgb(width: int, height: int, rgb: bytes) -> bytes:
    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    raw = bytearray()
    row = width * 3
    for y in range(height):
        raw.append(0)  # filter None
        raw.extend(rgb[y * row : (y + 1) * row])
    return b"".join(
        [
            b"\x89PNG\r\n\x1a\n",
            chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)),
            chunk(b"IDAT", zlib.compress(bytes(raw), 9)),
            chunk(b"IEND", b""),
        ]
    )


def make_equirect(width: int = 2048, height: int = 1024) -> bytes:
    if width < 64 or height < 32 or width != 2 * height:
        raise ValueError("equirect must be 2:1 and reasonably large")
    pixels = bytearray(width * height * 3)
    pole_h = max(8, height // 16)

    # Azimuth band colors (R,G,B)
    bands = [
        (40, 180, 40),  # FRONT  -45..+45
        (220, 40, 220),  # RIGHT  45..135
        (40, 80, 220),  # BACK   135..225
        (240, 140, 20),  # LEFT   225..315
    ]

    for y in range(height):
        for x in range(width):
            i = (y * width + x) * 3
            if y < pole_h:
                pixels[i : i + 3] = bytes((0, 220, 220))  # N cyan
                continue
            if y >= height - pole_h:
                pixels[i : i + 3] = bytes((240, 220, 40))  # S yellow
                continue

            # Map x to degrees 0..360 where x=0 and x=width are the same longitude
            deg = (x * 360.0) / width
            # Put FRONT at center of image (x=width/2 => 0°) for easier viewing:
            # remap so image center is yaw 0.
            deg_centered = (deg + 180.0) % 360.0
            # bands relative to FRONT at 0: -45..45 etc → shift by +45 then //90
            bi = int(((deg_centered + 45.0) % 360.0) // 90.0) % 4
            r, g, b = bands[bi]

            # Latitude darkening toward poles already handled; add horizon dark line
            if abs(y - height // 2) < 2:
                r = g = b = 255

            # 45° tick marks
            if abs((deg_centered % 45.0) - 0.0) < (360.0 / width) * 2:
                r = g = b = 255

            pixels[i : i + 3] = bytes((r, g, b))

    # Asymmetric chevron near FRONT (image center): points RIGHT only → detects mirror
    cx = width // 2
    cy = height // 2
    for t in range(0, height // 8):
        # right-pointing V
        for thick in range(-2, 3):
            x1 = cx + t
            y1 = cy - t // 2 + thick
            x2 = cx + t
            y2 = cy + t // 2 + thick
            for x, y in ((x1, y1), (x2, y2)):
                if 0 <= x < width and 0 <= y < height:
                    i = (y * width + x) * 3
                    pixels[i : i + 3] = bytes((255, 255, 255))

    # Seam markers at left/right edges (should meet seamlessly)
    for y in range(pole_h, height - pole_h):
        for x in (0, 1, width - 2, width - 1):
            i = (y * width + x) * 3
            pixels[i : i + 3] = bytes((255, 0, 0))

    return _png_rgb(width, height, bytes(pixels))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("-o", "--output", type=Path, required=True)
    ap.add_argument("--width", type=int, default=2048)
    args = ap.parse_args()
    height = args.width // 2
    data = make_equirect(args.width, height)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(data)
    print(f"wrote {args.output} ({args.width}x{height})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
