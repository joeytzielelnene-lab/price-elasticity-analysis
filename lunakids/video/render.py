"""Render "Boo-Boo's Halloween Night" (LunaKids) — 4:00, 1280x720, 24 fps.

Usage: python render.py ASSET_DIR AUDIO_DIR OUT.mp4 [--preview T0 T1] [--stills t1,t2,...]
"""
import json
import math
import os
import subprocess
import sys
from multiprocessing import Pool

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageOps

import gfx
import song
from song import BAR, BEAT, START as ST

W, H, FPS = 1280, 720, 24
N_FRAMES = int(song.DURATION * FPS)
G = {}  # globals built once before forking: backgrounds, captions, vignette


# ============================================================ math helpers
def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def ease(u):
    u = clamp(u)
    return u * u * (3 - 2 * u)


def lerp(a, b, u):
    return a + (b - a) * u


def seg(t, a, b):
    """Eased progress of t through [a, b]."""
    return ease((t - a) / (b - a)) if b > a else float(t >= a)


def bob(T, amp=8.0, period=2 * BEAT, ph=0.0):
    return amp * math.sin(2 * math.pi * T / period + ph)


def pulse(T, at, width=0.18):
    """1 at time `at`, decaying after."""
    d = T - at
    return math.exp(-d / width) if d >= 0 else 0.0


def beat_pulse(T, width=0.14):
    return math.exp(-((T % BEAT) / width))


def blink(T, seed=0.0, period=3.4):
    return ((T + seed) % period) < 0.13


def hop(u, h):
    return -4 * h * u * (1 - u)


