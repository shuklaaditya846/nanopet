"""Pip's memory.

Long-term: small notes files, one per topic, in a directory on the board
(e.g. /var/lib/nanopet/notes/user.md). The model asks to read topics or
append notes through its JSON reply (memory_read / memory_write); the
system prompt lists which topics exist so it knows when a read is useful.

Short-term: the conversation history as (user said, Pip said) pairs only;
no emotions or actions. Last N turns, each trimmed, with a total size
budget, and forgotten after a stretch of silence (a new conversation).

State: the pet's name and mood, a tiny JSON file.
"""
import json
import os
import re
import tempfile
import time
from collections import deque

DATA_DIR = "/var/lib/nanopet"


def _atomic_write(path, text):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path) or ".")
    with os.fdopen(fd, "w") as f:
        f.write(text)
    os.replace(tmp, path)


def topic_name(name):
    """Sanitise a topic into a safe file name: lowercase [a-z0-9_-]."""
    t = re.sub(r"[^a-z0-9_-]+", "_", str(name).strip().lower()).strip("_-")
    return t[:32]


class LongTermMemory:
    MAX_TOPICS = 16
    MAX_FILE_BYTES = 3000           # per topic: oldest notes drop out first
    MAX_READ_BYTES = 6000           # per read request, across topics

    def __init__(self, directory=os.path.join(DATA_DIR, "notes")):
        self.dir = directory

    def _path(self, topic):
        return os.path.join(self.dir, f"{topic}.md")

    def topics(self):
        """{topic: number of notes}"""
        out = {}
        try:
            for fn in sorted(os.listdir(self.dir)):
                if fn.endswith(".md"):
                    with open(os.path.join(self.dir, fn)) as f:
                        out[fn[:-3]] = sum(1 for line in f if line.startswith("- "))
        except OSError:
            pass
        return out

    def read(self, topics):
        """Contents of the requested topics (unknown ones are reported)."""
        parts, budget = [], self.MAX_READ_BYTES
        for raw in topics:
            t = topic_name(raw)
            if not t:
                continue
            try:
                with open(self._path(t)) as f:
                    text = f.read().strip()
            except OSError:
                parts.append(f"## {t}\n(no notes)")
                continue
            text = text[-budget:] if len(text) > budget else text
            budget -= len(text)
            parts.append(f"## {t}\n{text}")
            if budget <= 0:
                break
        return "\n\n".join(parts) if parts else "(nothing requested)"

    def append(self, topic, note):
        """Append one dated note; returns False if it was empty or a duplicate."""
        t = topic_name(topic) or "misc"
        note = " ".join(str(note).split())[:200]
        if not note:
            return False
        existing = self.topics()
        if t not in existing and len(existing) >= self.MAX_TOPICS:
            t = "misc"
        path = self._path(t)
        try:
            with open(path) as f:
                lines = f.read().splitlines()
        except OSError:
            lines = []
        if any(line.split("] ", 1)[-1].lower() == note.lower() for line in lines):
            return False
        lines.append(f"- [{time.strftime('%Y-%m-%d')}] {note}")
        while len("\n".join(lines)) > self.MAX_FILE_BYTES and len(lines) > 1:
            lines.pop(0)
        _atomic_write(path, "\n".join(lines) + "\n")
        return True


class ShortTermMemory:
    def __init__(self, max_turns=8, max_chars_each=300, budget_chars=2400,
                 idle_reset_s=15 * 60):
        self.turns = deque(maxlen=max_turns)
        self.max_each, self.budget, self.idle = max_chars_each, budget_chars, idle_reset_s
        self.last = 0.0

    def _expire(self):
        if self.turns and time.monotonic() - self.last > self.idle:
            self.turns.clear()

    def add(self, heard, said):
        self._expire()
        heard = " ".join(str(heard).split())[:self.max_each]
        said = " ".join(str(said).split())[:self.max_each]
        if heard or said:
            self.turns.append((heard or "(unclear)", said or "(no answer)"))
        self.last = time.monotonic()

    def messages(self):
        """Chat messages for the remembered turns, newest kept within budget."""
        self._expire()
        picked, used = [], 0
        for heard, said in reversed(self.turns):
            used += len(heard) + len(said)
            if used > self.budget and picked:
                break
            picked.append((heard, said))
        msgs = []
        for heard, said in reversed(picked):
            msgs.append({"role": "user", "content": heard})
            msgs.append({"role": "assistant", "content": said})
        return msgs

    def clear(self):
        self.turns.clear()


class PetState:
    def __init__(self, path=os.path.join(DATA_DIR, "state.json")):
        self.path = path
        self.name, self.mood = "Pip", 0.6
        try:
            with open(path) as f:
                d = json.load(f)
            self.name = d.get("name", self.name)
            self.mood = float(d.get("mood", self.mood))
        except (OSError, ValueError):
            pass

    def nudge_mood(self, delta):
        self.mood = max(0.0, min(1.0, self.mood + delta))

    def save(self):
        _atomic_write(self.path, json.dumps({"name": self.name, "mood": round(self.mood, 3)}))
