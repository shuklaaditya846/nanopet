# nanopet

A desk pet for the NanoPi NEO Air: an animated face on the ST7789 that will
listen, think and talk. See [PLAN.md](PLAN.md) for the design and milestones.

**Status: milestone 2, the face demo.** No AI yet.

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

## Files

| File | |
|---|---|
| `face.py` | face parameters, emotion presets, idle life (blink, glance, breathe), actions, particles, rendering |
| `gfx.py` | anti-aliased shapes on a numpy RGB canvas (signed-distance fields), RGB565 output |
| `font.py` | text from the glyph atlas |
| `fb.py` | `/dev/fb0` output: console in graphics mode, writes only the changed rows |
| `demo_face.py` | keyboard demo and benchmark |
| `tools/make_font.py` | laptop: TrueType → `assets/font.npz` (Noto Sans Bold 22/36 px) |
| `tools/preview.py` | laptop: all emotions in one PNG contact sheet |
