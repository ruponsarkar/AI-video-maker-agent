"""
The rhyme cast: cute characters drawn in code (no licences): kids, animals, birds, sun, moon, stars and a train.

    Critter("elephant").image(mouth=0.6, blink=False, phase=0.25) -> RGBA picture, feet at the bottom edge
    KINDS                    every kind there is
    Critter(kind).floats     True for things that fly or swim (sun, star, fish, butterfly ...)

mouth 0..1 opens the mouth (lip-sync), phase 0..1 drives the loop of each character (ears flap, tail wags, wings
beat, rays turn, wheels roll), blink closes the eyes.
"""
import functools
import math

from PIL import Image, ImageDraw

S = 2                       # drawn at twice the size, then reduced: smooth edges
OUT = (52, 34, 46)
LINE = 4
WHITE = (255, 255, 255)
PINK = (255, 150, 170)
CHEEK = (255, 140, 150, 110)
SKIN = (238, 192, 152)


class Pen:
    def __init__(self, w, h):
        self.img = Image.new("RGBA", (w * S, h * S), (0, 0, 0, 0))
        self.d = ImageDraw.Draw(self.img)

    @staticmethod
    def _p(pts):
        return [(x * S, y * S) for x, y in pts]

    def ellipse(self, cx, cy, rx, ry, fill, outline=OUT, width=LINE):
        self.d.ellipse([(cx - rx) * S, (cy - ry) * S, (cx + rx) * S, (cy + ry) * S], fill=fill,
                       outline=outline, width=width * S if outline else 0)

    def circle(self, cx, cy, r, fill, outline=OUT, width=LINE):
        self.ellipse(cx, cy, r, r, fill, outline, width)

    def poly(self, pts, fill, outline=OUT, width=LINE):
        self.d.polygon(self._p(pts), fill=fill)
        if outline:
            self.d.line(self._p(list(pts) + [pts[0]]), fill=outline, width=width * S, joint="curve")

    def line(self, pts, fill=OUT, width=LINE):
        self.d.line(self._p(pts), fill=fill, width=int(width * S), joint="curve")
        r = width * S / 2
        for x, y in (pts[0], pts[-1]):
            self.d.ellipse([x * S - r, y * S - r, x * S + r, y * S + r], fill=fill)

    def thick(self, pts, fill, width):
        """A tube with an outline: tails, trunks, arms."""
        self.line(pts, OUT, width + LINE * 2)
        self.line(pts, fill, width)

    def arc(self, cx, cy, rx, ry, a, b, fill=OUT, width=LINE):
        self.d.arc([(cx - rx) * S, (cy - ry) * S, (cx + rx) * S, (cy + ry) * S], a, b, fill=fill, width=int(width * S))

    def chord(self, cx, cy, rx, ry, a, b, fill, outline=OUT):
        self.d.chord([(cx - rx) * S, (cy - ry) * S, (cx + rx) * S, (cy + ry) * S], a, b, fill=fill,
                     outline=outline, width=LINE * S if outline else 0)

    def done(self, w, h):
        return self.img.resize((w, h), Image.LANCZOS)


def shade(c, f):
    return tuple(max(0, min(255, int(v * f))) for v in c[:3])


def light(c, f=0.45):
    return tuple(int(v + (255 - v) * f) for v in c[:3])


def curve(points, steps=16):
    """A smooth line through a few control points (Catmull-Rom)."""
    pts = [points[0]] + list(points) + [points[-1]]
    out = []
    for k in range(1, len(pts) - 2):
        p0, p1, p2, p3 = pts[k - 1], pts[k], pts[k + 1], pts[k + 2]
        for s in range(steps):
            t = s / steps
            out.append(tuple(0.5 * ((2 * p1[i]) + (-p0[i] + p2[i]) * t + (2 * p0[i] - 5 * p1[i] + 4 * p2[i] - p3[i]) * t * t
                                    + (-p0[i] + 3 * p1[i] - 3 * p2[i] + p3[i]) * t ** 3) for i in (0, 1)))
    out.append(points[-1])
    return out


