#!/usr/bin/env python3
"""Speak a sentence with Mistral TTS on the USB speaker.

    python3 say.py "Hello, I'm Pip!"
    python3 say.py --voice gb_jane_neutral "Testing another voice"
    python3 say.py --fx robot --pitch 1.3 "Beep boop"
    python3 say.py --voices        # try to list the available voices
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ensure_clock, load_config   # noqa: E402
from mistral import API_BASE, Mistral, MistralError   # noqa: E402
from speech import Player, decode               # noqa: E402
import voicefx                                  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("text", nargs="?", default="Hi! I'm Pip, your little desk pet.")
    ap.add_argument("--voice")
    ap.add_argument("--voices", action="store_true")
    ap.add_argument("--fx", help="cute_robot | robot | chipmunk | none")
    ap.add_argument("--pitch", type=float, help="pitch factor, e.g. 1.5")
    args = ap.parse_args()
    cfg = load_config()
    ensure_clock()
    c = Mistral(cfg["MISTRAL_API_KEY"], cfg["MISTRAL_MODEL"])
    if args.voices:
        for path in ("/audio/voices", "/voices"):
            r = c.session.get(API_BASE + path, timeout=30)
            print(f"GET {path}: HTTP {r.status_code}")
            if r.ok:
                print(r.text[:3000])
                return
        print("No voice list endpoint answered; see Mistral's docs for preset voice ids.")
        return
    voice = args.voice or cfg["VOICE"]
    try:
        audio, took = c.speech(args.text, voice, cfg["TTS_MODEL"])
    except MistralError as e:
        sys.exit(f"TTS failed: {e}")
    x, rate = decode(audio)
    fx = args.fx or cfg["VOICE_FX"]
    x = voicefx.apply(x, rate, fx, args.pitch or cfg["VOICE_PITCH"] or None)
    print(f"{took:.2f} s to synthesise {len(x) / rate:.1f} s of audio "
          f"({rate} Hz, {len(audio)} bytes, voice '{voice}' via '{c.tts_voice_key}', fx {fx})")
    p = Player(cfg["SPEAKER"] or None)
    print("speaker:", p.device or "none found")
    p.play(x, rate)
    while p.playing():
        time.sleep(0.05)
    time.sleep(0.3)


if __name__ == "__main__":
    main()
