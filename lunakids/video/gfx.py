"""Drawing toolkit: soft 3D 'clay' shading for 2D silhouettes, plus all character sprites."""
import math
from functools import lru_cache

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

SS = 2  # supersampling for sprite construction

LIGHT = np.array([-0.45, -0.62, 0.64])
LIGHT = LIGHT / np.linalg.norm(LIGHT)
HALF = LIGHT + np.array([0, 0, 1.0])
HALF = HALF / np.linalg.norm(HALF)

FONT_PATH = None


def font(size):
    return ImageFont.truetype(FONT_PATH, size)


def puffy(mask, color, blur, spec=0.35, amb=0.45, strength=3.0, bounce=(110, 70, 190)):
    """Shade a silhouette mask (L image) as a soft, rounded 3D object."""
    m = np.asarray(mask, np.float32) / 255.0
    h = fblur(m, blur)
    h = np.sqrt(np.clip(h, 0, 1))
    gy, gx = np.gradient(h * blur * strength * 0.5)
    nz = np.ones_like(gx)
    norm = np.sqrt(gx * gx + gy * gy + 1)
    nx, ny, nz = -gx / norm, -gy / norm, nz / norm
    diff = np.clip(nx * LIGHT[0] + ny * LIGHT[1] + nz * LIGHT[2], 0, 1)
    sp = np.clip(nx * HALF[0] + ny * HALF[1] + nz * HALF[2], 0, 1) ** 36 * spec
    c = np.array(color, np.float32)
    rgb = c[None, None, :] * (amb + (1 - amb) * diff)[..., None]
    rgb += np.array(bounce, np.float32)[None, None, :] * (0.22 * np.clip(ny, 0, 1) ** 1.5)[..., None]
    rgb += 255 * sp[..., None]
    out = np.dstack([np.clip(rgb, 0, 255), m * 255]).astype(np.uint8)
    return Image.fromarray(out, "RGBA")


def _box(a, r, axis):
    if r < 1:
        return a
    c = np.cumsum(np.pad(a, [(r + 1, r) if ax == axis else (0, 0) for ax in range(a.ndim)], mode="edge"),
                  axis=axis, dtype=np.float64)
    hi = np.take(c, np.arange(2 * r + 1, c.shape[axis]), axis=axis)
    lo = np.take(c, np.arange(0, c.shape[axis] - 2 * r - 1), axis=axis)
    return ((hi - lo) / (2 * r + 1)).astype(np.float32)


def fblur(a, sigma):
    """Float gaussian approximation (3 box passes) — no 8-bit banding."""
    r = max(1, int(round(sigma * 0.95)))
    for _ in range(3):
        a = _box(_box(a, r, 0), r, 1)
    return a


def flat(mask, color, alpha=1.0):
    m = np.asarray(mask, np.float32) * alpha
    c = np.zeros((mask.size[1], mask.size[0], 4), np.uint8)
    c[..., 0], c[..., 1], c[..., 2] = color[:3]
    c[..., 3] = m.astype(np.uint8)
    return Image.fromarray(c, "RGBA")


def glow(mask, color, radius, alpha=0.6):
    g = mask.filter(ImageFilter.GaussianBlur(radius))
    return flat(g, color, alpha)


def vgrad(w, h, stops):
    """Vertical gradient RGB image. stops: [(pos 0..1, (r,g,b)), ...]."""
    ys = np.linspace(0, 1, h)
    pos = [p for p, _ in stops]
    cols = np.array([c for _, c in stops], np.float32)
    rgb = np.stack([np.interp(ys, pos, cols[:, k]) for k in range(3)], -1)
    arr = np.repeat(rgb[:, None, :], w, axis=1).astype(np.uint8)
    return Image.fromarray(arr, "RGB")


def radial(w, h, cx, cy, r, inner, outer):
    yy, xx = np.mgrid[0:h, 0:w]
    d = np.clip(np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2) / r, 0, 1)
    a = np.array(inner, np.float32)
    b = np.array(outer, np.float32)
    out = a[None, None, :] * (1 - d[..., None]) + b[None, None, :] * d[..., None]
    return Image.fromarray(out.astype(np.uint8), "RGBA" if len(inner) == 4 else "RGB")


