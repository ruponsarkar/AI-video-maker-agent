"""
Backgrounds for rhymes: bright, simple, moving (clouds drift, bubbles rise, stars twinkle, the railway scrolls).

    Stage("garden", seed).frame(t) -> 1920x1080 RGB picture
    PLACES, Stage.ground (where feet stand), Stage.sky_band (where floating characters fly or swim)
"""
import functools
import math
import random

from PIL import Image, ImageDraw, ImageFilter

W, H = 1920, 1080
PLACES = ("garden", "jungle", "farm", "pond", "underwater", "sky", "night", "beach", "room", "rail")
OUT = (52, 34, 46)


def grad(d, y0, y1, top, bottom, x0=0, x1=W):
    for y in range(int(y0), int(y1)):
        t = (y - y0) / max(1, y1 - y0)
        d.line([(x0, y), (x1, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(top, bottom)))


def hills(d, rng, base, colour, height, count=4, x_offset=0, width=W):
    for k in range(count + 1):
        cx = x_offset + k * width / count + rng.uniform(-80, 80)
        r = rng.uniform(260, 420)
        d.ellipse([cx - r, base - height, cx + r, base + height * 1.5], fill=colour)


def tree(d, x, y, size, leaf=(70, 170, 80), kind="round"):
    d.rectangle([x - size * 0.09, y - size * 0.55, x + size * 0.09, y], fill=(140, 90, 50), outline=OUT, width=3)
    if kind == "palm":
        for a in range(-150, -20, 26):
            r = math.radians(a)
            d.ellipse([x + math.cos(r) * size * 0.35 - size * 0.28, y - size * 0.58 + math.sin(r) * size * 0.2 - 22,
                       x + math.cos(r) * size * 0.35 + size * 0.28, y - size * 0.58 + math.sin(r) * size * 0.2 + 22],
                      fill=leaf, outline=OUT, width=3)
        return
    for dx, dy, r in ((-0.22, -0.62, 0.26), (0.22, -0.62, 0.26), (0, -0.82, 0.3)):
        d.ellipse([x + dx * size - r * size, y + dy * size - r * size, x + dx * size + r * size, y + dy * size + r * size],
                  fill=leaf, outline=OUT, width=3)


def flower(d, x, y, colour, r=14):
    d.line([(x, y), (x, y + 40)], fill=(60, 140, 60), width=4)
    for k in range(5):
        a = k * 2 * math.pi / 5
        d.ellipse([x + math.cos(a) * r - r * 0.7, y + math.sin(a) * r - r * 0.7, x + math.cos(a) * r + r * 0.7,
                   y + math.sin(a) * r + r * 0.7], fill=colour, outline=OUT, width=2)
    d.ellipse([x - r * 0.55, y - r * 0.55, x + r * 0.55, y + r * 0.55], fill=(255, 220, 60), outline=OUT, width=2)


def cloud_sprite(scale=1.0):
    w, h = int(360 * scale), int(170 * scale)
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for cx, cy, r in ((0.3, 0.62, 0.3), (0.52, 0.45, 0.36), (0.74, 0.62, 0.26), (0.5, 0.7, 0.3)):
        d.ellipse([w * (cx - r * 0.5), h * (cy - r), w * (cx + r * 0.5), h * (cy + r)], fill=(255, 255, 255, 235))
    return img


@functools.lru_cache(maxsize=12)
def paint(place, seed):
    rng = random.Random(f"{place}{seed}")
    img = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(img)
    flowers = [(255, 110, 140), (255, 170, 60), (180, 120, 255), (255, 90, 90), (255, 255, 255)]
    if place == "underwater":
        grad(d, 0, H, (80, 200, 240), (20, 80, 160))
        for k in range(6):   # light rays
            x = rng.uniform(0, W)
            d.polygon([(x, 0), (x + 120, 0), (x + 380, H), (x + 220, H)], fill=(110, 215, 245))
        img = img.filter(ImageFilter.GaussianBlur(30))
        d = ImageDraw.Draw(img)
        d.ellipse([-300, H * 0.86, W + 300, H * 1.4], fill=(240, 214, 150), outline=OUT, width=4)
        for k in range(9):
            x, hgt = rng.uniform(40, W - 40), rng.uniform(160, 340)
            pts = [(x + math.sin(i / 3) * 18, H * 0.9 - i * hgt / 12) for i in range(13)]
            d.line(pts, fill=(60, 170, 90), width=18, joint="curve")
        for k in range(5):
            x = rng.uniform(100, W - 100)
            d.ellipse([x - 50, H * 0.88 - 30, x + 50, H * 0.88 + 20], fill=rng.choice(flowers), outline=OUT, width=3)
        return img
    if place == "night":
        grad(d, 0, H * 0.78, (20, 24, 80), (70, 50, 130))
        hills(d, rng, H * 0.66, (40, 70, 90), 120, 4)
        for x in range(60, W, 360):
            hx = x + rng.uniform(-30, 30)
            d.rectangle([hx, H * 0.58, hx + 110, H * 0.68], fill=(120, 80, 110), outline=OUT, width=3)
            d.polygon([(hx - 15, H * 0.58), (hx + 55, H * 0.52), (hx + 125, H * 0.58)], fill=(160, 70, 80), outline=OUT)
            d.rectangle([hx + 38, H * 0.61, hx + 70, H * 0.65], fill=(255, 214, 110))
        d.rectangle([0, H * 0.68, W, H], fill=(40, 90, 80))
        return img
    if place == "room":
        d.rectangle([0, 0, W, H * 0.8], fill=(255, 236, 200))
        for x in range(0, W, 120):
            d.line([(x, 0), (x, H * 0.8)], fill=(250, 222, 180), width=40)
        d.rectangle([0, H * 0.8, W, H], fill=(200, 140, 90))
        for x in range(0, W, 160):
            d.line([(x, H * 0.8), (x - 60, H)], fill=(180, 120, 76), width=4)
        d.rectangle([W * 0.08, H * 0.16, W * 0.3, H * 0.46], fill=(150, 210, 255), outline=(150, 100, 60), width=14)
        d.line([(W * 0.19, H * 0.16), (W * 0.19, H * 0.46)], fill=(150, 100, 60), width=8)
        d.rectangle([W * 0.72, H * 0.3, W * 0.92, H * 0.8], fill=(170, 110, 70), outline=OUT, width=4)
        for k, c in enumerate(((240, 80, 80), (80, 160, 240), (250, 200, 60), (120, 200, 100))):
            d.rectangle([W * 0.74 + k * 70, H * 0.36, W * 0.74 + k * 70 + 50, H * 0.5], fill=c, outline=OUT, width=3)
        d.ellipse([W * 0.45, H * 0.82, W * 0.75, H * 0.95], fill=(240, 110, 140))
        return img
    # outdoor places with sky
    sky = {"sky": ((120, 200, 255), (200, 235, 255)), "beach": ((110, 200, 250), (210, 240, 255)),
           "rail": ((130, 205, 255), (220, 240, 255))}.get(place, ((120, 200, 255), (215, 240, 255)))
    grad(d, 0, H, *sky)
    if place == "sky":
        for k in range(4):
            hills(d, rng, H * (1.02 + k * 0.03), (130 - k * 15, 210 - k * 10, 120), 90, 5)
        return img
    if place == "beach":
        d.rectangle([0, H * 0.55, W, H * 0.72], fill=(40, 150, 220))
        for x in range(0, W, 90):
            d.arc([x, H * 0.6, x + 90, H * 0.64], 200, 340, fill=(220, 245, 255), width=4)
        d.ellipse([-200, H * 0.66, W + 200, H * 1.3], fill=(250, 220, 150), outline=OUT, width=4)
        tree(d, W * 0.88, H * 0.8, 380, (60, 170, 80), "palm")
        for k in range(6):
            x = rng.uniform(80, W - 80)
            d.ellipse([x - 22, H * 0.9 - 12, x + 22, H * 0.9 + 12], fill=(255, 180, 190), outline=OUT, width=2)
        return img
    if place == "rail":
        return img   # the scrolling hills and the track are drawn per frame
    far = {"jungle": (60, 150, 90), "farm": (150, 210, 110), "pond": (120, 200, 120), "garden": (140, 210, 110)}[place]
    hills(d, rng, H * 0.62, light(far, 0.3), 160, 4)
    hills(d, rng, H * 0.7, far, 120, 5)
    d.rectangle([0, H * 0.78, W, H], fill=shade(far, 1.1))
    if place == "jungle":
        for k in range(9):
            x = k * W / 8 + rng.uniform(-40, 40)
            tree(d, x, H * 0.84, rng.uniform(420, 560), (40 + rng.randint(0, 40), 140 + rng.randint(0, 40), 70),
                 "palm" if k % 3 == 0 else "round")
        for k in range(5):
            x = rng.uniform(0, W)
            d.line([(x, 0), (x + rng.uniform(-30, 30), H * rng.uniform(0.2, 0.4))], fill=(50, 130, 60), width=8)
    if place == "garden":
        for x in (W * 0.08, W * 0.92):
            tree(d, x, H * 0.82, 420, (80, 180, 90))
        for k in range(26):
            flower(d, rng.uniform(30, W - 30), rng.uniform(H * 0.84, H * 0.95), rng.choice(flowers), rng.uniform(10, 16))
    if place == "farm":
        bx = W * 0.72
        d.rectangle([bx, H * 0.48, bx + 330, H * 0.8], fill=(210, 60, 60), outline=OUT, width=5)
        d.polygon([(bx - 30, H * 0.48), (bx + 165, H * 0.32), (bx + 360, H * 0.48)], fill=(160, 40, 50), outline=OUT)
        d.rectangle([bx + 115, H * 0.62, bx + 215, H * 0.8], fill=(250, 240, 220), outline=OUT, width=5)
        for x in range(0, W, 70):
            d.rectangle([x, H * 0.74, x + 16, H * 0.86], fill=(250, 240, 220), outline=OUT, width=2)
        d.rectangle([0, H * 0.77, W, H * 0.79], fill=(250, 240, 220))
        tree(d, W * 0.12, H * 0.82, 400)
    if place == "pond":
        d.ellipse([W * 0.15, H * 0.8, W * 0.85, H * 1.05], fill=(60, 160, 230), outline=OUT, width=5)
        for x in (W * 0.3, W * 0.62):
            d.ellipse([x - 70, H * 0.88, x + 70, H * 0.93], fill=(70, 170, 70), outline=OUT, width=3)
        for x in (W * 0.1, W * 0.9):
            for k in range(5):
                d.line([(x + k * 14, H * 0.85), (x + k * 14 - 10, H * 0.66)], fill=(70, 150, 60), width=6)
                d.ellipse([x + k * 14 - 18, H * 0.64, x + k * 14 - 2, H * 0.7], fill=(130, 90, 50))
    return img


def light(c, f=0.4):
    return tuple(int(v + (255 - v) * f) for v in c)


def shade(c, f):
    return tuple(max(0, min(255, int(v * f))) for v in c)


class Stage:
    def __init__(self, place="garden", seed=0):
        self.place = place if place in PLACES else "garden"
        self.seed = seed
        self.base = paint(self.place, seed)
        rng = random.Random(f"{self.place}-{seed}")
        self.clouds = [(rng.uniform(0, W), rng.uniform(40, 300), rng.uniform(0.6, 1.2), rng.uniform(8, 22))
                       for _ in range(5 if self.place not in ("underwater", "room", "night") else 0)]
        self.cloud = cloud_sprite()
        self.stars = [(rng.uniform(0, W), rng.uniform(0, H * 0.6), rng.uniform(2, 6), rng.uniform(0, 6))
                      for _ in range(120 if self.place == "night" else 0)]
        self.bubbles = [(rng.uniform(0, W), rng.uniform(0, H), rng.uniform(6, 20), rng.uniform(40, 90))
                        for _ in range(40 if self.place == "underwater" else 0)]
        self.ground = 0.8 * H   # above the lyrics box
        self.sky_band = (H * 0.12, H * 0.45) if self.place != "underwater" else (H * 0.2, H * 0.7)

    def frame(self, t):
        img = self.base.copy()
        if self.place == "rail":
            img = self.rail(t)
        d = ImageDraw.Draw(img, "RGBA")
        for x, y, s, r in self.stars:
            a = int(140 + 115 * math.sin(t * 2.2 + r))
            d.ellipse([x - s, y - s, x + s, y + s], fill=(255, 250, 200, a))
        for x, y, r, speed in self.bubbles:
            yy = (y - t * speed) % (H + 60) - 30
            xx = x + math.sin(t * 1.5 + y) * 14
            d.ellipse([xx - r, yy - r, xx + r, yy + r], outline=(230, 250, 255, 200), width=3)
            d.ellipse([xx - r * 0.4, yy - r * 0.5, xx - r * 0.1, yy - r * 0.2], fill=(255, 255, 255, 200))
        for x, y, s, speed in self.clouds:
            spr = self.cloud if s == 1 else self.cloud.resize((int(self.cloud.width * s), int(self.cloud.height * s)))
            xx = (x + t * speed) % (W + spr.width) - spr.width
            img.paste(spr, (int(xx), int(y)), spr)
        return img

    def rail(self, t):
        rng = random.Random("rail-hills")
        img = paint("rail", self.seed).copy()
        d = ImageDraw.Draw(img)
        for layer, (speed, base, col, hgt) in enumerate(((30, 0.62, (160, 215, 140), 170), (90, 0.74, (110, 190, 100), 120))):
            off = -(t * speed) % W
            for rep in (-1, 0, 1):
                r2 = random.Random(f"rail{layer}")
                hills(d, r2, H * base, col, hgt, 4, x_offset=off + rep * W)
        d.rectangle([0, H * 0.76, W, H], fill=(140, 200, 110))
        off = -(t * 260) % 120
        for x in range(-120, W + 120, 120):
            d.rectangle([x + off, H * 0.86, x + off + 60, H * 0.885], fill=(140, 100, 70))
        d.rectangle([0, H * 0.855, W, H * 0.862], fill=(120, 120, 130))
        d.rectangle([0, H * 0.878, W, H * 0.885], fill=(120, 120, 130))
        for k in range(3):
            x = (rng.uniform(0, W) - t * 160) % (W + 400) - 200
            tree(d, x, H * 0.8, 300)
        return img
