"""The pet's face: parameters, emotion presets, idle life, actions, and
rendering onto a gfx.Canvas.

Style: two glowing rounded-rectangle eyes (Cozmo/EMO-like) with eyelids,
a small mouth, blush, and particle overlays (hearts, sparkles, z's).
Everything is a float parameter that eases toward a target each frame, so
changes of emotion animate instead of jumping.
"""
import math
import random

import numpy as np

W, H = 320, 240
BG = "#0b1020"

# Parameters and their neutral values
NEUTRAL = {
    "open": 1.0,          # eye openness (0 closed .. 1.2 wide)
    "scale_l": 1.0,       # per-eye size
    "scale_r": 1.0,
    "lid": 0.0,           # top lid cut at the tilted side (0..0.6)
    "tilt": 0.0,          # lid tilt: +1 angry (inner corners down), -1 sad
    "smile_eyes": 0.0,    # bottom of the eyes cut into ^ ^ arcs (0..1)
    "look_x": 0.0,        # -1 left .. +1 right
    "look_y": 0.0,        # -1 up .. +1 down
    "mouth_curve": 0.35,  # -1 frown .. +1 big smile
    "mouth_open": 0.0,    # 0 closed .. 1 wide open "O"
    "mouth_w": 1.0,
    "blush": 0.0,
    "cr": 61.0, "cg": 242.0, "cb": 255.0,   # eye colour (cyan)
}

EMOTIONS = {
    "neutral": {},
    "happy": {"smile_eyes": 0.75, "mouth_curve": 1.0, "blush": 0.45},
    "excited": {"open": 1.1, "scale_l": 1.12, "scale_r": 1.12, "mouth_curve": 1.0,
                "mouth_open": 0.45, "blush": 0.3, "cr": 120, "cg": 255, "cb": 200},
    "sad": {"lid": 0.35, "tilt": -0.85, "look_y": 0.35, "mouth_curve": -0.8,
            "scale_l": 0.95, "scale_r": 0.95, "cr": 90, "cg": 150, "cb": 255},
    "angry": {"lid": 0.42, "tilt": 0.9, "mouth_curve": -0.55, "mouth_w": 0.8,
              "cr": 255, "cg": 90, "cb": 70},
    "surprised": {"open": 1.15, "scale_l": 1.15, "scale_r": 1.15, "mouth_open": 0.75,
                  "mouth_w": 0.55, "mouth_curve": 0.0},
    "curious": {"scale_l": 1.12, "scale_r": 0.85, "look_x": 0.45, "look_y": -0.3,
                "mouth_curve": 0.15, "mouth_w": 0.7},
    "confused": {"scale_l": 0.88, "scale_r": 1.08, "lid": 0.18, "tilt": -0.4,
                 "mouth_curve": -0.25, "mouth_w": 0.75, "cr": 200, "cg": 170, "cb": 255},
    "love": {"smile_eyes": 0.6, "mouth_curve": 0.9, "blush": 0.85,
             "cr": 255, "cg": 110, "cb": 175},
    "sleepy": {"open": 0.22, "look_y": 0.45, "mouth_curve": 0.05, "mouth_w": 0.7,
               "cr": 40, "cg": 150, "cb": 170},
}

# Overlay particles that come with an emotion
EMOTION_FX = {"love": "hearts", "excited": "sparkle", "sleepy": "zzz",
              "confused": "question", "surprised": "bang"}

ACTIONS = ("none", "bounce", "wiggle", "nod", "shake", "wink", "hearts", "sparkle")


def _mix(a, b, t):
    return a + (b - a) * t


