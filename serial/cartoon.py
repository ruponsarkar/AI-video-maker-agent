"""
Cartoon characters, drawn in code from a fixed description, so a character looks the same in every episode.

A character spec (stored once in the series bible, never changed):
    {"id": "ram", "kind": "human", "gender": "male", "age": "young", "skin": "blue",
     "outfit": "royal", "colors": ["yellow", "red"], "hair": "long", "headwear": "crown",
     "beard": "none", "prop": "bow", "extras": ["tilak", "aura"], "height": 1.0}

kind:     human | monkey | bear | bird | demon
outfit:   royal | queen | princess | sage | warrior | common | common_woman | forest | demon | monkey | bear | bird
hair:     short | long | bun | jata | bald | braid | spiky | none
headwear: none | crown | tiara | turban | horns | helmet
beard:    none | moustache | short | long_white | long_black | long_grey
prop:     none | bow | mace | staff | sword | trident | lotus | kamandal | conch | flute
extras:   tilak | bindi | aura | tail | ten_heads | fangs | earrings | mala

States drawn on request (and cached):
    head: emotion (calm happy sad angry surprised fear), mouth (0 closed, 1 half, 2 open), blink
    body: pose (idle point raise namaste bless attack), walk frame (0-3)
"""
import math
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFilter

S = 2                 # drawn at twice the size, then reduced: smooth edges
BASE_W, BASE_H = 700, 900
CX = 350              # the character's centre line in its own canvas
HEAD_H = 600          # the head layer covers the top of the canvas (crown to the end of a long beard)
OUTLINE = (40, 28, 30)

SKIN = {"fair": (247, 214, 186), "wheat": (234, 190, 150), "brown": (198, 142, 100), "dark": (140, 96, 66),
        "blue": (104, 150, 222), "deep_blue": (72, 110, 196), "demon_green": (112, 152, 96), "demon_red": (184, 76, 64),
        "demon_dark": (92, 74, 104), "monkey_orange": (220, 124, 56), "monkey_brown": (152, 102, 62),
        "bear": (92, 72, 58), "grey": (150, 150, 156), "golden": (232, 184, 84), "white": (240, 236, 228)}
COLORS = {"saffron": (244, 142, 32), "red": (210, 44, 52), "maroon": (128, 30, 48), "yellow": (250, 204, 44),
          "gold": (232, 178, 40), "green": (52, 160, 86), "emerald": (16, 140, 110), "blue": (48, 98, 206),
          "sky": (96, 178, 236), "purple": (124, 64, 180), "pink": (236, 104, 156), "white": (246, 244, 236),
          "cream": (244, 228, 192), "black": (40, 36, 44), "brown": (124, 80, 48), "orange": (246, 112, 34),
          "teal": (28, 150, 160), "silver": (196, 202, 212), "ochre": (198, 136, 54), "indigo": (64, 52, 150)}
HAIR = {"black": (34, 28, 32), "white": (236, 234, 228), "grey": (150, 148, 150), "brown": (92, 58, 36)}
GOLD, GOLD_DARK, GEM_RED, GEM_GREEN = (240, 190, 50), (184, 128, 24), (214, 40, 60), (30, 170, 110)


def colour(name, table=COLORS, default=(200, 120, 60)):
    if isinstance(name, (list, tuple)) and len(name) == 3:
        return tuple(name)
    return table.get(str(name), default)


def shade(c, f):
    return tuple(max(0, min(255, int(v * f))) for v in c)


def lighter(c, f=0.35):
    return tuple(int(v + (255 - v) * f) for v in c)


class Pen:
    """Drawing in character units (700 x 900), done at S times the size."""

    def __init__(self, w, h):
        self.img = Image.new("RGBA", (w * S, h * S), (0, 0, 0, 0))
        self.d = ImageDraw.Draw(self.img)

    @staticmethod
    def p(*xy):
        return [v * S for v in xy]

    def ellipse(self, cx, cy, rx, ry, fill, outline=OUTLINE, width=4):
        self.d.ellipse(self.p(cx - rx, cy - ry, cx + rx, cy + ry), fill=fill,
                       outline=outline, width=int(width * S) if outline else 0)

    def poly(self, pts, fill, outline=OUTLINE, width=4):
        flat = [v * S for xy in pts for v in xy]
        self.d.polygon(flat, fill=fill, outline=outline, width=int(width * S) if outline else 0)

    def line(self, pts, fill, width, rounded=True):
        flat = [v * S for xy in pts for v in xy]
        self.d.line(flat, fill=fill, width=int(width * S), joint="curve")
        if rounded:
            for x, y in pts:
                r = width / 2
                self.d.ellipse(self.p(x - r, y - r, x + r, y + r), fill=fill)

    def thick(self, pts, fill, width, outline=OUTLINE):
        """A limb: outlined thick line."""
        self.line(pts, outline, width + 7)
        self.line(pts, fill, width)

    def arc(self, cx, cy, rx, ry, start, end, fill, width=4):
        self.d.arc(self.p(cx - rx, cy - ry, cx + rx, cy + ry), start, end, fill=fill, width=int(width * S))

    def chord(self, cx, cy, rx, ry, start, end, fill, outline=OUTLINE, width=4):
        self.d.chord(self.p(cx - rx, cy - ry, cx + rx, cy + ry), start, end, fill=fill,
                     outline=outline, width=int(width * S) if outline else 0)

    def pieslice(self, cx, cy, rx, ry, start, end, fill, outline=None, width=0):
        self.d.pieslice(self.p(cx - rx, cy - ry, cx + rx, cy + ry), start, end, fill=fill,
                        outline=outline, width=int(width * S) if outline else 0)

    def done(self, w, h):
        return self.img.resize((w, h), Image.LANCZOS)


