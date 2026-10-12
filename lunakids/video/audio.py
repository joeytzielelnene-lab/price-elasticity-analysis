"""Synthesize the soundtrack: xylophone + glockenspiel arrangement and spoken/chanted vocals.

Usage: python audio.py OUT_DIR
Writes music.wav, vocals.wav and mix.wav (44.1 kHz, 16-bit stereo) into OUT_DIR.
"""
import os
import subprocess
import sys
import tempfile
import wave

import numpy as np

import song
from song import BAR, BEAT, DURATION, SECTIONS, CHORDS, n

SR = 44100
HERE = os.path.dirname(os.path.abspath(__file__))
RNG = np.random.default_rng(7)


def hz(midi):
    return 440.0 * 2 ** ((midi - 69) / 12)


def add(buf, sig, t, gain=1.0, pan=0.0):
    """Mix mono `sig` into stereo `buf` at time t (seconds) with equal-power pan."""
    i = int(round(t * SR))
    if i >= buf.shape[1] or i + len(sig) <= 0:
        return
    j = min(buf.shape[1], i + len(sig))
    s = sig[: j - i] * gain
    a = (pan + 1) * np.pi / 4
    buf[0, i:j] += s * np.cos(a)
    buf[1, i:j] += s * np.sin(a)


# ------------------------------------------------------------------ instruments
def xylophone(f, dur=0.9):
    t = np.arange(int(dur * SR)) / SR
    s = (np.sin(2 * np.pi * f * t) * np.exp(-t * 6.5)
         + 0.28 * np.sin(2 * np.pi * f * 3.0 * t) * np.exp(-t * 14)
         + 0.07 * np.sin(2 * np.pi * f * 6.3 * t) * np.exp(-t * 30))
    click = RNG.standard_normal(int(0.006 * SR)) * np.linspace(1, 0, int(0.006 * SR)) * 0.12
    s[: len(click)] += click
    s *= np.minimum(1, t / 0.002)
    return s * 0.5


def glock(f, dur=2.0):
    t = np.arange(int(dur * SR)) / SR
    s = (np.sin(2 * np.pi * f * t) * np.exp(-t * 2.0)
         + 0.32 * np.sin(2 * np.pi * f * 2.756 * t) * np.exp(-t * 4.5)
         + 0.12 * np.sin(2 * np.pi * f * 5.404 * t) * np.exp(-t * 9))
    s *= np.minimum(1, t / 0.001)
    return s * 0.32


def bass(f, dur=1.0):
    t = np.arange(int(dur * SR)) / SR
    s = np.sin(2 * np.pi * f * t) + 0.3 * np.sin(4 * np.pi * f * t) * np.exp(-t * 6)
    return s * np.minimum(1, t / 0.008) * np.exp(-t * 2.6) * 0.42


def pad(freqs, dur):
    t = np.arange(int(dur * SR)) / SR
    s = np.zeros_like(t)
    for f in freqs:
        for det in (0.998, 1.002):
            s += np.sin(2 * np.pi * f * det * t) + 0.15 * np.sin(2 * np.pi * 3 * f * det * t)
    env = np.minimum(1, t / 0.35) * np.minimum(1, (dur - t) / 0.4)
    return s * env * 0.022


def shaker(accent=1.0):
    k = int(0.07 * SR)
    x = np.diff(RNG.standard_normal(k + 1))
    env = np.exp(-np.arange(k) / SR * 55) * np.minimum(1, np.arange(k) / (0.01 * SR))
    return x * env * 0.035 * accent


def snap():
    k = int(0.05 * SR)
    x = np.diff(RNG.standard_normal(k + 1))
    x = np.convolve(x, np.ones(3) / 3, mode="same")
    return x * np.exp(-np.arange(k) / SR * 90) * 0.16


def soft_kick():
    t = np.arange(int(0.35 * SR)) / SR
    f = 55 + 70 * np.exp(-t * 30)
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 9) * 0.35


def whoosh(dur=1.2):
    k = int(dur * SR)
    x = RNG.standard_normal(k)
    y = np.zeros(k)
    acc = 0.0
    tt = np.arange(k) / k
    cut = 0.02 + 0.25 * np.sin(np.pi * tt) ** 2
    for i in range(k):
        acc += cut[i] * (x[i] - acc)
        y[i] = acc
    return y * np.sin(np.pi * tt) ** 1.5 * 0.25


def pop():
    t = np.arange(int(0.12 * SR)) / SR
    f = 500 + 900 * np.exp(-t * 40)
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 35) * 0.2