def face(pen, cx, cy, r, mouth, blink, eye_gap=0.4, eye_size=0.2, mouth_dy=0.42, mouth_dx=0.0, cheeks=True,
         lashes=False):
    """Big shiny eyes, rosy cheeks and a mouth that opens for singing."""
    er = r * eye_size
    for side in (-1, 1):
        ex, ey = cx + side * r * eye_gap, cy
        if blink:
            pen.arc(ex, ey - er * 0.2, er, er * 0.7, 20, 160, OUT, 4)
        else:
            pen.ellipse(ex, ey, er, er * 1.15, WHITE, OUT, 3)
            pen.ellipse(ex + er * 0.12, ey + er * 0.15, er * 0.62, er * 0.72, (40, 28, 40), None)
            pen.circle(ex + er * 0.35, ey - er * 0.2, er * 0.24, WHITE, None)
            pen.circle(ex - er * 0.1, ey + er * 0.4, er * 0.1, WHITE, None)
            if lashes:
                for k in (-1, 0, 1):
                    a = math.radians(-90 + side * 35 + k * 18)
                    pen.line([(ex + math.cos(a) * er, ey + math.sin(a) * er * 1.1),
                              (ex + math.cos(a) * er * 1.45, ey + math.sin(a) * er * 1.5)], OUT, 3)
        if cheeks:
            pen.ellipse(ex + side * er * 0.4, ey + er * 1.9, er * 0.85, er * 0.5, CHEEK, None)
    mx, my = cx + r * mouth_dx, cy + r * mouth_dy
    if mouth < 0.15:
        pen.arc(mx, my - r * 0.08, r * 0.2, r * 0.13, 15, 165, OUT, 4)
    else:
        h = r * (0.08 + 0.2 * mouth)
        pen.ellipse(mx, my, r * (0.15 + 0.05 * mouth), h, (150, 40, 60), OUT, 3)
        pen.ellipse(mx, my + h * 0.45, r * 0.1, h * 0.4, (240, 110, 120), None)


def wave(phase, amp=1.0):
    return math.sin(phase * 2 * math.pi) * amp


# ------------------------------------------------------------------ the cast
def kid(pen, mouth, blink, phase, girl=False, shirt=(60, 140, 240)):
    cx = 200
    sway = wave(phase, 3)
    # legs and shoes
    for side in (-1, 1):
        x = cx + side * 26
        pen.poly([(x - 15, 330), (x + 15, 330), (x + 13, 418), (x - 13, 418)], SKIN)
        pen.ellipse(x + side * 6, 422, 24, 12, (230, 70, 70) if girl else (60, 60, 80))
    if girl:
        pen.poly([(cx - 50, 245), (cx + 50, 245), (cx + 80, 355), (cx - 80, 355)], (240, 90, 150))
        pen.poly([(cx - 80, 342), (cx + 80, 342), (cx + 80, 355), (cx - 80, 355)], (255, 210, 230), None)
    else:
        pen.poly([(cx - 54, 245), (cx + 54, 245), (cx + 58, 330), (cx - 58, 330)], shirt)
        pen.poly([(cx - 58, 318), (cx + 58, 318), (cx + 56, 352), (cx - 56, 352)], (60, 70, 110))
    # arms wave in turn
    for side in (-1, 1):
        lift = wave(phase + (0.5 if side > 0 else 0), 1)
        sx, sy = cx + side * 50, 258
        hx, hy = sx + side * (40 + 10 * lift), sy + 55 - 75 * max(0, lift)
        pen.thick([(sx, sy), (hx, hy)], SKIN if girl else shirt, 22)
        pen.circle(hx, hy, 14, SKIN)
    hx, hy = cx + sway, 150
    if girl:   # pigtails with ribbons
        for side in (-1, 1):
            pen.circle(hx + side * 98, hy + 20, 34, (40, 28, 30))
            pen.poly([(hx + side * 78, hy - 20), (hx + side * 112, hy - 40), (hx + side * 106, hy + 2)], (240, 60, 120))
    pen.circle(hx, hy, 95, SKIN)
    for side in (-1, 1):
        pen.ellipse(hx + side * 95, hy + 8, 14, 20, SKIN)
    hair = (40, 28, 30)
    pen.chord(hx, hy - 4, 99, 96, 180, 360, hair)
    for k in range(5):   # a soft fringe of curls
        pen.circle(hx - 70 + k * 35, hy - 22 + (6 if k in (1, 3) else 0), 26, hair, None)
    pen.ellipse(hx - 90, hy - 2, 12, 26, hair, None)
    pen.ellipse(hx + 90, hy - 2, 12, 26, hair, None)
    face(pen, hx, hy + 20, 80, mouth, blink, eye_gap=0.42, eye_size=0.21, mouth_dy=0.5, lashes=girl)