# ------------------------------------------------------------------ proportions
def frame(spec):
    """Key heights for this character, in canvas units."""
    child = spec.get("age") == "child"
    kind = spec.get("kind", "human")
    head_cy, head_r = (285, 130) if child else (265, 122)
    shoulder = 420 if child else 402
    hip = 590 if child else 622
    foot = 872
    width = 1.25 if kind in ("bear",) or spec.get("outfit") == "demon" else 1.0
    return {"head_cy": head_cy, "head_r": head_r, "shoulder": shoulder, "hip": hip, "foot": foot, "w": width,
            "child": child}


def canvas_width(spec):
    return 1100 if "ten_heads" in (spec.get("extras") or []) else BASE_W


def skin_of(spec):
    return colour(spec.get("skin", "wheat"), SKIN, SKIN["wheat"])


def hair_colour(spec):
    if spec.get("age") == "old":
        return HAIR["white"]
    if spec.get("hair_colour") in HAIR:
        return HAIR[spec["hair_colour"]]
    if spec.get("kind") in ("monkey", "bear"):
        return shade(skin_of(spec), 0.7)
    return HAIR["black"]


def main_colours(spec):
    cs = spec.get("colors") or ["saffron", "red"]
    a = colour(cs[0])
    b = colour(cs[1]) if len(cs) > 1 else shade(a, 0.7)
    return a, b


# ------------------------------------------------------------------ head
def draw_head(spec, emotion="calm", mouth=0, blink=False):
    w = canvas_width(spec)
    cx = w // 2
    pen = Pen(w, HEAD_H)
    f = frame(spec)
    extras = set(spec.get("extras") or [])
    if "aura" in extras:
        glow = Image.new("RGBA", pen.img.size, (0, 0, 0, 0))
        gd = ImageDraw.Draw(glow)
        r = f["head_r"] * 1.75
        for k in range(10, 0, -1):
            rr = r * k / 10
            gd.ellipse([(cx - rr) * S, (f["head_cy"] - rr) * S, (cx + rr) * S, (f["head_cy"] + rr) * S],
                       fill=(255, 222, 120, int(18 + 6 * (10 - k))))
        pen.img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(14 * S)))
        pen.d = ImageDraw.Draw(pen.img)
    if "ten_heads" in extras:   # Ravan: nine more heads behind, getting smaller to the sides
        side = Pen(w, HEAD_H)
        for k in range(1, 6):
            for sgn in (-1, 1):
                if sgn == -1 and k == 5:
                    continue
                _face(side, spec, cx + sgn * (k * 92), f["head_cy"] + 8 + k * 4, f["head_r"] * (0.78 - 0.04 * k),
                      emotion, 0, blink, small=True)
        pen.img.alpha_composite(side.img)
        pen.d = ImageDraw.Draw(pen.img)
    _face(pen, spec, cx, f["head_cy"], f["head_r"], emotion, mouth, blink)
    return pen.done(w, HEAD_H)


