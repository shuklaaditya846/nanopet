#!/usr/bin/env python3
"""Render every emotion (and a few actions) into one PNG contact sheet,
on the laptop, to check the face design without the board.

    python3 tools/preview.py [out.png]
"""
import os
import sys

from PIL import Image, ImageDraw

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from face import EMOTIONS, Face, H, W   # noqa: E402
from font import Font                    # noqa: E402
from gfx import Canvas                   # noqa: E402


def frame(font, emotion, settle=1.5, talk=0.0, subtitle="", action=None, after=0.0):
    face = Face(font, seed=1)
    face.next_blink = 1e9              # no blink mid-capture
    face.next_glance = 1e9
    face.set_emotion(emotion, 0.9)
    face.subtitle = subtitle
    t = 0.0
    while t < settle:
        face.update(1 / 30)
        t += 1 / 30
    if action:
        face.do(action)
        t = 0.0
        while t < after:
            face.update(1 / 30)
            t += 1 / 30
    face.set_talk(talk)
    canvas = Canvas(W, H)
    face.render(canvas)
    return Image.fromarray(canvas.to_rgb888())


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "preview.png"
    font = Font()
    shots = [(e, frame(font, e, subtitle=e)) for e in EMOTIONS]
    shots.append(("talking", frame(font, "happy", talk=0.7, subtitle="Hi! I'm Pip")))
    shots.append(("french", frame(font, "love", subtitle="Ça va très bien…")))
    shots.append(("hindi (romanised)", frame(font, "happy", subtitle="Main Pip hoon!")))
    shots.append(("bounce", frame(font, "excited", action="bounce", after=0.15)))
    cols = 4
    rows = (len(shots) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * (W + 8), rows * (H + 24)), "#202020")
    draw = ImageDraw.Draw(sheet)
    for i, (name, img) in enumerate(shots):
        x, y = (i % cols) * (W + 8), (i // cols) * (H + 24)
        sheet.paste(img, (x, y + 20))
        draw.text((x + 4, y + 4), name, fill="#ffffff")
    sheet.save(out)
    print(out, sheet.size)


if __name__ == "__main__":
    main()
