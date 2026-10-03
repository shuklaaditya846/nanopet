"""Text from the pre-rendered glyph atlas (assets/font.npz, built on the
laptop by tools/make_font.py). Needs only numpy."""
import os

import numpy as np

from gfx import rgb

ATLAS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "font.npz")


class Font:
    def __init__(self, path=ATLAS):
        d = np.load(path)
        chars = d["chars"]
        if chars.dtype == np.uint8:                  # older atlas: ASCII bytes
            text = bytes(chars).decode()
        else:
            text = "".join(chr(int(c)) for c in chars)
        self.chars = {c: i for i, c in enumerate(text)}
        self.sizes = {}
        for s in d["sizes"]:
            s = int(s)
            ascent, descent = (int(v) for v in d[f"s{s}_metrics"])
            self.sizes[s] = {
                "alpha": d[f"s{s}_alpha"].astype(np.float32) / 255.0,
                "x": d[f"s{s}_x"], "adv": d[f"s{s}_adv"],
                "ascent": ascent, "height": ascent + descent,
            }

    def nearest(self, size):
        return min(self.sizes, key=lambda s: abs(s - size))

    def supports(self, text):
        return all(c in self.chars or c.isspace() for c in text)

    def _index(self, ch):
        return self.chars.get(ch, self.chars["?"])

    def width(self, text, size):
        f = self.sizes[self.nearest(size)]
        return int(sum(f["adv"][self._index(c)] for c in text))

    def height(self, size):
        return self.sizes[self.nearest(size)]["height"]

    def draw(self, canvas, x, y, text, size, color, alpha=1.0):
        """Draw text with its top-left corner at (x, y)."""
        f = self.sizes[self.nearest(size)]
        col = rgb(color)
        x = int(round(x))
        y = int(round(y))
        h = f["height"]
        for ch in text:
            i = self._index(ch)
            adv = int(f["adv"][i])
            gx = int(f["x"][i])
            x0, x1 = max(x, 0), min(x + adv, canvas.w)
            y0, y1 = max(y, 0), min(y + h, canvas.h)
            if x0 < x1 and y0 < y1:
                a = f["alpha"][y0 - y:y1 - y, gx + (x0 - x):gx + (x1 - x)] * alpha
                region = canvas.px[y0:y1, x0:x1]
                region += (col - region) * a[..., None]
            x += adv

    def wrap(self, text, size, max_width):
        """Greedy word wrap to pixel width; returns a list of lines."""
        lines, cur = [], ""
        for word in text.split():
            trial = f"{cur} {word}".strip()
            if self.width(trial, size) <= max_width or not cur:
                cur = trial
            else:
                lines.append(cur)
                cur = word
        if cur:
            lines.append(cur)
        return lines