# ============================================================ backgrounds
class BG:
    def __init__(self, w, h, stops=None):
        self.w, self.h = w, h
        stops = stops or [(0, (24, 16, 64)), (0.45, (66, 38, 124)), (0.72, (128, 66, 150)), (1.0, (232, 128, 112))]
        self.img = gfx.vgrad(w, h, stops).convert("RGBA")
        self.stars = []

    def starfield(self, n, y1, seed=1):
        rng = np.random.default_rng(seed)
        d = ImageDraw.Draw(self.img)
        for _ in range(n):
            x, y = rng.uniform(0, self.w), rng.uniform(0, y1) ** 1.0
            r = rng.choice([1, 1, 1.5, 2, 2.5])
            a = int(rng.uniform(120, 255))
            d.ellipse([x - r, y - r, x + r, y + r], fill=(255, 250, 225, a))
        for _ in range(n // 6):
            self.stars.append((rng.uniform(0, self.w), rng.uniform(0, y1), rng.uniform(0, 6.28), rng.uniform(0.6, 1.4)))
        return self

    def paste(self, spr, x, y, s=1.0, anchor="bottom"):
        im = spr if s == 1.0 else spr.resize((max(1, int(spr.width * s)), max(1, int(spr.height * s))), Image.LANCZOS)
        ox = int(x - im.width / 2)
        oy = int(y - im.height) if anchor == "bottom" else int(y - im.height / 2)
        paste_clip(self.img, im, ox, oy)
        return self

    def land(self, pts, color, blur=60, amb=0.55, strength=1.6):
        m = Image.new("L", (self.w, self.h), 0)
        ImageDraw.Draw(m).polygon([tuple(p) for p in pts], fill=255)
        self.img.alpha_composite(gfx.puffy(m, color, blur, spec=0.05, amb=amb, strength=strength, bounce=(90, 60, 150)))
        return self

    def hill(self, box, color, blur=80):
        m = Image.new("L", (self.w, self.h), 0)
        ImageDraw.Draw(m).ellipse(box, fill=255)
        self.img.alpha_composite(gfx.puffy(m, color, blur, spec=0.04, amb=0.55, strength=1.6, bounce=(90, 60, 150)))
        return self

    def glowspot(self, x, y, r, color, alpha=0.5):
        m = Image.new("L", (self.w, self.h), 0)
        ImageDraw.Draw(m).ellipse([x - r, y - r, x + r, y + r], fill=255)
        self.img.alpha_composite(gfx.glow(m, color, r * 0.6, alpha))
        return self


def wave_ground(w, y0, amp, n, h, seed=0):
    rng = np.random.default_rng(seed)
    xs = np.linspace(-50, w + 50, n)
    ys = y0 + amp * np.sin(xs / w * math.pi * rng.uniform(1.5, 3) + rng.uniform(0, 6))
    pts = [(x, y) for x, y in zip(xs, ys)]
    flat_pts = [v for p in pts for v in p]
    sm = gfx.smooth_poly(flat_pts + [w + 50, h + 50, -50, h + 50], 3)
    return [(sm[i], sm[i + 1]) for i in range(0, len(sm), 2)]


def build_backgrounds():
    B = {}
    # --- village (tall: sky on top, village at bottom) --------------------------
    b = BG(1600, 1700, [(0, (18, 12, 52)), (0.35, (52, 30, 108)), (0.6, (96, 52, 146)), (0.78, (190, 104, 140)), (1, (60, 40, 110))])
    b.starfield(500, 1000, 2)
    b.paste(gfx.moon(520), 1250, 300, anchor="center")
    b.land(wave_ground(1600, 1080, 30, 9, 1700, 1), (92, 60, 150))
    b.land(wave_ground(1600, 1230, 25, 9, 1700, 2), (70, 46, 128))
    houses = [((250, 160, 190), (120, 70, 175)), ((120, 200, 200), (240, 140, 60)), ((250, 200, 120), (140, 80, 190)),
              ((200, 170, 250), (255, 140, 60)), ((255, 170, 120), (110, 70, 170)), ((140, 210, 170), (150, 90, 200))]
    for i, (c, r) in enumerate(houses):
        b.paste(gfx.house(c, r, i), 160 + i * 255, 1300 + (i % 2) * 30, 0.95 + 0.1 * (i % 3))
    b.land(wave_ground(1600, 1440, 20, 9, 1700, 3), (58, 40, 112))
    for i in range(9):
        b.paste(gfx.pip(baby=True), 100 + i * 180, 1560 + (i % 2) * 40, 0.22 + 0.04 * (i % 3))
    B["village"] = b
    # --- home on the hill ------------------------------------------------------
    b = BG(1600, 900).starfield(260, 560, 3)
    b.paste(gfx.moon(410), 1330, 170, anchor="center")
    b.land(wave_ground(1600, 700, 25, 8, 900, 4), (82, 56, 140))
    b.hill([-300, 560, 1100, 1400], (96, 66, 158))
    b.paste(gfx.cottage(), 430, 700, 0.9)
    b.paste(gfx.tree(2), 1150, 760, 0.75)
    B["home"] = b
    # --- moonlit field (wide) ---------------------------------------------------
    b = BG(2400, 900).starfield(320, 560, 4)
    b.paste(gfx.moon(440), 1950, 170, anchor="center")
    b.land(wave_ground(2400, 600, 30, 12, 900, 5), (88, 60, 150))
    for i, x in enumerate([150, 700, 1250, 1750, 2280]):
        b.paste(gfx.tree(i), x, 720 + (i % 2) * 20, 0.9)
    b.land(wave_ground(2400, 720, 18, 12, 900, 6), (72, 50, 132))
    path = [(0, 820), (600, 790), (1200, 810), (1800, 780), (2400, 805)]
    d = ImageDraw.Draw(b.img)
    d.line(path, fill=(120, 92, 170, 255), width=50, joint="curve")
    for i in range(14):
        b.paste(gfx.pip(baby=True), 80 + i * 175, 880 - (i % 3) * 10, 0.12 + 0.03 * (i % 2))
    B["field"] = b
    # --- giant moon hilltop -----------------------------------------------------
    b = BG(1600, 900).starfield(240, 900, 5)
    b.paste(gfx.moon(1120), 800, 400, anchor="center")
    b.hill([-200, 680, 1800, 1300], (88, 60, 150))
    B["moonhill"] = b
    # --- pumpkin patch ------------------------------------------------------------
    b = BG(2400, 900).starfield(280, 500, 6)
    b.paste(gfx.moon(360), 600, 150, anchor="center")
    for i, x in enumerate([300, 1000, 1600, 2200]):
        b.paste(gfx.tree(i + 3), x, 610, 0.7)
    b.land(wave_ground(2400, 560, 20, 12, 900, 7), (96, 64, 150))
    rng = np.random.default_rng(9)
    for i in range(22):
        x = 60 + i * 110 + rng.uniform(-20, 20)
        b.paste(gfx.pip(baby=True), x, 640 + rng.uniform(-10, 10), 0.14 + rng.uniform(0, 0.05))
    d = ImageDraw.Draw(b.img)
    d.line([(0, 790), (800, 760), (1600, 790), (2400, 770)], fill=(124, 96, 172, 255), width=90, joint="curve")
    for i in range(16):
        x = 100 + i * 145
        y = 775 + 12 * math.sin(i)
        b.paste(gfx.stone(), x, y, 0.8, anchor="center")
    for i in range(20):
        x = 40 + i * 125 + rng.uniform(-20, 20)
        b.paste(gfx.pip(baby=True), x, 900 + rng.uniform(0, 20), 0.22 + rng.uniform(0, 0.06))
    B["patch"] = b
    # --- forest -------------------------------------------------------------------
    b = BG(1600, 1400, [(0, (24, 16, 64)), (0.5, (60, 36, 116)), (1, (90, 50, 130))]).starfield(150, 500, 7)
    for i, x in enumerate([0, 330, 1180, 1500, 760]):
        b.paste(gfx.tree(i + 1), x, 1260 if i != 4 else 1240, 1.6 if i != 4 else 2.0)
    b.land(wave_ground(1600, 1200, 18, 9, 1400, 8), (78, 52, 136))
    for i in range(10):
        b.paste(gfx.pip(baby=True), 70 + i * 160, 1380, 0.16)
    B["forest"] = b
    # --- above the clouds -----------------------------------------------------------
    b = BG(1600, 1400, [(0, (16, 10, 48)), (0.5, (60, 34, 118)), (1, (190, 110, 150))]).starfield(400, 1100, 8)
    b.paste(gfx.moon(360), 300, 220, anchor="center")
    b.hill([1050, 1080, 1750, 1600], (84, 56, 144))
    for i in range(6):
        b.paste(gfx.lantern(), 1240 + i * 60, 1110 - abs(i - 2.5) * 10, 0.6)
    for i in range(6):
        b.paste(gfx.cloud(i), 150 + i * 280, 1250 + (i % 2) * 60, 1.0)
    B["above"] = b
    # --- the big hill -----------------------------------------------------------------
    b = BG(1600, 1300).starfield(300, 700, 9)
    b.paste(gfx.moon(330), 300, 200, anchor="center")
    b.hill([500, 380, 2600, 2400], (92, 62, 150), blur=120)
    for i in range(7):
        b.paste(gfx.lantern(), 1150 + i * 70, 420 + abs(i - 3) * 14, 0.7)
    b.land(wave_ground(1600, 1120, 15, 8, 1300, 10), (74, 50, 132))
    for x in (120, 360):
        b.paste(gfx.tree(x), x, 1150, 0.8)
    B["bighill"] = b
    # --- flying sky ---------------------------------------------------------------------
    b = BG(2400, 900, [(0, (16, 10, 50)), (0.6, (70, 40, 128)), (1, (176, 98, 146))]).starfield(600, 800, 10)
    b.paste(gfx.moon(410), 1800, 180, anchor="center")
    for i in range(9):
        b.paste(gfx.cloud(i + 3), 120 + i * 290, 860 + (i % 2) * 40, 0.9)
    B["sky"] = b
    # --- garden (finale) ------------------------------------------------------------------
    b = BG(1600, 900).starfield(240, 450, 11)
    b.paste(gfx.moon(330), 1380, 150, anchor="center")
    b.land(wave_ground(1600, 560, 15, 8, 900, 11), (92, 62, 150))
    b.paste(gfx.cottage(), 800, 610, 0.95)
    b.paste(gfx.tree(1), 140, 640, 0.75)
    b.paste(gfx.tree(4), 1480, 640, 0.75)
    b.land(wave_ground(1600, 640, 10, 8, 900, 12), (80, 56, 140))
    for i in range(8):
        b.paste(gfx.pip(baby=True), 80 + i * 205, 900, 0.2)
    B["garden"] = b
    # --- bedroom ---------------------------------------------------------------------------
    b = BG(1600, 900, [(0, (70, 44, 120)), (0.7, (96, 60, 150)), (0.71, (120, 80, 70)), (1, (90, 60, 50))])
    win = Image.new("L", (1600, 900), 0)
    ImageDraw.Draw(win).ellipse([1000, 120, 1380, 500], fill=255)
    sky = BG(1600, 900, [(0, (20, 14, 60)), (1, (80, 46, 130))]).starfield(80, 900, 12)
    sky.paste(gfx.crescent(220), 1220, 290, anchor="center")
    sky.img.putalpha(win)
    rim = Image.new("L", (1600, 900), 0)
    ImageDraw.Draw(rim).ellipse([980, 100, 1400, 520], fill=255)
    b.img.alpha_composite(gfx.puffy(rim, (150, 100, 190), 20, strength=2))
    b.img.alpha_composite(sky.img)
    ImageDraw.Draw(b.img).line([(1190, 120), (1190, 500)], fill=(150, 100, 190), width=10)
    b.glowspot(250, 560, 120, (255, 200, 120), 0.6)
    b.paste(gfx.lantern((255, 200, 120)), 250, 600, 1.2)
    B["bedroom"] = b
    # --- end card ----------------------------------------------------------------------------
    b = BG(1600, 900, [(0, (20, 12, 60)), (0.6, (70, 40, 128)), (1, (150, 80, 150))]).starfield(400, 900, 13)
    B["end"] = b
    return B


# ============================================================ compositing
def paste_clip(canvas, im, ox, oy):
    x0, y0 = max(0, ox), max(0, oy)
    x1, y1 = min(canvas.width, ox + im.width), min(canvas.height, oy + im.height)
    if x1 <= x0 or y1 <= y0:
        return
    canvas.alpha_composite(im, (x0, y0), (x0 - ox, y0 - oy, x1 - ox, y1 - oy))


class Frame:
    def __init__(self, T):
        self.T = T
        self.canvas = None
        self.cam = (800, 450, 1600)
        self.bgname = None

    # camera: (cx, cy, vw) in world units of the current background
    def bg(self, name, cx, cy, vw):
        b = G["bg"][name]
        vw = min(vw, b.w, b.h * 16 / 9)
        vh = vw * 9 / 16
        cx = clamp(cx, vw / 2, b.w - vw / 2)
        cy = clamp(cy, vh / 2, b.h - vh / 2)
        self.cam = (cx, cy, vw)
        self.bgname = name
        self.canvas = b.img.resize((W, H), Image.BILINEAR, box=(cx - vw / 2, cy - vh / 2, cx + vw / 2, cy + vh / 2))
        # twinkles
        k = W / vw
        sp = gfx.sparkle(28)
        for (x, y, ph, sp_rate) in b.stars:
            a = 0.5 + 0.5 * math.sin(self.T * 2.2 * sp_rate + ph)
            if a < 0.35:
                continue
            sx, sy = (x - cx) * k + W / 2, (y - cy) * k + H / 2
            if -20 < sx < W + 20 and -20 < sy < H + 20:
                im = sp.resize((max(4, int(20 * a * min(1.6, k))),) * 2, Image.BILINEAR)
                paste_clip(self.canvas, im, int(sx - im.width / 2), int(sy - im.height / 2))

    def scale(self):
        return W / self.cam[2]

    def to_screen(self, x, y):
        cx, cy, vw = self.cam
        k = W / vw
        return (x - cx) * k + W / 2, (y - cy) * k + H / 2

    def put(self, spr, x, y, s=1.0, rot=0.0, sq=0.0, alpha=1.0, flip=False, screen=False):
        """Place sprite centred at world (x, y) with scale s (relative to world)."""
        if spr is None or s <= 0.001 or alpha <= 0.01:
            return
        if screen:
            sx, sy, k = x, y, s
        else:
            sx, sy = self.to_screen(x, y)
            k = s * self.scale()
        w = max(1, int(spr.width * k * (1 + sq)))
        h = max(1, int(spr.height * k * (1 - sq)))
        if w > 4000 or h > 4000:
            return
        im = spr.resize((w, h), Image.BILINEAR)
        if flip:
            im = ImageOps.mirror(im)
        if abs(rot) > 0.3:
            im = im.rotate(rot, Image.BILINEAR, expand=True)
        if alpha < 0.999:
            a = im.getchannel("A").point(lambda v: int(v * alpha))
            im.putalpha(a)
        paste_clip(self.canvas, im, int(sx - im.width / 2), int(sy - im.height / 2))

    def text(self, txt, x, y, size, fill=(255, 255, 255), stroke=(70, 30, 120), sw=None, alpha=1.0, scale=1.0, rot=0):
        im = text_img(txt, int(size), fill, stroke, sw)
        self.put(im, x, y, scale, rot=rot, alpha=alpha, screen=True)


_TEXT_CACHE = {}


def text_img(txt, size, fill, stroke, sw=None):
    key = (txt, size, fill, stroke, sw)
    if key not in _TEXT_CACHE:
        f = gfx.font(size)
        sw = sw if sw is not None else max(3, size // 9)
        bb = ImageDraw.Draw(Image.new("RGBA", (1, 1))).textbbox((0, 0), txt, font=f, stroke_width=sw)
        im = Image.new("RGBA", (bb[2] - bb[0] + 20, bb[3] - bb[1] + 26), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.text((10 - bb[0], 16 - bb[1]), txt, font=f, fill=(40, 16, 70, 160), stroke_width=sw, stroke_fill=(40, 16, 70, 160))
        im = im.filter(ImageFilter.GaussianBlur(3))
        d = ImageDraw.Draw(im)
        d.text((10 - bb[0], 10 - bb[1]), txt, font=f, fill=fill, stroke_width=sw, stroke_fill=stroke)
        _TEXT_CACHE[key] = im
    return _TEXT_CACHE[key]


# ============================================================ character helpers
def boo_spr(T, eye=None, mouth="smile", arms="down", seed=0.0, **kw):
    if eye is None:
        eye = "closed" if blink(T, seed) else "open"
    return gfx.boo(eye, mouth, arms, **kw)


def mama(T, arms="wave", eye=None):
    return gfx.boo(eye or ("closed" if blink(T, 1.3) else "open"), "smile", arms, False, (205, 170, 245), False)


def papa(T, arms="wave", eye=None):
    return gfx.boo(eye or ("closed" if blink(T, 2.1) else "open"), "smile", arms, False, None, True)


def bella_spr(T, rate=0.16, eye=None):
    ph = int(T / rate) % 4
    wings = ["up", "mid", "down", "mid"][ph]
    return gfx.bella(wings, eye or ("closed" if blink(T, 0.7, 2.9) else "open"))


def owl_spr(T, yawn_at=None):
    if yawn_at is not None and 0 < T - yawn_at < 1.4:
        return gfx.owl("yawn")
    return gfx.owl("closed" if blink(T, 0.4, 2.5) or (T % 7) > 5.0 else "open")


RIDERS = {  # offsets relative to Wanda sprite centre, in Wanda-sprite pixels, plus rider scale ratio
    "boo": (-80, 45, 0.33),
    "pip": (-175, 80, 0.30),
    "bella": (-262, 40, 0.30),
}


def broom_group(fr, T, x, y, s, flip=False, riders=("boo", "pip", "bella"), arm="wave", wanda_eye=None,
                rider_arms="down", rot=0.0, cheer=False):
    fr.put(gfx.wanda(arm, wanda_eye or ("closed" if blink(T, 0.9) else "open")), x, y, s, rot=rot, flip=flip)
    ang = math.radians(-rot)
    for name in riders:
        dx, dy, r = RIDERS[name]
        dx = -dx if flip else dx
        rx = dx * math.cos(ang) - dy * math.sin(ang)
        ry = dx * math.sin(ang) + dy * math.cos(ang)
        bb = bob(T, 3, 2 * BEAT, {"boo": 0, "pip": 2, "bella": 4}[name])
        if name == "boo":
            spr = boo_spr(T, mouth="open" if cheer else "smile", arms="up" if cheer else rider_arms,
                          eye="happy" if cheer else None)
        elif name == "pip":
            spr = gfx.pip("wave" if cheer else "down", 1.2)
        else:
            spr = bella_spr(T)
        fr.put(spr, x + rx * s, y + (ry + bb) * s, s * r, rot=rot, flip=flip)


def fireflies(fr, T, n, box, seed=0, alpha=1.0):
    rng = np.random.default_rng(seed)
    x0, y0, x1, y1 = box
    dg = gfx.dot_glow(36)
    for i in range(n):
        bx, by = rng.uniform(x0, x1), rng.uniform(y0, y1)
        p1, p2, w1, w2 = rng.uniform(0, 6.28, 2).tolist() + rng.uniform(0.3, 0.8, 2).tolist()
        x = bx + 50 * math.sin(T * w1 + p1)
        y = by + 35 * math.sin(T * w2 + p2)
        a = alpha * (0.45 + 0.55 * abs(math.sin(T * 1.7 + p1 * 3)))
        fr.put(dg, x, y, 1.0, alpha=a)


def sparkle_trail(fr, T, path_fn, t_head, length=1.0, n=26, size=1.0, colors=((255, 230, 140), (220, 170, 255))):
    for i in range(n):
        tt = t_head - i * length / n
        if tt < 0:
            continue
        x, y = path_fn(tt)
        a = (1 - i / n) ** 1.3
        c = colors[i % len(colors)]
        fr.put(gfx.sparkle(40, c), x + 10 * math.sin(i * 2.3), y + 10 * math.cos(i * 1.7), size * (0.5 + 0.7 * a), alpha=a)


def boo_text(fr, T, sec, x=W / 2, y=150):
    """Bouncy 'BOO!' on the four call-and-response beats of a chorus."""
    t0 = ST[sec][0] + 4 * BAR
    for k in range(4):
        at = t0 + k * BEAT
        if at <= T < at + BEAT:
            u = (T - at) / BEAT
            sc = 1.0 + 0.6 * math.exp(-u * 8) * math.cos(u * 18)
            col = (255, 160, 40) if k % 2 == 0 else (200, 150, 255)
            off = -180 if k % 2 == 0 else 180
            fr.text("BOO!", x + off * 0.6, y, 110, fill=col, stroke=(255, 255, 255), sw=8, scale=sc * 0.9,
                    rot=(-8 if k % 2 == 0 else 8))


def punch(T, sec):
    t0 = ST[sec][0] + 4 * BAR
    return sum(pulse(T, t0 + k * BEAT, 0.16) for k in range(4) if T >= t0 + k * BEAT)


# ============================================================ shots
SHOTS = []


def shot(t0, t1):
    def deco(fn):
        SHOTS.append((t0, t1, fn))
        return fn
    return deco


def S(name, bar=0, beat=0):
    return ST[name][0] + bar * BAR + beat * BEAT


# ---------------- Scene 1: intro
@shot(S("intro"), S("intro", 2))
def s1a(fr, T, t, u):
    fr.bg("village", 800, 450, 1600)
    y = lerp(560, 300, seg(t, 0, 2.6)) + bob(T, 6)
    fr.put(gfx.crescent(), 800, y, 0.85 + 0.05 * seg(t, 0, 2.6))
    a = seg(t, 1.8, 2.8)
    if a > 0:
        fr.text("LunaKids", W / 2, 470, 96, fill=(255, 226, 120), stroke=(110, 50, 170), sw=8, alpha=a,
                scale=0.85 + 0.15 * a + 0.04 * math.sin(T * 5) * a)
        fr.text("nursery rhymes & songs", W / 2, 548, 34, fill=(255, 255, 255), stroke=(90, 40, 140), alpha=a)


@shot(S("intro", 2), S("verse1"))
def s1b(fr, T, t, u):
    cy = lerp(480, 1300, ease(u))
    fr.bg("village", 800, cy, lerp(1600, 1300, ease(u)))
    a = seg(t, 1.0, 1.6) * (1 - seg(t, 4.2, 4.8))
    if a > 0:
        sc = 1 + 0.25 * math.exp(-(t - 1.0) * 5) * math.cos((t - 1.0) * 14) if t > 1 else 1
        fr.text("Boo-Boo's", W / 2, 250, 100, fill=(255, 255, 255), stroke=(110, 50, 170), sw=9, alpha=a, scale=sc)
        fr.text("Halloween Night", W / 2, 360, 92, fill=(255, 170, 50), stroke=(110, 50, 170), sw=9, alpha=a, scale=sc)


# ---------------- Scene 2: verse 1
@shot(S("verse1"), S("verse1", 2))
def s2a(fr, T, t, u):
    fr.bg("home", lerp(700, 800, u), lerp(560, 470, u), lerp(1050, 1500, ease(u)))
    fr.put(mama(T), 300, 760, 0.3)
    # out of the window and up
    wx, wy = 668, 620
    p = seg(t, 0.3, 3.6)
    x = lerp(wx, 1000, p)
    y = lerp(wy, 420, p) + hop(p, 60) + bob(T, 8)
    s = lerp(0.12, 0.38, seg(t, 0.3, 1.6))
    fr.put(boo_spr(T, arms="wave" if t < 4 else "down"), x, y, s, rot=6 * math.sin(T * 3))


@shot(S("verse1", 2), S("verse1", 4))
def s2b(fr, T, t, u):
    cx = lerp(500, 1000, u)
    fr.bg("field", cx, 470, 1500)
    lt = t * 1.3
    lx = 450 + 230 * t + 90 * math.cos(lt * 2.2)
    ly = 470 + 70 * math.sin(lt * 2.2)
    fr.put(gfx.leaf(), lx, ly, 0.9, rot=T * 200)
    tb = max(0, t - 0.55)
    bx = 450 + 230 * tb + 90 * math.cos(tb * 1.3 * 2.2) - 120
    by = 470 + 70 * math.sin(tb * 1.3 * 2.2) + 20
    loop = 360 * seg(t, 2.4, 3.6)
    fr.put(boo_spr(T, mouth="grin" if 1 < t < 4 else "smile", arms="up"), bx, by, 0.36, rot=loop)


@shot(S("verse1", 4), S("verse1", 6))
def s2c(fr, T, t, u):
    cx = lerp(1050, 1500, u)
    fr.bg("field", cx, 470, 1400)
    fr.put(owl_spr(T, yawn_at=S("verse1", 4) + 1.6), 1145, 440, 0.45)
    fr.put(gfx.leaf(), 1300 + 250 * u + 30 * math.sin(T * 3), 380 + 40 * math.sin(T * 2), 0.8, rot=T * 160)
    fr.put(boo_spr(T, arms="down"), lerp(980, 1520, u), 520 + bob(T, 14), 0.36, rot=5 * math.sin(T * 2.5))


@shot(S("verse1", 6), S("chorus1"))
def s2d(fr, T, t, u):
    vw = lerp(1500, 1050, seg(t, 2.4, 4.8))
    fr.bg("field", 1750, 500, vw)
    fr.put(gfx.leaf(), 1850 + 400 * seg(t, 0, 2.0), 380 - 260 * seg(t, 0, 2.0), 0.7, rot=T * 220,
           alpha=1 - seg(t, 1.6, 2.0))
    if t < 1.2:
        look, eye, mouth = True, None, "smile"
    elif t < 2.4:
        look, eye, mouth = False, None, "smile"
    else:
        look, eye, mouth = False, "worried", "o"
    turn = 0.1 * pulse(T, S("verse1", 6)) + 0.1 * pulse(T, S("verse1", 6, 2))
    fr.put(boo_spr(T, eye=eye, mouth=mouth), 1750, 540 + bob(T, 6), 0.42, sq=turn, flip=look)
    if t > 3.2:
        a = seg(t, 3.2, 3.6)
        fr.put(gfx.star(True, 120), 1930, 330 + bob(T, 5), 0.8 * a + 0.15 * pulse(T, S("verse1", 7, 2)), rot=10 * math.sin(T * 3))


# ---------------- Scene 3: chorus 1
@shot(S("chorus1"), S("chorus1", 2))
def s3a(fr, T, t, u):
    fr.bg("moonhill", 800, 430, 1600)
    sway = math.sin(math.pi * T / BEAT)
    fr.put(boo_spr(T, arms="down"), 800 + 50 * sway, 560 + bob(T, 10), 0.6, rot=-8 * sway, sq=0.04 * beat_pulse(T))


@shot(S("chorus1", 2), S("chorus1", 4))
def s3b(fr, T, t, u):
    fr.bg("moonhill", 900, 520, 1300)
    left = (t % (2 * BAR)) < BAR * 0.5 or (BAR <= t % (2 * BAR) < BAR * 1.5)
    left = int(t / (2 * BEAT)) % 2 == 0
    spin = math.cos(T * 4)
    fr.put(gfx.signpost(), 1180, 690, 0.95)
    fr.put(boo_spr(T, arms="wave", mouth="o" if int(t / BEAT) % 2 else "smile"), 820, 600 + bob(T, 8), 0.55, flip=left,
           sq=0.05 * beat_pulse(T))
    fr.put(gfx.sparkle(60), 1180 + 120 * spin, 610, 0.8, alpha=0.6)


@shot(S("chorus1", 4), S("chorus1", 6))
def s3c(fr, T, t, u):
    p = punch(T, "chorus1")
    fr.bg("moonhill", 800, 470, 1000 * (1 - 0.08 * min(1, p)))
    calls = [S("chorus1", 4, k) for k in range(4)]
    mouth = "open" if any(0 <= T - c < 0.35 for c in calls[::2]) else ("grin" if t > 2.4 else "smile")
    arms = "up" if t > 2.4 else ("wave" if any(0 <= T - c < 0.4 for c in calls) else "down")
    fr.put(boo_spr(T, mouth=mouth, arms=arms, eye="happy" if t > 3.6 else None), 800, 540 + bob(T, 8), 0.75,
           sq=0.08 * p - 0.03, rot=6 * math.sin(math.pi * T / BEAT) if t > 2.4 else 0)
    for i, (sx, sy) in enumerate([(520, 300), (1080, 280), (600, 650), (1020, 640)]):
        bnc = sum(pulse(T, calls[k], 0.2) for k in (1, 3) if T >= calls[k])
        fr.put(gfx.star(True, 120), sx, sy - 40 * bnc, 0.55 + 0.15 * bnc, rot=15 * math.sin(T * 2 + i))
    boo_text(fr, T, "chorus1")


@shot(S("chorus1", 6), S("verse2"))
def s3d(fr, T, t, u):
    fr.bg("moonhill", lerp(820, 860, u), 480, lerp(1300, 1050, ease(u)))
    fr.put(boo_spr(T, eye="happy", mouth="smile", arms="hug"), 700, 570 + bob(T, 6), 0.6, rot=5 * math.sin(T * 2))
    a = seg(t, 0.4, 1.2)
    for i, (dx, dy, r) in enumerate([(120, -200, 0.12), (200, -280, 0.2)]):
        fr.put(gfx.cloud(1), 700 + dx, 570 + dy, r * a * 1.6 / 1.6, alpha=a)
    if a > 0:
        fr.put(gfx.cloud(2), 1040, 270, 0.95 * a, alpha=0.95 * a)
        fr.put(gfx.cottage(), 1040, 250, 0.38 * a + 0.02 * math.sin(T * 3), alpha=a)


# ---------------- Scene 4: verse 2 — Pip
@shot(S("verse2"), S("verse2", 2))
def s4a(fr, T, t, u):
    fr.bg("patch", 700, 620, 1300)
    p = seg(t, 0.4, 2.6)
    px = lerp(1500, 860, p)
    wob = 8 * math.sin(t * 10) * math.exp(-max(0, t - 2.6) * 2) if t > 2.6 else 0
    fr.put(gfx.pip("down", 1.0), px, 690 - abs(math.sin(p * 8)) * 30 * (1 - p), 0.42, rot=(1 - p) * 540 + wob)
    eye = "worried" if 0.5 < t < 2.6 else None
    fr.put(boo_spr(T, eye=eye, mouth="o" if t < 2.8 else "smile"), 480, 600 + bob(T, 8), 0.38)


@shot(S("verse2", 2), S("verse2", 4))
def s4b(fr, T, t, u):
    fr.bg("patch", 840, 600, 820)
    sq = 0.06 * beat_pulse(T) if t < 4 else 0
    fr.put(gfx.pip("wave" if int(t / BEAT) % 2 == 0 else "down", 1.5), 860, 600, 0.75, sq=sq)
    fr.put(boo_spr(T), 470, 560 + bob(T, 6), 0.42, alpha=1.0)


@shot(S("verse2", 4), S("verse2", 6))
def s4c(fr, T, t, u):
    fr.bg("patch", 800, 600, 1000)
    pat = int(t / (BEAT * 2)) % 2 == 0
    fr.put(gfx.pip("pat" if pat else "down", 1.3), 640, 640, 0.6)
    happy = t > 1.0
    fr.put(boo_spr(T, eye="happy" if happy else None, mouth="grin" if happy else "smile"), 980,
           560 + bob(T, 6) + (12 if pat else 0), 0.5, sq=0.05 * (1 if pat else 0))


@shot(S("verse2", 6), S("chant_pip"))
def s4d(fr, T, t, u):
    fr.bg("patch", lerp(700, 1500, ease(u)), 640, 1300)
    for i in range(16):
        x = 100 + i * 145
        y = 775 + 12 * math.sin(i)
        on = S("verse2", 6) + 0.25 + (i - 4) * BEAT * 0.5
        if T > on and i >= 4:
            fr.put(gfx.stone(True), x, y, 0.8 + 0.2 * pulse(T, on), alpha=seg(T, on, on + 0.2))
    glow_lvl = 2.0 if t > 0.5 else 1.0
    camx = lerp(700, 1500, ease(u))
    fr.put(gfx.pip("down", glow_lvl), camx - 200, 680, 0.45, sq=-0.08 * pulse(T, S("verse2", 6) + 0.4, 0.4))
    fr.put(boo_spr(T, eye="happy" if t > 2 else None, mouth="grin"), camx + 20, 600 + bob(T, 8), 0.34)


# ---------------- Scene 5: Pip's chant
def _chant_bounce(T):
    return abs(math.sin(math.pi * T / BEAT))


@shot(S("chant_pip"), S("chant_pip", 2))
def s5a(fr, T, t, u):
    cx = lerp(900, 1500, u)
    fr.bg("patch", cx, 620, 1300)
    x = cx - 120
    fr.put(gfx.pip("wave" if int(T / BEAT) % 2 else "down", 1.5), x, 700 - 30 * _chant_bounce(T), 0.42,
           rot=-(T * 120) % 360 if t < 2.4 else 0)
    fr.put(boo_spr(T, mouth="grin", arms="up" if int(T / BEAT) % 2 else "down"), x + 250, 600 - 25 * _chant_bounce(T + 0.3),
           0.34)
    _babies(fr, T, "chant_pip", 1, cx)


def _babies(fr, T, sec, bar, cx):
    for k, dx in enumerate([-500, -320, 320, 520]):
        at = S(sec, bar, 0 if k < 2 else 2)
        if T >= at:
            p = clamp((T - at) / 0.4)
            sc = 0.3 * (p + 0.3 * math.sin(p * math.pi) )
            fr.put(gfx.pip("down", 2.0, baby=True), cx + dx, 770 - 30 * math.sin(p * math.pi), sc,
                   sq=0.05 * math.sin(T * 8))


@shot(S("chant_pip", 2), S("chorus2"))
def s5b(fr, T, t, u):
    fr.bg("patch", 1500, 580, 1600)
    _babies(fr, T, "chant_pip", 1, 1500)
    _babies(fr, T, "chant_pip", 3, 1450)
    fr.put(gfx.pip("wave", 1.6), 1420, 700 - 30 * _chant_bounce(T), 0.38)
    fr.put(boo_spr(T, mouth="grin", arms="up"), 1640, 610 - 25 * _chant_bounce(T + 0.3), 0.3)


# ---------------- Scene 6: chorus 2
@shot(S("chorus2"), S("chorus2", 2))
def s6a(fr, T, t, u):
    cx = lerp(400, 900, u)
    fr.bg("field", cx, 520, 1600)
    sway = math.sin(math.pi * T / BEAT)
    fr.put(gfx.pip("down", 1.2), cx - 100 + 20 * sway, 740 - 10 * abs(sway), 0.3, rot=-5 * sway)
    fr.put(boo_spr(T), cx + 80 + 20 * sway, 640 + bob(T, 8), 0.28, rot=-5 * sway)


@shot(S("chorus2", 2), S("chorus2", 4))
def s6b(fr, T, t, u):
    fr.bg("field", 1000, 560, 1100)
    giggle = t > 2.4
    fr.put(gfx.pip("wave", 1.2), 860, 700 + (8 * math.sin(T * 20) if giggle else 0), 0.42, flip=False)
    fr.put(boo_spr(T, eye="happy" if giggle else None, mouth="grin" if giggle else "smile", arms="wave"), 1140,
           600 + bob(T, 6) + (6 * math.sin(T * 22) if giggle else 0), 0.42, flip=False)


@shot(S("chorus2", 4), S("chorus2", 6))
def s6c(fr, T, t, u):
    p = punch(T, "chorus2")
    fr.bg("field", 1000, 560, 1000 * (1 - 0.08 * min(1, p)))
    calls = [S("chorus2", 4, k) for k in range(4)]
    open_m = any(0 <= T - c < 0.35 for c in calls)
    fr.put(gfx.pip("wave" if open_m else "down", 1.0 + 1.2 * min(1, p)), 830, 690, 0.5, sq=0.06 * p)
    fr.put(boo_spr(T, mouth="open" if open_m else "grin", arms="up" if t > 2.4 else "wave",
                   eye="happy" if t > 3.6 else None), 1160, 600 + bob(T, 6), 0.5, sq=0.06 * p)
    boo_text(fr, T, "chorus2")


@shot(S("chorus2", 6), S("verse3"))
def s6d(fr, T, t, u):
    fr.bg("forest", 800, lerp(1000, 900, u), lerp(1600, 1150, ease(u)))
    fireflies(fr, T, 22, (100, 600, 1500, 1200), 3)
    x = lerp(450, 800, u)
    fr.put(gfx.pip("down", 1.3), x - 70, 1190 - 15 * _chant_bounce(T), 0.3)
    fr.put(boo_spr(T), x + 70, 1110 + bob(T, 8), 0.26)


# ---------------- Scene 7: verse 3 — Bella
@shot(S("verse3"), S("verse3", 2))
def s7a(fr, T, t, u):
    fr.bg("forest", 800, lerp(1000, 760, ease(u)), 1400)
    fireflies(fr, T, 18, (100, 300, 1500, 1200), 4)
    fr.put(gfx.bella("down", "closed" if blink(T, 0.3) else "open"), 790, 560 + 10 * math.sin(T * 2), 0.35, rot=180 + 10 * math.sin(T * 2))
    fr.put(gfx.pip("down", 1.3), 640, 1190, 0.32)
    fr.put(boo_spr(T, mouth="o"), 900, 1110 + bob(T, 6), 0.28)


@shot(S("verse3", 2), S("verse3", 4))
def s7b(fr, T, t, u):
    fr.bg("forest", 800, 600, 760)
    flip_p = seg(t, 3.5, 4.4)
    swing = 14 * math.sin(T * 2.6) * (1 - flip_p)
    rot = 180 * (1 - flip_p) + swing
    giggle = 6 * math.sin(T * 24) if 1.0 < t < 3.0 else 0
    eye = "happy" if 1.0 < t < 3.0 else None
    spr = bella_spr(T, eye=eye) if flip_p > 0.5 else gfx.bella("down", eye or ("closed" if blink(T, 0.3) else "open"))
    fr.put(spr, 800, 600 + giggle + hop(flip_p, 80), 0.75, rot=rot)
    fireflies(fr, T, 10, (450, 350, 1150, 850), 5)


@shot(S("verse3", 4), S("verse3", 6))
def s7c(fr, T, t, u):
    fr.bg("above", 800, lerp(1000, 650, ease(u)), 1500)
    y = lerp(1250, 600, ease(seg(t, 0, 3.5)))
    x = lerp(600, 760, u)
    fr.put(bella_spr(T, 0.12), x, y, 0.42, rot=8 * math.sin(T * 3))
    if t > 2.6:
        a = seg(t, 2.6, 3.4)
        for i in range(6):
            fr.put(gfx.sparkle(50), 1240 + i * 60, 1060 - abs(i - 2.5) * 10, 0.7 * a * (0.8 + 0.3 * math.sin(T * 4 + i)))


@shot(S("verse3", 6), S("chant_bella"))
def s7d(fr, T, t, u):
    fr.bg("forest", 800, 900, 1300)
    fireflies(fr, T, 14, (100, 500, 1500, 1150), 6)
    fr.put(bella_spr(T), 700, 760 + bob(T, 12), 0.45, flip=False)
    sparkle_trail(fr, T, lambda tt: (760 + tt * 500, 780 - tt * 120), max(0, t - 0.6) * 1.0, length=0.8, size=0.7)
    look = t > 1.2
    fr.put(gfx.pip("wave" if look else "down", 1.3), 560, 1190, 0.32)
    fr.put(boo_spr(T, mouth="grin" if look else "smile", arms="wave" if look else "down"), 900, 1110 + bob(T, 6), 0.28,
           flip=not look)


# ---------------- Scene 8: Bella's chant
@shot(S("chant_bella"), S("chant_bella", 2))
def s8a(fr, T, t, u):
    fr.bg("forest", 800, 960, 1100)
    fireflies(fr, T, 14, (200, 600, 1400, 1150), 7)
    on = int(T / BEAT) % 2 == 0
    fr.put(gfx.bella("up" if on else "down"), 800, 800 + (-20 if on else 10), 0.42)
    fr.put(gfx.pip("wave" if on else "down", 1.3), 520, 1180 - 20 * _chant_bounce(T), 0.34)
    fr.put(boo_spr(T, mouth="grin", arms="up" if on else "down"), 1080, 1100 - 20 * _chant_bounce(T + 0.3), 0.3)


@shot(S("chant_bella", 2), S("chorus3"))
def s8b(fr, T, t, u):
    fr.bg("forest", 800, 860, 1500)
    p = seg(t, 0.2, 2.6)
    rng = np.random.default_rng(12)
    arrow = [(500 + i * 70, 700) for i in range(9)] + [(1060 - i * 50, 700 - i * 50) for i in range(1, 5)] + \
            [(1060 - i * 50, 700 + i * 50) for i in range(1, 5)]
    pulse_k = 1 + 0.4 * sum(pulse(T, S("chant_bella", 3, b), 0.2) for b in (0, 2) if T >= S("chant_bella", 3, b))
    for i, (ax, ay) in enumerate(arrow):
        sx, sy = rng.uniform(150, 1450), rng.uniform(500, 1100)
        x = lerp(sx, ax, p) + 6 * math.sin(T * 3 + i)
        y = lerp(sy, ay, p) + 6 * math.cos(T * 2.7 + i)
        fr.put(gfx.dot_glow(36), x, y, 1.3 * pulse_k)
    on = int(T / BEAT) % 2 == 0
    fr.put(gfx.bella("up" if on else "down"), 380, 820, 0.32)
    fr.put(gfx.pip("down", 1.3), 300, 1150, 0.26)
    fr.put(boo_spr(T, mouth="grin"), 480, 1090 + bob(T, 6), 0.24)


# ---------------- Scene 9: chorus 3
@shot(S("chorus3"), S("chorus3", 2))
def s9a(fr, T, t, u):
    cx = lerp(1300, 1900, u)
    fr.bg("field", cx, 560, 1500)
    sway = math.sin(math.pi * T / BEAT)
    fr.put(bella_spr(T), cx - 300, 560 + bob(T, 12), 0.3)
    fr.put(gfx.pip("down", 1.3), cx - 100, 760 - 15 * abs(sway), 0.32, rot=-6 * sway)
    fr.put(boo_spr(T), cx + 120, 670 + bob(T, 8), 0.3, rot=-6 * sway)


@shot(S("chorus3", 2), S("chorus3", 4))
def s9b(fr, T, t, u):
    fr.bg("bighill", 700, lerp(1000, 850, ease(u)), 1500)
    yawn = 1.8 < t < 3.2
    fr.put(bella_spr(T), 420, 980 + bob(T, 10), 0.26)
    fr.put(gfx.pip("down", 1.3), 560, 1140, 0.28)
    fr.put(boo_spr(T, eye="closed" if yawn else None, mouth="o" if yawn else "smile"), 760, 1070 + bob(T, 6), 0.26,
           sq=-0.08 if yawn else 0)


@shot(S("chorus3", 4), S("chorus3", 6))
def s9c(fr, T, t, u):
    p = punch(T, "chorus3")
    fr.bg("bighill", 640, 1000, 1000 * (1 - 0.08 * min(1, p)))
    calls = [S("chorus3", 4, k) for k in range(4)]
    open_m = any(0 <= T - c < 0.35 for c in calls)
    fr.put(bella_spr(T, eye="happy" if open_m else None), 360, 900 + bob(T, 10), 0.36, sq=0.05 * p)
    fr.put(gfx.pip("wave" if open_m else "down", 1.3 + p), 620, 1110, 0.36, sq=0.05 * p)
    fr.put(boo_spr(T, mouth="open" if open_m else "grin", arms="up" if t > 2.4 else "wave"), 880, 1020 + bob(T, 6), 0.36,
           sq=0.05 * p)
    boo_text(fr, T, "chorus3")


@shot(S("chorus3", 6), S("verse4"))
def s9d(fr, T, t, u):
    fr.bg("bighill", 800, lerp(900, 420, ease(seg(t, 0, 2.5))), 1500)
    head = max(0, t - 1.6)
    sparkle_trail(fr, T, lambda tt: (-100 + tt * 700, 260 + 80 * math.sin(tt * 2)), head * 1.0, length=1.0, n=34, size=1.1)


# ---------------- Scene 10: verse 4 — Wanda
@shot(S("verse4"), S("verse4", 2))
def s10a(fr, T, t, u):
    fr.bg("bighill", 700, 900, 1600)
    fr.put(bella_spr(T), 440, 990 + bob(T, 8), 0.2)
    fr.put(gfx.pip("down", 1.0), 560, 1135, 0.22)
    fr.put(boo_spr(T, eye="worried", mouth="o" if t > 2.4 else "smile"), 720, 1080 + bob(T, 4), 0.2, sq=-0.06)


def _wanda_path(tt):
    p = ease(clamp(tt / 3.4))
    return lerp(-150, 1000, p), 380 + 640 * math.sin(p * math.pi / 2) - 120 * p


@shot(S("verse4", 2), S("verse4", 4))
def s10b(fr, T, t, u):
    fr.bg("bighill", 700, 860, 1500)
    sparkle_trail(fr, T, _wanda_path, t, length=1.2, n=30, size=1.0)
    x, y = _wanda_path(t)
    fr.put(bella_spr(T), 360, 990 + bob(T, 8), 0.24)
    fr.put(gfx.pip("down", 1.2), 480, 1135, 0.26)
    fr.put(boo_spr(T, mouth="o" if t < 3.0 else "grin", eye=None if t < 3.0 else "happy"), 640, 1070 + bob(T, 6), 0.25)
    broom_group(fr, T, x, y + bob(T, 10), 0.5, riders=(), rot=-8 * (1 - seg(t, 2.4, 3.6)))


@shot(S("verse4", 4), S("verse4", 6))
def s10c(fr, T, t, u):
    fr.bg("bighill", 1000, 960, 780)
    wink = 2.4 < t < 3.0
    broom_group(fr, T, 1000, 980 + bob(T, 10), 1.05, riders=(), wanda_eye="wink" if wink else None,
                arm="wave" if int(t / BEAT) % 4 < 2 else "down")


@shot(S("verse4", 6), S("chant_wanda"))
def s10d(fr, T, t, u):
    lift = seg(t, 2.6, 4.8)
    fr.bg("bighill", 900, lerp(920, 760, lift), 1200)
    gx, gy, gs = 950, 980 - 260 * lift + bob(T, 8), 0.6
    fr.put(gfx.wanda("down", "closed" if blink(T, 0.9) else "open"), gx, gy, gs)
    starts = {"boo": (620, 1060, 0.4), "pip": (480, 1135, 1.0), "bella": (360, 990, 1.6)}
    sprites = {"boo": boo_spr(T, mouth="grin"), "pip": gfx.pip("down", 1.2), "bella": bella_spr(T)}
    for name in ("bella", "pip", "boo"):
        sx, sy, st = starts[name]
        dx, dy, r = RIDERS[name]
        p = seg(t, st * 0.6, st * 0.6 + 1.0)
        x = lerp(sx, gx + dx * gs, p)
        y = lerp(sy, gy + dy * gs, p) + hop(clamp((t - st * 0.6) / 1.0), 120)
        base_scale = {"boo": 0.25, "pip": 0.26, "bella": 0.24}[name]
        fr.put(sprites[name], x, y, lerp(base_scale, gs * r, p))
    if lift > 0:
        sparkle_trail(fr, T, lambda tt: (gx - 200 - tt * 50, gy + 40 + tt * 150), t, length=0.8, n=16, size=0.7)


# ---------------- Scene 11: Wanda's chant
@shot(S("chant_wanda"), S("chant_wanda", 2))
def s11a(fr, T, t, u):
    fr.bg("sky", 1200, 470, 1700)
    ang = 2 * math.pi * (t / (2 * BAR)) - math.pi / 2
    x = 1200 + 520 * math.cos(ang)
    y = 470 + 170 * math.sin(ang)
    moving_left = math.sin(ang) > 0
    s = 0.42 + 0.08 * math.sin(ang)
    sparkle_trail(fr, T, lambda tt: (1200 + 520 * math.cos(2 * math.pi * (tt / (2 * BAR)) - math.pi / 2),
                                     500 + 170 * math.sin(2 * math.pi * (tt / (2 * BAR)) - math.pi / 2)), t, 0.9, 20, 0.6)
    broom_group(fr, T, x, y, s, flip=moving_left, cheer=True, rot=(6 if moving_left else -6))


@shot(S("chant_wanda", 2), S("bridge"))
def s11b(fr, T, t, u):
    cx = lerp(800, 1500, u)
    fr.bg("sky", cx, 450, 1000)
    sparkle_trail(fr, T, lambda tt: (800 + tt * 700 / 4.8 - 330, 520 + 30 * math.sin(tt * 3)), t, 1.0, 20, 0.8)
    broom_group(fr, T, cx + 40, 450 + 30 * math.sin(T * 2.2), 0.75, cheer=True, rot=-4 + 4 * math.sin(T * 2))


# ---------------- Scene 12: bridge — counting stars
STAR_POS = [(1300, 180), (1500, 260), (1700, 200), (1900, 300), (2100, 230)]


def _stars(fr, T, gather=0.0):
    for k, (x, y) in enumerate(STAR_POS):
        at = S("bridge", k)
        if T < at:
            continue
        p = clamp((T - at) / 0.35)
        sc = 0.75 * (p + 0.35 * math.sin(p * math.pi))
        tx, ty = 1500 + k * 140, 330 + k * 90
        fr.put(gfx.star(True, 120), lerp(x, tx, gather), lerp(y, ty, gather) + bob(T, 6, 2 * BEAT, k), sc,
               rot=12 * math.sin(T * 2 + k))


def _numbers(fr, T):
    for k in range(5):
        at = S("bridge", k, 3) if k < 4 else S("bridge", 4, 0)
        if at <= T < at + 1.2:
            uu = (T - at) / 1.2
            sc = 1 + 0.5 * math.exp(-uu * 9) * math.cos(uu * 25)
            fr.text(str(k + 1), W - 170, 170, 150, fill=(255, 214, 80), stroke=(255, 255, 255), sw=10,
                    alpha=1 - seg(uu, 0.75, 1.0), scale=sc)


@shot(S("bridge"), S("bridge", 2))
def s12a(fr, T, t, u):
    fr.bg("sky", 1500, 380, 1400)
    _stars(fr, T)
    broom_group(fr, T, 1180, 560 + bob(T, 10), 0.5, rider_arms="wave")
    _numbers(fr, T)


@shot(S("bridge", 2), S("bridge", 4))
def s12b(fr, T, t, u):
    fr.bg("sky", 1650, 380, 1400)
    _stars(fr, T)
    broom_group(fr, T, 1320 + 60 * u, 560 + bob(T, 10), 0.5, rider_arms="wave")
    _numbers(fr, T)


@shot(S("bridge", 4), S("bridge", 6))
def s12c(fr, T, t, u):
    fr.bg("sky", 1750, 470, 1500)
    g = seg(t, 0.8, 2.6)
    _stars(fr, T, g)
    if g > 0.3:
        sparkle_trail(fr, T, lambda tt: (1500 + tt * 420, 330 + tt * 270 + 20 * math.sin(tt * 5)), (t - 1.2) * 1.0, 1.4, 34, 0.8)
        fr.put(gfx.cottage(), 2130, 780, 0.28 * seg(t, 1.8, 2.8), alpha=seg(t, 1.8, 2.8))
    broom_group(fr, T, 1380 + 120 * u, 600 + bob(T, 10), 0.45, rider_arms="wave")
    _numbers(fr, T)


@shot(S("bridge", 6), S("final_a"))
def s12d(fr, T, t, u):
    fr.bg("home", lerp(800, 560, ease(u)), lerp(520, 600, ease(u)), lerp(1500, 1050, ease(u)))
    fr.put(mama(T), 300, 770, 0.3)
    fr.put(papa(T), 560, 770, 0.3)
    p = seg(t, 0, 4.8)
    broom_group(fr, T, lerp(1500, 900, p), lerp(250, 480, p) + bob(T, 8), 0.4, flip=True, cheer=t > 1.2)


# ---------------- Scene 13: final chorus A — home!
CAST = {"pip": 360, "bella": 560, "mama": 1020, "papa": 1230, "wanda": 1430}


@shot(S("final_a"), S("final_a", 2))
def s13a(fr, T, t, u):
    fr.bg("garden", 900, 560, 1300)
    _garden_friends(fr, T, skip=("mama", "papa"))
    p = seg(t, 0.4, 1.6)
    hug = p >= 1
    fr.put(mama(T, "hug" if hug else "wave", "happy" if hug else None), 1010 - 30 * p, 700, 0.36)
    fr.put(papa(T, "hug" if hug else "wave", "happy" if hug else None), 1240 + 30 * p, 700, 0.36)
    bx = lerp(700, 1125, p)
    fr.put(boo_spr(T, eye="happy" if hug else None, mouth="grin", arms="hug" if hug else "up"), bx,
           lerp(500, 700, p) + hop(p, 60), 0.28)


def _garden_friends(fr, T, skip=(), dance=False):
    b = (lambda k: -20 * _chant_bounce(T + k * 0.15)) if dance else (lambda k: 0)
    if "pip" not in skip:
        fr.put(gfx.pip("wave" if dance and int(T / BEAT) % 2 else "down", 1.4), CAST["pip"], 730 + b(0), 0.3)
    if "bella" not in skip:
        fr.put(bella_spr(T), CAST["bella"], 560 + bob(T, 10) + b(1), 0.3)
    if "mama" not in skip:
        fr.put(mama(T, "up" if dance and int(T / BEAT) % 2 else "wave"), CAST["mama"], 700 + b(2), 0.36)
    if "papa" not in skip:
        fr.put(papa(T, "up" if dance and int(T / BEAT) % 2 == 0 else "wave"), CAST["papa"], 700 + b(3), 0.36)
    if "wanda" not in skip:
        fr.put(gfx.wanda("wave" if dance and int(T / BEAT) % 2 else "down", "closed" if blink(T, 0.9) else "open"),
               CAST["wanda"], 640 + bob(T, 10) + b(4), 0.36, flip=True)


@shot(S("final_a", 2), S("final_a", 4))
def s13b(fr, T, t, u):
    fr.bg("garden", 900, 580, 1450)
    _garden_friends(fr, T)
    stops = [("pip", 0.0), ("bella", 1.6), ("wanda", 3.2)]
    idx = min(2, int(t / 1.6))
    name, t0 = stops[idx]
    prev = CAST[stops[idx - 1][0]] if idx > 0 else 760
    tx = CAST[name] + (90 if name != "wanda" else -150)
    p = seg(t - t0, 0, 0.6)
    x = lerp(prev + (90 if idx > 0 and stops[idx - 1][0] != "wanda" else 0), tx, p)
    hugging = p >= 1
    fr.put(boo_spr(T, eye="happy" if hugging else None, mouth="grin", arms="hug" if hugging else "down"), x,
           640 + hop(p, 70) + bob(T, 4), 0.27, flip=True)


@shot(S("final_a", 4), S("final_a", 6))
def s13c(fr, T, t, u):
    p = punch(T, "final_a")
    fr.bg("garden", 900, 600, 1250 * (1 - 0.07 * min(1, p)))
    _garden_friends(fr, T, dance=t > 2.4)
    calls = [S("final_a", 4, k) for k in range(4)]
    open_m = any(0 <= T - c < 0.35 for c in calls)
    fr.put(boo_spr(T, mouth="open" if open_m else "grin", arms="up"), 790, 560 + bob(T, 8), 0.3, sq=0.06 * p)
    boo_text(fr, T, "final_a")


@shot(S("final_a", 6), S("final_b"))
def s13d(fr, T, t, u):
    fr.bg("garden", 860, lerp(620, 520, ease(u)), lerp(900, 1500, ease(u)))
    g = seg(t, 0, 1.4)
    pos = {"pip": lerp(CAST["pip"], 640, g), "bella": lerp(CAST["bella"], 720, g), "mama": lerp(CAST["mama"], 900, g),
           "papa": lerp(CAST["papa"], 1040, g), "wanda": lerp(CAST["wanda"], 1150, g)}
    hug = g >= 1
    fr.put(gfx.wanda("down", "happy" if False else ("closed" if hug else "open")), pos["wanda"], 600 + bob(T, 6), 0.36, flip=True)
    fr.put(papa(T, "hug" if hug else "wave", "happy" if hug else None), pos["papa"], 700, 0.36)
    fr.put(mama(T, "hug" if hug else "wave", "happy" if hug else None), pos["mama"], 700, 0.36)
    fr.put(bella_spr(T, eye="happy" if hug else None), pos["bella"], 600 + bob(T, 6), 0.3)
    fr.put(gfx.pip("down", 1.6), pos["pip"], 735, 0.3)
    fr.put(boo_spr(T, eye="happy", mouth="grin", arms="hug"), 820, 690 + bob(T, 4), 0.3)
    if hug:
        for i in range(8):
            a = 0.5 + 0.5 * math.sin(T * 3 + i)
            fr.put(gfx.sparkle(50), 600 + i * 80, 470 + 40 * math.sin(i * 1.7 + T), 0.8 * a, alpha=a)


# ---------------- Scene 14: final chorus B — dance party
LIGHT_COLS = [(255, 150, 60), (190, 140, 255), (255, 220, 90), (120, 230, 200)]


def _string_lights(fr, T, n_on=99):
    for i in range(22):
        x = 120 + i * 62
        y = 330 + 60 * math.sin(i / 21 * math.pi) ** 1.0 * 0 + 50 * (1 - ((i - 10.5) / 10.5) ** 2) * -1 + 70
        if i >= n_on:
            break
        a = 0.7 + 0.3 * math.sin(T * 5 + i)
        fr.put(gfx.string_light(LIGHT_COLS[i % 4]), x, y, 0.9, alpha=a)


@shot(S("final_b"), S("final_b", 2))
def s14a(fr, T, t, u):
    fr.bg("garden", 900, lerp(380, 560, ease(seg(t, 0, 2.4))), 1500)
    _string_lights(fr, T, int(clamp(t / 2.4) * 22) + 1)
    _garden_friends(fr, T, dance=True)
    fr.put(boo_spr(T, mouth="grin", arms="up" if int(T / BEAT) % 2 else "down"), 790, 560 - 20 * _chant_bounce(T), 0.3)


@shot(S("final_b", 2), S("final_b", 4))
def s14b(fr, T, t, u):
    fr.bg("garden", lerp(700, 1000, u), 600, 1300)
    _string_lights(fr, T)
    fireflies(fr, T, 18, (100, 300, 1500, 800), 8)
    _garden_friends(fr, T, dance=True)
    fr.put(boo_spr(T, mouth="grin", arms="up" if int(T / BEAT) % 2 else "down"), 790, 560 - 20 * _chant_bounce(T), 0.3)
    fr.put(owl_spr(T), 200, 640 - 20 * _chant_bounce(T + 0.2), 0.42, rot=8 * math.sin(math.pi * T / BEAT))
    for k, x in enumerate([120, 470, 960, 1400, 1520]):
        fr.put(gfx.pip("down", 2.0, baby=True), x, 820 - 25 * _chant_bounce(T + 0.1 * k), 0.17)


@shot(S("final_b", 4), S("final_b", 6))
def s14c(fr, T, t, u):
    p = punch(T, "final_b")
    fr.bg("garden", 900, 600, 1200 * (1 - 0.07 * min(1, p)))
    _string_lights(fr, T)
    bi = int(t / BEAT)
    bt = (t % BEAT) / BEAT
    # signature moves on rotating beats
    who = bi % 4
    fr.put(gfx.pip("wave", 1.6), CAST["pip"] + 40, 730 - 20 * _chant_bounce(T), 0.32, rot=360 * ease(bt) if who == 0 else 0)
    fr.put(bella_spr(T), CAST["bella"], 560 + hop(bt, 60 if who == 1 else 0), 0.32, rot=-360 * ease(bt) if who == 1 else 0)
    fr.put(mama(T, "up"), CAST["mama"], 700 - 20 * _chant_bounce(T + 0.2), 0.36)
    fr.put(papa(T, "up"), CAST["papa"], 700 - 20 * _chant_bounce(T + 0.35), 0.36)
    fr.put(gfx.wanda("wave"), CAST["wanda"] - 20, 640 + bob(T, 8), 0.36, flip=True,
           rot=25 * math.sin(bt * math.pi * 2) if who == 2 else 0)
    calls = [S("final_b", 4, k) for k in range(4)]
    open_m = any(0 <= T - c < 0.35 for c in calls)
    fr.put(boo_spr(T, mouth="open" if open_m else "grin", arms="up"), 790, 540 + bob(T, 8), 0.32,
           rot=360 * ease(bt) if who == 3 else 0, sq=0.05 * p)
    boo_text(fr, T, "final_b")


@shot(S("final_b", 6), S("outro"))
def s14d(fr, T, t, u):
    fr.bg("garden", 860, lerp(600, 300, ease(u)), lerp(1250, 1600, ease(u)))
    _string_lights(fr, T)
    _garden_friends(fr, T, dance=True)
    fr.put(boo_spr(T, mouth="grin", arms="wave"), 790, 560 + bob(T, 8), 0.3)
    rng = np.random.default_rng(21)
    for i in range(40):
        x0, sp, ph = rng.uniform(0, 1600), rng.uniform(80, 160), rng.uniform(0, 6)
        y = -50 + ((T * sp + ph * 100) % 900)
        fr.put(gfx.sparkle(40, LIGHT_COLS[i % 4]), x0 + 30 * math.sin(T + ph), y, 0.8)


# ---------------- Scene 15: outro
@shot(S("outro"), S("outro", 2))
def s15a(fr, T, t, u):
    fr.bg("bedroom", lerp(800, 720, u), lerp(470, 560, u), lerp(1500, 1100, ease(u)))
    sleepy = t > 2.4
    yawn = 1.2 < t < 2.2
    fr.put(boo_spr(T, eye="closed" if sleepy or yawn else None, mouth="o" if yawn else "smile",
                   arms="wave" if t < 1.2 or 2.4 < t < 3.6 else "down"), 640, 640 + bob(T, 3), 0.42, rot=-6)
    fr.put(gfx.bed(), 700, 720, 1.05)
    if sleepy:
        a = seg(t, 2.6, 3.2)
        for i in range(3):
            zt = (t * 0.6 + i * 0.33) % 1
            fr.text("z", 760 + 30 * i + 40 * zt, 330 - 120 * zt, 40 + 12 * i, fill=(220, 210, 255), alpha=a * (1 - zt))


@shot(S("outro", 2), song.DURATION + 1)
def s15b(fr, T, t, u):
    fr.bg("end", 800, 450, 1600)
    fr.put(gfx.crescent(), 800, 250 + bob(T, 6), 0.7)
    fr.text("LunaKids", W / 2, 375, 92, fill=(255, 226, 120), stroke=(110, 50, 170), sw=8)
    fr.text("Happy Halloween!", W / 2, 455, 52, fill=(255, 170, 60), stroke=(90, 40, 140))
    # subscribe button + 2 'more songs' boxes
    a = seg(t, 0.5, 1.0)
    fr.put(G["subscribe"], W / 2, 548, 1.0 + 0.04 * math.sin(T * 6), alpha=a, screen=True)
    for i, x in enumerate((180, W - 180)):
        fr.put(G["thumb"], x, 360, 1.0, alpha=a, screen=True)
        fr.text("More songs!", x, 470, 30, alpha=a)
    fr.put(gfx.boo("open", "smile", "wave"), 180, 350, 0.25, screen=True, alpha=a)
    fr.put(gfx.pip("wave", 1.5), W - 180, 355, 0.24, screen=True, alpha=a)


# ============================================================ captions & finishing
def build_captions(timing):
    caps = []
    for d in song.caption_lines():
        if d["section"] == "bridge" and d["voice"] == "kids":
            continue
        key = f"{d['t0']:.3f}"
        dur = d["t1"] - d["t0"] if d["voice"] == "silent" else timing.get(key, d["t1"] - d["t0"])
        caps.append((d["t0"], d["t1"], d["t0"], d["t0"] + max(0.4, dur), d["text"]))
    # merge: a caption stays until the next one starts (max 1.2s gap)
    out = []
    for i, (a, b, h0, h1, txt) in enumerate(caps):
        nxt = caps[i + 1][0] if i + 1 < len(caps) else b
        out.append((a, min(nxt, max(b, h1) + 0.6), h0, h1, txt))
    return out


def caption_imgs(txt):
    key = ("cap", txt)
    if key not in _TEXT_CACHE:
        size = 40 if len(txt) < 44 else 34
        base = text_img(txt, size, (255, 255, 255), (60, 24, 100), 4)
        hi = text_img(txt, size, (255, 214, 80), (60, 24, 100), 4)
        _TEXT_CACHE[key] = (base, hi)
    return _TEXT_CACHE[key]


def draw_caption(canvas, T):
    for (a, b, h0, h1, txt) in G["caps"]:
        if a <= T < b:
            base, hi = caption_imgs(txt)
            fade = min(1.0, (T - a) / 0.15, (b - T) / 0.15)
            bw, bh = base.width + 50, base.height + 6
            band = G["band_cache"].get((bw, bh))
            if band is None:
                band = Image.new("RGBA", (bw, bh), (0, 0, 0, 0))
                ImageDraw.Draw(band).rounded_rectangle([0, 0, bw - 1, bh - 1], radius=bh // 2, fill=(40, 18, 80, 150))
                G["band_cache"][(bw, bh)] = band
            y = H - bh - 22
            x = (W - bw) // 2
            if fade < 1:
                band = band.copy()
                band.putalpha(band.getchannel("A").point(lambda v: int(v * fade)))
            paste_clip(canvas, band, x, y)
            prog = clamp((T - h0) / max(0.1, h1 - h0))
            im = base
            if prog > 0:
                im = base.copy()
                cut = int(10 + (base.width - 20) * prog)
                im.paste(hi.crop((0, 0, cut, hi.height)), (0, 0))
            if fade < 1:
                im = im.copy()
                im.putalpha(im.getchannel("A").point(lambda v: int(v * fade)))
            paste_clip(canvas, im, (W - im.width) // 2, y + (bh - im.height) // 2 + 2)
            break


def find_shot(T):
    for t0, t1, fn in SHOTS:
        if t0 <= T < t1:
            return t0, t1, fn
    return SHOTS[-1]


def render_frame(i):
    T = i / FPS
    t0, t1, fn = find_shot(T)
    fr = Frame(T)
    fn(fr, T, T - t0, (T - t0) / (t1 - t0))
    img = fr.canvas
    # crossfade into section boundaries (soft 0.25 s dissolve between shots)
    if T - t0 < 0.25 and t0 > 0:
        pt0, pt1, pfn = find_shot(t0 - 1e-6)
        if pfn is not fn:
            pf = Frame(T)
            pfn(pf, T, T - pt0, (T - pt0) / (pt1 - pt0))
            img = Image.blend(pf.canvas, img, (T - t0) / 0.25)
    img.alpha_composite(G["vignette"])
    draw_caption(img, T)
    # fade from/to black
    k = min(1.0, T / 0.5, (song.DURATION - T) / 1.0)
    if k < 1:
        img = Image.blend(Image.new("RGBA", img.size, (0, 0, 0, 255)), img, max(0, k))
    return img.convert("RGB").tobytes()


def build_globals(asset_dir, audio_dir):
    gfx.FONT_PATH = os.path.join(asset_dir, "fredoka.woff")
    G["bg"] = build_backgrounds()
    timing_path = os.path.join(audio_dir, "vocal_timing.json")
    timing = json.load(open(timing_path)) if os.path.exists(timing_path) else {}
    G["caps"] = build_captions(timing)
    G["band_cache"] = {}
    v = gfx.radial(W, H, W / 2, H / 2, math.hypot(W, H) / 2, (0, 0, 0, 0), (20, 6, 40, 150))
    G["vignette"] = v
    sub = Image.new("RGBA", (300, 70), (0, 0, 0, 0))
    ImageDraw.Draw(sub).rounded_rectangle([0, 0, 299, 69], radius=35, fill=(230, 40, 60, 255))
    t = text_img("SUBSCRIBE", 34, (255, 255, 255), (150, 20, 40), 2)
    sub.alpha_composite(t, ((300 - t.width) // 2, (70 - t.height) // 2 + 2))
    G["subscribe"] = sub
    th = Image.new("RGBA", (260, 150), (0, 0, 0, 0))
    ImageDraw.Draw(th).rounded_rectangle([0, 0, 259, 149], radius=22, fill=(255, 255, 255, 60), outline=(255, 214, 80, 255),
                                         width=5)
    G["thumb"] = th


def main():
    asset_dir, audio_dir, out = sys.argv[1], sys.argv[2], sys.argv[3]
    build_globals(asset_dir, audio_dir)
    frames = range(N_FRAMES)
    if "--stills" in sys.argv:
        ts = [float(x) for x in sys.argv[sys.argv.index("--stills") + 1].split(",")]
        for T in ts:
            data = render_frame(int(T * FPS))
            Image.frombytes("RGB", (W, H), data).save(f"{out}_{T:06.1f}.jpg", quality=88)
        return
    audio = os.path.join(audio_dir, "mix.wav")
    ss = 0.0
    if "--preview" in sys.argv:
        k = sys.argv.index("--preview")
        a, b = float(sys.argv[k + 1]), float(sys.argv[k + 2])
        frames = range(int(a * FPS), int(b * FPS))
        ss = a
    # warm caches in the parent so workers inherit them
    for i in range(0, N_FRAMES, FPS // 2):
        render_frame(i)
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
           "-i", "-", "-ss", f"{ss}", "-i", audio, "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-preset", "medium",
           "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", out]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    with Pool(os.cpu_count()) as pool:
        for n, data in enumerate(pool.imap(render_frame, frames, chunksize=8)):
            proc.stdin.write(data)
            if n % 240 == 0:
                print(f"frame {n}/{len(frames)}", flush=True)
    proc.stdin.close()
    proc.wait()
    print("wrote", out)


if __name__ == "__main__":
    main()
