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

import voicefx                                 # noqa: E402
from conversation import Conversation          # noqa: E402
from common import Recorder, ensure_clock, load_config   # noqa: E402
from face import Face, H, W                    # noqa: E402
from font import Font                          # noqa: E402
from gfx import Canvas                         # noqa: E402
from memory import LongTermMemory, PetState, ShortTermMemory   # noqa: E402
from mistral import Mistral, MistralError      # noqa: E402
from speech import Player, decode              # noqa: E402



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
        duration is known (longer chunks stay up longer), else ~1-2 s each.
        Chunks the font can't draw (non-Latin scripts) are left out."""
        font = self.face.font
        if font is not None:
            chunks = [c for c in chunks if font.supports(c)]
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
    data_dir = cfg["DATA_DIR"]
    client = Mistral(cfg["MISTRAL_API_KEY"], cfg["MISTRAL_MODEL"])
    conv = Conversation(client, LongTermMemory(os.path.join(data_dir, "notes")),
                        ShortTermMemory(max_turns=int(cfg["HISTORY_TURNS"]),
                                        idle_reset_s=float(cfg["HISTORY_IDLE_MIN"]) * 60),
                        PetState(os.path.join(data_dir, "state.json")))
    rec = Recorder(cfg["AUDIO_DEVICE"], int(cfg["SAMPLE_RATE"]), int(cfg["MAX_SECONDS"]))

    player = Player(cfg["SPEAKER"] or None)
    tts = cfg["TTS"] != "0"
    print(f"Speaker: {player.device or 'none found (subtitles only)'}; "
          f"voice: {cfg['VOICE'] + ' + ' + cfg['VOICE_FX'] if tts else 'off'}")
    print(f"Memory topics: {conv.ltm.topics() or 'none yet'}")

    face = Face(Font())
    face.set_emotion("happy", 0.6)
    loop = FaceLoop(face, player)
    loop.start()
    loop.say([f"Hi! I'm {conv.state.name}"])

    def status(what):
        if what == "remembering":
            face.set_emotion("curious", 0.8)
            face.look("up")
            face.subtitle = "remembering..."

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
            try:
                if args.text:
                    r, info = conv.ask(text=msg, on_status=status)
                else:
                    r, info = conv.ask(wav=wav, on_status=status)
            except MistralError as e:
                print("  error:", e)
                face.set_emotion("sad", 0.6)
                loop.say(["Oops, I", "couldn't think"])
                continue
            times = " + ".join(f"{t:.1f}" for t in info["times"])
            print(f"  model {client.model}, JSON mode {'on' if client.json_mode else 'off'}, "
                  f"{times} s, valid JSON: {r.ok}, history {len(conv.stm.turns)} turns")
            for raw in info["raw"]:
                print(f"  raw: {' '.join(raw.split())[:400]}")
            for line in info["log"]:
                print(f"  memory: {line}")
            print(f"  heard ({r.lang}): {info['heard']}")
            print(f"  -> {r.emotion} ({r.intensity:.1f}), action {r.action}, look {r.look}")
            print(f"     say: {r.say}")
            print(f"     screen: {r.screen}")
            face.set_emotion(r.emotion, r.intensity)
            face.do(r.action)
            face.look(r.look)
            spoken = False
            if tts and r.say:
                try:
                    voice = cfg.get(f"VOICE_{r.lang.upper()}") or cfg["VOICE"]
                    audio, tts_s = client.speech(r.say, voice, cfg["TTS_MODEL"])
                    x, rate = decode(audio)
                    t_fx = time.monotonic()
                    x = voicefx.apply(x, rate, cfg["VOICE_FX"], cfg["VOICE_PITCH"] or None)
                    print(f"     voice: {tts_s:.1f} s TTS + {time.monotonic() - t_fx:.2f} s fx, "
                          f"{len(x) / rate:.1f} s of audio ({rate} Hz, field '{client.tts_voice_key}')")
                    player.play(x, rate)
                    loop.say(r.screen, duration=len(x) / rate)
                    spoken = True
                except (MistralError, ValueError) as e:
                    print("     voice failed:", e)
            if not spoken:
                loop.say(r.screen)
    except (KeyboardInterrupt, EOFError):
        print()
    finally:
        loop.running = False
        loop.join(timeout=2)


if __name__ == "__main__":
    main()