class Spr:
    """Sprite canvas drawn at SS x supersampling in 'design' coordinates."""

    def __init__(self, w, h):
        self.w, self.h = w, h
        self.img = Image.new("RGBA", (w * SS, h * SS), (0, 0, 0, 0))

    def S(self, v):
        if isinstance(v, (list, tuple)):
            return [self.S(x) for x in v]
        return v * SS

    def mask(self):
        m = Image.new("L", (self.w * SS, self.h * SS), 0)
        return m, ImageDraw.Draw(m)

    def put(self, layer):
        self.img = Image.alpha_composite(self.img, layer)

    def blob(self, shapes, color, blur=None, spec=0.35, amb=0.45, strength=3.0, clip=None, bounce=(110, 70, 190)):
        """shapes: list of ('e'|'r'|'p'|'l'|'a'|'rr', coords, extra...)."""
        m, d = self.mask()
        draw_shapes(d, shapes, self.S)
        if clip is not None:
            m = Image.fromarray(np.minimum(np.asarray(m), np.asarray(clip)))
        if blur is None:
            bb = m.getbbox() or (0, 0, 10, 10)
            blur = max(3, 0.16 * min(bb[2] - bb[0], bb[3] - bb[1]))
        self.put(puffy(m, color, blur, spec, amb, strength, bounce))
        return m

    def paint(self, shapes, color, alpha=1.0, blur=0):
        m, d = self.mask()
        draw_shapes(d, shapes, self.S)
        if blur:
            m = m.filter(ImageFilter.GaussianBlur(blur * SS))
        self.put(flat(m, color, alpha))
        return m

    def halo(self, shapes, color, radius, alpha=0.6):
        m, d = self.mask()
        draw_shapes(d, shapes, self.S)
        self.put(glow(m, color, radius * SS, alpha))

    def done(self):
        return self.img.resize((self.w, self.h), Image.LANCZOS)


def draw_shapes(d, shapes, S):
    for sh in shapes:
        kind, c = sh[0], S(sh[1])
        if kind == "e":
            d.ellipse(c, fill=255)
        elif kind == "r":
            d.rectangle(c, fill=255)
        elif kind == "rr":
            d.rounded_rectangle(c, radius=S(sh[2]), fill=255)
        elif kind == "p":
            d.polygon([tuple(c[i:i + 2]) for i in range(0, len(c), 2)], fill=255)
        elif kind == "l":
            d.line([tuple(c[i:i + 2]) for i in range(0, len(c), 2)], fill=255, width=int(S(sh[2])), joint="curve")
            if len(sh) > 3 and sh[3]:  # round caps
                r = S(sh[2]) / 2
                for i in (0, len(c) - 2):
                    d.ellipse([c[i] - r, c[i + 1] - r, c[i] + r, c[i + 1] + r], fill=255)
        elif kind == "a":  # arc: box, start, end, width
            d.arc(c, sh[2], sh[3], fill=255, width=int(S(sh[4])))
        elif kind == "pie":
            d.pieslice(c, sh[2], sh[3], fill=255)
        elif kind == "chord":
            d.chord(c, sh[2], sh[3], fill=255)
        elif kind == "-e":
            d.ellipse(c, fill=0)
        elif kind == "-p":
            d.polygon([tuple(c[i:i + 2]) for i in range(0, len(c), 2)], fill=0)
        elif kind == "-r":
            d.rectangle(c, fill=0)


def star_points(cx, cy, r1, r2, n=5, rot=-90):
    pts = []
    for i in range(2 * n):
        r = r1 if i % 2 == 0 else r2
        a = math.radians(rot + i * 180 / n)
        pts += [cx + r * math.cos(a), cy + r * math.sin(a)]
    return pts


def smooth_poly(pts, iters=3):
    """Chaikin smoothing of a closed polygon given as flat list."""
    P = [(pts[i], pts[i + 1]) for i in range(0, len(pts), 2)]
    for _ in range(iters):
        Q = []
        for i in range(len(P)):
            a, b = P[i], P[(i + 1) % len(P)]
            Q += [(0.75 * a[0] + 0.25 * b[0], 0.75 * a[1] + 0.25 * b[1]),
                  (0.25 * a[0] + 0.75 * b[0], 0.25 * a[1] + 0.75 * b[1])]
        P = Q
    return [v for p in P for v in p]


# ====================================================================== eyes
def eyes(s, boxes, state, iris=(28, 32, 78), brows=False):
    for (x0, y0, x1, y1) in boxes:
        w, h = x1 - x0, y1 - y0
        if state == "closed":
            s.paint([("a", [x0, y0 + h * 0.15, x1, y1 - h * 0.15], 20, 160, max(3, w * 0.13))], iris)
            continue
        if state == "happy":
            s.paint([("a", [x0, y0 + h * 0.35, x1, y1 + h * 0.35], 200, 340, max(3, w * 0.14))], iris)
            continue
        s.blob([("e", [x0, y0, x1, y1])], iris, blur=w * 0.25, spec=0.0, amb=0.7)
        s.paint([("e", [x0 + w * 0.18, y0 + h * 0.14, x0 + w * 0.55, y0 + h * 0.46])], (255, 255, 255))
        s.paint([("e", [x0 + w * 0.58, y0 + h * 0.58, x0 + w * 0.76, y0 + h * 0.76])], (255, 255, 255), 0.85)
        if brows:
            s.paint([("a", [x0 - w * 0.1, y0 - h * 0.45, x1 + w * 0.1, y0 + h * 0.2], 200, 340, max(3, w * 0.1))], iris)


