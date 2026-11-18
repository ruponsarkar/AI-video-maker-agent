"""
Painted backgrounds for the serial, drawn in code. The same place id always gives the same picture, so a palace
or a forest looks the same in every episode that goes back to it.

    Scenery(place="forest", time="night", weather="rain", seed="panchavati")
    .base      the still picture (1920 x 1080)
    .overlay(img, t)   moving things drawn on a frame: clouds, water, fireflies, rain, lightning

place:   palace throne_room forest ashram village river sea mountain battlefield cave garden golden_city sky
         desert market temple
time:    dawn day evening night
weather: clear rain storm fog wind
"""
import hashlib
import math
import random

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

W, H = 1920, 1080
GROUND = int(H * 0.86)      # where the characters stand
S = 2

PLACES = ("palace", "throne_room", "forest", "ashram", "village", "river", "sea", "mountain", "battlefield", "cave",
          "garden", "golden_city", "sky", "desert", "market", "temple")
INDOOR = {"throne_room", "cave", "temple"}
SKIES = {"dawn": [(255, 196, 150), (250, 150, 120), (150, 120, 180)],
         "day": [(120, 190, 250), (170, 216, 250), (220, 238, 250)],
         "evening": [(250, 140, 70), (230, 100, 110), (90, 60, 130)],
         "night": [(10, 16, 48), (24, 32, 80), (40, 44, 96)]}
TINT = {"dawn": (255, 220, 200, 30), "day": (0, 0, 0, 0), "evening": (255, 140, 80, 40), "night": (20, 30, 90, 110)}


def _rng(seed):
    return random.Random(int(hashlib.md5(str(seed).encode()).hexdigest(), 16))


def _mix(a, b, t):
    return tuple(int(x + (y - x) * t) for x, y in zip(a, b))


def _dark(c, f):
    return tuple(max(0, min(255, int(v * f))) for v in c[:3])


class _Pen:
    def __init__(self):
        self.img = Image.new("RGBA", (W * S, H * S), (0, 0, 0, 255))
        self.d = ImageDraw.Draw(self.img)

    def p(self, pts):
        return [(x * S, y * S) for x, y in pts]

    def poly(self, pts, fill, outline=None, width=0):
        self.d.polygon(self.p(pts), fill=fill, outline=outline, width=width * S)

    def rect(self, x0, y0, x1, y1, fill, outline=None, width=0):
        self.d.rectangle([x0 * S, y0 * S, x1 * S, y1 * S], fill=fill, outline=outline, width=width * S)

    def ellipse(self, cx, cy, rx, ry, fill, outline=None, width=0):
        self.d.ellipse([(cx - rx) * S, (cy - ry) * S, (cx + rx) * S, (cy + ry) * S], fill=fill, outline=outline,
                       width=width * S)

    def chord(self, cx, cy, rx, ry, a, b, fill):
        self.d.chord([(cx - rx) * S, (cy - ry) * S, (cx + rx) * S, (cy + ry) * S], a, b, fill=fill)

    def line(self, pts, fill, width):
        self.d.line(self.p(pts), fill=fill, width=int(width * S))

    def gradient(self, y0, y1, colours):
        for y in range(int(y0 * S), int(y1 * S)):
            t = (y / S - y0) / max(1, (y1 - y0))
            k = min(len(colours) - 2, int(t * (len(colours) - 1)))
            local = t * (len(colours) - 1) - k
            self.d.line([(0, y), (W * S, y)], fill=_mix(colours[k], colours[k + 1], local))

    def done(self):
        return self.img.resize((W, H), Image.LANCZOS)


# ------------------------------------------------------------------ pieces
def sky(pen, time, rng):
    pen.gradient(0, GROUND, SKIES.get(time, SKIES["day"]))
    if time == "night":
        for _ in range(160):
            x, y, r = rng.uniform(0, W), rng.uniform(0, GROUND * 0.7), rng.choice((1, 1, 1.5, 2))
            pen.ellipse(x, y, r, r, (255, 255, 240))
        pen.ellipse(W * 0.8, H * 0.16, 62, 62, (250, 244, 214))
        pen.ellipse(W * 0.8 + 22, H * 0.16 - 10, 54, 54, SKIES["night"][1])   # a crescent
    elif time in ("dawn", "evening"):
        sun_y = GROUND * (0.62 if time == "evening" else 0.66)
        for k in range(6, 0, -1):
            pen.ellipse(W * 0.3, sun_y, 70 + k * 26, 70 + k * 26, (255, 210, 140, 24))
        pen.ellipse(W * 0.3, sun_y, 70, 70, (255, 236, 170))
    else:
        pen.ellipse(W * 0.82, H * 0.14, 64, 64, (255, 248, 200))


