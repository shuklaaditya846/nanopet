"""Make Mistral's human-sounding TTS into Pip's voice: a small, cute
robot. Pure numpy, applied after synthesis, before playback.

    pitch_shift   granular time-stretch + resample: higher pitch, same
                  speed; the grains themselves add a synthetic texture
    ring_mod      multiply by a low sine: the classic robot buzz
    comb          a few ms of feed-forward echo: metallic resonance
    crush         reduce bit depth a little: retro toy grit
"""
import numpy as np

PRESETS = {
    "cute_robot": {"pitch": 1.45, "ring_hz": 45.0, "ring_mix": 0.3,
                   "comb_ms": 4.5, "comb_gain": 0.45, "bits": 8, "crush_mix": 0.25},
    "robot": {"pitch": 1.0, "ring_hz": 60.0, "ring_mix": 0.55,
              "comb_ms": 7.0, "comb_gain": 0.55, "bits": 6, "crush_mix": 0.35},
    "chipmunk": {"pitch": 1.7, "ring_hz": 0.0, "ring_mix": 0.0,
                 "comb_ms": 0.0, "comb_gain": 0.0, "bits": 16, "crush_mix": 0.0},
    "none": {"pitch": 1.0, "ring_hz": 0.0, "ring_mix": 0.0,
             "comb_ms": 0.0, "comb_gain": 0.0, "bits": 16, "crush_mix": 0.0},
}


def time_stretch(x, factor, rate, grain_s=0.03):
    """Overlap-add time stretch: output is ~factor times longer, same pitch.
    Plain OLA (no waveform alignment), which is exactly what gives the
    slightly buzzy, synthetic character we want."""
    if abs(factor - 1.0) < 1e-3 or len(x) == 0:
        return x
    g = max(64, int(rate * grain_s))
    hs = g // 2                                  # synthesis hop
    ha = hs / factor                             # analysis hop
    win = np.hanning(g).astype(np.float32)
    n_grains = max(1, int((len(x) - g) / ha) + 1)
    out = np.zeros(n_grains * hs + g, dtype=np.float32)
    norm = np.zeros_like(out)
    xp = np.concatenate([x, np.zeros(g, dtype=np.float32)])
    for i in range(n_grains):
        a = int(i * ha)
        s = i * hs
        out[s:s + g] += xp[a:a + g] * win
        norm[s:s + g] += win
    norm[norm < 1e-3] = 1.0
    return out / norm


def resample(x, factor):
    """Speed up by factor (pitch up, shorter) with linear interpolation."""
    if abs(factor - 1.0) < 1e-3 or len(x) == 0:
        return x
    n = int(len(x) / factor)
    return np.interp(np.arange(n) * factor, np.arange(len(x)), x).astype(np.float32)


def pitch_shift(x, factor, rate):
    return resample(time_stretch(x, factor, rate), factor)


def ring_mod(x, rate, hz, mix):
    if hz <= 0 or mix <= 0:
        return x
    t = np.arange(len(x), dtype=np.float32) / rate
    return x * (1 - mix) + x * np.sin(2 * np.pi * hz * t).astype(np.float32) * mix


def comb(x, rate, ms, gain):
    if ms <= 0 or gain <= 0:
        return x
    d = max(1, int(rate * ms / 1000))
    y = x.copy()
    for k, g in ((1, gain), (2, gain * gain), (3, gain ** 3)):
        y[k * d:] += x[:-k * d] * g if k * d < len(x) else 0
    return y


def crush(x, bits, mix):
    if bits >= 16 or mix <= 0:
        return x
    levels = 2 ** (bits - 1)
    return x * (1 - mix) + np.round(x * levels) / levels * mix


def apply(x, rate, preset="cute_robot", pitch=None):
    p = dict(PRESETS.get(preset, PRESETS["cute_robot"]))
    if pitch:
        p["pitch"] = float(pitch)
    y = pitch_shift(x.astype(np.float32), p["pitch"], rate)
    y = ring_mod(y, rate, p["ring_hz"], p["ring_mix"])
    y = comb(y, rate, p["comb_ms"], p["comb_gain"])
    y = crush(y, p["bits"], p["crush_mix"])
    peak = float(np.abs(y).max()) if len(y) else 0.0
    return (y / peak * 0.9).astype(np.float32) if peak > 1e-6 else y