def _face(pen, spec, cx, cy, r, emotion, mouth, blink, small=False):
    kind = spec.get("kind", "human")
    skin = skin_of(spec)
    hair = hair_colour(spec)
    female = spec.get("gender") == "female"
    extras = set(spec.get("extras") or [])
    hairstyle = spec.get("hair", "short")
    head = spec.get("headwear", "none")
    k = r / 122.0

    # hair behind the head
    if hairstyle in ("long", "braid") or (female and hairstyle not in ("bald", "none", "bun")):
        pen.ellipse(cx, cy + 10 * k, r * 1.07, r * 1.14, hair)
    if kind == "bear":
        for sx in (-1, 1):
            pen.ellipse(cx + sx * r * 0.78, cy - r * 0.78, r * 0.32, r * 0.32, shade(skin, 0.85))
            pen.ellipse(cx + sx * r * 0.78, cy - r * 0.78, r * 0.17, r * 0.17, lighter(skin, 0.3), outline=None)
    # ears
    ear_r = r * (0.34 if kind == "monkey" else 0.2)
    for sx in (-1, 1):
        pen.ellipse(cx + sx * r * 0.98, cy + 12 * k, ear_r * 0.8, ear_r, shade(skin, 0.95))
        if kind == "monkey":
            pen.ellipse(cx + sx * r * 0.98, cy + 12 * k, ear_r * 0.45, ear_r * 0.6, lighter(skin, 0.45), outline=None)
        if "earrings" in extras or female or head == "crown":
            pen.ellipse(cx + sx * r * 0.98, cy + 12 * k + ear_r * 1.15, 11 * k, 13 * k, GOLD)
    # the face
    pen.ellipse(cx, cy, r, r * 1.06, skin)
    if kind in ("monkey", "bear"):   # lighter muzzle
        pen.ellipse(cx, cy + r * 0.38, r * 0.66, r * 0.5, lighter(skin, 0.5), outline=None)
        pen.ellipse(cx, cy - r * 0.16, r * 0.74, r * 0.46, lighter(skin, 0.38), outline=None)

    # hair on top
    if hairstyle not in ("bald", "none") and kind in ("human", "demon"):
        pen.chord(cx, cy - 6 * k, r * 1.04, r * 1.06, 180, 360, hair)
        if hairstyle == "spiky":
            for j in range(-3, 4):
                x = cx + j * r * 0.27
                pen.poly([(x - 22 * k, cy - r * 0.72), (x + j * 6 * k, cy - r * 1.32), (x + 22 * k, cy - r * 0.72)], hair)
        else:   # a fringe that frames the forehead
            pen.chord(cx - r * 0.5, cy - r * 0.48, r * 0.6, r * 0.34, 0, 180, hair, outline=None)
            pen.chord(cx + r * 0.5, cy - r * 0.48, r * 0.6, r * 0.34, 0, 180, hair, outline=None)
        if hairstyle == "bun":
            pen.ellipse(cx, cy - r * 1.08, r * 0.38, r * 0.3, hair)
        if hairstyle == "jata":   # matted hair piled on top
            for j, (dy, rw) in enumerate(((1.05, 0.46), (1.32, 0.38), (1.55, 0.28))):
                pen.ellipse(cx, cy - r * dy, r * rw, r * 0.22, hair)
            pen.line([(cx - r * 0.42, cy - r * 1.0), (cx + r * 0.42, cy - r * 1.0)], (140, 70, 40), 9 * k)

    # eyes
    ex, ey = r * 0.42, cy + r * 0.04
    iris = (150, 30, 30) if kind == "demon" else (60, 40, 30)
    look = 7 * k   # characters face right; mirrored for left
    for sx in (-1, 1):
        x = cx + sx * ex
        if blink:
            pen.arc(x, ey, r * 0.24, r * 0.12, 20, 160, OUTLINE, 6 * k)
            continue
        ry = r * (0.36 if emotion in ("surprised", "fear") else 0.29 if emotion == "happy" else 0.31)
        pen.ellipse(x, ey, r * 0.25, ry, (255, 255, 255), width=4 * k)
        pen.ellipse(x + look, ey + 4 * k, r * 0.15, r * 0.17, iris, outline=None)
        pen.ellipse(x + look, ey + 4 * k, r * 0.075, r * 0.085, (14, 10, 12), outline=None)
        pen.ellipse(x + look + r * 0.06, ey - r * 0.04, r * 0.045, r * 0.045, (255, 255, 255), outline=None)
        if female or "aura" in extras:   # kajal
            pen.arc(x, ey, r * 0.27, ry * 1.03, 195, 345, OUTLINE, 7 * k)
        if emotion == "happy":   # smiling eyes: lower lid lifts
            pen.chord(x, ey + ry * 1.05, r * 0.3, ry * 0.55, 180, 360, skin, outline=None)

    # brows
    by = ey - r * 0.4
    tilt = {"angry": 16, "sad": -14, "fear": -12, "surprised": 0, "happy": -3, "calm": 0}.get(emotion, 0)
    lift = {"surprised": -14, "fear": -8}.get(emotion, 0) * k
    brow = shade(hair, 0.9) if hair != HAIR["white"] else (200, 196, 190)
    for sx in (-1, 1):
        x0, x1 = cx + sx * ex - sx * r * 0.2, cx + sx * ex + sx * r * 0.2
        dy = tilt * k * 0.6
        pen.line([(x0, by + lift + dy), (x1, by + lift - dy * 0.2)], brow, (11 if kind == "demon" else 8) * k)

    # nose
    if kind in ("monkey", "bear"):
        pen.ellipse(cx, cy + r * 0.24, r * 0.16, r * 0.1, (60, 40, 36), outline=None)
    else:
        pen.arc(cx + 4 * k, cy + r * 0.24, r * 0.08, r * 0.1, 300, 120, shade(skin, 0.7), 5 * k)

    # moustache and beards
    beard = spec.get("beard", "none")
    bcol = HAIR["white"] if beard == "long_white" else HAIR["grey"] if beard == "long_grey" else shade(hair, 1.0)
    if beard.startswith("long"):
        pen.poly([(cx - r * 0.82, cy + r * 0.32), (cx - r * 0.55, cy + r * 1.75), (cx, cy + r * 2.25),
                  (cx + r * 0.55, cy + r * 1.75), (cx + r * 0.82, cy + r * 0.32), (cx, cy + r * 0.78)], bcol)
    elif beard == "short":
        pen.chord(cx, cy + r * 0.55, r * 0.8, r * 0.6, 0, 180, bcol)

    # mouth
    my = cy + r * 0.56
    dark, tongue = (90, 20, 30), (226, 100, 110)
    if mouth == 0:
        if emotion == "happy":
            pen.chord(cx, my - r * 0.08, r * 0.3, r * 0.22, 0, 180, dark)
            pen.chord(cx, my - r * 0.08, r * 0.3, r * 0.1, 0, 180, (255, 255, 255), outline=None)
        elif emotion in ("sad", "fear"):
            pen.arc(cx, my + r * 0.12, r * 0.2, r * 0.12, 200, 340, OUTLINE, 6 * k)
        elif emotion == "surprised":
            pen.ellipse(cx, my, r * 0.1, r * 0.12, dark)
        elif emotion == "angry":
            pen.line([(cx - r * 0.2, my), (cx + r * 0.2, my - 3 * k)], OUTLINE, 6 * k)
        else:
            pen.arc(cx, my - r * 0.08, r * 0.2, r * 0.12, 20, 160, OUTLINE, 6 * k)
    else:
        open_h = r * (0.12 if mouth == 1 else 0.22) * (1.2 if emotion in ("surprised", "angry") else 1)
        open_w = r * (0.2 if mouth == 1 else 0.24) * (1.25 if emotion == "happy" else 1)
        pen.ellipse(cx, my, open_w, open_h, dark)
        if mouth == 2:
            pen.chord(cx, my + open_h * 0.4, open_w * 0.65, open_h * 0.55, 180, 360, tongue, outline=None)
    if "fangs" in extras or kind == "demon":
        for sx in (-1, 1):
            pen.poly([(cx + sx * r * 0.2, my - 2 * k), (cx + sx * r * 0.14, my + r * 0.16), (cx + sx * r * 0.08, my - 2 * k)],
                     (255, 255, 250), width=3 * k)
    if beard == "moustache" or (beard.startswith("long") or beard == "short"):
        for sx in (-1, 1):
            pen.poly([(cx, my - r * 0.18), (cx + sx * r * 0.36, my - r * 0.08), (cx + sx * r * 0.42, my + r * 0.04),
                      (cx + sx * r * 0.2, my - r * 0.08)], bcol, width=3 * k)

    # cheeks
    if female or spec.get("age") == "child" or emotion == "happy":
        for sx in (-1, 1):
            pen.ellipse(cx + sx * r * 0.62, cy + r * 0.38, r * 0.14, r * 0.08, (246, 150, 150, 150), outline=None)
    # marks on the forehead
    if "tilak" in extras:
        pen.line([(cx, cy - r * 0.5), (cx, cy - r * 0.22)], (232, 60, 40), 8 * k)
        pen.arc(cx, cy - r * 0.42, r * 0.12, r * 0.14, 20, 160, (250, 250, 250), 5 * k)
    if "bindi" in extras or female:
        pen.ellipse(cx, cy - r * 0.32, r * 0.06, r * 0.06, (210, 30, 50), outline=None)

    # headwear
    if head == "crown":
        top = cy - r * 0.9
        pen.poly([(cx - r * 0.72, top + r * 0.2), (cx - r * 0.62, top - r * 0.62), (cx - r * 0.3, top - r * 0.38),
                  (cx, top - r * 1.05), (cx + r * 0.3, top - r * 0.38), (cx + r * 0.62, top - r * 0.62),
                  (cx + r * 0.72, top + r * 0.2)], GOLD)
        pen.poly([(cx - r * 0.76, top + r * 0.04), (cx + r * 0.76, top + r * 0.04), (cx + r * 0.72, top + r * 0.28),
                  (cx - r * 0.72, top + r * 0.28)], GOLD_DARK)
        pen.ellipse(cx, top - r * 0.36, r * 0.13, r * 0.16, GEM_RED)
        for sx in (-1, 1):
            pen.ellipse(cx + sx * r * 0.45, top + r * 0.15, r * 0.07, r * 0.07, GEM_GREEN, width=2)
    elif head == "tiara":
        pen.arc(cx, cy - r * 0.36, r * 0.8, r * 0.5, 200, 340, GOLD, 9 * k)
        pen.line([(cx, cy - r * 0.88), (cx, cy - r * 0.6)], GOLD, 6 * k)
        pen.ellipse(cx, cy - r * 0.55, r * 0.07, r * 0.09, GEM_RED, width=2)
    elif head == "turban":
        tc = main_colours(spec)[1]
        pen.ellipse(cx, cy - r * 0.62, r * 1.02, r * 0.56, tc)
        for j in range(3):
            pen.arc(cx, cy - r * (0.52 - j * 0.13), r * 0.95, r * 0.42, 200, 340, shade(tc, 0.75), 5 * k)
        pen.ellipse(cx, cy - r * 0.72, r * 0.1, r * 0.12, GEM_RED)
    elif head == "helmet":
        pen.chord(cx, cy - r * 0.12, r * 1.06, r * 1.0, 180, 360, COLORS["silver"])
        pen.poly([(cx - r * 0.08, cy - r * 1.1), (cx, cy - r * 1.5), (cx + r * 0.08, cy - r * 1.1)], COLORS["red"])
    elif head == "horns":
        for sx in (-1, 1):
            pen.poly([(cx + sx * r * 0.42, cy - r * 0.8), (cx + sx * r * 0.95, cy - r * 1.45),
                      (cx + sx * r * 0.7, cy - r * 0.68)], (232, 222, 196))


