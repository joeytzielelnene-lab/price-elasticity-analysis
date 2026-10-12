# Boo-Boo's Halloween Night: video generator

This folder holds the code that renders the 4:00 LunaKids video: 1280×720, 24 fps, 100 BPM, with xylophone, glockenspiel, a spoken-chant narrator and sing-along captions. It follows the storyboard in `../boo-boo-halloween-night.md`.

| File | What it does |
|------|--------------|
| `song.py` | Bar map (100 bars = 240 s), chords, melodies, lyrics and their timings |
| `audio.py` | Synthesizes the music and the narrator/kids vocals (Piper TTS), then mixes them |
| `gfx.py` | Soft "clay 3D" shading plus every character and prop: Boo-Boo, Pip, Bella, Wanda, Mama/Papa Ghost, the owl, the cottage… |
| `render.py` | Backgrounds, shot-by-shot animation (15 scenes, 46 shots), karaoke captions, encoding |

## Rebuild

```bash
pip install numpy pillow piper-tts
mkdir -p assets out
# font: Fredoka 600 (OFL)
curl -L -o assets/fredoka.woff https://cdn.jsdelivr.net/npm/@fontsource/fredoka@5.0.0/files/fredoka-latin-600-normal.woff
# voice: Piper "amy" (en_US, medium)
for f in en_US-amy-medium.onnx en_US-amy-medium.onnx.json; do
  curl -L -o assets/$f https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/amy/medium/$f; done

LUNA_ASSETS=assets python audio.py out                         # ~3 min
python render.py assets out LunaKids_BooBoo_Halloween_Night.mp4  # ~20-30 min on 4 cores
# quick checks:
python render.py assets out still --stills 40,120,200            # single frames
python render.py assets out preview.mp4 --preview 28.8 48         # one section
```

## Upgrading the vocals

The narrator is text-to-speech, chanted on the beat. To make it a fully sung track, generate the song with an AI music tool using the lyrics and music prompt in the storyboard file, keep 100 BPM, and swap it in for `out/mix.wav` before encoding. Every scene is cut to the bar map, so a song with the same structure will line up.
