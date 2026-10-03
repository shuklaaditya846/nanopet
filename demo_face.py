#!/usr/bin/env python3
"""Face demo: no AI, keyboard-driven. Run on the board over ssh -t.

    python3 demo_face.py            # live on the LCD
    python3 demo_face.py --bench    # time rendering only (works anywhere)

Keys:
  1-9, 0   emotions (1 neutral 2 happy 3 excited 4 sad 5 angry
           6 surprised 7 curious 8 confused 9 love 0 sleepy)
  b w n s k  bounce, wiggle, nod, shake, wink
  h p      hearts, sparkles
  i j l m  look up / left / right / down (c = centre)
  t        toggle fake talking (mouth flaps, subtitles cycle)
  a        toggle auto-cycling through the emotions
  q        quit
"""
import argparse
import math
import os
import select
import sys
import termios
import time
import tty

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from face import EMOTIONS, Face, H, W    # noqa: E402
from font import Font                     # noqa: E402
from gfx import Canvas                    # noqa: E402

KEYS_EMO = dict(zip("1234567890", EMOTIONS))
KEYS_ACT = {"b": "bounce", "w": "wiggle", "n": "nod", "s": "shake", "k": "wink",
            "h": "hearts", "p": "sparkle"}
KEYS_LOOK = {"i": "up", "j": "left", "l": "right", "m": "down", "c": "center"}
LINES = ["Hi! I'm Pip", "Nice to meet", "you! Want a", "joke? Ask me!"]


def bench(n):
    font = Font()
    face = Face(font)
    canvas = Canvas(W, H)
    times = {"update": 0.0, "render": 0.0, "convert": 0.0}
    emos = list(EMOTIONS)
    for i in range(n):
        if i % 30 == 0:
            face.set_emotion(emos[(i // 30) % len(emos)])
            face.do("hearts")
        t0 = time.perf_counter()
        face.update(1 / 20)
        t1 = time.perf_counter()
        face.render(canvas)
        t2 = time.perf_counter()
        canvas.to_rgb565()
        t3 = time.perf_counter()
        times["update"] += t1 - t0
        times["render"] += t2 - t1
        times["convert"] += t3 - t2
    total = sum(times.values())
    print(f"{n} frames: " + ", ".join(f"{k} {v / n * 1000:.1f} ms" for k, v in times.items())
          + f" -> {n / total:.1f} FPS (render only)")


def live(fps):
    from fb import Framebuffer
    font = Font()
    face = Face(font)
    canvas = Canvas(W, H)
    fb = Framebuffer()
    face.set_emotion("neutral")
    old = termios.tcgetattr(sys.stdin)
    tty.setcbreak(sys.stdin.fileno())
    talking = auto = False
    emos = list(EMOTIONS)
    frames, t_stat, last = 0, time.monotonic(), time.monotonic()
    next_auto = 0.0
    print(__doc__.split("Keys:")[1])
    try:
        while True:
            now = time.monotonic()
            dt, last = now - last, now
            if select.select([sys.stdin], [], [], 0)[0]:
                ch = sys.stdin.read(1)
                if ch == "q":
                    break
                if ch in KEYS_EMO:
                    face.set_emotion(KEYS_EMO[ch])
                    face.subtitle = KEYS_EMO[ch]
                elif ch in KEYS_ACT:
                    face.do(KEYS_ACT[ch])
                elif ch in KEYS_LOOK:
                    face.look(KEYS_LOOK[ch])
                elif ch == "t":
                    talking = not talking
                    face.subtitle = LINES[0] if talking else ""
                elif ch == "a":
                    auto = not auto
            if auto and now >= next_auto:
                e = emos[int(now / 3) % len(emos)]
                face.set_emotion(e)
                face.subtitle = e
                next_auto = now + 3
            if talking:      # fake speech loudness + rotating subtitle chunks
                face.set_talk(max(0.0, math.sin(now * 13) * 0.5 + math.sin(now * 7.3) * 0.4))
                face.subtitle = LINES[int(now / 1.5) % len(LINES)]
            else:
                face.set_talk(0)
            face.update(dt)
            face.render(canvas)
            fb.show(canvas.to_rgb565())
            frames += 1
            if now - t_stat >= 3:
                print(f"\r{frames / (now - t_stat):.1f} FPS  ", end="", flush=True)
                frames, t_stat = 0, now
            sleep = 1 / fps - (time.monotonic() - now)
            if sleep > 0:
                time.sleep(sleep)
    finally:
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old)
        fb.close()
        print()


def main():
    ap = argparse.ArgumentParser(description="nanopet face demo")
    ap.add_argument("--bench", type=int, nargs="?", const=200, help="time N frames, no LCD")
    ap.add_argument("--fps", type=float, default=20, help="target frame rate")
    args = ap.parse_args()
    if args.bench:
        bench(args.bench)
    else:
        live(args.fps)


if __name__ == "__main__":
    main()