# ------------------------------------------------------------------ body
POSES = ("idle", "point", "raise", "namaste", "bless", "attack")


def arm_points(spec, pose, side, f):
    """Shoulder, elbow, hand for one arm. side +1 is the arm in front (the way the character faces)."""
    sx = CX + side * 100 * f["w"]
    sy = f["shoulder"] + 16
    up, fore = (108, 100) if f["child"] else (124, 112)

    def seg(x, y, angle, length):   # angle: 0 = straight down, positive = outward
        a = math.radians(angle)
        return x + side * math.sin(a) * length, y + math.cos(a) * length

    if pose == "raise":
        e = seg(sx, sy, 155, up)
        return (sx, sy), e, seg(*e, 168, fore)
    if pose == "namaste":
        e = seg(sx, sy, 30, up)
        return (sx, sy), e, (CX + side * 12, f["shoulder"] + 82)
    if side == 1 and pose == "point":
        e = seg(sx, sy, 80, up)
        return (sx, sy), e, seg(*e, 86, fore)
    if side == 1 and pose == "attack":
        e = seg(sx, sy, 96, up)
        return (sx, sy), e, seg(*e, 92, fore)
    if side == 1 and pose == "bless":
        e = seg(sx, sy, 34, up * 0.9)
        return (sx, sy), e, seg(*e, 172, fore * 0.85)
    e = seg(sx, sy, 12, up)
    return (sx, sy), e, seg(*e, 6, fore)