# ====================================================================== Boo-Boo family
@lru_cache(None)
def boo(eye="open", mouth="smile", arms="down", scarf=True, bow=None, bowtie=False):
    W, H = 440, 520
    s = Spr(W, H)
    body = [("e", [50, 20, 390, 360]), ("r", [50, 190, 390, 440])]
    for i, x in enumerate([92, 162, 232, 302, 350]):
        body.append(("e", [x - 52, 395, x + 52, 485 - (i % 2) * 18]))
    body.append(("-e", [118, 452, 196, 530]))
    body.append(("-e", [258, 452, 336, 530]))
    s.halo(body, (205, 215, 255), 16, 0.55)
    # arms
    if arms == "up":
        arm_l = [("e", [6, 140, 82, 230])]
        arm_r = [("e", [358, 140, 434, 230])]
    elif arms == "wave":
        arm_l = [("e", [14, 255, 92, 320])]
        arm_r = [("e", [356, 120, 432, 210])]
    elif arms == "hug":
        arm_l = [("e", [90, 280, 175, 340])]
        arm_r = [("e", [265, 280, 350, 340])]
    else:
        arm_l = [("e", [14, 255, 92, 320])]
        arm_r = [("e", [348, 255, 426, 320])]
    body_color = (246, 244, 255)
    if arms != "hug":
        s.blob(arm_l, body_color, blur=14, bounce=(150, 120, 220))
        s.blob(arm_r, body_color, blur=14, bounce=(150, 120, 220))
    bm = s.blob(body, body_color, blur=56, spec=0.28, amb=0.55, strength=2.4, bounce=(150, 120, 230))
    if arms == "hug":
        s.blob(arm_l, body_color, blur=14, bounce=(150, 120, 220))
        s.blob(arm_r, body_color, blur=14, bounce=(150, 120, 220))
    # face
    eyes(s, [(140, 140, 200, 222), (240, 140, 300, 222)], eye, brows=(eye == "worried"))
    s.paint([("e", [102, 222, 158, 254]), ("e", [282, 222, 338, 254])], (255, 140, 170), 0.55, blur=6)
    if mouth == "smile":
        s.paint([("a", [192, 210, 248, 256], 15, 165, 7)], (60, 40, 90))
    elif mouth == "open":
        s.paint([("chord", [186, 222, 254, 284], 0, 180)], (70, 30, 70))
        s.paint([("e", [204, 258, 240, 282])], (255, 120, 150))
    elif mouth == "o":
        s.paint([("e", [206, 232, 234, 266])], (70, 30, 70))
    elif mouth == "grin":
        s.paint([("chord", [180, 218, 260, 272], 0, 180)], (70, 30, 70))
        s.paint([("e", [204, 250, 240, 272])], (255, 120, 150))
    if scarf:
        clip = bm
        stripes = []
        for i in range(10):
            x = 40 + i * 38
            stripes.append((i, [("p", [x, 280, x + 38, 280, x + 26, 330, x - 12, 330])]))
        for i, sh in stripes:
            s.blob(sh + [], (255, 140, 40) if i % 2 == 0 else (150, 85, 215), blur=10,
                   clip=_band(s, [44, 284, 396, 330]), strength=2.0)
        s.blob([("rr", [290, 305, 336, 410], 16)], (255, 140, 40), blur=10)
        s.paint([("r", [290, 335, 336, 352]), ("r", [290, 372, 336, 389])], (150, 85, 215))
        s.paint([("l", [296, 410, 300, 422], 5), ("l", [313, 410, 313, 424], 5), ("l", [330, 410, 326, 422], 5)],
                (255, 140, 40))
    if bow:
        s.blob([("p", [220, 34, 160, 0, 150, 70]), ("p", [220, 34, 280, 0, 290, 70])], bow, blur=12)
        s.blob([("e", [204, 18, 236, 52])], bow, blur=8)
    if bowtie:
        s.blob([("p", [220, 300, 168, 270, 168, 332]), ("p", [220, 300, 272, 270, 272, 332])], (255, 140, 40), blur=10)
        s.blob([("e", [204, 284, 236, 316])], (255, 160, 60), blur=8)
    return s.done()


def _band(s, box):
    m, d = s.mask()
    d.rounded_rectangle(s.S(box), radius=s.S(18), fill=255)
    return m