# ------------------------------------------------------------------ arrangement
def build_music():
    buf = np.zeros((2, int((DURATION + 3) * SR)))
    t_sec = 0.0
    for name, kind, bars, melody, chords, tr in SECTIONS:
        for b in range(bars):
            tb = t_sec + b * BAR
            ch = [n(x) + tr for x in CHORDS[chords[b]]]
            root = ch[0]
            # melody on xylophone
            tm = tb
            for midi, d in melody[b]:
                if midi is not None:
                    add(buf, xylophone(hz(midi + tr)), tm, 0.9, -0.15)
                tm += d * BEAT
            # pad + bass
            if kind != "outro" or b < 3:
                add(buf, pad([hz(m + 12) for m in ch], BAR + 0.3), tb, 1.0 if kind != "intro" else 0.8)
            if kind in ("verse", "chorus", "chant", "bridge"):
                add(buf, bass(hz(root - 12 if root >= 48 else root)), tb, 1.0, 0.1)
                add(buf, bass(hz((ch[2] if root >= 48 else ch[2]) - 12)), tb + 2 * BEAT, 0.8, 0.1)
            elif kind == "intro" and b >= 2:
                add(buf, bass(hz(root - 12 if root >= 48 else root)), tb, 0.7, 0.1)
            # percussion
            if kind in ("verse", "chorus", "chant", "bridge"):
                for e in range(8):
                    add(buf, shaker(1.3 if e % 2 == 0 else 0.8), tb + e * BEAT / 2, 1.0, 0.35)
            if kind in ("chorus", "chant"):
                add(buf, snap(), tb + BEAT, 1.0, -0.3)
                add(buf, snap(), tb + 3 * BEAT, 1.0, -0.3)
                add(buf, soft_kick(), tb, 1.0)
                add(buf, soft_kick(), tb + 2 * BEAT, 0.8)
            # glockenspiel colour
            hi = [m + 24 for m in ch]
            if kind == "intro":
                if b == 0:
                    scale = [72, 74, 76, 77, 79, 81, 83, 84, 86, 88, 89, 91]
                    for i, m in enumerate(scale):
                        add(buf, glock(hz(m)), tb + i * BEAT / 4, 0.55 + 0.03 * i, 0.4)
                else:
                    for e, m in enumerate([hi[0], hi[1], hi[2], hi[1] + 12]):
                        add(buf, glock(hz(m)), tb + e * BEAT, 0.6, 0.4)
            elif kind == "chorus":
                if b == 4:  # kids' "Boo!" echoes
                    add(buf, glock(hz(96 + tr)), tb + BEAT, 0.9, 0.4)
                    add(buf, glock(hz(96 + tr)), tb + 3 * BEAT, 0.9, 0.4)
                else:
                    arp = [hi[0], hi[1], hi[2], hi[1]] * 2
                    for e, m in enumerate(arp):
                        add(buf, glock(hz(m), 1.2), tb + e * BEAT / 2, 0.32, 0.4)
            elif kind == "verse":
                add(buf, glock(hz(hi[2])), tb, 0.45, 0.4)
                add(buf, glock(hz(hi[1])), tb + 2.5 * BEAT, 0.3, 0.4)
            elif kind == "chant" and b in (1, 3):
                add(buf, glock(hz(hi[0] + 12)), tb, 0.7, 0.4)
                add(buf, glock(hz(hi[2])), tb + 2 * BEAT, 0.7, 0.4)
            elif kind == "bridge":
                if b < 5:
                    add(buf, glock(hz(84 + [0, 2, 4, 5, 7][b])), tb + 3 * BEAT, 0.9, 0.4)
                    add(buf, pop(), tb + 3 * BEAT, 1.0, 0.0)
                else:
                    for e in range(4):
                        add(buf, glock(hz(hi[e % 3] + 12), 1.2), tb + e * BEAT, 0.4, 0.4)
            elif kind == "outro":
                add(buf, glock(hz(hi[0] + 12), 2.5), tb, 0.5, 0.4)
                add(buf, glock(hz(hi[2] + 12), 2.5), tb + 2 * BEAT, 0.35, 0.4)
        t_sec += bars * BAR

    st = song.START
    # sound effects
    add(buf, whoosh(1.6), st["chorus3"][1] - 4.0, 0.8, -0.6)       # sparkle streak across sky
    add(buf, whoosh(1.4), st["verse4"][0] + 2 * BAR, 1.0, 0.5)       # Wanda swoops in
    add(buf, whoosh(1.4), st["verse4"][0] + 7 * BAR, 0.8, -0.3)      # lift-off
    for k in range(4):
        add(buf, whoosh(1.0), st["chant_wanda"][0] + k * BAR, 0.6, (-1) ** k * 0.6)
    for k in range(6):                                               # stones light up
        add(buf, pop(), st["verse2"][0] + 6 * BAR + k * BEAT, 0.6, 0.0)
    return buf


def reverb(buf, seconds=1.4, wet=0.2):
    k = int(seconds * SR)
    out = np.empty_like(buf)
    for c in range(2):
        ir = RNG.standard_normal(k) * np.exp(-np.arange(k) / SR * (6.9 / seconds))
        ir[: int(0.012 * SR)] = 0
        ir /= np.sqrt(np.sum(ir ** 2))
        size = 1 << int(np.ceil(np.log2(buf.shape[1] + k)))
        y = np.fft.irfft(np.fft.rfft(buf[c], size) * np.fft.rfft(ir, size), size)[: buf.shape[1]]
        out[c] = buf[c] + wet * y
    return out


