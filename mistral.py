"""Mistral API client (plain requests): chat with audio or text input,
optional JSON mode. Text-to-speech arrives in milestone 4.

Chat with audio (docs.mistral.ai, audio input):
  POST /v1/chat/completions
  messages: [{"role": "user", "content": [
      {"type": "input_audio", "input_audio": "<base64 audio file>"},
      {"type": "text", "text": "..."}]}]
"""
import base64
import os
import time

import requests

API_BASE = os.environ.get("MISTRAL_API_BASE", "https://api.mistral.ai/v1")


class MistralError(Exception):
    pass


class Mistral:
    def __init__(self, api_key, model, timeout=60):
        self.model = model
        self.timeout = timeout
        self.json_mode = True          # switched off if the model rejects it
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {api_key}",
                                     "Content-Type": "application/json"})

    def _post(self, path, payload):
        r = self.session.post(API_BASE + path, json=payload, timeout=self.timeout)
        if r.status_code == 401:
            raise MistralError("API key rejected (401): check the config file")
        if r.status_code >= 400:
            raise MistralError(f"HTTP {r.status_code}: {r.text[:300]}")
        return r.json()

    def list_models(self):
        r = self.session.get(API_BASE + "/models", timeout=self.timeout)
        r.raise_for_status()
        return [m["id"] for m in r.json().get("data", [])]

    def pick_voxtral_chat_model(self):
        ids = self.list_models()
        cands = [i for i in ids if "voxtral" in i and not any(
            x in i for x in ("transcribe", "tts", "realtime"))]
        cands.sort(key=lambda i: ("small" not in i, "latest" not in i, i))
        if not cands:
            raise MistralError("no Voxtral chat model available")
        return cands[0]

    def chat(self, messages, max_tokens=400, temperature=0.7):
        """messages: full chat message list. Returns (text, seconds)."""
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        t0 = time.monotonic()
        for _ in range(3):              # at most: drop JSON mode, switch model
            if self.json_mode:
                payload["response_format"] = {"type": "json_object"}
            else:
                payload.pop("response_format", None)
            payload["model"] = self.model
            try:
                data = self._post("/chat/completions", payload)
                break
            except MistralError as e:
                msg = str(e).lower()
                if "401" in msg:
                    raise
                if self.json_mode and ("response_format" in msg or "json" in msg):
                    self.json_mode = False          # model can't do JSON mode
                    continue
                if "model" in msg:
                    new = self.pick_voxtral_chat_model()
                    if new != self.model:
                        print(f"[model {self.model!r} rejected, using {new!r}]")
                        self.model = new
                        continue
                raise
        else:
            raise MistralError("chat request kept failing")
        content = data["choices"][0]["message"]["content"]
        if isinstance(content, list):
            content = "".join(c.get("text", "") for c in content if isinstance(c, dict))
        return content, time.monotonic() - t0

    # --- text to speech ------------------------------------------------------
    # POST /v1/audio/speech {model, input, voice|voice_id, response_format}.
    # Sources disagree on the voice field name and on whether audio comes
    # back raw or base64 in JSON ("audio_data"), so both are handled and the
    # working voice field is remembered.
    tts_voice_key = None

    def speech(self, text, voice, model="voxtral-mini-tts-2603", fmt="wav"):
        """Returns (audio bytes in format fmt, seconds)."""
        t0 = time.monotonic()
        keys = [self.tts_voice_key] if self.tts_voice_key else ["voice", "voice_id"]
        last = None
        for key in keys:
            payload = {"model": model, "input": text, "response_format": fmt}
            if voice:
                payload[key] = voice
            r = self.session.post(API_BASE + "/audio/speech", json=payload,
                                  timeout=self.timeout)
            if r.status_code == 401:
                raise MistralError("API key rejected (401)")
            if r.status_code >= 400:
                last = MistralError(f"TTS HTTP {r.status_code}: {r.text[:300]}")
                if "voice" in r.text.lower() and key != keys[-1]:
                    continue            # wrong field name: try the other one
                raise last
            self.tts_voice_key = key
            ctype = r.headers.get("Content-Type", "")
            if "json" in ctype:
                data = r.json()
                b64 = data.get("audio_data") or data.get("audio") or data.get("data")
                if not b64:
                    raise MistralError(f"TTS: no audio in JSON reply: {str(data)[:200]}")
                return base64.b64decode(b64), time.monotonic() - t0
            return r.content, time.monotonic() - t0
        raise last or MistralError("TTS failed")

    @staticmethod
    def audio_parts(wav_bytes, instruction):
        b64 = base64.b64encode(wav_bytes).decode("ascii")
        return [{"type": "input_audio", "input_audio": b64},
                {"type": "text", "text": instruction}]

    def chat_audio(self, system_prompt, wav_bytes, instruction, history=(), **kw):
        msgs = [{"role": "system", "content": system_prompt}, *history,
                {"role": "user", "content": self.audio_parts(wav_bytes, instruction)}]
        return self.chat(msgs, **kw)

    def chat_text(self, system_prompt, text, history=(), **kw):
        msgs = [{"role": "system", "content": system_prompt}, *history,
                {"role": "user", "content": text}]
        return self.chat(msgs, **kw)