# ====================================================================== Pip the Pumpkin
@lru_cache(None)
def pip(arms="down", glow_level=1.0, face="smile", baby=False):
    W, H = 480, 480
    s = Spr(W, H)
    orange, dark = (255, 138, 28), (232, 110, 18)
    if glow_level > 1.0:
        s.halo([("e", [90, 140, 390, 430])], (255, 170, 60), 26, min(0.9, 0.35 * glow_level))
    if not baby:
        if arms == "wave":
            s.paint([("l", [70, 300, 30, 240, 40, 180], 16, True)], (90, 150, 60))
            s.paint([("l", [410, 300, 450, 340, 440, 380], 16, True)], (90, 150, 60))
            s.blob([("e", [20, 160, 64, 200])], (110, 175, 70), blur=8)
        elif arms == "pat":
            s.paint([("l", [70, 300, 30, 340, 40, 380], 16, True)], (90, 150, 60))
            s.paint([("l", [410, 280, 460, 230, 478, 200], 16, True)], (90, 150, 60))
        else:
            s.paint([("l", [70, 300, 30, 340, 40, 385], 16, True)], (90, 150, 60))
            s.paint([("l", [410, 300, 450, 340, 440, 385], 16, True)], (90, 150, 60))
    lobes = [([40, 120, 230, 440], dark), ([250, 120, 440, 440], dark),
             ([95, 105, 290, 450], orange), ([190, 105, 385, 450], orange), ([150, 95, 330, 455], (255, 150, 40))]
    for box, col in lobes:
        s.blob([("e", box)], col, blur=40, spec=0.25, amb=0.5, strength=2.6, bounce=(140, 60, 120))
    s.blob([("p", [222, 112, 228, 40, 262, 30, 262, 112])], (110, 150, 55), blur=10, strength=2)
    s.paint([("a", [250, 10, 300, 60], 90, 300, 8)], (110, 150, 55))
    s.blob([("p", smooth_poly([262, 60, 320, 30, 360, 50, 330, 85, 280, 85], 3))], (120, 185, 70), blur=12)
    # carved face with candle glow
    rim = (130, 55, 15)
    if face == "smile":
        eyes_boxes = [[160, 200, 218, 262], [262, 200, 320, 262]]
    else:
        eyes_boxes = [[165, 205, 215, 255], [265, 205, 315, 255]]
    inner = (255, 236, 140) if glow_level >= 1 else (255, 200, 100)
    for b in eyes_boxes:
        s.paint([("e", [b[0] - 5, b[1] - 5, b[2] + 5, b[3] + 5])], rim)
        s.paint([("e", b)], (255, 170, 40))
        s.paint([("e", [b[0] + 10, b[1] + 10, b[2] - 10, b[3] - 10])], inner, 0.9, blur=4)
    smile = [("chord", [150, 250, 330, 380], 0, 180)]
    s.paint([("chord", [143, 243, 337, 387], 0, 180)], rim)
    s.paint(smile, (255, 170, 40))
    s.paint([("chord", [175, 270, 305, 360], 0, 180)], inner, 0.9, blur=5)
    s.paint([("e", [118, 280, 160, 306]), ("e", [320, 280, 362, 306])], (255, 90, 90), 0.4, blur=6)
    return s.done()


# ====================================================================== Bella the Bat
@lru_cache(None)
def bella(wings="up", eye="open"):
    W, H = 540, 400
    s = Spr(W, H)
    body_c, wing_c = (196, 168, 245), (150, 108, 215)
    if wings == "up":
        L = [250, 190, 190, 130, 120, 60, 40, 40, 60, 120, 90, 170, 140, 200, 160, 250, 200, 240]
    elif wings == "mid":
        L = [250, 200, 180, 170, 100, 150, 20, 160, 70, 210, 100, 260, 150, 250, 180, 290, 220, 250]
    else:
        L = [250, 210, 190, 220, 130, 240, 60, 300, 120, 320, 150, 360, 190, 330, 210, 370, 235, 290]
    R = []
    for i in range(0, len(L), 2):
        R += [540 - L[i], L[i + 1]]
    for poly in (L, R):
        s.blob([("p", smooth_poly(poly, 2))], wing_c, blur=18, strength=2.2)
    for (cx, cy) in [(L[6] + 40, L[7] + 35), (L[10] + 15, L[11] - 5), (R[6] - 40, R[7] + 35), (R[10] - 15, R[11] - 5)]:
        s.paint([("p", star_points(cx, cy, 11, 5))], (255, 215, 90))
    s.blob([("p", smooth_poly([200, 150, 215, 70, 250, 140], 2))], body_c, blur=10)
    s.blob([("p", smooth_poly([290, 140, 325, 70, 340, 150], 2))], body_c, blur=10)
    s.paint([("p", smooth_poly([212, 140, 220, 95, 240, 138], 2)), ("p", smooth_poly([300, 138, 320, 95, 328, 140], 2))],
            (255, 160, 200))
    s.blob([("e", [172, 104, 368, 296])], body_c, blur=50, spec=0.3, amb=0.5, strength=2.5)
    s.blob([("e", [235, 285, 260, 305]), ("e", [280, 285, 305, 305])], wing_c, blur=6)
    eyes(s, [(214, 160, 258, 214), (282, 160, 326, 214)], eye)
    s.paint([("a", [255, 205, 285, 232], 20, 160, 5)], (70, 40, 100))
    s.paint([("e", [196, 212, 232, 234]), ("e", [308, 212, 344, 234])], (255, 120, 170), 0.6, blur=5)
    return s.done()