def hills(pen, rng, base_y, colour, height, count=5):
    pts = [(0, base_y)]
    for k in range(count + 1):
        x = W * k / count
        pts += [(x - W / count / 2, base_y - rng.uniform(0.4, 1.0) * height), (x, base_y - rng.uniform(0.2, 0.6) * height)]
    pts += [(W, base_y), (W, GROUND + 5), (0, GROUND + 5)]
    pen.poly(pts, colour)


def mountains(pen, rng, colour, snow=True):
    for k in range(5):
        cx, h, w = rng.uniform(-100, W + 100), rng.uniform(320, 520), rng.uniform(420, 700)
        top = GROUND - 120 - h
        pen.poly([(cx - w / 2, GROUND - 60), (cx, top), (cx + w / 2, GROUND - 60)], _dark(colour, rng.uniform(0.85, 1.1)))
        if snow:
            pen.poly([(cx - w * 0.12, top + h * 0.2), (cx, top), (cx + w * 0.12, top + h * 0.2), (cx + w * 0.04, top + h * 0.16),
                      (cx - w * 0.03, top + h * 0.24)], (245, 248, 252))


def tree(pen, x, y, size, leaf, trunk=(110, 70, 40), kind="round"):
    pen.poly([(x - size * 0.07, y), (x - size * 0.04, y - size * 0.6), (x + size * 0.04, y - size * 0.6), (x + size * 0.07, y)],
             trunk)
    if kind == "palm":
        for a in range(-80, 100, 32):
            t = math.radians(a - 90)
            pen.line([(x, y - size * 0.62), (x + math.cos(t) * size * 0.5, y - size * 0.62 + math.sin(t) * size * 0.32 + size * 0.1)],
                     leaf, size * 0.06)
        return
    for dx, dy, r in ((0, -0.85, 0.36), (-0.26, -0.68, 0.28), (0.26, -0.68, 0.28), (-0.14, -1.06, 0.26), (0.16, -1.04, 0.24)):
        pen.ellipse(x + dx * size, y + dy * size, r * size, r * size * 0.92, _dark(leaf, 1 + dy * 0.12))


def ground(pen, colour, rng, grass=True):
    pen.rect(0, GROUND - 40, W, H, colour)
    pen.poly([(0, GROUND - 40), (W, GROUND - 52), (W, GROUND - 20), (0, GROUND - 10)], _dark(colour, 1.08))
    if grass:
        for _ in range(240):
            x, y = rng.uniform(0, W), rng.uniform(GROUND - 30, H)
            pen.line([(x, y), (x + rng.uniform(-6, 6), y - rng.uniform(10, 22))], _dark(colour, 0.8), 3)


LIT = (255, 206, 110)