# ------------------------------------------------------------------ vocals
def tts_line(voice, text, length_scale):
    from piper import SynthesisConfig
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as fh:
        path = fh.name
    with wave.open(path, "wb") as w:
        voice.synthesize_wav(text, w, syn_config=SynthesisConfig(length_scale=length_scale, noise_scale=0.6))
    with wave.open(path, "rb") as w:
        sr = w.getframerate()
        x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float64) / 32768
    os.unlink(path)
    # trim silence
    idx = np.where(np.abs(x) > 0.02)[0]
    if len(idx):
        x = x[max(0, idx[0] - 200): idx[-1] + 800]
    return x, sr


def resample(x, ratio):
    """Change length by 1/ratio (ratio>1 => higher pitch & shorter)."""
    m = int(len(x) / ratio)
    return np.interp(np.arange(m) * ratio, np.arange(len(x)), x)


def atempo(x, factor):
    """Pitch-preserving speed change via ffmpeg (factor>1 = faster)."""
    with tempfile.TemporaryDirectory() as d:
        a, b = os.path.join(d, "a.wav"), os.path.join(d, "b.wav")
        write_wav(a, np.vstack([x, x]))
        chain = []
        f = factor
        while f > 2.0:
            chain.append("atempo=2.0")
            f /= 2.0
        chain.append(f"atempo={f:.4f}")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", a, "-af", ",".join(chain), "-ac", "1", b], check=True)
        with wave.open(b, "rb") as w:
            return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float64) / 32768


def speakable(text):
    t = text.replace("—", ",").replace("\"", "").replace("...", ",")
    t = t.replace("Boo-Boo", "Boo Boo").replace("(Boo!)", "")
    return t


def build_vocals():
    from piper import PiperVoice
    voice = PiperVoice.load(os.path.join(ASSETS, "en_US-amy-medium.onnx"))
    buf = np.zeros((2, int((DURATION + 3) * SR)))
    timing = {}
    for d in song.lyrics():
        if d["voice"] == "silent":
            continue
        slot = d["t1"] - d["t0"]
        ls = {"lead": 0.88, "kids": 0.8, "boo": 0.9}[d["voice"]]
        if d["voice"] == "lead" and slot >= 4.7:
            ls = 1.3  # long chorus lines: slower, sing-song delivery
        x, sr = tts_line(voice, speakable(d["text"]), ls)
        x = resample(x, sr / SR)  # upsample to 44.1k, same pitch
        if d["voice"] == "kids":
            x = resample(x, 1.32)   # higher, child-like
            gain, pan = 0.75, 0.25
        elif d["voice"] == "boo":
            x = resample(x, 1.22)
            gain, pan = 0.9, -0.1
        else:
            gain, pan = 0.95, 0.0
        fit = slot * 0.94
        if len(x) / SR > fit:
            x = atempo(x, (len(x) / SR) / fit)
        # gentle fades
        f = min(len(x) // 4, int(0.01 * SR))
        x[:f] *= np.linspace(0, 1, f)
        x[-f:] *= np.linspace(1, 0, f)
        x /= max(1e-6, np.max(np.abs(x)))
        add(buf, x * 0.5, d["t0"] + 0.03, gain, pan)
        timing[f"{d['t0']:.3f}"] = len(x) / SR
        print(f"  vocal {d['t0']:6.1f}s {d['voice']:5s} {d['text'][:40]}", flush=True)
    return buf, timing


def write_wav(path, buf):
    y = np.clip(buf, -1, 1)
    data = (y.T * 32767).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(data.tobytes())


ASSETS = os.environ.get("LUNA_ASSETS", os.path.join(HERE, "assets"))


def main(out):
    os.makedirs(out, exist_ok=True)
    print("music...", flush=True)
    music = reverb(build_music(), 1.6, 0.22)
    print("vocals...", flush=True)
    voc, timing = build_vocals()
    voc = reverb(voc, 0.9, 0.1)
    import json
    json.dump(timing, open(os.path.join(out, "vocal_timing.json"), "w"), indent=0)
    n_out = int(DURATION * SR)
    music, voc = music[:, :n_out], voc[:, :n_out]
    # fade out the last two seconds
    fade = np.ones(n_out)
    fade[-int(2.0 * SR):] = np.linspace(1, 0, int(2.0 * SR)) ** 2
    music *= fade
    music /= np.max(np.abs(music)) / 0.7
    voc /= np.max(np.abs(voc)) / 0.8
    mix = np.tanh(1.2 * (music * 0.75 + voc * 0.85)) / np.tanh(1.2)
    mix /= np.max(np.abs(mix)) / 0.89
    write_wav(os.path.join(out, "music.wav"), music)
    write_wav(os.path.join(out, "vocals.wav"), voc)
    write_wav(os.path.join(out, "mix.wav"), mix)
    print("done", flush=True)


if __name__ == "__main__":
    main(sys.argv[1])