def cat(pen, mouth, blink, phase, fur=(250, 165, 70)):
    cx = 200
    tail = [(285, 380), (335, 350), (350, 290 + wave(phase, 18)), (330 + wave(phase, 20), 240)]
    pen.thick(curve(tail), fur, 26)
    pen.ellipse(cx, 345, 88, 78, fur)
    pen.ellipse(cx, 365, 50, 50, light(fur, 0.6), None)
    for side in (-1, 1):
        pen.ellipse(cx + side * 45, 418, 28, 16, fur)
    hy = 190
    for side in (-1, 1):
        pen.poly([(cx + side * 40, hy - 70), (cx + side * 85, hy - 125), (cx + side * 92, hy - 40)], fur)
        pen.poly([(cx + side * 52, hy - 72), (cx + side * 80, hy - 105), (cx + side * 84, hy - 55)], PINK, None)
    pen.ellipse(cx, hy, 100, 88, fur)
    for side in (-1, 1):   # stripes
        pen.line([(cx + side * 20, hy - 86), (cx + side * 26, hy - 62)], shade(fur, 0.75), 6)
    face(pen, cx, hy, 88, mouth, blink, mouth_dy=0.48)
    pen.poly([(cx - 9, hy + 22), (cx + 9, hy + 22), (cx, hy + 31)], PINK, OUT, 2)
    for side in (-1, 1):
        for k in (-1, 0, 1):
            pen.line([(cx + side * 40, hy + 35 + k * 8), (cx + side * 95, hy + 28 + k * 14)], OUT, 2)


def dog(pen, mouth, blink, phase, fur=(196, 136, 82)):
    cx = 200
    pen.thick(curve([(280, 360), (320, 330), (330 + wave(phase * 2, 22), 285)]), fur, 22)
    pen.ellipse(cx, 345, 92, 76, fur)
    pen.ellipse(cx + 40, 330, 30, 26, shade(fur, 0.8), None)
    for side in (-1, 1):
        pen.ellipse(cx + side * 45, 418, 30, 16, light(fur, 0.3))
    hy = 185
    pen.ellipse(cx, hy, 98, 90, fur)
    for side in (-1, 1):
        pen.ellipse(cx + side * 95, hy + 15 + wave(phase, 4), 30, 62, shade(fur, 0.72))
    pen.ellipse(cx, hy + 45, 52, 36, light(fur, 0.55), None)
    face(pen, cx, hy - 5, 86, mouth, blink, mouth_dy=0.78)
    pen.ellipse(cx, hy + 28, 16, 11, (40, 30, 36), None)