# ====================================================================== Wanda (on broom)
@lru_cache(None)
def wanda(arm="wave", eye="open"):
    W, H = 640, 540
    s = Spr(W, H)
    # broom
    s.blob([("l", [70, 420, 620, 372], 18, True)], (160, 105, 60), blur=8, strength=2)
    bristle = smooth_poly([120, 400, 20, 350, 0, 420, 20, 490, 120, 440], 2)
    s.blob([("p", bristle)], (236, 196, 104), blur=16, strength=2.2)
    for k in range(6):
        y = 370 + k * 20
        s.paint([("l", [118, 420, 10, y + 5], 3)], (200, 150, 70), 0.6)
    s.blob([("p", [118, 400, 90, 370, 95, 440]), ("p", [118, 420, 150, 385, 145, 450])], (255, 140, 40), blur=8)
    s.blob([("e", [108, 400, 132, 440])], (255, 160, 60), blur=6)
    # legs/shoes
    s.blob([("rr", [330, 400, 360, 480], 12)], (95, 50, 140), blur=8)
    s.blob([("e", [320, 466, 390, 496])], (80, 40, 110), blur=10)
    # dress body
    s.blob([("p", smooth_poly([250, 420, 270, 250, 330, 215, 390, 250, 420, 420, 335, 440], 3))], (134, 72, 196),
           blur=40, strength=2.4)
    for y in (280, 330, 380):
        s.paint([("p", star_points(332, y, 12, 5))], (255, 150, 50))
    # arms
    if arm == "wave":
        s.blob([("l", [380, 270, 440, 210, 455, 150], 26, True)], (134, 72, 196), blur=12)
        s.blob([("e", [436, 120, 480, 164])], (245, 200, 170), blur=10)
    else:
        s.blob([("l", [380, 280, 430, 350, 470, 370], 26, True)], (134, 72, 196), blur=12)
        s.blob([("e", [455, 352, 495, 392])], (245, 200, 170), blur=10)
    # hair behind
    for (x, y, r) in [(262, 180, 28), (402, 180, 28), (258, 214, 24), (406, 214, 24), (270, 150, 26), (394, 150, 26)]:
        s.blob([("e", [x - r, y - r, x + r, y + r])], (222, 222, 238), blur=10)
    # head
    s.blob([("e", [270, 105, 394, 235])], (247, 204, 172), blur=34, strength=2.2, bounce=(160, 90, 120))
    s.paint([("e", [276, 182, 312, 206]), ("e", [352, 182, 388, 206])], (255, 120, 130), 0.55, blur=5)
    # glasses + eyes
    for cx in (306, 358):
        if eye == "wink" and cx == 358:
            s.paint([("a", [cx - 12, 148, cx + 12, 172], 200, 340, 4)], (60, 40, 70))
        else:
            s.paint([("e", [cx - 9, 152, cx + 9, 172])], (60, 40, 70))
            s.paint([("e", [cx - 5, 154, cx + 1, 160])], (255, 255, 255))
        s.paint([("a", [cx - 22, 140, cx + 22, 184], 0, 360, 4)], (90, 60, 120))
    s.paint([("l", [328, 160, 336, 160], 4)], (90, 60, 120))
    s.paint([("a", [312, 180, 352, 214], 20, 160, 5)], (140, 50, 70))
    # hat
    s.blob([("e", [230, 100, 434, 140])], (110, 60, 170), blur=12, strength=2)
    cone = smooth_poly([280, 120, 384, 120, 360, 60, 330, 20, 300, 4, 335, 40, 310, 70], 2)
    s.blob([("p", cone)], (124, 68, 190), blur=24, strength=2.2)
    s.blob([("p", [283, 100, 381, 100, 386, 122, 279, 122])], (255, 140, 40), blur=6)
    s.blob([("p", star_points(300, 6, 20, 9))], (255, 215, 90), blur=6)
    return s.done()