def draw_body(spec, pose="idle", walk=0):
    """Everything but the head, for one pose and walk frame (0 standing, 1-4 steps)."""
    w = canvas_width(spec)
    pen = Pen(w, BASE_H)
    shift = (w - BASE_W) // 2
    f = frame(spec)
    if shift:   # keep the body centred in a wide (ten-headed) canvas
        global CX
        old = CX
        CX = old + shift
    try:
        _body(pen, spec, pose, walk, f)
    finally:
        if shift:
            CX = old
    return pen.done(w, BASE_H)


def _body(pen, spec, pose, walk, f):
    kind = spec.get("kind", "human")
    outfit = spec.get("outfit", "common")
    skin = skin_of(spec)
    a, b = main_colours(spec)
    extras = set(spec.get("extras") or [])
    hair = hair_colour(spec)
    female = spec.get("gender") == "female"
    sh, hip, foot, wf = f["shoulder"], f["hip"], f["foot"], f["w"]
    swing = [0, 1, 0, -1][walk % 4] if walk else 0

    if kind == "bird":
        return _bird(pen, spec, pose, walk, f)

    # behind the body: long hair, tail
    if female or spec.get("hair") in ("long", "braid"):
        pen.poly([(CX - 112, sh - 40), (CX + 112, sh - 40), (CX + 96, sh + 150), (CX - 96, sh + 150)], hair, width=3)
    if "tail" in extras or kind == "monkey":
        tail = [(CX - 60, hip - 10), (CX - 170, hip + 40), (CX - 230, hip - 60), (CX - 200, hip - 170), (CX - 150, hip - 190)]
        pen.thick(tail, skin, 26)

    # legs
    long_garment = outfit in ("queen", "princess", "common_woman", "sage") or female
    knee = hip + (foot - hip) * 0.5
    for side in (-1, 1):
        lx = CX + side * 40 * wf
        dx = swing * side * 26
        foot_x = lx + dx
        leg_col = skin if outfit not in ("demon", "warrior") else shade(b, 0.8)
        if not long_garment:
            pen.thick([(lx, hip), (lx + dx * 0.5, knee), (foot_x, foot - 18)], leg_col, 44 if not f["child"] else 38)
        pen.ellipse(foot_x + 14, foot - 8, 34, 16, (110, 66, 40) if kind == "human" else shade(skin, 0.8))

    # lower garment
    if long_garment:
        sway = swing * 10
        pen.poly([(CX - 92 * wf, hip - 30), (CX + 92 * wf, hip - 30), (CX + 128 * wf + sway, foot - 14),
                  (CX - 128 * wf + sway, foot - 14)], a)
        pen.poly([(CX - 124 * wf + sway, foot - 44), (CX + 124 * wf + sway, foot - 44), (CX + 128 * wf + sway, foot - 14),
                  (CX - 128 * wf + sway, foot - 14)], GOLD if outfit in ("queen", "princess") else b, width=3)
        for j in (-1, 0, 1):
            pen.line([(CX + j * 30, hip), (CX + j * 44 + sway, foot - 50)], shade(a, 0.82), 4)
    elif kind in ("monkey", "bear"):
        pen.poly([(CX - 88 * wf, hip - 24), (CX + 88 * wf, hip - 24), (CX + 80 * wf, hip + 70), (CX - 80 * wf, hip + 70)], a)
    else:   # dhoti to the calf, or a warrior's skirt
        hem = knee + 70 if outfit != "warrior" else knee - 10
        pen.poly([(CX - 90 * wf, hip - 26), (CX + 90 * wf, hip - 26), (CX + 98 * wf + swing * 8, hem),
                  (CX - 98 * wf + swing * 8, hem)], a)
        pen.line([(CX, hip - 10), (CX + swing * 8, hem - 6)], shade(a, 0.78), 5)
        pen.line([(CX - 98 * wf + swing * 8, hem - 6), (CX + 98 * wf + swing * 8, hem - 6)], b, 9)

    # torso
    tw = 112 * wf
    top_col = skin
    if outfit in ("common", "warrior", "demon", "queen", "princess", "common_woman", "sage") or female:
        top_col = b if outfit in ("queen", "princess", "common_woman") or female else a if outfit in ("common", "sage") else b
    if kind in ("monkey", "bear"):
        top_col = skin
    pen.poly([(CX - tw, sh), (CX + tw, sh), (CX + tw * 0.78, hip - 10), (CX - tw * 0.78, hip - 10)], top_col)
    for side in (-1, 1):   # round shoulders
        pen.ellipse(CX + side * (tw - 18), sh + 22, 40, 34, top_col, outline=None)
    if kind in ("monkey", "bear"):
        pen.ellipse(CX, sh + (hip - sh) * 0.58, tw * 0.55, (hip - sh) * 0.4, lighter(skin, 0.45), outline=None)
    if outfit == "warrior":
        for j in range(3):
            y = sh + 40 + j * 52
            pen.line([(CX - tw * 0.8, y), (CX + tw * 0.8, y)], shade(b, 0.7), 6)
        for side in (-1, 1):
            pen.ellipse(CX + side * tw * 0.95, sh + 10, 42, 30, COLORS["silver"])
    if outfit == "demon":
        for side in (-1, 1):
            pen.poly([(CX + side * tw * 0.7, sh - 10), (CX + side * tw * 1.3, sh - 30), (CX + side * tw * 1.05, sh + 40)],
                     (70, 60, 70))
    # sash / pallu across the chest
    if outfit in ("royal", "forest", "sage") or female:
        sash = GOLD if outfit == "royal" and not female else b if not female else a
        pen.poly([(CX - tw * 0.95, sh + 2), (CX - tw * 0.55, sh - 2), (CX + tw * 0.72, hip - 20), (CX + tw * 0.32, hip - 12)],
                 shade(sash, 1.0) if outfit != "forest" else COLORS["ochre"])
    # jewellery
    if outfit in ("royal", "queen", "princess") or "aura" in extras:
        pen.arc(CX, sh - 4, 70, 70, 20, 160, GOLD, 10)
        pen.ellipse(CX, sh + 64, 13, 16, GEM_RED, width=3)
    if "mala" in extras or outfit == "sage":
        for j in range(13):
            t = math.pi * (0.12 + 0.76 * j / 12)
            pen.ellipse(CX + math.cos(t) * 74, sh - 4 + math.sin(t) * 94, 7, 7, (110, 54, 34), width=2)
    # belt
    pen.poly([(CX - tw * 0.8, hip - 34), (CX + tw * 0.8, hip - 34), (CX + tw * 0.8, hip - 10), (CX - tw * 0.8, hip - 10)],
             GOLD if outfit in ("royal", "queen", "princess", "warrior") else shade(a, 0.7), width=3)

    # neck
    neck_w = 30
    pen.poly([(CX - neck_w, sh - 40), (CX + neck_w, sh - 40), (CX + neck_w, sh + 6), (CX - neck_w, sh + 6)], skin, outline=None)

    # arms, props
    prop = spec.get("prop", "none")
    arm_col = skin
    sleeve = outfit in ("common", "common_woman") or (female and outfit != "princess")
    for side in (-1, 1):
        s0, e, hnd = arm_points(spec, pose, side, f)
        pen.thick([s0, e], b if sleeve else arm_col, 44 if not f["child"] else 36)
        pen.thick([e, hnd], arm_col, 38 if not f["child"] else 32)
        if outfit in ("royal", "queen", "princess", "warrior") or "aura" in extras:
            mx, my = (s0[0] + e[0]) / 2, (s0[1] + e[1]) / 2
            pen.ellipse(mx, my, 20, 10, GOLD, width=2)
        pen.ellipse(hnd[0], hnd[1], 21, 21, arm_col)
        if side == 1 and prop != "none" and pose != "namaste":
            _prop(pen, prop, hnd, pose)