def rabbit(pen, mouth, blink, phase, fur=(246, 244, 250)):
    cx = 200
    for side in (-1, 1):
        tilt = wave(phase + (0.25 if side > 0 else 0), 6)
        pen.ellipse(cx + side * 38 + tilt, 70, 24, 72, fur)
        pen.ellipse(cx + side * 38 + tilt, 74, 12, 56, PINK, None)
    pen.circle(290, 385, 26, WHITE)
    pen.ellipse(cx, 350, 80, 74, fur)
    pen.ellipse(cx, 365, 46, 48, (255, 236, 240), None)
    for side in (-1, 1):
        pen.ellipse(cx + side * 40, 420, 34, 14, fur)
    hy = 205
    pen.ellipse(cx, hy, 88, 80, fur)
    face(pen, cx, hy - 5, 80, mouth, blink, mouth_dy=0.55)
    pen.ellipse(cx, hy + 18, 9, 7, PINK, None)
    if mouth < 0.3:
        pen.poly([(cx - 9, hy + 46), (cx + 9, hy + 46), (cx + 9, hy + 60), (cx - 9, hy + 60)], WHITE, OUT, 2)


def elephant(pen, mouth, blink, phase, skin=(158, 170, 198)):
    cx = 200
    pen.ellipse(cx, 335, 125, 85, skin)
    for k, x in enumerate((110, 160, 240, 290)):
        pen.poly([(x - 22, 360), (x + 22, 360), (x + 22, 420), (x - 22, 420)], shade(skin, 0.92 if k % 3 else 1))
        pen.ellipse(x, 420, 22, 8, light(skin, 0.5))
    hy = 175
    flap = 0.85 + 0.15 * wave(phase)
    for side in (-1, 1):
        pen.ellipse(cx + side * 105, hy + 10, 70 * flap, 85, skin)
        pen.ellipse(cx + side * 108, hy + 14, 48 * flap, 62, (240, 170, 185), None)
    pen.circle(cx, hy, 100, skin)
    face(pen, cx, hy - 15, 92, mouth, blink, mouth_dy=0.82, mouth_dx=0.38, eye_gap=0.45)
    sway = wave(phase, 14)
    trunk = curve([(cx, hy + 20), (cx + 5, hy + 80), (cx + sway, hy + 130), (cx + 30 + sway, hy + 150),
                   (cx + 45 + sway * 1.2, hy + 128)])
    pen.thick(trunk, skin, 34)
    for k in range(3):
        y = hy + 60 + k * 22
        pen.arc(cx + 3 + (sway * k / 3), y, 16, 6, 20, 160, shade(skin, 0.7), 2)


def lion(pen, mouth, blink, phase, fur=(244, 186, 84)):
    cx = 200
    pen.thick(curve([(285, 370), (330, 350), (350, 300 + wave(phase, 12))]), fur, 16)
    pen.circle(352, 296 + wave(phase, 12), 18, (190, 100, 40))
    pen.ellipse(cx, 345, 90, 76, fur)
    for side in (-1, 1):
        pen.ellipse(cx + side * 45, 418, 30, 16, fur)
    hy = 190
    mane = (196, 104, 44)
    for k in range(16):
        a = k / 16 * 2 * math.pi + wave(phase, 0.04)
        pen.circle(cx + math.cos(a) * 108, hy + math.sin(a) * 102, 38, mane)
    pen.circle(cx, hy, 108, mane, None)
    for side in (-1, 1):
        pen.circle(cx + side * 62, hy - 70, 22, fur)
    pen.circle(cx, hy, 84, fur)
    pen.ellipse(cx, hy + 38, 46, 30, light(fur, 0.55), None)
    face(pen, cx, hy - 8, 80, mouth, blink, mouth_dy=0.78)
    pen.poly([(cx - 13, hy + 18), (cx + 13, hy + 18), (cx, hy + 32)], (120, 60, 40), OUT, 2)


def monkey(pen, mouth, blink, phase, fur=(150, 96, 60)):
    cx = 200
    tail = curve([(270, 380), (330, 380), (350, 320), (320, 290 + wave(phase, 10)), (300, 310)])
    pen.thick(tail, fur, 16)
    pen.ellipse(cx, 345, 80, 75, fur)
    pen.ellipse(cx, 355, 48, 52, (232, 196, 150), None)
    for side in (-1, 1):
        lift = max(0, wave(phase + (0.5 if side > 0 else 0)))
        pen.thick([(cx + side * 60, 300), (cx + side * 100, 300 - 60 * lift)], fur, 22)
        pen.ellipse(cx + side * 45, 418, 30, 15, (232, 196, 150))
    hy = 190
    for side in (-1, 1):
        pen.circle(cx + side * 92, hy, 34, fur)
        pen.circle(cx + side * 92, hy, 20, (232, 196, 150), None)
    pen.circle(cx, hy, 90, fur)
    mask = (236, 200, 156)
    for side in (-1, 1):
        pen.circle(cx + side * 32, hy - 8, 38, mask, None)
    pen.ellipse(cx, hy + 38, 62, 42, mask, None)
    face(pen, cx, hy - 10, 80, mouth, blink, mouth_dy=0.75, cheeks=False)


