# nanopet

A desk pet for the NanoPi NEO Air: an animated face on the ST7789 that will
listen, think and talk. See [PLAN.md](PLAN.md) for the design and milestones.

**Status: milestone 3, the brain.** Talk to it and it reacts with emotions,
actions and subtitles. It doesn't speak yet: that's milestone 4.

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

### Brain demo (needs your Mistral key)

```sh
ssh -t root@192.168.29.120 python3 /opt/nanopet/demo_brain.py          # Enter = talk / send
ssh -t root@192.168.29.120 python3 /opt/nanopet/demo_brain.py --text   # type instead
```

The key comes from `/etc/nanopet.conf`, falling back to ptt-assistant's
`/etc/assistant.conf`. Every turn prints the raw model output, whether JSON
mode was accepted, the parsed reply, and the latency. Facts the pet chooses to
remember go to `/var/lib/nanopet/memory.json`.

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
| `memory.py` | remembered facts, the pet's name and mood (JSON file) |
| `common.py` | config, clock bootstrap, microphone recorder |
| `demo_brain.py` | talk → reaction demo (face thread + subtitle cycling) |
| `tools/make_font.py` | laptop: TrueType → `assets/font.npz` (Noto Sans Bold 22/36 px) |
| `tools/preview.py` | laptop: all emotions in one PNG contact sheet |
