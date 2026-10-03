#!/usr/bin/env python3
"""Voice effect tests:  python3 tests/test_voicefx.py"""
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import voicefx   # noqa: E402

failures = 0


def check(name, cond):
    global failures
    print(("  ok   " if cond else "  FAIL ") + name)
    failures += 0 if cond else 1


def dominant_hz(x, rate):
    spec = np.abs(np.fft.rfft(x * np.hanning(len(x))))
    return np.argmax(spec) * rate / len(x)


rate = 24000
t = np.arange(rate * 2) / rate
voice = (0.4 * np.sin(2 * np.pi * 200 * t)).astype(np.float32)   # a 200 Hz "voice"

y = voicefx.pitch_shift(voice, 1.5, rate)
check("pitch shift keeps the duration (within 3%)", abs(len(y) - len(voice)) / len(voice) < 0.03)
f = dominant_hz(y[rate // 2: rate // 2 + 8192], rate)
check(f"pitch goes up 1.5x (200 -> {f:.0f} Hz)", 280 < f < 320)

for name in voicefx.PRESETS:
    t0 = time.perf_counter()
    out = voicefx.apply(voice, rate, name)
    ms = (time.perf_counter() - t0) * 1000
    ok = out.dtype == np.float32 and abs(np.abs(out).max() - 0.9) < 1e-3 and np.isfinite(out).all()
    check(f"preset {name}: normalised, finite ({ms:.0f} ms for 2 s on this machine)", ok)
check("none preset leaves the waveform shape", np.allclose(
    voicefx.apply(voice, rate, "none"), voice / np.abs(voice).max() * 0.9, atol=1e-5))
check("empty input survives", len(voicefx.apply(np.zeros(0, np.float32), rate)) == 0)

print(f"\n{'all passed' if not failures else f'{failures} FAILED'}")
sys.exit(1 if failures else 0)