def palace_building(pen, x, y, w, h, wall, roof, rng, gold=False, night=False):
    pen.rect(x, y - h, x + w, y, wall)
    for k in range(int(w // 120)):   # arches, lit from inside at night
        ax = x + 40 + k * 120
        inside = LIT if night and rng.random() < 0.7 else _dark(wall, 0.55)
        pen.rect(ax, y - h * 0.55, ax + 60, y - 4, inside)
        pen.ellipse(ax + 30, y - h * 0.55, 30, 30, inside)
    pen.rect(x - 14, y - h - 20, x + w + 14, y - h, _dark(wall, 0.85))
    for k in range(max(1, int(w // 220))):   # domes
        dx = x + w * (k + 0.5) / max(1, int(w // 220))
        r = min(110, w / 5)
        pen.chord(dx, y - h - 20, r, r * 1.1, 180, 360, roof)
        pen.line([(dx, y - h - 20 - r * 1.1), (dx, y - h - 20 - r * 1.1 - 40)], (240, 190, 50), 6)
        pen.poly([(dx, y - h - 30 - r * 1.1 - 50), (dx + 40, y - h - 30 - r * 1.1 - 40), (dx, y - h - 30 - r * 1.1 - 30)],
                 (220, 50, 50))
    if gold:
        for k in range(int(w // 60)):
            pen.line([(x + k * 60 + 30, y - h + 10), (x + k * 60 + 30, y - h * 0.6)], (255, 222, 120), 3)


def hut(pen, x, y, w, wall, roof, night=False):
    pen.rect(x, y - w * 0.55, x + w, y, wall)
    pen.poly([(x - w * 0.18, y - w * 0.5), (x + w / 2, y - w * 1.05), (x + w * 1.18, y - w * 0.5)], roof)
    for k in range(6):
        pen.line([(x + w / 2, y - w * 1.02), (x - w * 0.1 + k * w * 0.26, y - w * 0.52)], _dark(roof, 0.75), 3)
    pen.rect(x + w * 0.38, y - w * 0.34, x + w * 0.62, y, LIT if night else (70, 46, 30))


def pillar(pen, x, top, bottom, colour):
    pen.rect(x - 34, top, x + 34, bottom, colour)
    pen.rect(x - 48, top - 20, x + 48, top, _dark(colour, 0.85))
    pen.rect(x - 48, bottom - 24, x + 48, bottom, _dark(colour, 0.85))
    for k in (-16, 0, 16):
        pen.line([(x + k, top + 6), (x + k, bottom - 30)], _dark(colour, 0.88), 3)


def water(pen, y0, y1, colour):
    pen.gradient_rect = None
    for y in range(int(y0), int(y1), 2):
        t = (y - y0) / max(1, y1 - y0)
        pen.line([(0, y), (W, y)], _mix(_dark(colour, 1.15), _dark(colour, 0.75), t), 2)


def flowers(pen, rng, count, y0, y1):
    for _ in range(count):
        x, y = rng.uniform(0, W), rng.uniform(y0, y1)
        c = rng.choice([(240, 80, 120), (250, 200, 60), (255, 255, 255), (200, 90, 220), (250, 120, 60)])
        for a in range(5):
            t = math.radians(a * 72)
            pen.ellipse(x + math.cos(t) * 7, y + math.sin(t) * 7, 6, 6, c)
        pen.ellipse(x, y, 4, 4, (250, 220, 80))


# ------------------------------------------------------------------ places
def paint(place, time, rng):
    pen = _Pen()
    night = time == "night"
    if place not in INDOOR:
        sky(pen, time, rng)
    if place == "sky":
        pen.gradient(GROUND - 200, H, [SKIES.get(time, SKIES["day"])[-1], (236, 244, 252) if time != "night" else (50, 54, 100)])
    green = (92, 160, 76) if not night else (40, 70, 52)
    if place == "forest":
        hills(pen, rng, GROUND - 120, _dark(green, 0.7), 160)
        for k in range(16):
            x = rng.uniform(-60, W + 60)
            tree(pen, x, GROUND - rng.uniform(30, 80), rng.uniform(260, 380), _dark(green, rng.uniform(0.55, 0.8)))
        ground(pen, (110, 150, 70), rng)
        for x in (rng.uniform(40, 300), rng.uniform(W - 300, W - 40)):
            tree(pen, x, GROUND + 40, 560, _dark(green, 0.65))
    elif place == "ashram":
        hills(pen, rng, GROUND - 110, _dark(green, 0.75), 150)
        for k in range(6):
            tree(pen, rng.uniform(0, W), GROUND - 60, rng.uniform(240, 320), _dark(green, 0.7))
        ground(pen, (150, 160, 90), rng)
        hut(pen, W * 0.12, GROUND - 20, 300, (196, 150, 100), (170, 140, 70))
        hut(pen, W * 0.72, GROUND - 30, 260, (196, 150, 100), (170, 140, 70))
        pen.ellipse(W * 0.5, GROUND + 40, 90, 22, (120, 90, 60))   # the sacred fire pit
        tree(pen, W * 0.9, GROUND + 30, 520, _dark(green, 0.6))
    elif place == "palace":
        hills(pen, rng, GROUND - 160, (150, 180, 150) if not night else (50, 60, 70), 120)
        palace_building(pen, W * 0.12, GROUND - 60, W * 0.76, 360, (246, 226, 196), (250, 240, 230), rng, night=night)
        palace_building(pen, W * 0.36, GROUND - 420, W * 0.28, 200, (240, 214, 180), (250, 236, 220), rng, night=night)
        pen.rect(0, GROUND - 60, W, H, (214, 190, 160))
        for k in range(5):   # steps
            pen.rect(W * 0.3 - k * 20, GROUND - 60 + k * 12, W * 0.7 + k * 20, GROUND - 48 + k * 12, (232, 210, 180),
                     outline=(190, 166, 140), width=2)
        for x in (W * 0.06, W * 0.94):
            tree(pen, x, GROUND + 20, 420, _dark(green, 0.8), kind="palm")
    elif place == "golden_city":
        sea_col = (40, 90, 150) if not night else (20, 30, 70)
        water(pen, GROUND - 260, GROUND - 120, sea_col)
        for k in range(5):
            w = rng.uniform(220, 340)
            palace_building(pen, k * W / 5 + rng.uniform(-30, 30), GROUND - 100, w, rng.uniform(260, 460),
                            (236, 190, 70), (250, 214, 90), rng, gold=True, night=night)
        pen.rect(0, GROUND - 100, W, H, (190, 150, 70))
    elif place == "throne_room":
        pen.gradient(0, H, [(120, 40, 50), (90, 30, 44), (60, 20, 34)])
        for x in (W * 0.1, W * 0.3, W * 0.7, W * 0.9):
            pillar(pen, x, 120, GROUND - 20, (236, 214, 176))
        pen.poly([(W * 0.42, GROUND - 20), (W * 0.58, GROUND - 20), (W * 0.7, H), (W * 0.3, H)], (180, 30, 40))
        pen.rect(W * 0.43, GROUND - 330, W * 0.57, GROUND - 60, (232, 178, 40))   # the throne
        pen.ellipse(W * 0.5, GROUND - 330, 120, 70, (232, 178, 40))
        pen.rect(W * 0.455, GROUND - 260, W * 0.545, GROUND - 120, (180, 40, 60))
        pen.rect(0, GROUND - 20, W, H, (150, 110, 80))
        for x in (W * 0.2, W * 0.5, W * 0.8):   # hanging lamps
            pen.line([(x, 0), (x, 110)], (200, 170, 90), 4)
            pen.ellipse(x, 120, 26, 16, (250, 200, 80))
    elif place == "village":
        hills(pen, rng, GROUND - 120, _dark(green, 0.8), 130)
        for k in range(5):
            hut(pen, k * W / 5 + rng.uniform(0, 80), GROUND - 30, rng.uniform(220, 300), (200, 150, 104), (176, 120, 70), night=night)
        ground(pen, (180, 150, 100), rng, grass=False)
        tree(pen, W * 0.5, GROUND + 10, 460, _dark(green, 0.75))
    elif place == "river":
        hills(pen, rng, GROUND - 200, _dark(green, 0.75), 140)
        for k in range(8):
            tree(pen, rng.uniform(0, W), GROUND - 210, rng.uniform(160, 230), _dark(green, 0.7))
        water(pen, GROUND - 200, GROUND - 40, (70, 140, 200) if not night else (30, 50, 100))
        ground(pen, (170, 150, 100), rng)
        pen.poly([(W * 0.62, GROUND - 120), (W * 0.82, GROUND - 120), (W * 0.79, GROUND - 92), (W * 0.65, GROUND - 92)],
                 (120, 76, 44))   # a boat
    elif place == "sea":
        water(pen, GROUND - 330, GROUND - 40, (40, 110, 180) if not night else (20, 36, 80))
        ground(pen, (232, 210, 160), rng, grass=False)
        for x in (W * 0.08, W * 0.92):
            tree(pen, x, GROUND + 20, 460, (60, 140, 70), kind="palm")
    elif place == "mountain":
        mountains(pen, rng, (120, 130, 150) if not night else (50, 56, 80))
        ground(pen, (130, 140, 110), rng)
    elif place == "battlefield":
        hills(pen, rng, GROUND - 100, (150, 130, 100), 110)
        ground(pen, (176, 146, 100), rng, grass=False)
        for k in range(7):   # banners and tents in the distance
            x = rng.uniform(0, W)
            pen.line([(x, GROUND - 60), (x, GROUND - 260)], (90, 60, 40), 6)
            pen.poly([(x, GROUND - 260), (x + 80, GROUND - 240), (x, GROUND - 220)], rng.choice([(210, 40, 50), (240, 160, 30)]))
        for k in range(3):
            x = rng.uniform(0, W)
            pen.poly([(x - 90, GROUND - 60), (x, GROUND - 180), (x + 90, GROUND - 60)], (230, 220, 200))
    elif place == "cave":
        pen.gradient(0, H, [(40, 34, 40), (60, 50, 54), (30, 26, 30)])
        for k in range(14):
            x = rng.uniform(0, W)
            pen.poly([(x - 60, 0), (x, rng.uniform(80, 220)), (x + 60, 0)], (54, 46, 50))
        pen.ellipse(W * 0.5, GROUND - 300, 420, 300, (20, 16, 20))
        pen.rect(0, GROUND - 30, W, H, (70, 60, 60))
        for x in (W * 0.12, W * 0.88):   # torches
            pen.line([(x, GROUND - 320), (x, GROUND - 200)], (100, 70, 40), 12)
            pen.ellipse(x, GROUND - 340, 26, 40, (255, 160, 40))
    elif place == "garden":
        hills(pen, rng, GROUND - 140, _dark(green, 0.8), 120)
        for k in range(9):
            tree(pen, rng.uniform(0, W), GROUND - 50, rng.uniform(260, 360), _dark(green, rng.uniform(0.7, 0.9)))
        ground(pen, (110, 170, 80), rng)
        flowers(pen, rng, 140, GROUND - 30, H - 20)
        pen.ellipse(W * 0.7, GROUND + 60, 220, 40, (90, 160, 210))
    elif place == "sky":
        for _ in range(9):
            x, y = rng.uniform(0, W), rng.uniform(H * 0.3, H)
            for dx in (-60, 0, 60):
                pen.ellipse(x + dx, y, 120, 60, (250, 250, 255) if not night else (90, 100, 140))
    elif place == "desert":
        hills(pen, rng, GROUND - 80, (220, 180, 110), 140)
        ground(pen, (230, 196, 130), rng, grass=False)
    elif place == "market":
        hills(pen, rng, GROUND - 200, (160, 180, 160), 80)
        for k in range(6):
            x = k * W / 6
            pen.rect(x + 10, GROUND - 330, x + W / 6 - 10, GROUND - 40, rng.choice([(226, 190, 140), (214, 170, 130), (236, 206, 160)]))
            pen.poly([(x, GROUND - 200), (x + W / 6, GROUND - 200), (x + W / 6 - 20, GROUND - 160), (x + 20, GROUND - 160)],
                     rng.choice([(210, 60, 60), (240, 170, 40), (60, 140, 90)]))
        ground(pen, (190, 166, 130), rng, grass=False)
    elif place == "temple":
        pen.gradient(0, H, [(250, 220, 170), (230, 190, 140), (200, 160, 110)])
        pen.poly([(W * 0.35, GROUND - 40), (W * 0.42, 140), (W * 0.5, 60), (W * 0.58, 140), (W * 0.65, GROUND - 40)],
                 (226, 170, 110))
        for x in (W * 0.15, W * 0.85):
            pillar(pen, x, 160, GROUND - 20, (240, 220, 186))
        pen.rect(0, GROUND - 30, W, H, (200, 160, 120))
        pen.line([(W * 0.5, 0), (W * 0.5, 200)], (200, 160, 60), 4)
        pen.ellipse(W * 0.5, 220, 34, 40, (220, 170, 50))   # the temple bell
    else:
        ground(pen, (120, 160, 80), rng)
    img = pen.done()
    tint = TINT.get(time, (0, 0, 0, 0))
    if tint[3]:
        img = Image.alpha_composite(img, Image.new("RGBA", (W, H), tint))
    return img


# ------------------------------------------------------------------ the scene
class Scenery:
    def __init__(self, place="forest", time="day", weather="clear", seed=""):
        self.place = place if place in PLACES else "forest"
        self.time = time if time in SKIES else "day"
        self.weather = weather
        rng = _rng(f"{seed or place}")
        self.base = paint(self.place, self.time, rng)
        self.rng = random.Random(1)
        self.clouds = [] if self.place in INDOOR or self.time == "night" else self._clouds(rng)
        self.motes = [(rng.uniform(0, W), rng.uniform(GROUND * 0.4, GROUND + 40), rng.uniform(0, 6.28)) for _ in range(40)]
        self.drops = [(rng.uniform(0, W), rng.uniform(0, H), rng.uniform(0.7, 1.3)) for _ in range(380)]
        self.flash_at = [rng.uniform(2, 9) + 9 * k for k in range(60)] if weather == "storm" else []
        if weather == "fog" or (weather in ("rain", "storm")):
            veil = Image.new("RGBA", (W, H), (180, 190, 200, 70 if weather == "fog" else 50))
            self.base = Image.alpha_composite(self.base, veil)

    def _clouds(self, rng):
        out = []
        for _ in range(5):
            c = Image.new("RGBA", (520, 220), (0, 0, 0, 0))
            d = ImageDraw.Draw(c)
            for _ in range(7):
                x, y, r = rng.uniform(100, 420), rng.uniform(90, 140), rng.uniform(45, 80)
                d.ellipse([x - r * 1.4, y - r, x + r * 1.4, y + r], fill=(255, 255, 255, 210))
            out.append([c.filter(ImageFilter.GaussianBlur(5)), rng.uniform(-500, W), rng.uniform(20, 260), rng.uniform(6, 16)])
        return out

    def frame(self, t):
        """The background for time t (seconds into the scene), with its slow movements."""
        img = self.base.copy()
        for cloud, x0, y, speed in self.clouds:
            x = (x0 + t * speed) % (W + 600) - 560
            img.alpha_composite(cloud, (int(x), int(y)))
        d = ImageDraw.Draw(img)
        if self.place in ("river", "sea", "golden_city"):
            top = GROUND - (330 if self.place == "sea" else 260 if self.place == "golden_city" else 200)
            for k in range(26):
                y = top + 12 + (k * 37) % (GROUND - 60 - top)
                x = (k * 211 + t * (40 + k % 5 * 8)) % (W + 200) - 100
                d.line([(x, y), (x + 60 + k % 3 * 30, y)], fill=(230, 244, 255, 150), width=3)
        if self.place not in INDOOR and (self.time == "night" or self.place in ("garden", "forest")):
            glow = (255, 240, 140) if self.time == "night" else (255, 255, 255)
            for x, y, ph in self.motes[:24 if self.time == "night" else 10]:
                xx, yy = x + math.sin(t * 0.7 + ph) * 26, y + math.cos(t * 0.5 + ph) * 18
                a = int(120 + 120 * math.sin(t * 2 + ph))
                d.ellipse([xx - 4, yy - 4, xx + 4, yy + 4], fill=glow + (max(0, a),))
        if self.place == "cave" or self.place == "throne_room":   # flickering light
            a = int(18 + 14 * math.sin(t * 9) + 10 * math.sin(t * 23))
            img.alpha_composite(Image.new("RGBA", (W, H), (255, 170, 60, max(0, a))))
        return img

    def weather_overlay(self, img, t):
        """Rain and lightning go in front of the characters."""
        if self.weather in ("rain", "storm"):
            d = ImageDraw.Draw(img)
            for x, y, sp in self.drops:
                yy = (y + t * 1400 * sp) % (H + 40) - 20
                xx = (x - t * 220 * sp) % W
                d.line([(xx, yy), (xx - 8, yy + 26)], fill=(210, 220, 240, 150), width=2)
        if self.flash_at:
            for f in self.flash_at:
                if 0 <= t - f < 0.25:
                    img.alpha_composite(Image.new("RGBA", (W, H), (255, 255, 255, int(200 * (1 - (t - f) / 0.25)))))
        if self.weather == "wind":
            d = ImageDraw.Draw(img)
            for k, (x, y, ph) in enumerate(self.motes[:18]):
                xx = (x + t * 260 + k * 80) % W
                yy = y * 0.6 + math.sin(t * 3 + ph) * 30
                d.ellipse([xx - 7, yy - 4, xx + 7, yy + 4], fill=(120, 170, 60, 220))
        return img

    def lightning(self, t):
        return any(0 <= t - f < 0.25 for f in self.flash_at)
