"""Draw the Peek app icons ("Screen eye": an eye inside a monitor) with only the standard library.

The same mark lives as SVG in static/icons/peek.svg; this rasterises it to PNG for the
phone home screen (iOS needs PNG). Glyph coordinates match that SVG's 0-100 viewBox.
"""

import math
import struct
import zlib

from . import config

ICON_VERSION = "peek-3"            # bump to redraw icons after a design change
GROUND = (11, 17, 32)              # #0B1120
ACCENT = (52, 211, 153)            # #34D399
GLYPH_SCALE = 0.66                 # glyph fills ~2/3 of the tile: safe for Android's round mask


def _seg_dist(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def _on_glyph(x, y):
    """x, y in the SVG's 0-100 space. True where the mark is drawn."""
    # Monitor: rounded rect 12..88 x 18..72, radius 10, stroke 6
    qx = abs(x - 50) - (38 - 10)
    qy = abs(y - 45) - (27 - 10)
    d = math.hypot(max(qx, 0), max(qy, 0)) + min(max(qx, qy), 0) - 10
    if abs(d) <= 3:
        return True
    # Stand: line 38..62 at y=86, stroke 6, round caps
    if _seg_dist(x, y, 38, 86, 62, 86) <= 3:
        return True
    # Pupil
    if math.hypot(x - 50, y - 45) <= 7:
        return True
    # Eye outline: two quadratic arcs 27,45 -> 73,45 (half-height 19*s*(1-s)... as y = 45 -+ 38t(1-t)),
    # stroke 5. Perpendicular distance ~ vertical gap / sqrt(1 + slope^2).
    if 27 <= x <= 73:
        t = (x - 27) / 46
        h = 38 * t * (1 - t)
        slope = 38 * (1 - 2 * t) / 46
        if abs(abs(y - 45) - h) / math.sqrt(1 + slope * slope) <= 2.5:
            return True
    return math.hypot(x - 27, y - 45) <= 2.5 or math.hypot(x - 73, y - 45) <= 2.5


def _png(size):
    rows = []
    ss = 3
    for py in range(size):
        row = bytearray([0])
        for px in range(size):
            hits = 0
            for sy in range(ss):
                for sx in range(ss):
                    u = (px + (sx + 0.5) / ss) / size
                    v = (py + (sy + 0.5) / ss) / size
                    gx = (u - 0.5) / GLYPH_SCALE * 100 + 50
                    gy = (v - 0.5) / GLYPH_SCALE * 100 + 50 + 2   # nudge: optical centre
                    hits += _on_glyph(gx, gy)
            a = hits / (ss * ss)
            row += bytes(round(GROUND[i] * (1 - a) + ACCENT[i] * a) for i in range(3))
        rows.append(bytes(row))

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"".join(rows), 9)) + chunk(b"IEND", b""))


def ensure_icons():
    folder = config.STATIC_DIR / "icons"
    folder.mkdir(parents=True, exist_ok=True)
    stamp = folder / ".version"
    fresh = not stamp.exists() or stamp.read_text().strip() != ICON_VERSION
    for size in (32, 180, 192, 512):
        path = folder / f"icon-{size}.png"
        if fresh or not path.exists():
            path.write_bytes(_png(size))
    stamp.write_text(ICON_VERSION)