def cow(pen, mouth, blink, phase, skin=(250, 248, 244)):
    cx = 200
    pen.ellipse(cx, 335, 120, 80, skin)
    for x, y, r in ((150, 320, 30), (250, 350, 24), (210, 300, 16)):
        pen.ellipse(x, y, r * 1.3, r, (50, 44, 50), None)
    for x in (110, 160, 240, 290):
        pen.poly([(x - 18, 365), (x + 18, 365), (x + 16, 420), (x - 16, 420)], skin)
        pen.ellipse(x, 420, 18, 8, (60, 50, 50))
    pen.thick(curve([(312, 320), (335, 350 + wave(phase, 10)), (330, 395)]), skin, 10)
    hy = 175
    for side in (-1, 1):
        pen.poly([(cx + side * 50, hy - 70), (cx + side * 80, hy - 120), (cx + side * 70, hy - 62)], (250, 230, 180))
        pen.ellipse(cx + side * 102, hy - 20 + wave(phase, 3), 40, 20, skin)
        pen.ellipse(cx + side * 102, hy - 20 + wave(phase, 3), 26, 11, PINK, None)
    pen.ellipse(cx, hy, 88, 95, skin)
    pen.ellipse(cx - 40, hy - 50, 30, 24, (50, 44, 50), None)
    face(pen, cx, hy - 25, 80, 0, blink, mouth_dy=0)
    pen.ellipse(cx, hy + 55, 72, 46, (255, 180, 190))
    for side in (-1, 1):
        pen.ellipse(cx + side * 26, hy + 45, 8, 11, (180, 90, 110), None)
    if mouth >= 0.15:
        pen.ellipse(cx, hy + 75, 22, 6 + 12 * mouth, (150, 40, 60), OUT, 3)
    else:
        pen.arc(cx, hy + 68, 22, 12, 20, 160, OUT, 4)


def frog(pen, mouth, blink, phase, skin=(120, 200, 90)):
    cx = 200
    for side in (-1, 1):
        pen.poly([(cx + side * 60, 360), (cx + side * 130, 380), (cx + side * 140, 420), (cx + side * 70, 420)], shade(skin, 0.85))
    pen.ellipse(cx, 360, 118, 66, skin)
    pen.ellipse(cx, 378, 70, 40, light(skin, 0.6), None)
    hy = 260 + wave(phase, 3)
    pen.ellipse(cx, hy, 125, 78, skin)
    for side in (-1, 1):
        pen.circle(cx + side * 60, hy - 70, 42, skin)
    face(pen, cx, hy - 70, 130, 0, blink, eye_gap=0.46, eye_size=0.22, cheeks=False, mouth_dy=0)
    for side in (-1, 1):
        pen.ellipse(cx + side * 75, hy + 10, 18, 10, CHEEK, None)
    if mouth >= 0.15:
        pen.chord(cx, hy + 10, 70, 12 + 30 * mouth, 0, 180, (150, 40, 60))
    else:
        pen.arc(cx, hy - 5, 70, 30, 20, 160, OUT, 5)


