#!/usr/bin/env python3
"""Brain tests, laptop only:  python3 tests/test_brain.py
(the mock-server part needs `requests`; it is skipped if missing)."""
import json
import os
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from brain import chunk_text, parse_reply, system_prompt   # noqa: E402
from memory import Memory                                   # noqa: E402

failures = 0


def check(name, cond):
    global failures
    print(("  ok   " if cond else "  FAIL ") + name)
    failures += 0 if cond else 1


print("parse_reply")
good = json.dumps({"emotion": "happy", "intensity": 0.9, "say": "Hi! I'm Pip.",
                   "screen": ["Hi!", "I'm Pip."], "action": "bounce", "look": "up",
                   "remember": "likes cats"})
r = parse_reply(good)
check("well-formed reply", r.ok and r.emotion == "happy" and r.action == "bounce"
      and r.look == "up" and r.screen == ["Hi!", "I'm Pip."] and r.remember == "likes cats")
r = parse_reply("Sure! ```json\n" + good + "\n``` hope that helps")
check("code fence + chatter", r.ok and r.emotion == "happy")
r = parse_reply('{"emotion": "joyful", "say": "a {brace} in text", "intensity": "7"}')
check("synonym + brace inside string + intensity clamped",
      r.emotion == "happy" and r.say == "a {brace} in text" and r.intensity == 1.0)
r = parse_reply('{"emotion": "melancholic", "action": "backflip", "look": "sideways"}')
check("unknown values fall back", (r.emotion, r.action, r.look) == ("neutral", "none", "center"))
r = parse_reply('{"say": "This is a rather long sentence for one subtitle chunk"}')
check("screen derived from say, chunks <= 18", r.screen and all(len(c) <= 18 for c in r.screen))
r = parse_reply('{"screen": "Hello there | how are you | today"}')
check("pipe-separated screen string", r.screen == ["Hello there", "how are you", "today"]
      and r.say == "Hello there how are you today")
r = parse_reply('{"screen": ["an extremely long chunk that does not fit"]}')
check("over-long chunks are re-split", len(r.screen) > 1 and all(len(c) <= 18 for c in r.screen))
r = parse_reply('{"intensity": null, "screen": 5, "remember": 42}')
check("wrong types survive", r.intensity == 0.6 and r.screen == [] and r.remember == "42")
r = parse_reply("I'm not JSON at all, just chatting.")
check("plain text -> confused, still spoken", not r.ok and r.emotion == "confused"
      and r.say.startswith("I'm not JSON") and r.screen)
r = parse_reply("")
check("empty reply", not r.ok and r.screen == ["..."])
r = parse_reply('{"broken": } {"emotion": "sad", "say": "second object"}')
check("skips a broken object, takes the next", r.ok and r.emotion == "sad")

print("chunk_text")
check("basic", chunk_text("one two three four", 9) == ["one two", "three", "four"])
check("hard split", chunk_text("supercalifragilistic", 8) == ["supercal", "ifragili", "stic"])

print("system_prompt / memory")
p = system_prompt("Pip", ["user is Aditya"], 0.8)
check("prompt has name, memory, contract",
      "Pip" in p and "user is Aditya" in p and '"emotion"' in p and "sleepy" in p)
with tempfile.TemporaryDirectory() as d:
    path = os.path.join(d, "sub", "memory.json")
    m = Memory(path)
    check("remember stores", m.remember("likes cats"))
    check("dedupe (case-insensitive)", not m.remember("Likes  CATS"))
    m.nudge_mood(+5)
    m.save()
    check("persists", Memory(path).facts == ["likes cats"] and Memory(path).mood == 1.0)

print("mistral client: JSON-mode fallback (mock server)")
try:
    import requests  # noqa: F401
except ImportError:
    print("  skip (no requests)")
else:
    import mistral
    seen = []

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            seen.append(body)
            if "response_format" in body:
                out, code = {"message": "response_format not supported with audio"}, 400
            else:
                out, code = {"choices": [{"message": {"content": good}}]}, 200
            data = json.dumps(out).encode()
            self.send_response(code)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    mistral.API_BASE = f"http://127.0.0.1:{srv.server_port}/v1"
    c = mistral.Mistral("key", "voxtral-small-latest")
    text, _ = c.chat_audio("sys", b"RIFFfake", "respond")
    check("retries without response_format", len(seen) == 2 and not c.json_mode
          and parse_reply(text).emotion == "happy")
    c.chat_text("sys", "hello")
    check("remembers JSON mode is off", "response_format" not in seen[-1])
    check("audio sent as input_audio",
          seen[0]["messages"][1]["content"][0]["type"] == "input_audio")
    srv.shutdown()

print(f"\n{'all passed' if not failures else f'{failures} FAILED'}")
sys.exit(1 if failures else 0)