def _prop(pen, prop, hand, pose):
    x, y = hand
    if prop == "bow":
        pen.arc(x + 6, y, 46, 150, 270, 90, (120, 70, 36), 11)
        pen.line([(x + 6, y - 150), (x + 6, y + 150)], (236, 230, 210), 2.5, rounded=False)
    elif prop == "mace":
        up = pose in ("raise", "attack")
        end = (x + (70 if pose == "attack" else 0), y - (170 if up or pose == "idle" else 120))
        pen.thick([(x, y + 30), end], (150, 96, 40), 16)
        pen.ellipse(end[0], end[1], 52, 56, GOLD)
        pen.ellipse(end[0] - 14, end[1] - 16, 12, 12, (255, 236, 150), outline=None)
    elif prop in ("staff", "trident"):
        pen.thick([(x, y + 150), (x, y - 210)], (130, 84, 44) if prop == "staff" else COLORS["silver"], 12)
        if prop == "trident":
            for dx in (-34, 0, 34):
                pen.poly([(x + dx - 9, y - 205), (x + dx, y - 270 - (18 if dx == 0 else 0)), (x + dx + 9, y - 205)],
                         COLORS["silver"])
            pen.line([(x - 36, y - 205), (x + 36, y - 205)], COLORS["silver"], 10)
    elif prop == "sword":
        if pose in ("attack", "point"):   # pointing forward, clear of the face
            pen.poly([(x + 12, y - 9), (x + 230, y - 6), (x + 262, y), (x + 230, y + 6), (x + 12, y + 9)], COLORS["silver"])
            pen.line([(x + 12, y - 34), (x + 12, y + 34)], GOLD, 12)
        else:
            pen.poly([(x - 9, y - 12), (x - 6, y - 230), (x, y - 262), (x + 6, y - 230), (x + 9, y - 12)], COLORS["silver"])
            pen.line([(x - 34, y - 12), (x + 34, y - 12)], GOLD, 12)
    elif prop == "lotus":
        for j in range(5):
            t = math.radians(-90 + (j - 2) * 30)
            pen.ellipse(x + math.cos(t) * 22, y - 30 + math.sin(t) * 22, 14, 24, (244, 140, 180))
        pen.ellipse(x, y - 30, 12, 12, GOLD)
    elif prop == "kamandal":
        pen.ellipse(x, y + 40, 34, 30, (150, 100, 50))
        pen.line([(x + 24, y + 26), (x + 48, y + 4)], (150, 100, 50), 9)
    elif prop == "conch":
        pen.ellipse(x + 8, y - 26, 26, 38, (250, 246, 236))
        pen.arc(x + 8, y - 26, 16, 26, 200, 420, (200, 180, 160), 4)
    elif prop == "flute":
        pen.line([(x - 70, y - 30), (x + 90, y + 10)], (160, 110, 50), 11)