def duck(pen, mouth, blink, phase, feather=(255, 214, 70)):
    cx = 210
    for side in (-1, 1):
        pen.poly([(cx + side * 30 - 22, 425), (cx + side * 30 + 22, 425), (cx + side * 30, 400)], (250, 140, 40))
    pen.ellipse(cx, 345, 105, 72, feather)
    pen.poly([(cx + 95, 330), (cx + 135, 295), (cx + 120, 345)], feather)
    flap = wave(phase * 2, 18)
    pen.ellipse(cx + 20, 335 - flap * 0.5, 60, 36 + flap * 0.4, shade(feather, 0.9))
    hx, hy = cx - 35, 215
    pen.circle(hx, hy, 76, feather)
    face(pen, hx, hy - 15, 72, 0, blink, mouth_dy=0, eye_gap=0.38)
    open_ = 4 + 22 * mouth
    pen.ellipse(hx - 10, hy + 40 + open_, 46, 14, (230, 110, 30))
    pen.ellipse(hx - 10, hy + 32, 50, 16, (250, 150, 40))


def fish(pen, mouth, blink, phase, scales=(250, 140, 60)):
    cy = 230
    wag = wave(phase * 2, 22)
    pen.poly([(300, cy), (370, cy - 70 + wag), (355, cy + wag * 0.3), (370, cy + 70 + wag)], shade(scales, 0.85))
    pen.poly([(170, cy - 80), (240, cy - 125), (260, cy - 70)], shade(scales, 0.85))
    pen.ellipse(190, cy, 135, 90, scales)
    for x in (230, 270):
        pen.arc(x, cy, 30, 80, 300, 60, WHITE, 8)
    pen.poly([(190, cy + 35), (240, cy + 60 + wag * 0.4), (200, cy + 70)], shade(scales, 0.85))
    face(pen, 130, cy - 20, 80, 0, blink, eye_gap=0.38, mouth_dy=0)
    if mouth >= 0.15:
        pen.ellipse(108, cy + 40, 16, 8 + 12 * mouth, (150, 40, 60), OUT, 3)
    else:
        pen.arc(108, cy + 32, 18, 10, 20, 160, OUT, 4)


def butterfly(pen, mouth, blink, phase, wing=(240, 110, 200)):
    cx, cy = 200, 230
    f = 0.35 + 0.65 * abs(math.cos(phase * 2 * math.pi))
    for side in (-1, 1):
        pen.ellipse(cx + side * 80 * f, cy - 55, 85 * f, 75, wing)
        pen.ellipse(cx + side * 65 * f, cy + 55, 60 * f, 55, light(wing, 0.3))
        pen.circle(cx + side * 95 * f, cy - 60, 22 * f + 2, (255, 230, 90), None)
        pen.circle(cx + side * 70 * f, cy + 60, 14 * f + 2, (120, 210, 255), None)
    pen.ellipse(cx, cy + 20, 18, 80, (80, 50, 90))
    for side in (-1, 1):
        pen.line(curve([(cx + side * 10, cy - 80), (cx + side * 30, cy - 130), (cx + side * 50, cy - 140)]), OUT, 3)
        pen.circle(cx + side * 50, cy - 140, 7, OUT, None)
    pen.circle(cx, cy - 60, 36, (120, 80, 130))
    face(pen, cx, cy - 64, 36, mouth, blink, eye_gap=0.42, eye_size=0.28)


def sun(pen, mouth, blink, phase):
    cx, cy = 200, 220
    turn = phase * 2 * math.pi / 6
    for k in range(12):
        a = turn + k * 2 * math.pi / 12
        long_ = 175 if k % 2 else 155
        pts = [(cx + math.cos(a) * long_, cy + math.sin(a) * long_),
               (cx + math.cos(a + 0.16) * 112, cy + math.sin(a + 0.16) * 112),
               (cx + math.cos(a - 0.16) * 112, cy + math.sin(a - 0.16) * 112)]
        pen.poly(pts, (255, 170, 40))
    pen.circle(cx, cy, 120, (255, 214, 60))
    face(pen, cx, cy - 10, 110, mouth, blink)


