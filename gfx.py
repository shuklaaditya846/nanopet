"""Tiny anti-aliased 2D drawing on a numpy RGB canvas. No Pillow needed.

Every shape is a signed-distance function evaluated only inside its
bounding box; coverage = clip(0.5 - distance, 0, 1) gives a 1-pixel soft
edge, then it is alpha-blended in. Fast enough for a 320x240 face on a
Cortex-A7 because each shape only touches its own few thousand pixels.
"""
import numpy as np


def rgb(hexstr):
    h = hexstr.lstrip("#")
    return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)], dtype=np.float32)


class Canvas:
    def __init__(self, width, height, bg="#000000"):
        self.w, self.h = width, height
        self.px = np.zeros((height, width, 3), dtype=np.float32)
        self.bg = rgb(bg)
        self.clear()

    def clear(self, color=None):
        self.px[:] = self.bg if color is None else rgb(color)

    # --- core: blend a coverage mask over a box ---------------------------
    def _box(self, x0, y0, x1, y1):
        x0 = max(0, int(np.floor(x0)) - 1)
        y0 = max(0, int(np.floor(y0)) - 1)
        x1 = min(self.w, int(np.ceil(x1)) + 2)
        y1 = min(self.h, int(np.ceil(y1)) + 2)
        if x0 >= x1 or y0 >= y1:
            return None
        ys = np.arange(y0, y1, dtype=np.float32)[:, None] + 0.5
        xs = np.arange(x0, x1, dtype=np.float32)[None, :] + 0.5
        return (slice(y0, y1), slice(x0, x1), xs, ys)

    def _blend(self, box, dist, color, alpha=1.0):
        sy, sx = box[0], box[1]
        cov = np.clip(0.5 - dist, 0.0, 1.0) * alpha
        if not cov.any():
            return
        region = self.px[sy, sx]
        region += (rgb(color) - region) * cov[..., None]

    # --- shapes ---------------------------------------------------------
    def ellipse(self, cx, cy, rx, ry, color, alpha=1.0):
        if rx <= 0.3 or ry <= 0.3:
            return
        box = self._box(cx - rx, cy - ry, cx + rx, cy + ry)
        if box is None:
            return
        _, _, xs, ys = box
        nx, ny = (xs - cx) / rx, (ys - cy) / ry
        dist = (np.sqrt(nx * nx + ny * ny) - 1.0) * min(rx, ry)
        self._blend(box, dist, color, alpha)

    def rounded_rect(self, cx, cy, w, h, r, color, alpha=1.0, clip=None):
        """Centered rounded rectangle. clip(xs, ys) -> extra distance field
        to intersect with (e.g. eyelids); positive = outside."""
        if w <= 0.5 or h <= 0.5:
            return
        r = max(0.0, min(r, w / 2, h / 2))
        box = self._box(cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)
        if box is None:
            return
        _, _, xs, ys = box
        qx = np.abs(xs - cx) - (w / 2 - r)
        qy = np.abs(ys - cy) - (h / 2 - r)
        outside = np.sqrt(np.maximum(qx, 0) ** 2 + np.maximum(qy, 0) ** 2)
        inside = np.minimum(np.maximum(qx, qy), 0)
        dist = outside + inside - r
        if clip is not None:
            dist = np.maximum(dist, clip(xs, ys))
        self._blend(box, dist, color, alpha)

    def curve(self, cx, cy, half_w, bend, thickness, color, alpha=1.0):
        """A parabolic stroke y = cy + bend * (1 - (dx/half_w)^2): bend > 0
        sags in the middle (a smile), < 0 bulges up (a frown)."""
        if half_w <= 0.5:
            return
        pad = thickness + abs(bend)
        box = self._box(cx - half_w - thickness, cy - pad, cx + half_w + thickness, cy + pad)
        if box is None:
            return
        _, _, xs, ys = box
        t = np.clip((xs - cx) / half_w, -1.0, 1.0)
        y = cy + bend * (1 - t * t)
        slope = -2 * bend * t / half_w
        dist_line = np.abs(ys - y) / np.sqrt(1 + slope * slope)
        dx_end = np.maximum(np.abs(xs - cx) - half_w, 0)    # round caps
        dist = np.sqrt(dist_line ** 2 + dx_end ** 2) - thickness / 2
        self._blend(box, dist, color, alpha)

    def heart(self, cx, cy, size, color, alpha=1.0):
        """Classic heart from two circles and a triangle-ish bottom."""
        r = size * 0.3
        self.ellipse(cx - r * 0.95, cy - r * 0.4, r, r, color, alpha)
        self.ellipse(cx + r * 0.95, cy - r * 0.4, r, r, color, alpha)
        box = self._box(cx - size * 0.6, cy - r * 0.4, cx + size * 0.6, cy + size * 0.6)
        if box is None:
            return
        _, _, xs, ys = box
        # downward-pointing wedge: inside when |dx| < (bottom - y) * k
        bottom = cy + size * 0.55
        k = (size * 0.58) / (bottom - (cy - r * 0.2))
        dist = (np.abs(xs - cx) - (bottom - ys) * k) / np.sqrt(1 + k * k)
        dist = np.maximum(dist, (cy - r * 0.35) - ys)
        self._blend(box, dist, color, alpha)

    def sparkle(self, cx, cy, size, color, alpha=1.0):
        """Four-pointed star."""
        box = self._box(cx - size, cy - size, cx + size, cy + size)
        if box is None:
            return
        _, _, xs, ys = box
        ax, ay = np.abs(xs - cx), np.abs(ys - cy)
        # astroid-like star: sqrt(ax) + sqrt(ay) <= sqrt(size)
        f = np.sqrt(ax / size) + np.sqrt(ay / size) - 1.0
        dist = f * size * 0.5
        self._blend(box, dist, color, alpha)

    # --- output -----------------------------------------------------------
    def to_rgb565(self, out=None):
        p = np.clip(self.px, 0, 255).astype(np.uint16)
        v = ((p[..., 0] >> 3) << 11) | ((p[..., 1] >> 2) << 5) | (p[..., 2] >> 3)
        if out is not None:
            out[:] = v
            return out
        return v

    def to_rgb888(self):
        return np.clip(self.px, 0, 255).astype(np.uint8)
