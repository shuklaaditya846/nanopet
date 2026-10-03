"""The LCD framebuffer (/dev/fb0, RGB565), owned by the app.

- Switches the console on tty1 to graphics mode (KDSETMODE KD_GRAPHICS),
  so the kernel stops drawing text and the cursor over our frames.
- show() writes only the rows that changed since the last frame; fbtft
  then sends just that strip over SPI.
"""
import fcntl
import os

import numpy as np

KDSETMODE = 0x4B3A
KD_TEXT, KD_GRAPHICS = 0x00, 0x01


def _sysfs(name, key):
    with open(f"/sys/class/graphics/{name}/{key}") as f:
        return f.read().strip()


class Framebuffer:
    def __init__(self, dev="/dev/fb0", tty="/dev/tty1"):
        name = os.path.basename(dev)
        self.width, self.height = (int(v) for v in _sysfs(name, "virtual_size").split(","))
        bpp = int(_sysfs(name, "bits_per_pixel"))
        if bpp != 16:
            raise RuntimeError(f"{dev}: {bpp} bpp, expected RGB565")
        self.stride = int(_sysfs(name, "stride"))
        self.fd = os.open(dev, os.O_RDWR)
        self.prev = None
        self.tty = None
        try:
            self.tty = os.open(tty, os.O_RDWR | os.O_NOCTTY)
            fcntl.ioctl(self.tty, KDSETMODE, KD_GRAPHICS)
        except OSError:
            self.tty = None             # not fatal: the console may scribble

    def show(self, frame):
        """frame: (height, width) uint16 RGB565. Returns rows written."""
        if self.prev is None:
            r0, r1 = 0, self.height
        else:
            changed = np.flatnonzero((frame != self.prev).any(axis=1))
            if changed.size == 0:
                return 0
            r0, r1 = int(changed[0]), int(changed[-1]) + 1
        if self.stride == self.width * 2:
            os.pwrite(self.fd, frame[r0:r1].tobytes(), r0 * self.stride)
        else:
            for r in range(r0, r1):
                os.pwrite(self.fd, frame[r].tobytes(), r * self.stride)
        self.prev = frame.copy()
        return r1 - r0

    def close(self):
        if self.tty is not None:
            try:
                fcntl.ioctl(self.tty, KDSETMODE, KD_TEXT)
            except OSError:
                pass
            os.close(self.tty)
        os.close(self.fd)