def _bird(pen, spec, pose, walk, f):
    """A great bird (Jatayu, Garuda): no arms, wings instead."""
    a, b = main_colours(spec)
    body = colour(spec.get("skin", "monkey_brown"), SKIN, (140, 96, 60))
    sh, hip, foot = f["shoulder"], f["hip"], f["foot"]
    up = pose in ("raise", "attack")
    for side in (-1, 1):   # wings
        tip = (CX + side * 270, sh - (150 if up else -40))
        pen.poly([(CX + side * 70, sh + 10), tip, (CX + side * 230, sh + (40 if up else 170)), (CX + side * 90, hip - 30)],
                 shade(body, 0.85))
        for j in range(4):
            pen.line([(CX + side * 90, sh + 30 + j * 30), (tip[0] - side * 40 * j, tip[1] + 40 + j * 36)], shade(body, 0.65), 4)
    for side in (-1, 1):   # legs
        pen.line([(CX + side * 34, hip + 40), (CX + side * 40, foot - 12)], (232, 178, 60), 12)
        pen.line([(CX + side * 40, foot - 12), (CX + side * 40 + 34, foot - 6)], (232, 178, 60), 9)
    pen.ellipse(CX, (sh + hip) / 2 + 20, 108, 150, body)
    pen.ellipse(CX, (sh + hip) / 2 + 50, 66, 100, lighter(body, 0.5), outline=None)
    if spec.get("headwear") == "crown" or "aura" in (spec.get("extras") or []):
        pen.arc(CX, sh - 4, 64, 60, 20, 160, GOLD, 10)


