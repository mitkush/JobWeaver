"""Draws the extension icons (a woven mark on the JobWeaver accent) without image
libraries: python3 scripts/icons.py writes public/icons/icon-{16,48,128}.png."""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

ACCENT = (204, 15, 112)
THREAD = (255, 255, 255)
SCALE = 4  # supersampling for smooth edges


def inside_rounded(x: float, y: float, size: float, radius: float) -> bool:
    cx = min(max(x, radius), size - radius)
    cy = min(max(y, radius), size - radius)
    return (x - cx) ** 2 + (y - cy) ** 2 <= radius**2


def thread(x: float, y: float, size: float) -> bool:
    """Three warp and three weft threads, each passing over and under in turn: the lower
    thread breaks for a moment beside the upper one."""
    lanes = [size * f for f in (0.3, 0.5, 0.7)]
    half, gap = size * 0.06, size * 0.035
    margin = size * 0.19
    if not (margin <= x <= size - margin and margin <= y <= size - margin):
        return False

    def lane(v: float, reach: float) -> int | None:
        return next((i for i, c in enumerate(lanes) if abs(v - c) <= reach), None)

    on_warp, near_warp = lane(x, half), lane(x, half + gap)
    on_weft, near_weft = lane(y, half), lane(y, half + gap)
    if on_warp is not None and on_weft is not None:
        return True
    if on_weft is not None:
        # Beside a warp thread that lies on top: the weft is hidden there.
        return near_warp is None or (near_warp + on_weft) % 2 == 1
    if on_warp is not None:
        return near_weft is None or (on_warp + near_weft) % 2 == 0
    return False


def render(size: int) -> bytes:
    big = size * SCALE
    rows = []
    for py in range(size):
        row = bytearray([0])
        for px in range(size):
            acc = [0, 0, 0, 0]
            for sy in range(SCALE):
                for sx in range(SCALE):
                    x, y = px * SCALE + sx + 0.5, py * SCALE + sy + 0.5
                    if not inside_rounded(x, y, big, big * 0.22):
                        continue
                    colour = THREAD if thread(x, y, big) else ACCENT
                    for i in range(3):
                        acc[i] += colour[i]
                    acc[3] += 255
            n = SCALE * SCALE
            covered = acc[3] // 255
            pixel = [acc[i] // covered if covered else 0 for i in range(3)] + [acc[3] // n]
            row.extend(pixel)
        rows.append(bytes(row))
    raw = b"".join(rows)

    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    header = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")


if __name__ == "__main__":
    out = Path(__file__).resolve().parent.parent / "public" / "icons"
    out.mkdir(parents=True, exist_ok=True)
    for size in (16, 32, 48, 128):
        (out / f"icon-{size}.png").write_bytes(render(size))