# ====================================================================== small things
@lru_cache(None)
def owl(eye="open"):
    s = Spr(220, 240)
    s.blob([("p", [50, 60, 60, 10, 95, 50]), ("p", [170, 60, 160, 10, 125, 50])], (110, 82, 140), blur=8)
    s.blob([("e", [30, 30, 190, 230])], (120, 90, 150), blur=36, strength=2.4)
    s.blob([("e", [65, 110, 155, 225])], (200, 175, 220), blur=20)
    for cx in (80, 140):
        s.blob([("e", [cx - 32, 58, cx + 32, 122])], (255, 220, 120), blur=10)
        if eye == "closed":
            s.paint([("a", [cx - 18, 76, cx + 18, 104], 20, 160, 5)], (60, 40, 70))
        else:
            s.paint([("e", [cx - 16, 74, cx + 16, 106])], (50, 35, 70))
            s.paint([("e", [cx - 9, 78, cx - 1, 86])], (255, 255, 255))
    if eye == "yawn":
        s.paint([("e", [92, 118, 128, 160])], (90, 40, 60))
    else:
        s.blob([("p", [100, 118, 120, 118, 110, 136])], (255, 150, 50), blur=5)
    return s.done()


@lru_cache(None)
def star(face=False, size=120):
    s = Spr(size, size)
    c = size / 2
    s.halo([("p", star_points(c, c, c * 0.8, c * 0.38))], (255, 230, 140), size * 0.08, 0.7)
    s.blob([("p", smooth_poly(star_points(c, c, c * 0.8, c * 0.4), 1))], (255, 214, 80), blur=size * 0.08, strength=2.2,
           bounce=(255, 140, 60))
    if face:
        k = size / 120
        s.paint([("e", [c - 16 * k, c - 8 * k, c - 8 * k, c + 4 * k]), ("e", [c + 8 * k, c - 8 * k, c + 16 * k, c + 4 * k])],
                (90, 60, 40))
        s.paint([("a", [c - 10 * k, c - 2 * k, c + 10 * k, c + 16 * k], 20, 160, max(2, 3 * k))], (90, 60, 40))
    return s.done()


@lru_cache(None)
def sparkle(size=40, color=(255, 240, 180)):
    s = Spr(size, size)
    c = size / 2
    s.halo([("e", [c - 6, c - 6, c + 6, c + 6])], color, size * 0.15, 0.9)
    s.paint([("p", [c, 0, c + size * 0.08, c, c, size, c - size * 0.08, c]),
             ("p", [0, c, c, c - size * 0.08, size, c, c, c + size * 0.08])], color)
    s.paint([("e", [c - 3, c - 3, c + 3, c + 3])], (255, 255, 255))
    return s.done()


@lru_cache(None)
def dot_glow(size=36, color=(230, 255, 150)):
    s = Spr(size, size)
    c = size / 2
    s.halo([("e", [c - 4, c - 4, c + 4, c + 4])], color, size * 0.2, 1.0)
    s.paint([("e", [c - 3, c - 3, c + 3, c + 3])], (255, 255, 230))
    return s.done()


@lru_cache(None)
def leaf():
    s = Spr(90, 90)
    s.blob([("p", smooth_poly([45, 5, 70, 25, 85, 50, 60, 60, 45, 85, 30, 60, 5, 50, 20, 25], 2))], (255, 130, 40), blur=10)
    s.paint([("l", [45, 15, 45, 80], 3)], (190, 80, 20))
    return s.done()


@lru_cache(None)
def moon(size=420, face=False):
    s = Spr(size, size)
    c = size / 2
    s.halo([("e", [c - c * 0.5, c - c * 0.5, c + c * 0.5, c + c * 0.5])], (255, 240, 190), size * 0.07, 0.8)
    s.blob([("e", [c - c * 0.46, c - c * 0.46, c + c * 0.46, c + c * 0.46])], (255, 246, 205), blur=size * 0.12,
           spec=0.1, amb=0.75, strength=1.5, bounce=(255, 200, 150))
    for (dx, dy, r) in [(-0.18, -0.11, 0.09), (0.15, 0.15, 0.07), (0.07, -0.22, 0.045), (-0.11, 0.22, 0.05)]:
        s.paint([("e", [c + (dx - r) * c, c + (dy - r) * c, c + (dx + r) * c, c + (dy + r) * c])], (235, 220, 175), 0.6, blur=3)
    if face:
        k = size / 420
        s.paint([("a", [c - 80 * k, c - 40 * k, c - 30 * k, c + 10 * k], 200, 340, 8 * k)], (150, 110, 80))
        s.paint([("a", [c + 30 * k, c - 40 * k, c + 80 * k, c + 10 * k], 200, 340, 8 * k)], (150, 110, 80))
        s.paint([("a", [c - 50 * k, c + 10 * k, c + 50 * k, c + 90 * k], 20, 160, 9 * k)], (150, 110, 80))
        s.paint([("e", [c - 120 * k, c + 20 * k, c - 70 * k, c + 55 * k]), ("e", [c + 70 * k, c + 20 * k, c + 120 * k, c + 55 * k])],
                (255, 160, 150), 0.5, blur=6)
    return s.done()