def moon(pen, mouth, blink, phase):
    cx, cy = 200, 220
    pen.circle(cx, cy, 125, (252, 240, 190))
    for x, y, r in ((-60, -60, 18), (55, 55, 14), (70, -30, 10), (-40, 75, 12)):
        pen.circle(cx + x, cy + y, r, (236, 220, 160), None)
    face(pen, cx, cy, 110, mouth, blink or (phase % 1) > 0.9)


def star(pen, mouth, blink, phase):
    cx, cy = 200, 240
    big = 1 + 0.06 * wave(phase)
    pts = []
    for k in range(10):
        a = -math.pi / 2 + k * math.pi / 5
        r = (150 if k % 2 == 0 else 66) * big
        pts.append((cx + math.cos(a) * r, cy + math.sin(a) * r))
    pen.poly(pts, (255, 220, 60))
    face(pen, cx, cy + 5, 70, mouth, blink, eye_size=0.24)


def peacock(pen, mouth, blink, phase, body=(40, 96, 210)):
    cx = 200
    spread = 1 + 0.04 * wave(phase)
    for k in range(13):
        a = math.radians(-170 + k * (160 / 12))
        x, y = cx + math.cos(a) * 165 * spread, 280 + math.sin(a) * 165 * spread
        pen.line([(cx, 290), (x, y)], (60, 140, 70), 6)
        pen.ellipse(x, y, 26, 34, (40, 160, 90))
        pen.circle(x, y + 2, 14, (40, 190, 210), None)
        pen.circle(x, y + 3, 7, (30, 40, 140), None)
    for side in (-1, 1):
        pen.line([(cx + side * 18, 360), (cx + side * 22, 420)], (200, 150, 90), 6)
    pen.ellipse(cx, 330, 52, 70, body)
    hy = 205
    pen.thick([(cx, 290), (cx, hy + 30)], body, 40)
    for k in (-1, 0, 1):
        pen.line([(cx + k * 6, hy - 50), (cx + k * 18, hy - 85)], body, 3)
        pen.circle(cx + k * 18, hy - 88, 8, (40, 190, 210))
    pen.circle(cx, hy, 54, body)
    face(pen, cx, hy - 6, 52, 0, blink, mouth_dy=0, cheeks=False, eye_size=0.26)
    open_ = 3 + 10 * mouth
    pen.poly([(cx - 10, hy + 18), (cx + 10, hy + 18), (cx, hy + 38 + open_)], (240, 200, 120))


def parrot(pen, mouth, blink, phase, body=(70, 190, 90)):
    cx = 200
    pen.poly([(cx + 10, 360), (cx + 50, 435), (cx + 20, 440), (cx - 10, 380)], (40, 120, 220))
    pen.ellipse(cx, 320, 70, 92, body)
    pen.ellipse(cx + 30, 320 + wave(phase * 2, 6), 40, 70, shade(body, 0.8))
    for side in (-1, 1):
        pen.line([(cx + side * 20, 405), (cx + side * 22, 425)], (120, 110, 110), 6)
    hy = 205
    pen.circle(cx, hy, 72, body)
    face(pen, cx - 10, hy - 12, 66, 0, blink, mouth_dy=0, eye_gap=0.42)
    open_ = 2 + 14 * mouth
    pen.poly([(cx - 35, hy + 20), (cx + 10, hy + 18), (cx - 18, hy + 70)], (230, 50, 50))
    pen.poly([(cx - 30, hy + 30 + open_), (cx, hy + 30 + open_), (cx - 18, hy + 52 + open_)], (200, 40, 40))


