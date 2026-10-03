#!/usr/bin/env python3
"""Voice tests, laptop only:  python3 tests/test_speech.py
(the TTS mock-server part needs `requests`; skipped if missing)."""
import base64
import io
import json
import os
import struct
import sys
import threading
import wave
from http.server import BaseHTTPRequestHandler, HTTPServer

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from speech import Player, decode, envelope   # noqa: E402

failures = 0


def check(name, cond):
    global failures
    print(("  ok   " if cond else "  FAIL ") + name)
    failures += 0 if cond else 1


rate = 24000
t = np.arange(rate) / rate
tone = (0.5 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
tone[rate // 2: rate // 2 + rate // 5] = 0          # a 200 ms pause


def wav16(x, r):
    b = io.BytesIO()
    with wave.open(b, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(r)
        w.writeframes((x * 32767).astype("<i2").tobytes())
    return b.getvalue()


def wav_float(x, r):
    data = x.astype("<f4").tobytes()
    fmt = struct.pack("<HHIIHH", 3, 1, r, r * 4, 4, 32)
    return (b"RIFF" + struct.pack("<I", 4 + 8 + len(fmt) + 8 + len(data)) + b"WAVE"
            + b"fmt " + struct.pack("<I", len(fmt)) + fmt
            + b"data" + struct.pack("<I", len(data)) + data)


print("decode")
x, r = decode(wav16(tone, rate))
check("16-bit WAV", r == rate and len(x) == rate and abs(x.max() - 0.5) < 0.01)
x, r = decode(wav_float(tone, 22050))
check("float WAV keeps its rate", r == 22050 and np.allclose(x, tone, atol=1e-6))
x, r = decode(tone.astype("<f4").tobytes())
check("raw float32 PCM", r == 24000 and np.allclose(x, tone))

print("envelope")
env = envelope(tone, rate)
check("25 steps per second", len(env) == 25)
mid = env[int(0.5 / 0.04) + 1: int(0.7 / 0.04) - 1]
check("mouth closes in the pause", mid.max() == 0.0 and env[:10].min() > 0.5)
p = Player(device=None)
p.play(tone, rate)
check("player without a speaker still runs the envelope", p.playing() and p.duration == 1.0)
p.stop()

print("TTS client (mock server)")
try:
    import requests  # noqa: F401
except ImportError:
    print("  skip (no requests)")
else:
    import mistral
    seen = []
    mode = {"style": "json", "voice_field": "voice_id"}
    audio = wav16(tone, rate)

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            seen.append(body)
            if mode["voice_field"] not in body:
                out = json.dumps({"detail": "unknown field: voice"}).encode()
                self.send_response(422)
                self.send_header("Content-Type", "application/json")
            elif mode["style"] == "json":
                out = json.dumps({"audio_data": base64.b64encode(audio).decode()}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
            else:
                out = audio
                self.send_response(200)
                self.send_header("Content-Type", "audio/wav")
            self.send_header("Content-Length", str(len(out)))
            self.end_headers()
            self.wfile.write(out)

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    mistral.API_BASE = f"http://127.0.0.1:{srv.server_port}/v1"
    c = mistral.Mistral("key", "voxtral-small-latest")
    data, _ = c.speech("Hello there", "en_paul_neutral")
    check("base64-in-JSON reply decoded", data == audio)
    check("retried with voice_id after 'voice' was rejected",
          len(seen) == 2 and "voice" in seen[0] and seen[1].get("voice_id") == "en_paul_neutral"
          and c.tts_voice_key == "voice_id")
    mode["style"] = "raw"
    data, _ = c.speech("Again", "en_paul_neutral")
    check("raw audio reply, remembered field (one request)", data == audio and len(seen) == 3)
    check("request fields", seen[-1]["input"] == "Again" and seen[-1]["response_format"] == "wav"
          and seen[-1]["model"] == "voxtral-mini-tts-2603")
    srv.shutdown()

print(f"\n{'all passed' if not failures else f'{failures} FAILED'}")
sys.exit(1 if failures else 0)
