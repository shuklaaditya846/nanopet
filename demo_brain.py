#!/usr/bin/env python3
"""Brain + voice demo: talk to the pet; it reacts and answers out loud.

    python3 demo_brain.py              # Enter to start/stop talking
    python3 demo_brain.py --text       # type messages instead (no mic)

Prints the raw model output, whether JSON mode was accepted, the parsed
reply and the timing; the face shows the emotion, action and gaze, with
the subtitles cycling chunk by chunk.
"""
import argparse
import os

import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from brain import parse_reply, system_prompt   # noqa: E402
from common import Recorder, ensure_clock, load_config   # noqa: E402
from face import Face, H, W                    # noqa: E402
from font import Font                          # noqa: E402
from gfx import Canvas                         # noqa: E402
from memory import Memory                      # noqa: E402
from mistral import Mistral, MistralError      # noqa: E402
from speech import Player, decode              # noqa: E402

INSTRUCTION = "The audio is the user speaking to you. Reply as specified."


class FaceLoop(threading.Thread):
    """Renders the face at ~20 FPS on its own thread; the main thread
    talks to it through set_* calls (simple attribute writes)."""

    def __init__(self, face, player):
        super().__init__(daemon=True)
        self.face, self.player = face, player
        self.subtitles = []
        self.sub_until = 0.0
        self.timed = None           # [(start_s, chunk)] while speech plays
        self.running = True

    def say(self, chunks, duration=None):
        """Show chunks one after another: timed across the speech when its
        duration is known (longer chunks stay up longer), else ~1-2 s each."""
        if duration:
            total = sum(len(c) + 3 for c in chunks) or 1
            t, self.timed = 0.0, []
            for c in chunks:
                self.timed.append((t, c))
                t += duration * (len(c) + 3) / total
            self.subtitles, self.sub_until = [], 0.0
        else:
            self.timed = None
            self.subtitles = list(chunks)
            self.sub_until = 0.0

    def _subtitle_tick(self, now):
        if self.timed is not None:
            el = self.player.elapsed()
            if self.player.playing():
                current = [c for t, c in self.timed if t <= el]
                self.face.subtitle = current[-1] if current else self.timed[0][1]
            elif el > self.player.duration + 1.5:
                self.face.subtitle, self.timed = "", None
            return
        if self.subtitles and now >= self.sub_until:
            chunk = self.subtitles.pop(0)
            self.face.subtitle = chunk
            self.sub_until = now + max(1.2, 0.09 * len(chunk))
        elif not self.subtitles and self.sub_until and now >= self.sub_until + 2:
            self.face.subtitle, self.sub_until = "", 0.0

    def run(self):
        from fb import Framebuffer
        canvas, fb = Canvas(W, H), Framebuffer()
        last = time.monotonic()
        try:
            while self.running:
                now = time.monotonic()
                self._subtitle_tick(now)
                self.face.set_talk(self.player.level())
                self.face.update(now - last)
                last = now
                self.face.render(canvas)
                fb.show(canvas.to_rgb565())
                time.sleep(max(0.0, 0.05 - (time.monotonic() - now)))
        finally:
            fb.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--text", action="store_true", help="type instead of talking")
    args = ap.parse_args()

    cfg = load_config()
    if not cfg["MISTRAL_API_KEY"] or cfg["MISTRAL_API_KEY"].startswith("FAKE"):
        sys.exit("Set MISTRAL_API_KEY in /etc/nanopet.conf (or /etc/assistant.conf)")
    if not ensure_clock():
        print("Warning: clock not set, HTTPS may fail")
    mem = Memory(cfg["MEMORY"])
    client = Mistral(cfg["MISTRAL_API_KEY"], cfg["MISTRAL_MODEL"])
    rec = Recorder(cfg["AUDIO_DEVICE"], int(cfg["SAMPLE_RATE"]), int(cfg["MAX_SECONDS"]))

    player = Player(cfg["SPEAKER"] or None)
    tts = cfg["TTS"] != "0"
    print(f"Speaker: {player.device or 'none found (subtitles only)'}; "
          f"voice: {cfg['VOICE'] if tts else 'off'}")

    face = Face(Font())
    face.set_emotion("happy", 0.6)
    loop = FaceLoop(face, player)
    loop.start()
    loop.say([f"Hi! I'm {mem.name}"])

    try:
        while True:
            if args.text:
                msg = input("\nyou> ").strip()
                if not msg:
                    continue
            else:
                input("\n[Enter] to talk ")
                face.set_emotion("curious", 0.7)
                face.look("up")
                face.subtitle = "listening..."
                rec.start()
                input("  ...talking. [Enter] to send ")
                wav, secs = rec.stop()
                print(f"  {secs:.1f} s recorded")
            face.subtitle = "hmm..."
            face.set_emotion("curious", 0.5)
            prompt = system_prompt(mem.name, mem.facts, mem.mood)
            try:
                if args.text:
                    raw, took = client.chat_text(prompt, msg)
                else:
                    raw, took = client.chat_audio(prompt, wav, INSTRUCTION)
            except MistralError as e:
                print("  error:", e)
                face.set_emotion("sad", 0.6)
                loop.say(["Oops, I", "couldn't think"])
                continue
            r = parse_reply(raw)
            print(f"  model {client.model}, JSON mode {'on' if client.json_mode else 'off'}, "
                  f"{took:.1f} s, valid JSON: {r.ok}")
            print(f"  raw: {raw.strip()[:400]}")
            print(f"  -> {r.emotion} ({r.intensity:.1f}), action {r.action}, look {r.look}")
            print(f"     say: {r.say}")
            print(f"     screen: {r.screen}")
            face.set_emotion(r.emotion, r.intensity)
            face.do(r.action)
            face.look(r.look)
            spoken = False
            if tts and r.say:
                try:
                    audio, tts_s = client.speech(r.say, cfg["VOICE"], cfg["TTS_MODEL"])
                    x, rate = decode(audio)
                    print(f"     voice: {tts_s:.1f} s for {len(x) / rate:.1f} s of audio "
                          f"({rate} Hz, field '{client.tts_voice_key}')")
                    player.play(x, rate)
                    loop.say(r.screen, duration=len(x) / rate)
                    spoken = True
                except (MistralError, ValueError) as e:
                    print("     voice failed:", e)
            if not spoken:
                loop.say(r.screen)
            if r.remember and mem.remember(r.remember):
                print(f"     remembered: {r.remember}")
    except (KeyboardInterrupt, EOFError):
        print()
    finally:
        loop.running = False
        loop.join(timeout=2)


if __name__ == "__main__":
    main()
