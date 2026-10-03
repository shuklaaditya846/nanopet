"""What the pet remembers between runs: facts about the user, its name,
and its mood. A small JSON file, written atomically."""
import json
import os
import tempfile

DEFAULT_PATH = "/var/lib/nanopet/memory.json"


class Memory:
    MAX_FACTS = 25

    def __init__(self, path=DEFAULT_PATH):
        self.path = path
        self.name = "Pip"
        self.facts = []
        self.mood = 0.6
        try:
            with open(path) as f:
                d = json.load(f)
            self.name = d.get("name", self.name)
            self.facts = [str(x) for x in d.get("facts", [])][-self.MAX_FACTS:]
            self.mood = float(d.get("mood", self.mood))
        except (OSError, ValueError):
            pass

    def remember(self, fact):
        fact = " ".join(str(fact).split())
        if not fact:
            return False
        low = fact.lower()
        if any(low == f.lower() for f in self.facts):
            return False
        self.facts.append(fact)
        self.facts = self.facts[-self.MAX_FACTS:]
        self.save()
        return True

    def nudge_mood(self, delta):
        self.mood = max(0.0, min(1.0, self.mood + delta))

    def save(self):
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        data = {"name": self.name, "facts": self.facts, "mood": round(self.mood, 3)}
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(self.path) or ".")
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=1)
        os.replace(tmp, self.path)
