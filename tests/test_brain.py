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
from conversation import Conversation                       # noqa: E402
from memory import LongTermMemory, PetState, ShortTermMemory, topic_name   # noqa: E402

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
      and r.look == "up" and r.screen == ["Hi!", "I'm Pip."]
      and r.memory_write == [("user", "likes cats")])          # legacy "remember"
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
check("wrong types survive", r.intensity == 0.6 and r.screen == [] and r.memory_write == [])
r = parse_reply(json.dumps({"heard": "  what's  my name? ", "say": "",
                            "memory_read": ["user", "", "people"],
                            "memory_write": [{"topic": "user", "note": "asked about name"},
                                             {"topic": "x"}, "loose note"]}))
check("heard / memory_read / memory_write parsed",
      r.heard == "what's my name?" and r.memory_read == ["user", "people"]
      and r.memory_write == [("user", "asked about name"), ("misc", "loose note")])
r = parse_reply('{"memory_read": "user", "memory_write": {"topic": "pets", "note": "has a cat"}}')
check("single string / single object forms", r.memory_read == ["user"]
      and r.memory_write == [("pets", "has a cat")])
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

print("system_prompt")
p = system_prompt("Pip", {"user": 3, "preferences": 1}, 0.8)
check("prompt has name, topics, contract, memory rules",
      "Pip" in p and "user (3 notes)" in p and '"memory_read"' in p and "sleepy" in p)
check("empty memory is announced", "memory is empty" in system_prompt("Pip", {}))

print("long-term memory")
with tempfile.TemporaryDirectory() as d:
    ltm = LongTermMemory(os.path.join(d, "notes"))
    check("append creates topic", ltm.append("User", "name is Aditya"))
    check("dedupe (case/space-insensitive)", not ltm.append("user", "Name  is ADITYA"))
    ltm.append("preferences", "likes cats")
    check("topics with counts", ltm.topics() == {"preferences": 1, "user": 1})
    out = ltm.read(["user", "nope"])
    check("read returns notes, reports missing", "name is Aditya" in out and "## nope" in out)
    check("unsafe topic names sanitised", topic_name("../../etc/passwd") == "etc_passwd")
    ltm.append("../evil", "x")
    check("no file escapes the notes dir", sorted(os.listdir(os.path.join(d, "notes")))
          == ["evil.md", "preferences.md", "user.md"])
    for i in range(300):
        ltm.append("log", f"event number {i} with some padding text")
    size = os.path.getsize(os.path.join(d, "notes", "log.md"))
    check("per-topic size cap drops the oldest", size <= LongTermMemory.MAX_FILE_BYTES + 80
          and "event number 299" in ltm.read(["log"]) and "event number 0 " not in ltm.read(["log"]))
    st = PetState(os.path.join(d, "state.json"))
    st.nudge_mood(+5)
    st.save()
    check("state persists", PetState(os.path.join(d, "state.json")).mood == 1.0)

print("short-term memory")
stm = ShortTermMemory(max_turns=3, max_chars_each=20, budget_chars=60, idle_reset_s=60)
for i in range(5):
    stm.add(f"question {i}", f"answer {i}")
m = stm.messages()
check("keeps only the last N turns, as user/assistant pairs",
      [x["content"] for x in m] == ["question 2", "answer 2", "question 3", "answer 3",
                                    "question 4", "answer 4"])
stm.add("x" * 100, "y" * 100)
check("each text trimmed, budget respected",
      all(len(x["content"]) <= 20 for x in stm.messages())
      and sum(len(x["content"]) for x in stm.messages()) <= 80)
stm.last -= 61
check("forgotten after idle time", stm.messages() == [])


class FakeClient:
    """Answers with a memory_read first, then a real reply."""

    def __init__(self, replies):
        self.replies, self.calls = list(replies), []

    @staticmethod
    def audio_parts(wav, instruction):
        return [{"type": "input_audio", "input_audio": "AAAA"},
                {"type": "text", "text": instruction}]

    def chat(self, messages):
        self.calls.append(messages)
        return self.replies.pop(0), 0.1


print("conversation")
with tempfile.TemporaryDirectory() as d:
    ltm = LongTermMemory(os.path.join(d, "notes"))
    ltm.append("user", "name is Aditya")
    client = FakeClient([
        json.dumps({"heard": "what's my name", "say": "", "memory_read": ["user"],
                    "memory_write": []}),
        json.dumps({"heard": "", "say": "You're Aditya!", "emotion": "happy",
                    "memory_write": [{"topic": "events", "note": "asked for name"}]}),
        json.dumps({"heard": "thanks", "say": "Anytime!"}),
    ])
    conv = Conversation(client, ltm, ShortTermMemory(), PetState(os.path.join(d, "s.json")))
    statuses = []
    r, info = conv.ask(wav=b"RIFF", on_status=statuses.append)
    follow = client.calls[1][-1]["content"]
    check("memory_read triggers a second call with the notes",
          len(client.calls) == 2 and "name is Aditya" in follow and "memory_read must be []" in follow)
    check("final reply used, heard carried over, status shown",
          r.say == "You're Aditya!" and info["heard"] == "what's my name"
          and statuses == ["remembering"])
    check("writes from the second reply saved", ltm.topics().get("events") == 1)
    r, info = conv.ask(text="thanks")
    hist = client.calls[2][1:-1]
    check("history sent as plain user/assistant text",
          [h["content"] for h in hist] == ["what's my name", "You're Aditya!"])
    check("system prompt lists memory topics", "events (1 notes)" in client.calls[2][0]["content"])

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
