# nanopet: plan

A desk-pet voice assistant for the NanoPi NEO Air. It has an animated face on
the ST7789, listens through the INMP441, talks through the USB sound card, and
reacts with emotions driven by the AI's structured replies.

## Decisions

| | Choice |
|---|---|
| Hearing | Voxtral chat with audio input: no separate speech-to-text step (as in ptt-assistant) |
| Voice | **Mistral Voxtral TTS**, streamed as PCM (~0.8 s to first audio), with **espeak-ng** on the board as the offline fallback |
| Subtitles | always shown: short chunks (≤ ~14 characters) timed to the speech |
| Speaker | USB sound card (works today); an I2S amp (MAX98357A) is a later option |
| Code | new repo `nanopet`; reuses the GPIO, recorder and Mistral client code from `ptt-assistant` |

## Turn pipeline

```
hold knob ─▶ record (arecord -D mic, 16 kHz)            face: "listening" (ears up, eyes wide)
release   ─▶ Voxtral chat (audio in, JSON out)          face: "thinking" (eyes up, dots)
          ─▶ parse JSON → emotion, action, look          face: blends to the emotion
          ─▶ Voxtral TTS (stream PCM 24 kHz) ─▶ aplay    mouth follows the audio loudness
          ─▶ subtitles: screen[] chunks timed to the audio
idle      ─▶ blink, glance, breathe, get sleepy, wake on knob
```

## Reply contract (JSON)

```json
{
  "emotion": "happy",
  "intensity": 0.8,
  "say": "Hi! I'm Pip. Want to hear a joke?",
  "screen": ["Hi! I'm Pip", "Joke time?"],
  "action": "bounce",
  "look": "up",
  "remember": "user's name is Aditya"
}
```

| Field | Values | Default if missing or invalid |
|---|---|---|
| `emotion` | happy, sad, surprised, angry, sleepy, curious, love, confused, excited, neutral | neutral |
| `intensity` | 0.0–1.0 | 0.6 |
| `say` | spoken text, ≤ ~25 words | `screen` joined, else nothing |
| `screen` | subtitle chunks, ≤ ~14 characters each | derived from `say` by word-wrapping |
| `action` | none, bounce, wiggle, wink, nod, shake, sparkle, hearts | none |
| `look` | left, right, up, down, center | center |
| `remember` | a fact worth keeping | nothing saved |

Try Mistral's JSON mode (`response_format`) first. If Voxtral-with-audio
rejects it, rely on the prompt plus a tolerant parser: pull out the first
`{...}`, ignore unknown fields, and clamp values. A bad reply never crashes the
pet; it just looks confused.

## The face

Drawn procedurally with Pillow, at 320×240.

- **Parameters** (the face blends smoothly between targets): eye openness, eye
  shape/curve, pupil position and size, eyebrow angle and height, mouth curve,
  openness and width, cheek blush, head offset (bounce/wiggle).
- **Each emotion** is one set of target parameters, scaled by `intensity`.
- **Idle:** random blinks, glances and slow breathing. After N minutes without
  interaction it gets sleepy (closed eyes, "z"); a knob turn wakes it up.
- **Talking:** mouth openness follows the RMS loudness of the audio being played.
- **Rendering:** stop the text console drawing over the face (`KDSETMODE
  KD_GRAPHICS` on tty1) and convert to RGB565 with numpy. Write only the rows
  that changed: fbtft sends just the dirty region over SPI.

## Controls (rotary encoder)

| Action | Effect |
|---|---|
| hold, speak, release | talk to the pet |
| turn | **pet it**: happiness goes up, hearts; while subtitles show, scroll back through them |
| tap | menu: personality, voice, volume, sleep |

## Pet state

A mood value (0–1) that rises with petting and chatting and slowly drifts back
to neutral. Memory (`remember` facts plus the pet's name) persists in a JSON
file and is added to the system prompt. Both decide the idle face and the tone
of replies.

## Milestones

1. **Image (`system` repo).** Add python-pillow + freetype, a TrueType font
   (DejaVu), espeak-ng and NTP; raise the ST7789 SPI clock to 62.5 MHz (try 80).
   One rebuild and re-flash.
2. **Face demo, no AI.** `face.py` plus a keyboard demo that cycles emotions,
   actions and blinking. Measure the frame rate on the board (target ≥ 15 FPS).
3. **Brain.** The JSON contract, prompt and tolerant parser, with tests on fake
   replies; then check JSON mode with the real key.
4. **Voice.** Streamed Voxtral TTS to the USB card, lip-sync, timed subtitles,
   espeak-ng fallback, latency measurements.
5. **Pet.** Petting, mood, sleep/wake, memory, menu.
6. **Autostart.** An init script, so it runs at boot with no laptop.

## Open questions to settle while building

- The exact TTS voice IDs available to this account, and the streaming wire
  format: check with the real key in milestone 4.
- Whether Voxtral accepts `response_format` together with audio input
  (milestone 3).
- The SPI clock this panel and its wiring can hold before artefacts appear
  (milestone 1).