def bird_head(spec, emotion="calm", mouth=0, blink=False):
    w = canvas_width(spec)
    cx = w // 2
    pen = Pen(w, HEAD_H)
    f = frame(spec)
    body = colour(spec.get("skin", "monkey_brown"), SKIN, (140, 96, 60))
    cy, r = f["head_cy"] + 40, f["head_r"] * 0.8
    pen.ellipse(cx, cy, r, r, lighter(body, 0.6) if spec.get("age") != "old" else (236, 232, 224))
    beak_open = 0 if mouth == 0 else 16 if mouth == 1 else 30
    pen.poly([(cx + r * 0.55, cy - 4), (cx + r * 1.5, cy + 22), (cx + r * 0.55, cy + 30)], (240, 180, 40))
    if beak_open:
        pen.poly([(cx + r * 0.55, cy + 30), (cx + r * 1.3, cy + 30 + beak_open), (cx + r * 0.55, cy + 42)], (214, 150, 30))
    if blink:
        pen.arc(cx + r * 0.25, cy - r * 0.18, r * 0.18, r * 0.1, 20, 160, OUTLINE, 6)
    else:
        pen.ellipse(cx + r * 0.25, cy - r * 0.18, r * 0.2, r * 0.22, (255, 255, 255))
        pen.ellipse(cx + r * 0.32, cy - r * 0.16, r * 0.1, r * 0.11, (20, 14, 14), outline=None)
    tilt = {"angry": 12, "sad": -10}.get(emotion, 0)
    pen.line([(cx + r * 0.05, cy - r * 0.48 + tilt), (cx + r * 0.48, cy - r * 0.5 - tilt * 0.3)], (60, 40, 30), 9)
    if spec.get("headwear") == "crown":
        top = cy - r * 0.95
        pen.poly([(cx - r * 0.5, top + r * 0.2), (cx - r * 0.4, top - r * 0.4), (cx, top - r * 0.75),
                  (cx + r * 0.4, top - r * 0.4), (cx + r * 0.5, top + r * 0.2)], GOLD)
    return pen.done(w, HEAD_H)


# ------------------------------------------------------------------ cached parts
class Character:
    """One cast member, with its drawn parts cached."""

    def __init__(self, spec):
        self.spec = spec
        self.id = spec["id"]
        self.width = canvas_width(spec)
        self.height = float(spec.get("height", 1.0)) * (0.78 if spec.get("age") == "child" else 1.0)
        self._head = lru_cache(maxsize=48)(self._make_head)
        self._body = lru_cache(maxsize=40)(self._make_body)

    def _make_head(self, emotion, mouth, blink, facing):
        draw = bird_head if self.spec.get("kind") == "bird" else draw_head
        img = draw(self.spec, emotion, mouth, blink)
        return img.transpose(Image.FLIP_LEFT_RIGHT) if facing < 0 else img

    def _make_body(self, pose, walk, facing):
        img = draw_body(self.spec, pose, walk)
        return img.transpose(Image.FLIP_LEFT_RIGHT) if facing < 0 else img

    def image(self, emotion="calm", mouth=0, blink=False, pose="idle", walk=0, facing=1):
        """The whole character for these states: canvas units, feet at the bottom."""
        body = self._body(pose if pose in POSES else "idle", int(walk) % 5, 1 if facing >= 0 else -1).copy()
        body.alpha_composite(self._head(emotion, int(mouth), bool(blink), 1 if facing >= 0 else -1))
        return body
