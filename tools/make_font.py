#!/usr/bin/env python3
"""Render a TrueType font into a glyph atlas the board can use with numpy
only (runs on the laptop, needs Pillow).

    python3 tools/make_font.py [font.ttf] [sizes...]
    -> assets/font.npz

For each size: one alpha strip with all supported glyphs side by
side, each glyph's x offset and advance width, and the line metrics.
"""
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

DEFAULT_FONT = "/usr/share/fonts/noto/NotoSans-Bold.ttf"
DEFAULT_SIZES = [22, 36]
# ASCII + Latin-1 + Latin Extended-A (French, German, Spanish, Italian,
# Portuguese, Dutch, Polish, Czech, Turkish...) + typographic punctuation.
# Scripts that need shaping (Devanagari, Arabic) can't be drawn glyph by
# glyph; the model shows those languages romanised instead.
CHARS = "".join(chr(c) for c in list(range(32, 127)) + list(range(0xA1, 0x180))
                + [0x2013, 0x2014, 0x2018, 0x2019, 0x201C, 0x201D, 0x2026, 0x20AC])
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", "font.npz")


def build(path, size):
    font = ImageFont.truetype(path, size)
    ascent, descent = font.getmetrics()
    height = ascent + descent
    advances = [int(round(font.getlength(c))) for c in CHARS]
    strip = Image.new("L", (sum(advances) + len(CHARS), height), 0)
    draw = ImageDraw.Draw(strip)
    offsets, x = [], 0
    for c, adv in zip(CHARS, advances):
        offsets.append(x)
        draw.text((x, ascent), c, font=font, fill=255, anchor="ls")
        x += adv + 1                     # 1 px gap so glyphs never bleed
    return {
        f"s{size}_alpha": np.asarray(strip, dtype=np.uint8),
        f"s{size}_x": np.array(offsets, dtype=np.int32),
        f"s{size}_adv": np.array(advances, dtype=np.int32),
        f"s{size}_metrics": np.array([ascent, descent], dtype=np.int32),
    }


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_FONT
    sizes = [int(s) for s in sys.argv[2:]] or DEFAULT_SIZES
    data = {"chars": np.array([ord(c) for c in CHARS], dtype=np.int32),
            "sizes": np.array(sizes, dtype=np.int32)}
    for s in sizes:
        data.update(build(path, s))
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    np.savez_compressed(OUT, **data)
    print(f"{OUT}: {os.path.basename(path)} sizes {sizes}, "
          f"{os.path.getsize(OUT) // 1024} KiB")


if __name__ == "__main__":
    main()
