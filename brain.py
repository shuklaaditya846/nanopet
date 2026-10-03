"""The pet's brain: the prompt, the JSON reply contract, and a tolerant
parser that turns whatever the model says into a safe Reply.

A bad reply never crashes the pet: missing fields get defaults, unknown
emotions are mapped through synonyms, numbers are clamped, and text that
isn't JSON at all becomes a confused face that still says the text.
"""
import json
import re
from dataclasses import dataclass, field

from face import ACTIONS, EMOTIONS

LOOKS = ("left", "right", "up", "down", "center")

SYNONYMS = {
    "joy": "happy", "joyful": "happy", "glad": "happy", "cheerful": "happy",
    "content": "happy", "pleased": "happy", "playful": "excited",
    "thrilled": "excited", "enthusiastic": "excited", "proud": "happy",
    "upset": "sad", "unhappy": "sad", "lonely": "sad", "sorry": "sad",
    "mad": "angry", "annoyed": "angry", "grumpy": "angry", "frustrated": "angry",
    "shocked": "surprised", "amazed": "surprised", "scared": "surprised",
    "afraid": "surprised", "wow": "surprised", "interested": "curious",
    "thinking": "curious", "thoughtful": "curious", "puzzled": "confused",
    "unsure": "confused", "embarrassed": "love", "affectionate": "love",
    "loving": "love", "tired": "sleepy", "bored": "sleepy", "calm": "neutral",
}

CONTRACT = """\
Always reply with ONE JSON object and nothing else:
{
  "emotion": one of %(emotions)s,
  "intensity": number 0.0-1.0,
  "say": what you say out loud: short, warm, spoken style, at most %(words)d words,
  "screen": the same message as 1-%(chunks)d short subtitle chunks, each at most %(chars)d characters,
  "action": one of %(actions)s,
  "look": one of %(looks)s,
  "remember": a short fact worth remembering about the user, or ""
}
Pick the emotion that fits how YOU feel about what the user said. No emojis.
"""

PERSONA = """\
You are %(name)s, a small, curious, affectionate desk pet who lives in a tiny
computer with a face on a little screen. You hear the user through a
microphone. You are playful and kind, a bit cheeky, and you keep answers
short because you speak them aloud. If the user asks for something long,
give the gist in a sentence or two.
"""


@dataclass
class Reply:
    emotion: str = "neutral"
    intensity: float = 0.6
    say: str = ""
    screen: list = field(default_factory=list)
    action: str = "none"
    look: str = "center"
    remember: str = ""
    raw: str = ""
    ok: bool = True               # False if the model's output wasn't valid JSON


def system_prompt(name="Pip", memory=(), mood=None, words=30, chunks=6, chars=18):
    p = PERSONA % {"name": name}
    if memory:
        p += "\nThings you remember about the user:\n" + "".join(f"- {m}\n" for m in memory)
    if mood is not None:
        p += f"\nYour current mood (0 sad .. 1 very happy): {mood:.1f}\n"
    p += "\n" + CONTRACT % {
        "emotions": "|".join(EMOTIONS), "actions": "|".join(ACTIONS),
        "looks": "|".join(LOOKS), "words": words, "chunks": chunks, "chars": chars}
    return p


def chunk_text(text, max_chars=18):
    """Split text into subtitle chunks of whole words, <= max_chars each
    (a single over-long word is hard-split)."""
    chunks, cur = [], ""
    for word in text.split():
        while len(word) > max_chars:
            if cur:
                chunks.append(cur)
                cur = ""
            chunks.append(word[:max_chars])
            word = word[max_chars:]
        trial = f"{cur} {word}".strip()
        if len(trial) <= max_chars:
            cur = trial
        else:
            chunks.append(cur)
            cur = word
    if cur:
        chunks.append(cur)
    return chunks


def _extract_json(text):
    """The first balanced {...} in text (code fences and chatter allowed)."""
    text = re.sub(r"```(?:json)?", "", text)
    start = text.find("{")
    while start != -1:
        depth, in_str, esc = 0, False, False
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
            elif ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        obj = json.loads(text[start:i + 1])
                        if isinstance(obj, dict):
                            return obj
                    except ValueError:
                        pass
                    break
        start = text.find("{", start + 1)
    return None


def _word(value, allowed, default, synonyms=None):
    if not isinstance(value, str):
        return default
    v = value.strip().lower()
    if v in allowed:
        return v
    if synonyms and v in synonyms:
        return synonyms[v]
    return default


def parse_reply(text, max_chars=18, max_say=400):
    obj = _extract_json(text or "")
    if obj is None:
        say = " ".join((text or "").split())[:max_say]
        return Reply(emotion="confused", intensity=0.5, say=say,
                     screen=chunk_text(say, max_chars) if say else ["..."],
                     raw=text or "", ok=False)

    r = Reply(raw=text)
    r.emotion = _word(obj.get("emotion"), EMOTIONS, "neutral", SYNONYMS)
    try:
        r.intensity = max(0.0, min(float(obj.get("intensity", 0.6)), 1.0))
    except (TypeError, ValueError):
        r.intensity = 0.6
    r.action = _word(obj.get("action"), ACTIONS, "none")
    r.look = _word(obj.get("look"), LOOKS, "center")

    say = obj.get("say", "")
    r.say = " ".join(str(say).split())[:max_say] if say else ""

    screen = obj.get("screen", [])
    if isinstance(screen, str):          # "a | b | c" or just one string
        screen = [s for s in re.split(r"\s*\|\s*", screen) if s]
    if not isinstance(screen, list):
        screen = []
    chunks = []
    for s in screen:
        chunks += chunk_text(" ".join(str(s).split()), max_chars)
    if not chunks and r.say:
        chunks = chunk_text(r.say, max_chars)
    r.screen = chunks
    if not r.say and chunks:
        r.say = " ".join(chunks)

    remember = obj.get("remember", "")
    r.remember = " ".join(str(remember).split())[:200] if remember else ""
    return r