class Face:
    EYE_W, EYE_H, EYE_R = 74, 92, 24
    EYE_Y, EYE_GAP = 98, 116
    MOUTH_Y = 178

    def __init__(self, font=None, seed=None):
        self.font = font
        self.rng = random.Random(seed)
        self.cur = dict(NEUTRAL)
        self.tgt = dict(NEUTRAL)
        self.emotion = "neutral"
        self.t = 0.0
        self.talk = 0.0             # 0..1 loudness while speaking
        self.next_blink = 1.5
        self.blink_t = None
        self.next_glance = 3.0
        self.glance = (0.0, 0.0)
        self.actions = []           # (name, start time)
        self.particles = []         # dicts: kind, x, y, vx, vy, life, age, size
        self.fx = None
        self.fx_timer = 0.0
        self.subtitle = ""

    # --- inputs -----------------------------------------------------------
    def set_emotion(self, name, intensity=0.8):
        name = name if name in EMOTIONS else "neutral"
        k = max(0.0, min(float(intensity), 1.0))
        preset = EMOTIONS[name]
        self.tgt = {p: _mix(v, preset.get(p, v), k) for p, v in NEUTRAL.items()}
        self.emotion = name
        self.fx = EMOTION_FX.get(name)
        self.fx_timer = 0.0

    def do(self, action):
        if action in ("hearts", "sparkle"):
            for _ in range(7 if action == "hearts" else 10):
                self._spawn("heart" if action == "hearts" else "sparkle")
        elif action in ACTIONS and action != "none":
            self.actions.append((action, self.t))

    def look(self, where):
        self.glance = {"left": (-0.8, 0), "right": (0.8, 0), "up": (0, -0.8),
                       "down": (0, 0.8)}.get(where, (0.0, 0.0))
        self.next_glance = self.t + 3.0

    def set_talk(self, level):
        self.talk = max(0.0, min(float(level), 1.0))

    # --- animation ----------------------------------------------------------
    def update(self, dt):
        self.t += dt
        ease = min(1.0, dt * 7.0)
        for p in self.cur:
            self.cur[p] += (self.tgt[p] - self.cur[p]) * ease

        # blinking: every 2.5-6 s, sometimes a double blink; not when asleep
        if self.blink_t is None and self.t >= self.next_blink and self.emotion != "sleepy":
            self.blink_t = self.t
        if self.blink_t is not None and self.t - self.blink_t > 0.16:
            self.blink_t = None
            double = self.rng.random() < 0.2
            self.next_blink = self.t + (0.12 if double else self.rng.uniform(2.5, 6.0))

        # idle glances
        if self.t >= self.next_glance:
            if self.glance == (0.0, 0.0) and self.rng.random() < 0.7:
                self.glance = (self.rng.uniform(-0.7, 0.7), self.rng.uniform(-0.4, 0.4))
                self.next_glance = self.t + self.rng.uniform(0.6, 1.6)
            else:
                self.glance = (0.0, 0.0)
                self.next_glance = self.t + self.rng.uniform(2.0, 5.0)

        # emotion particles
        self.fx_timer -= dt
        if self.fx and self.fx_timer <= 0:
            kind = {"hearts": "heart", "sparkle": "sparkle", "zzz": "z",
                    "question": "?", "bang": "!"}[self.fx]
            if kind in ("?", "!"):
                if not any(p["kind"] == kind for p in self.particles):
                    self._spawn(kind)
                self.fx_timer = 0.5
            else:
                self._spawn(kind)
                self.fx_timer = {"heart": 0.7, "sparkle": 0.25, "z": 1.1}[kind]
        for p in self.particles:
            p["age"] += dt
            p["x"] += p["vx"] * dt
            p["y"] += p["vy"] * dt
        self.particles = [p for p in self.particles if p["age"] < p["life"]]
        self.actions = [(a, t0) for a, t0 in self.actions if self.t - t0 < 1.2]

    def _spawn(self, kind):
        r = self.rng
        if kind == "heart":
            p = dict(x=r.uniform(40, 280), y=r.uniform(150, 220), vx=r.uniform(-8, 8),
                     vy=r.uniform(-45, -30), life=r.uniform(1.6, 2.4), size=r.uniform(14, 24))
        elif kind == "sparkle":
            p = dict(x=r.choice([r.uniform(15, 70), r.uniform(250, 305)]),
                     y=r.uniform(20, 200), vx=0, vy=0, life=r.uniform(0.5, 0.9),
                     size=r.uniform(7, 13))
        elif kind == "z":
            p = dict(x=250 + r.uniform(-5, 5), y=70, vx=r.uniform(6, 14), vy=-18,
                     life=2.6, size=36)
        else:                                    # "?" or "!"
            p = dict(x=262, y=22, vx=0, vy=0, life=3.0, size=36)
        p.update(kind=kind, age=0.0)
        self.particles.append(p)

    def _motion(self):
        """Head offset from breathing and active actions."""
        dx = 0.0
        dy = math.sin(self.t * 2 * math.pi / 4.0) * 2.0       # breathing
        wink = 1.0
        for name, t0 in self.actions:
            a = self.t - t0
            decay = math.exp(-a * 3.0)
            if name == "bounce":
                dy -= abs(math.sin(a * math.pi * 3.5)) * 16 * math.exp(-a * 2.0)
            elif name == "wiggle":
                dx += math.sin(a * 26) * 9 * decay
            elif name == "nod":
                dy += math.sin(a * 13) * 8 * decay
            elif name == "shake":
                dx += math.sin(a * 19) * 12 * decay
            elif name == "wink" and a < 0.5:
                wink = min(wink, abs(math.cos(a * math.pi / 0.5)))
        return dx, dy, wink

    # --- drawing ----------------------------------------------------------
    def render(self, canvas):
        c = self.cur
        canvas.clear(BG)
        dx, dy, wink = self._motion()
        color = "#%02x%02x%02x" % tuple(int(max(0, min(255, c[k]))) for k in ("cr", "cg", "cb"))

        blink = 1.0
        if self.blink_t is not None:
            blink = abs(math.cos((self.t - self.blink_t) / 0.16 * math.pi))
        look_x = c["look_x"] + self.glance[0]
        look_y = c["look_y"] + self.glance[1]
        ox, oy = dx + look_x * 18, dy + look_y * 12

        for side in (-1, 1):            # -1 = left eye, +1 = right eye
            scale = c["scale_l"] if side < 0 else c["scale_r"]
            openness = max(0.0, c["open"] * blink * (wink if side > 0 else 1.0))
            ew, eh = self.EYE_W * scale, self.EYE_H * scale * openness
            cx = W / 2 + side * self.EYE_GAP / 2 + ox
            cy = self.EYE_Y + oy
            if eh < 6:                   # closed: a soft line
                canvas.curve(cx, cy + 4, ew / 2, -3 if self.emotion == "sleepy" else 0,
                             6, color)
                continue
            top = cy - eh / 2
            lid_drop = c["lid"] * eh
            slope = c["tilt"] * 0.55 * side * -1    # inner corner = towards the centre
            smile = c["smile_eyes"]

            def clip(xs, ys, cx=cx, top=top, eh=eh, ew=ew, lid_drop=lid_drop,
                     slope=slope, smile=smile):
                lid_y = top + lid_drop + slope * (xs - cx)
                d = (lid_y - ys) / math.sqrt(1 + slope * slope)
                if smile > 0.02:        # carve the bottom into an arc: ^ ^
                    ry = eh * 0.95 * smile
                    rx = ew * 0.75
                    ccy = top + eh + ry * 0.35
                    nx, ny = (xs - cx) / rx, (ys - ccy) / ry
                    cut = (1.0 - np.sqrt(nx * nx + ny * ny)) * min(rx, ry)
                    d = np.maximum(d, cut)
                return d

            canvas.rounded_rect(cx, cy, ew, eh, self.EYE_R * scale, color, clip=clip)
            # a little highlight makes the eyes look alive; keep it under the lid
            if eh > 30 and smile < 0.5:
                hx, hr = cx + ew * 0.2, ew * 0.11
                lid_here = top + lid_drop + slope * (hx - cx)
                hy = max(cy - eh * 0.22, lid_here + hr + 5)
                if hy + hr < cy + eh / 2 - 4:
                    canvas.ellipse(hx, hy, hr, hr, "#ffffff", alpha=0.75)

        # blush
        if c["blush"] > 0.02:
            for side in (-1, 1):
                canvas.ellipse(W / 2 + side * (self.EYE_GAP / 2 + 34) + dx,
                               self.EYE_Y + 52 + dy, 20, 9, "#ff6f91", alpha=c["blush"] * 0.7)

        # mouth: the curve, plus an open "O" while talking or surprised
        mw = 24 * c["mouth_w"]
        my = self.MOUTH_Y + dy
        mx = W / 2 + dx * 0.8
        opening = max(c["mouth_open"], self.talk)
        if opening > 0.08:
            # rounder "O" for a surprised narrow mouth, wider grin otherwise
            rx = mw * (0.75 + 0.35 * self.talk) if c["mouth_w"] < 0.7 else mw * 0.95
            ry = 4 + 16 * opening
            canvas.ellipse(mx, my + 2, rx, ry, color)
            canvas.ellipse(mx, my + 2 + 2 * opening, rx * 0.7, ry * 0.62,
                           "#3a1024", alpha=0.9)
        else:
            canvas.curve(mx, my - 4 * c["mouth_curve"], mw, 9 * c["mouth_curve"], 6, color)

        # particles
        for p in self.particles:
            fade = min(1.0, p["age"] * 4, (p["life"] - p["age"]) * 2.5)
            if p["kind"] == "heart":
                canvas.heart(p["x"], p["y"], p["size"], "#ff4f8b", alpha=fade)
            elif p["kind"] == "sparkle":
                tw = math.sin(p["age"] / p["life"] * math.pi)
                canvas.sparkle(p["x"], p["y"], p["size"] * tw + 1, "#fff6a8", alpha=fade)
            elif self.font is not None:
                txt = p["kind"]
                if txt == "z":
                    size = 22 + 14 * min(1.0, p["age"] / 2)
                    self.font.draw(canvas, p["x"], p["y"], txt, size, color, alpha=fade)
                else:                           # ? and ! pop in bright
                    bob = math.sin(p["age"] * 5) * 3
                    self.font.draw(canvas, p["x"], p["y"] + bob, txt, 36, "#ffe066",
                                   alpha=min(1.0, fade * 1.5))

        # subtitle band
        if self.subtitle and self.font is not None:
            size = 22
            tw = self.font.width(self.subtitle, size)
            canvas.rounded_rect(W / 2, 222, min(W - 8, tw + 24), 30, 12, "#000000", alpha=0.55)
            self.font.draw(canvas, (W - tw) / 2, 222 - self.font.height(size) / 2,
                           self.subtitle, size, "#ffffff")
