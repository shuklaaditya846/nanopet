"""Turning TTS audio into sound and mouth movement.

- decode(): WAV (16-bit PCM or 32-bit float) or raw float32 PCM -> float32 mono
- envelope(): loudness per 40 ms window, scaled 0..1, for lip-sync
- Player: plays through aplay on the USB sound card in a background thread
  and reports the current loudness while it plays.
"""
import struct
import subprocess
import threading
import time

import numpy as np

HOP = 0.04          # seconds per envelope step (25 per second)


def decode(data, default_rate=24000):
    """Returns (float32 samples in -1..1, sample rate)."""
    if data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        pos, fmt, rate, bits, chans, pcm = 12, 1, default_rate, 16, 1, b""
        while pos + 8 <= len(data):
            cid, size = data[pos:pos + 4], struct.unpack_from("<I", data, pos + 4)[0]
            body = data[pos + 8:pos + 8 + size]
            if cid == b"fmt ":
                fmt, chans, rate = struct.unpack_from("<HHI", body)
                bits = struct.unpack_from("<H", body, 14)[0]
                if fmt == 0xFFFE and len(body) >= 26:       # WAVE_FORMAT_EXTENSIBLE
                    fmt = struct.unpack_from("<H", body, 24)[0]
            elif cid == b"data":
                pcm = body
                if size in (0, 0xFFFFFFFF):                # streamed: size unknown
                    pcm = data[pos + 8:]
                break
            pos += 8 + size + (size & 1)
        if fmt == 3 and bits == 32:
            x = np.frombuffer(pcm[:len(pcm) // 4 * 4], dtype="<f4")
        elif fmt == 1 and bits == 16:
            x = np.frombuffer(pcm[:len(pcm) // 2 * 2], dtype="<i2").astype(np.float32) / 32768
        elif fmt == 1 and bits == 32:
            x = np.frombuffer(pcm[:len(pcm) // 4 * 4], dtype="<i4").astype(np.float32) / 2**31
        else:
            raise ValueError(f"unsupported WAV: format {fmt}, {bits} bits")
        if chans > 1:
            x = x.reshape(-1, chans).mean(axis=1)
        return x.astype(np.float32), rate
    # raw float32 little-endian PCM (Mistral's "pcm" format)
    x = np.frombuffer(data[:len(data) // 4 * 4], dtype="<f4")
    return x.astype(np.float32), default_rate


def envelope(x, rate):
    """Mouth openness per HOP: RMS, compressed and normalised to 0..1."""
    n = max(1, int(rate * HOP))
    steps = len(x) // n
    if steps == 0:
        return np.zeros(0, dtype=np.float32)
    rms = np.sqrt((x[:steps * n].reshape(steps, n) ** 2).mean(axis=1))
    peak = np.percentile(rms, 95) or 1e-6
    env = np.clip(rms / peak, 0, 1) ** 0.6       # lift quiet syllables
    env[env < 0.12] = 0.0                        # closed mouth in pauses
    return env.astype(np.float32)


def find_usb_card():
    """ALSA device of the first USB sound card, e.g. 'plughw:1,0'."""
    try:
        with open("/proc/asound/cards") as f:
            for line in f:
                parts = line.split()
                if parts and parts[0].isdigit() and "USB" in line:
                    return f"plughw:{parts[0]},0"
    except OSError:
        pass
    return None


class Player:
    LATENCY = 0.08      # aplay's buffer: the sound starts a little after we write it

    def __init__(self, device=None):
        self.device = device or find_usb_card()
        self.env = np.zeros(0, dtype=np.float32)
        self.t0 = 0.0
        self.duration = 0.0
        self.thread = None

    def play(self, x, rate):
        """Start playing float32 samples; returns immediately."""
        self.stop()
        self.env = envelope(x, rate)
        self.duration = len(x) / rate
        self.t0 = time.monotonic() + self.LATENCY
        if not self.device:
            return                      # no speaker: lip-sync and subtitles still run
        pcm = (np.clip(x, -1, 1) * 32767).astype("<i2").tobytes()
        self.proc = subprocess.Popen(
            ["aplay", "-q", "-D", self.device, "-t", "raw", "-f", "S16_LE",
             "-c", "1", "-r", str(rate)], stdin=subprocess.PIPE, stderr=subprocess.PIPE)

        def feed(proc=self.proc):
            try:
                proc.stdin.write(pcm)
                proc.stdin.close()
            except BrokenPipeError:
                pass
            proc.wait()
        self.thread = threading.Thread(target=feed, daemon=True)
        self.thread.start()

    def level(self):
        """Current loudness 0..1 (0 when not playing)."""
        i = int((time.monotonic() - self.t0) / HOP)
        return float(self.env[i]) if 0 <= i < len(self.env) else 0.0

    def playing(self):
        return time.monotonic() < self.t0 + self.duration

    def elapsed(self):
        return time.monotonic() - self.t0

    def stop(self):
        if self.thread and self.thread.is_alive():
            self.proc.kill()
            self.thread.join(timeout=1)
        self.duration = 0.0