@lru_cache(None)
def crescent(size=360):
    """Smiling crescent moon for the LunaKids logo."""
    s = Spr(size, size)
    c = size / 2
    shape = [("e", [c - 0.8 * c, c - 0.8 * c, c + 0.8 * c, c + 0.8 * c]), ("-e", [c - 0.35 * c, c - 0.95 * c, c + 1.05 * c, c + 0.55 * c])]
    s.halo(shape, (255, 235, 160), size * 0.06, 0.9)
    s.blob(shape, (255, 220, 110), blur=size * 0.06, strength=2.4, bounce=(255, 140, 80))
    k = size / 360
    s.paint([("a", [c - 120 * k, c + 0 * k, c - 80 * k, c + 30 * k], 200, 340, 6 * k)], (150, 90, 50))
    s.paint([("a", [c - 120 * k, c + 40 * k, c - 50 * k, c + 100 * k], 300, 60, 7 * k)], (150, 90, 50))
    s.paint([("e", [c - 150 * k, c + 40 * k, c - 115 * k, c + 62 * k])], (255, 140, 130), 0.6, blur=4)
    return s.done()


@lru_cache(None)
def cottage(lit=1.0):
    s = Spr(520, 520)
    s.blob([("rr", [328, 40, 382, 170], 18)], (150, 100, 190), blur=14)
    s.blob([("e", [318, 26, 392, 60])], (170, 120, 210), blur=10)
    s.blob([("rr", [90, 230, 430, 490], 40)], (232, 216, 246), blur=40, strength=2.2)
    s.blob([("chord", [50, 70, 470, 330], 180, 360)], (118, 72, 180), blur=50, strength=2.4)
    s.blob([("rr", [44, 190, 476, 220], 14)], (98, 58, 158), blur=10)
    # window
    s.halo([("e", [200, 250, 330, 380])], (255, 220, 120), 30, 0.8 * lit)
    s.blob([("e", [190, 240, 340, 390])], (150, 100, 190), blur=12)
    win = (255, 226, 120) if lit > 0.5 else (160, 140, 200)
    s.put(Image.alpha_composite(Image.new("RGBA", s.img.size, (0, 0, 0, 0)),
                                radial_masked(s, [204, 254, 326, 376], (255, 246, 190), win)))
    s.paint([("r", [262, 254, 268, 376]), ("r", [204, 312, 326, 318])], (150, 100, 190))
    # door
    s.blob([("rr", [118, 340, 184, 490], 30)], (200, 110, 60), blur=14)
    s.paint([("e", [166, 410, 176, 420])], (255, 210, 90))
    # moon lantern
    s.paint([("l", [70, 490, 70, 380], 6)], (90, 60, 110))
    s.halo([("e", [52, 352, 92, 392])], (255, 220, 120), 16, 0.9)
    s.blob([("e", [52, 352, 92, 392]), ("-e", [64, 344, 102, 384])], (255, 214, 90), blur=6)
    return s.done()


def radial_masked(s, box, inner, outer):
    m, d = s.mask()
    d.ellipse(s.S(box), fill=255)
    w, h = s.img.size
    x0, y0, x1, y1 = s.S(box)
    g = radial(w, h, (x0 + x1) / 2, (y0 + y1) / 2, (x1 - x0) / 2, inner + (255,), outer + (255,))
    g.putalpha(m)
    return g


