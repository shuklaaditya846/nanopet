"""One conversational turn with memory, used by the demos and the pet.

    send history + the new audio/text  ->  reply JSON
    apply memory_write notes
    if memory_read: read those topics, send them back, take the second reply
    remember (heard, said) in the short-term history
"""
import time

from brain import followup_text, parse_reply, system_prompt
from memory import LongTermMemory, PetState, ShortTermMemory

INSTRUCTION = "The audio is the user speaking to you. Reply as specified."


class Conversation:
    def __init__(self, client, long_term=None, short_term=None, state=None):
        self.client = client
        self.ltm = long_term or LongTermMemory()
        self.stm = short_term or ShortTermMemory()
        self.state = state or PetState()

    def _apply_writes(self, reply, log):
        for topic, note in reply.memory_write:
            if self.ltm.append(topic, note):
                log.append(f"saved to {topic}: {note}")

    def ask(self, wav=None, text=None, on_status=None):
        """Returns (Reply, info dict with timings, raw outputs, memory log)."""
        info = {"log": [], "raw": [], "times": []}
        system = {"role": "system",
                  "content": system_prompt(self.state.name, self.ltm.topics(), self.state.mood)}
        user = {"role": "user",
                "content": self.client.audio_parts(wav, INSTRUCTION) if wav is not None else text}
        msgs = [system, *self.stm.messages(), user]

        raw, took = self.client.chat(msgs)
        info["raw"].append(raw)
        info["times"].append(took)
        reply = parse_reply(raw)
        self._apply_writes(reply, info["log"])

        if reply.memory_read:
            if on_status:
                on_status("remembering")
            notes = self.ltm.read(reply.memory_read)
            info["log"].append(f"read {', '.join(reply.memory_read)}")
            msgs += [{"role": "assistant", "content": raw},
                     {"role": "user", "content": followup_text(notes)}]
            raw2, took2 = self.client.chat(msgs)
            info["raw"].append(raw2)
            info["times"].append(took2)
            second = parse_reply(raw2)
            second.heard = second.heard or reply.heard
            second.memory_read = []
            self._apply_writes(second, info["log"])
            reply = second

        heard = reply.heard or (text or "")
        self.stm.add(heard, reply.say)
        info["heard"] = heard
        info["at"] = time.time()
        return reply, info
