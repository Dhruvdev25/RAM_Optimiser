"""Generate a small branded Windows ICO using only the Python standard library."""
from __future__ import annotations

import math
import struct
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SIZE = 256


def segment_distance(px, py, a, b):
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - ax - t * dx, py - ay - t * dy)


def chunk(kind, data):
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)


def make_png():
    points = [(42, 150), (67, 150), (84, 108), (112, 186), (137, 127), (155, 158), (214, 158)]
    rows = []
    for y in range(SIZE):
        row = bytearray([0])
        for x in range(SIZE):
            # Rounded square, dark diagonal navy fill, and a fine blue outline.
            dx = max(0, 8 - x, x - 247)
            dy = max(0, 8 - y, y - 247)
            outside = math.hypot(dx, dy) > 58 if dx and dy else (dx > 0 and dy > 58 or dy > 0 and dx > 58)
            if outside:
                rgba = (0, 0, 0, 0)
            else:
                mix = (x + y) / (2 * SIZE)
                r, g, b = int(18 - 8 * mix), int(40 - 22 * mix), int(58 - 28 * mix)
                edge = x < 11 or x > 244 or y < 11 or y > 244
                if edge:
                    r, g, b = 40, 91, 120
                distance = min(segment_distance(x, y, points[i], points[i + 1]) for i in range(len(points) - 1))
                if distance < 15:
                    glow = max(0.0, (15 - distance) / 15) * 0.18
                    r = int(r * (1 - glow) + 45 * glow)
                    g = int(g * (1 - glow) + 185 * glow)
                    b = int(b * (1 - glow) + 245 * glow)
                if distance < 6.5:
                    tint = min(1.0, max(0.0, (x - 42) / 172))
                    r, g, b = int(78 - 9 * tint), int(225 - 50 * tint), int(210 + 40 * tint)
                if math.hypot(x - 213, y - 158) < 8:
                    r, g, b = 91, 225, 210
                rgba = (r, g, b, 255)
            row.extend(rgba)
        rows.append(bytes(row))
    raw = b"".join(rows)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", SIZE, SIZE, 8, 6, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")


def main():
    image = make_png()
    # Vista+ ICO directory entry containing a PNG-compressed 32-bit image.
    header = struct.pack("<HHH", 0, 1, 1)
    entry = struct.pack("<BBBBHHII", 0, 0, 0, 0, 1, 32, len(image), 22)
    destination = ROOT / "assets" / "ram_optimiser.ico"
    destination.write_bytes(header + entry + image)
    print(f"Generated {destination}")


if __name__ == "__main__":
    main()