@lru_cache(None)
def tree(variant=0, scale=1.0):
    rng = np.random.default_rng(variant + 11)
    W, H = 420, 560
    s = Spr(W, H)
    trunk = smooth_poly([190, 560, 200, 380, 175, 300, 200, 280, 225, 330, 240, 420, 240, 560], 2)
    s.blob([("p", trunk)], (92, 58, 110), blur=14, strength=2)
    s.paint([("l", [205, 330, 140, 270, 120, 240], 12, True), ("l", [232, 380, 300, 320, 320, 290], 12, True)], (92, 58, 110))
    cols = [(122, 78, 178), (140, 92, 196), (108, 66, 160)]
    blobs = [(210, 170, 150), (120, 230, 100), (300, 230, 105), (170, 100, 95), (260, 95, 90), (210, 250, 110)]
    for i, (x, y, r) in enumerate(blobs):
        x += rng.uniform(-15, 15)
        y += rng.uniform(-15, 15)
        s.blob([("e", [x - r, y - r, x + r, y + r])], cols[i % 3], blur=r * 0.35, strength=2.2, bounce=(70, 50, 140))
    for (x, y, r) in [(170, 150, 30), (260, 210, 26), (140, 240, 22)]:
        s.paint([("a", [x - r, y - r, x + r, y + r], 180, 420, 5)], (170, 130, 220), 0.7)
    return s.done()


@lru_cache(None)
def house(color, roof, variant=0):
    s = Spr(240, 260)
    s.blob([("rr", [30, 110, 210, 250], 26)], color, blur=24, strength=2)
    if variant % 2 == 0:
        s.blob([("chord", [10, 30, 230, 190], 180, 360)], roof, blur=26, strength=2.2)
    else:
        s.blob([("p", smooth_poly([10, 125, 120, 10, 230, 125], 1))], roof, blur=24, strength=2.2)
    for box in ([60, 140, 105, 185], [135, 140, 180, 185]):
        s.halo([("e", box)], (255, 220, 120), 12, 0.8)
        s.blob([("rr", box, 12)], (255, 222, 120), blur=6, amb=0.85, spec=0.0, bounce=(255, 160, 60))
    s.blob([("rr", [100, 195, 140, 250], 16)], (150, 90, 70), blur=8)
    return s.done()


@lru_cache(None)
def stone(lit=False):
    s = Spr(110, 60)
    if lit:
        s.halo([("e", [10, 10, 100, 50])], (255, 170, 60), 14, 0.9)
    s.blob([("e", [10, 10, 100, 50])], (255, 190, 90) if lit else (120, 100, 150), blur=12, strength=2)
    return s.done()


@lru_cache(None)
def signpost(arrow_phase=0):
    s = Spr(260, 340)
    s.blob([("rr", [118, 60, 142, 340], 10)], (170, 115, 70), blur=8)
    s.blob([("p", [40, 80, 200, 80, 240, 110, 200, 140, 40, 140])], (220, 160, 90), blur=12)
    s.blob([("p", [220, 160, 60, 160, 20, 190, 60, 220, 220, 220])], (210, 150, 85), blur=12)
    return s.done()


@lru_cache(None)
def lantern(color=(255, 200, 90)):
    s = Spr(70, 90)
    s.halo([("e", [12, 22, 58, 78])], color, 14, 0.9)
    s.blob([("e", [14, 24, 56, 76])], color, blur=8, amb=0.8, spec=0.1, bounce=(255, 120, 40))
    s.paint([("r", [26, 12, 44, 24])], (90, 60, 110))
    return s.done()


@lru_cache(None)
def cloud(variant=0):
    s = Spr(420, 200)
    rng = np.random.default_rng(variant)
    sh = [("e", [40, 90, 380, 190])]
    for i in range(4):
        x = 80 + i * 80 + rng.uniform(-15, 15)
        r = 60 + rng.uniform(-10, 25)
        sh.append(("e", [x - r, 120 - r, x + r, 120 + r]))
    s.blob(sh, (170, 140, 210), blur=40, amb=0.6, spec=0.05, strength=1.8, bounce=(240, 160, 140))
    return s.done()


@lru_cache(None)
def bed():
    s = Spr(700, 420)
    s.blob([("rr", [20, 60, 90, 420], 30), ("rr", [610, 160, 680, 420], 30)], (190, 120, 80), blur=16)
    s.blob([("rr", [60, 170, 120, 260], 30)], (250, 245, 255), blur=20)  # pillow
    s.blob([("rr", [40, 210, 660, 380], 50)], (60, 70, 160), blur=40, strength=2.2)
    rng = np.random.default_rng(3)
    for i in range(14):
        x, y = rng.uniform(90, 620), rng.uniform(235, 360)
        if i % 2:
            s.paint([("p", star_points(x, y, 14, 6))], (255, 215, 90))
        else:
            s.paint([("e", [x - 13, y - 13, x + 13, y + 13]), ("-e", [x - 6, y - 17, x + 18, y + 7])], (255, 225, 120))
    return s.done()


@lru_cache(None)
def string_light(color):
    s = Spr(40, 52)
    s.halo([("e", [8, 14, 32, 46])], color, 10, 1.0)
    s.blob([("e", [10, 16, 30, 44])], color, blur=5, amb=0.85, spec=0.2)
    return s.done()
