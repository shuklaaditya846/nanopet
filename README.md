# nanopet

A desk pet for the NanoPi NEO Air: an animated face on the ST7789 that will
listen, think and talk. See [PLAN.md](PLAN.md) for the design and milestones.

**Status: milestone 4, the voice.** Talk to it: it reacts with emotions and
actions and answers out loud through the USB sound card, with lip-sync and
timed subtitles.

It runs on the stock `nanopi-system` image, so no re-flash is needed:
numpy for drawing, plus a font atlas built on the laptop.

```sh
./deploy.sh root@192.168.29.120
ssh -t root@192.168.29.120 python3 /opt/nanopet/demo_face.py
```

| Keys | |
|---|---|
| `1`-`9`, `0` | neutral, happy, excited, sad, angry, surprised, curious, confused, love, sleepy |
| `b w n s k` | bounce, wiggle, nod, shake, wink |
| `h p` | hearts, sparkles |
| `i j l m c` | look up / left / right / down / centre |
| `t` | fake talking: mouth flaps, subtitles cycle |
| `a` | auto-cycle the emotions |
| `q` | quit |

`demo_face.py --bench` times the rendering alone, with no LCD needed.

### Voice check

```sh
ssh root@192.168.29.120 python3 /opt/nanopet/say.py "Hi, I'm Pip!"
ssh root@192.168.29.120 python3 /opt/nanopet/say.py --voice gb_jane_neutral "Another voice"
ssh root@192.168.29.120 python3 /opt/nanopet/say.py --voices    # try to list the voices
```

Pip's voice is a Mistral preset voice (`VOICE`, default `gb_jane_neutral`)
run through `voicefx.py`, which turns it into a small cute robot. Presets
(`VOICE_FX`):
- `cute_robot` (default): pitch ×1.45, ring modulation, metallic comb, light bit-crush
- `robot`: same pitch, heavier buzz
- `chipmunk`: pitch ×1.7, clean
- `none`

`VOICE_PITCH` overrides the pitch. Try combinations with
`say.py --fx robot --pitch 1.3 "Beep boop"`, then set them in
`/etc/nanopet.conf`. `TTS=0` gives subtitles only.

### Brain + voice demo (needs your Mistral key)

```sh
ssh -t root@192.168.29.120 python3 /opt/nanopet/demo_brain.py          # Enter = talk / send
ssh -t root@192.168.29.120 python3 /opt/nanopet/demo_brain.py --text   # type instead
```

The key comes from `/etc/nanopet.conf`, falling back to ptt-assistant's
`/etc/assistant.conf`. Every turn prints the raw model output, whether JSON
mode was accepted, what Pip heard, any memory activity, and the latency.

### Languages

Pip answers in whatever language you speak. The reply carries `lang` (an ISO
code). `say` is in that language's real script, because it's spoken, while
`screen` is always Latin script, because that's all the LCD font can draw:
accented European languages show as-is, and Hindi or other non-Latin scripts
show romanised ("Namaste! Main Pip hoon"). Subtitle chunks the font can't draw
are skipped. A per-language voice can be set with `VOICE_<LANG>=...`, e.g.
`VOICE_FR=fr_marie_neutral`; otherwise the default voice speaks every language.

### Memory

- **Long-term:** notes files, one per topic, in `/var/lib/nanopet/notes/`
  (e.g. `user.md`: `- [2026-10-03] name is Aditya`). The model saves facts with
  `memory_write: [{"topic", "note"}]`. When it needs a note that isn't in the
  conversation, it sends `memory_read: ["topic", ...]`: the pet reads those
  files, sends them back, and takes the second reply as the answer (one extra
  round trip, only when needed). The system prompt lists the topics and their
  note counts. Each topic is capped at 3 KB (the oldest notes drop out), 16 topics.
- **Short-term:** the conversation as `(user said, Pip said)` pairs only. The
  model transcribes what it heard into `heard`, so emotions and actions are not
  kept. Last `HISTORY_TURNS` (8) exchanges, trimmed to a size budget, forgotten
  after `HISTORY_IDLE_MIN` (15) minutes of silence.

To make it forget everything: `rm -r /var/lib/nanopet/notes`.

The model must reply with one JSON object (emotion, intensity, say, screen,
action, look, remember; see PLAN.md). `brain.py` parses it tolerantly:
- code fences and chatter around the JSON are stripped
- synonyms are mapped ("joyful" → happy)
- values are clamped, and over-long subtitle chunks are re-split
- plain text becomes a confused face that still shows the text

`tests/test_brain.py` covers all of this, plus the client's automatic
JSON-mode fallback.

## Files

| File | |
|---|---|
| `face.py` | face parameters, emotion presets, idle life (blink, glance, breathe), actions, particles, rendering |
| `gfx.py` | anti-aliased shapes on a numpy RGB canvas (signed-distance fields), RGB565 output |
| `font.py` | text from the glyph atlas |
| `fb.py` | `/dev/fb0` output: console in graphics mode, writes only the changed rows |
| `demo_face.py` | keyboard demo and benchmark |
| `brain.py` | persona prompt, JSON reply contract, tolerant parser, subtitle chunking |
| `mistral.py` | chat with audio or text, JSON mode with automatic fallback, model fallback |
| `memory.py` | long-term notes per topic, short-term (heard, said) history, name and mood |
| `conversation.py` | one turn: history + audio → reply, memory writes, memory-read round trip |
| `voicefx.py` | cute-robot voice: pitch shift, ring mod, comb, bit-crush (numpy) |
| `common.py` | config, clock bootstrap, microphone recorder |
| `demo_brain.py` | talk → reaction + spoken answer, with lip-sync and timed subtitles |
| `speech.py` | decodes TTS audio (WAV / float PCM), loudness envelope, USB playback |
| `say.py` | speak one sentence; voice check and voice list |
| `tools/make_font.py` | laptop: TrueType → `assets/font.npz` (Noto Sans Bold 22/36 px) |
| `tools/preview.py` | laptop: all emotions in one PNG contact sheet |