def train(pen, mouth, blink, phase, paint=(230, 60, 60)):
    roll = phase * 2 * math.pi
    for k in range(3):   # puffs of smoke
        t = (phase + k / 3) % 1
        pen.circle(395 + t * 40, 120 - t * 110, 18 + 26 * t, (240, 240, 245, int(230 * (1 - t))), None)
    pen.poly([(380, 135), (420, 135), (414, 205), (386, 205)], (60, 60, 70))
    pen.poly([(330, 200), (480, 200), (480, 380), (330, 380)], (60, 140, 230))
    pen.poly([(350, 220), (460, 220), (460, 290), (350, 290)], (200, 235, 255))
    pen.ellipse(220, 300, 190, 85, paint)
    pen.poly([(60, 380), (500, 380), (500, 395), (60, 395)], (60, 60, 70))
    for x, r in ((120, 44), (240, 44), (420, 44)):
        pen.circle(x, 395, r, (50, 50, 60))
        pen.circle(x, 395, r - 14, (200, 200, 210), None)
        for k in range(3):
            a = roll + k * math.pi / 3
            pen.line([(x + math.cos(a) * (r - 16), 395 + math.sin(a) * (r - 16)),
                      (x - math.cos(a) * (r - 16), 395 - math.sin(a) * (r - 16))], (90, 90, 100), 4)
    pen.circle(70, 300, 78, light(paint, 0.15))
    face(pen, 70, 290, 72, mouth, blink, eye_gap=0.4)


# kind: (draw, canvas width, canvas height, size in a scene, floats, Roman name)
KINDS = {
    "boy": (lambda p, m, b, ph: kid(p, m, b, ph), 400, 440, 1.0, False, "Baccha"),
    "girl": (lambda p, m, b, ph: kid(p, m, b, ph, girl=True), 400, 440, 1.0, False, "Bacchi"),
    "cat": (cat, 400, 440, 0.82, False, "Billi"),
    "dog": (dog, 400, 440, 0.86, False, "Kutta"),
    "rabbit": (rabbit, 400, 440, 0.8, False, "Khargosh"),
    "elephant": (elephant, 400, 440, 1.2, False, "Haathi"),
    "lion": (lion, 400, 440, 1.05, False, "Sher"),
    "monkey": (monkey, 400, 440, 0.88, False, "Bandar"),
    "cow": (cow, 400, 440, 1.1, False, "Gaay"),
    "frog": (frog, 400, 440, 0.72, False, "Medhak"),
    "duck": (duck, 400, 440, 0.78, False, "Battakh"),
    "fish": (fish, 400, 440, 0.75, True, "Machhli"),
    "butterfly": (butterfly, 400, 440, 0.6, True, "Titli"),
    "sun": (sun, 400, 440, 0.95, True, "Sooraj"),
    "moon": (moon, 400, 440, 0.95, True, "Chanda"),
    "star": (star, 400, 440, 0.55, True, "Tara"),
    "peacock": (peacock, 400, 440, 1.05, False, "Mor"),
    "parrot": (parrot, 400, 440, 0.75, False, "Tota"),
    "train": (train, 520, 440, 1.25, False, "Rail Gaadi"),
}


class Critter:
    def __init__(self, kind):
        if kind not in KINDS:
            raise ValueError(f"No cartoon for '{kind}'. There is: {', '.join(KINDS)}")
        self.kind = kind
        self.draw, self.w, self.h, self.size, self.floats, self.name = KINDS[kind]

    def image(self, mouth=0.0, blink=False, phase=0.0):
        return _drawn(self.kind, round(min(1.0, max(0.0, mouth)) * 3) / 3, bool(blink), round((phase % 1) * 16) % 16 / 16)


@functools.lru_cache(maxsize=1500)
def _drawn(kind, mouth, blink, phase):
    draw, w, h = KINDS[kind][:3]
    pen = Pen(w, h)
    draw(pen, mouth, blink, phase)
    return pen.done(w, h)


if __name__ == "__main__":   # a contact sheet of the whole cast: python rhyme/critters.py out.png
    import sys
    cols = 5
    sheet = Image.new("RGBA", (cols * 420, ((len(KINDS) + cols - 1) // cols) * 460), (190, 230, 255, 255))
    for k, kind in enumerate(KINDS):
        img = Critter(kind).image(0.6 if k % 2 else 0, False, 0.2)
        img.thumbnail((400, 440))
        sheet.alpha_composite(img, ((k % cols) * 420 + 10, (k // cols) * 460 + 10))
    sheet.convert("RGB").save(sys.argv[1] if len(sys.argv) > 1 else "cast.png")
