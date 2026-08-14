"""يولّد أيقونات التطبيق (PNG) بدون أي مكتبات خارجية.

    python make_icons.py

ينتج icons/icon-180.png (أيقونة شاشة الآيفون) و icons/icon-512.png.
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

ICONS = Path(__file__).resolve().parent / "icons"

BG_TOP = (17, 25, 51)
BG_BOTTOM = (10, 16, 32)
BLUE = (75, 139, 190)
YELLOW = (255, 212, 59)


def rounded(x: float, y: float, left: float, top: float, size: float, radius: float) -> bool:
    """هل النقطة داخل مربّع بزوايا دائرية؟"""
    right, bottom = left + size, top + size
    if not (left <= x < right and top <= y < bottom):
        return False
    cx = min(max(x, left + radius), right - radius)
    cy = min(max(y, top + radius), bottom - radius)
    return (x - cx) ** 2 + (y - cy) ** 2 <= radius ** 2


def blend(base: tuple[int, int, int], over: tuple[int, int, int], a: float) -> tuple[int, int, int]:
    return tuple(round(b + (o - b) * a) for b, o in zip(base, over))


def render(size: int) -> bytes:
    s = float(size)
    box = s * 0.42          # ضلع المربّعين
    rad = box * 0.30
    a_left, a_top = s * 0.15, s * 0.15
    b_left, b_top = s * 0.43, s * 0.43

    rows = bytearray()
    for py in range(size):
        rows.append(0)                                  # filter type = None
        t = py / s
        base = blend(BG_TOP, BG_BOTTOM, t)
        for px in range(size):
            x, y = px + 0.5, py + 0.5
            color = base
            if rounded(x, y, b_left, b_top, box, rad):
                color = YELLOW
            if rounded(x, y, a_left, a_top, box, rad):
                # تراكب المربّع الأزرق فوق الأصفر بحافة ناعمة
                color = BLUE if color is base else blend(YELLOW, BLUE, 0.85)
            rows.extend(color)
    return bytes(rows)


def write_png(path: Path, size: int) -> None:
    def chunk(tag: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    ihdr = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)   # 8-bit truecolor
    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", ihdr)
           + chunk(b"IDAT", zlib.compress(render(size), 9))
           + chunk(b"IEND", b""))
    path.write_bytes(png)
    print(f"  {path.name}  ({len(png) // 1024} KB)")


if __name__ == "__main__":
    ICONS.mkdir(exist_ok=True)
    for n in (180, 512):
        write_png(ICONS / f"icon-{n}.png", n)
    print("تم إنشاء الأيقونات.")
