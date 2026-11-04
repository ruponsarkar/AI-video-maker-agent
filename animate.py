"""
Snack Code - Step 7: build a graphical animated explainer video  (v3)

Reads:
    scripts/script.json         title + scenes (on_screen, narration, beats or visual)
    audio/scene_XX.wav          one voice file per scene (voice.py or your own recording)
    images/scene_XX.png/.jpg    OPTIONAL picture/screenshot for a scene's first beat
    music.mp3                   OPTIONAL background music (YouTube Audio Library)

Writes:
    output/animated.mp4         1920x1080, 30 fps, ready to upload
    output/animated.srt         subtitles for YouTube Studio > Subtitles

What makes it watchable:
    - every scene is split into beats, so the picture changes every ~4-6 seconds
    - "Byte", the Snack Code robot host, talks (mouth synced to the voice),
      blinks, waves and reacts (happy / shock / think / warn / explain)
    - sound effects (whoosh, pop, ding, ring, alarm, typing) generated in code
    - virtual camera: slow push-in, punch-in zooms, shake on warnings
    - keyword stickers that pop when a key word is spoken ("pop" in a beat)

Beat visuals:
    title, icon, kinetic, host, phone_call, phone_sms, chat, steps, compare,
    stat, warning, flow   (+ image when you add images/scene_XX.png)
Scenes without beats are split into beats automatically.

Usage:
    python animate.py                  # full video
    python animate.py --preview        # first 3 scenes only, quick check
    python animate.py --theme violet   # emerald, violet, ocean, sunset, crimson
    python animate.py --no-mascot      # without Byte
    python animate.py --no-sfx         # without sound effects
"""
import glob
import hashlib
import json
import math
import os
import random
import re
import subprocess
import sys
import time

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

# ======================================================================= settings
W, H, FPS = 1920, 1080, 30
GAP = 0.35            # pause after each scene (seconds)
OUTRO = 3.0           # subscribe card at the end
MUSIC_VOLUME = 0.08
WORDS_PER_CAPTION = 6
WIPE = 0.45           # scene transition length

WHITE = (245, 247, 250)
MUTED = (148, 163, 184)
DARK = (10, 14, 24)
RED = (239, 68, 68)
GREEN = (34, 197, 94)
YELLOW = (250, 204, 21)
BRAND = (34, 197, 94)

THEMES = {
    "emerald": {"top": (13, 20, 36), "bot": (4, 6, 12), "accent": (34, 197, 94), "accent2": (59, 130, 246)},
    "violet":  {"top": (26, 16, 46), "bot": (8, 5, 16), "accent": (168, 85, 247), "accent2": (236, 72, 153)},
    "ocean":   {"top": (7, 30, 50), "bot": (3, 10, 18), "accent": (56, 189, 248), "accent2": (45, 212, 191)},
    "sunset":  {"top": (40, 18, 20), "bot": (12, 5, 8), "accent": (249, 115, 22), "accent2": (250, 204, 21)},
    "crimson": {"top": (36, 12, 18), "bot": (10, 4, 7), "accent": (244, 63, 94), "accent2": (250, 204, 21)},
}
BG_STYLES = ["grid", "dots", "diagonal", "circuit"]
VISUAL_TYPES = {"title", "icon", "phone_call", "phone_sms", "chat", "steps",
                "compare", "stat", "warning", "flow", "host", "kinetic", "chapter"}
ICONS = ["phone", "shield", "lock", "bank", "money", "warning", "user", "hacker", "globe",
         "laptop", "wifi", "chip", "ram", "bug", "ai", "key", "sim", "mail", "check", "cross"]

PREVIEW = "--preview" in sys.argv
OUT = "output/preview.mp4" if PREVIEW else "output/animated.mp4"


# ======================================================================= fonts
def pick_font(candidates):
    for path in candidates:
        if os.path.exists(path):
            return path
    raise SystemExit("No font found. Run: sudo apt install fonts-dejavu-core fonts-noto-core")


BOLD = pick_font(sorted(glob.glob("fonts/*.ttf")) + [
    "/usr/share/fonts/truetype/ubuntu/Ubuntu-B.ttf",
    "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
])
REGULAR = pick_font([
    "/usr/share/fonts/truetype/ubuntu/Ubuntu-M.ttf",
    "/usr/share/fonts/truetype/noto/NotoSans-Medium.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
])
SYMBOL = pick_font([  # has the rupee sign
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
    BOLD,
])
MONO = pick_font([
    "/usr/share/fonts/truetype/ubuntu/UbuntuMono-B.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
])
_fonts = {}


def font(size, path=BOLD):
    key = (path, int(size))
    if key not in _fonts:
        _fonts[key] = ImageFont.truetype(path, int(size))
    return _fonts[key]


# ======================================================================= small helpers
def clamp01(x):
    return max(0.0, min(1.0, x))


def ease(x):
    x = clamp01(x)
    return 1 - (1 - x) ** 3


def ease_back(x):
    x = clamp01(x)
    c1 = 1.70158
    return 1 + (c1 + 1) * (x - 1) ** 3 + c1 * (x - 1) ** 2


def mix(c1, c2, f):
    return tuple(int(a + (b - a) * f) for a, b in zip(c1, c2))


def dim(c, f=0.25, base=DARK):
    return mix(base, c, f)


def duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "default=nw=1:nk=1", path],
                         capture_output=True, text=True, check=True).stdout
    return float(out.strip())


def wrap(text, fnt, max_width, max_lines=None):
    lines, line = [], ""
    for word in str(text).split():
        test = f"{line} {word}".strip()
        if fnt.getlength(test) <= max_width or not line:
            line = test
        else:
            lines.append(line)
            line = word
    if line:
        lines.append(line)
    if max_lines and len(lines) > max_lines:
        lines = lines[:max_lines]
        while lines[-1] and fnt.getlength(lines[-1] + "...") > max_width:
            lines[-1] = lines[-1][:-1]
        lines[-1] = lines[-1].rstrip() + "..."
    return lines


def fit(text, fnt, max_width):
    return wrap(text, fnt, max_width, max_lines=1)[0] if str(text).strip() else ""


def comp(dst, src, x, y):
    """alpha_composite that clips to the destination (works partly off-image)."""
    x, y = int(round(x)), int(round(y))
    sx0, sy0 = max(0, -x), max(0, -y)
    sx1, sy1 = min(src.width, dst.width - x), min(src.height, dst.height - y)
    if sx1 > sx0 and sy1 > sy0:
        dst.alpha_composite(src, dest=(x + sx0, y + sy0), source=(sx0, sy0, sx1, sy1))


def comp_c(dst, src, cx, cy):
    comp(dst, src, cx - src.width / 2, cy - src.height / 2)


def faded(img, f):
    if f >= 0.999:
        return img
    out = img.copy()
    out.putalpha(img.getchannel("A").point(lambda v: int(v * max(0.0, f))))
    return out


def scaled(img, f):
    if abs(f - 1) < 0.01:
        return img
    return img.resize((max(1, int(img.width * f)), max(1, int(img.height * f))), Image.BILINEAR)


_text_cache = {}


def text_sprite(text, size, color, path=BOLD, shadow=True):
    key = (text, size, color, path, shadow)
    if key in _text_cache:
        return _text_cache[key]
    fnt = font(size, path)
    left, top, right, bottom = fnt.getbbox(text or " ")
    pad = 14
    img = Image.new("RGBA", (right - left + pad * 2, bottom - top + pad * 2), (0, 0, 0, 0))
    if shadow:
        sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
        ImageDraw.Draw(sh).text((pad - left + 3, pad - top + 5), text, font=fnt, fill=(0, 0, 0, 170))
        img = Image.alpha_composite(img, sh.filter(ImageFilter.GaussianBlur(6)))
    ImageDraw.Draw(img).text((pad - left, pad - top), text, font=fnt, fill=color + (255,))
    _text_cache[key] = img
    return img


def text_block(lines, size, color, line_gap=1.25, path=BOLD, shadow=True, align="center"):
    """Several lines of text as one transparent image."""
    sprites = [text_sprite(l, size, color, path, shadow) for l in lines] or [text_sprite(" ", size, color)]
    lh = int(size * line_gap)
    w = max(s.width for s in sprites)
    img = Image.new("RGBA", (w, lh * (len(sprites) - 1) + sprites[-1].height), (0, 0, 0, 0))
    for j, s in enumerate(sprites):
        x = (w - s.width) // 2 if align == "center" else 0
        img.alpha_composite(s, dest=(x, j * lh))
    return img


def make_glow(color, size, strength):
    yy, xx = np.ogrid[-1:1:size * 1j, -1:1:size * 1j]
    alpha = np.clip(1 - np.sqrt(xx * xx + yy * yy), 0, 1) ** 2 * strength
    arr = np.zeros((size, size, 4), np.uint8)
    arr[..., :3] = color
    arr[..., 3] = alpha.astype(np.uint8)
    return Image.fromarray(arr, "RGBA")


def arrow(d, x0, y0, x1, y1, color, width=8, head=26):
    d.line([(x0, y0), (x1, y1)], fill=color, width=width)
    ang = math.atan2(y1 - y0, x1 - x0)
    pts = [(x1 + head * 0.4 * math.cos(ang), y1 + head * 0.4 * math.sin(ang)),
           (x1 - head * math.cos(ang - 0.5), y1 - head * math.sin(ang - 0.5)),
           (x1 - head * math.cos(ang + 0.5), y1 - head * math.sin(ang + 0.5))]
    d.polygon(pts, fill=color)


# ======================================================================= icons
_icon_cache = {}


def icon_sprite(name, size, color):
    """Vector icons drawn at 2x and scaled down for smooth edges."""
    name = name if name in ICONS else "shield"
    key = (name, size, color)
    if key in _icon_cache:
        return _icon_cache[key]
    S = size * 2
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    u = S / 100
    c = color + (255,)
    k = DARK + (255,)
    lw = max(2, int(7 * u))

    def B(x0, y0, x1, y1):
        return [x0 * u, y0 * u, x1 * u, y1 * u]

    def P(*pts):
        return [(x * u, y * u) for x, y in pts]

    def label(txt, cy=50, sz=46, fill=k, path=SYMBOL):
        d.text((50 * u, cy * u), txt, font=font(sz * u, path), fill=fill, anchor="mm")

    if name == "phone":
        d.rounded_rectangle(B(28, 5, 72, 95), radius=10 * u, outline=c, width=lw)
        d.line(P((43, 15), (57, 15)), fill=c, width=lw)
        d.ellipse(B(45, 80, 55, 90), fill=c)
    elif name == "shield":
        d.polygon(P((50, 5), (88, 19), (84, 58), (50, 95), (16, 58), (12, 19)), fill=c)
        d.line(P((32, 50), (45, 64), (70, 36)), fill=k, width=lw, joint="curve")
    elif name == "lock":
        d.arc(B(30, 6, 70, 60), 180, 360, fill=c, width=lw + 2)
        d.line(P((30, 33), (30, 45)), fill=c, width=lw + 2)
        d.line(P((70, 33), (70, 45)), fill=c, width=lw + 2)
        d.rounded_rectangle(B(18, 42, 82, 94), radius=10 * u, fill=c)
        d.ellipse(B(44, 56, 56, 68), fill=k)
        d.rectangle(B(47, 64, 53, 80), fill=k)
    elif name == "bank":
        d.polygon(P((8, 34), (50, 6), (92, 34)), fill=c)
        for x in (18, 36, 54, 72):
            d.rectangle(B(x, 40, x + 10, 80), fill=c)
        d.rectangle(B(8, 84, 92, 94), fill=c)
    elif name == "money":
        d.ellipse(B(6, 6, 94, 94), fill=c)
        label("₹", 52, 58)
    elif name == "warning":
        d.polygon(P((50, 6), (96, 90), (4, 90)), fill=c)
        label("!", 58, 58)
    elif name in ("user", "hacker"):
        d.ellipse(B(32, 6, 68, 42), fill=c)
        d.pieslice(B(14, 48, 86, 120), 180, 360, fill=c)
        if name == "hacker":
            d.rectangle(B(30, 18, 70, 28), fill=k)
            d.ellipse(B(38, 19, 46, 27), fill=c)
            d.ellipse(B(54, 19, 62, 27), fill=c)
    elif name == "globe":
        d.ellipse(B(6, 6, 94, 94), outline=c, width=lw)
        d.ellipse(B(30, 6, 70, 94), outline=c, width=lw)
        d.line(P((6, 50), (94, 50)), fill=c, width=lw)
        d.line(P((14, 28), (86, 28)), fill=c, width=lw - 1)
        d.line(P((14, 72), (86, 72)), fill=c, width=lw - 1)
    elif name == "laptop":
        d.rounded_rectangle(B(16, 14, 84, 66), radius=6 * u, outline=c, width=lw)
        d.polygon(P((4, 74), (96, 74), (88, 88), (12, 88)), fill=c)
    elif name == "wifi":
        for r in (44, 30, 16):
            d.arc(B(50 - r, 78 - r, 50 + r, 78 + r), 220, 320, fill=c, width=lw + 1)
        d.ellipse(B(44, 72, 56, 84), fill=c)
    elif name == "chip":
        d.rounded_rectangle(B(24, 24, 76, 76), radius=6 * u, outline=c, width=lw)
        d.rectangle(B(38, 38, 62, 62), fill=c)
        for p in (34, 50, 66):
            d.line(P((p, 6), (p, 24)), fill=c, width=lw - 1)
            d.line(P((p, 76), (p, 94)), fill=c, width=lw - 1)
            d.line(P((6, p), (24, p)), fill=c, width=lw - 1)
            d.line(P((76, p), (94, p)), fill=c, width=lw - 1)
    elif name == "ram":
        d.rounded_rectangle(B(4, 28, 96, 66), radius=4 * u, fill=c)
        for x in (12, 32, 52, 72):
            d.rectangle(B(x, 36, x + 14, 56), fill=k)
        for x in range(8, 94, 7):
            d.rectangle(B(x, 66, x + 3, 76), fill=c)
    elif name == "bug":
        for y in (40, 56, 72):
            d.line(P((14, y - 6), (86, y + 6)), fill=c, width=lw - 2)
            d.line(P((86, y - 6), (14, y + 6)), fill=c, width=lw - 2)
        d.ellipse(B(28, 30, 72, 92), fill=c)
        d.ellipse(B(36, 10, 64, 36), fill=c)
        d.line(P((50, 36), (50, 90)), fill=k, width=lw - 3)
    elif name == "ai":
        d.rounded_rectangle(B(14, 14, 86, 86), radius=14 * u, fill=c)
        label("AI", 51, 40, path=BOLD)
    elif name == "key":
        d.ellipse(B(6, 30, 46, 70), outline=c, width=lw + 2)
        d.line(P((44, 50), (94, 50)), fill=c, width=lw + 2)
        d.line(P((80, 50), (80, 66)), fill=c, width=lw + 2)
        d.line(P((66, 50), (66, 62)), fill=c, width=lw + 2)
    elif name == "sim":
        d.polygon(P((22, 4), (64, 4), (80, 20), (80, 96), (22, 96)), fill=c)
        d.rounded_rectangle(B(34, 44, 68, 80), radius=4 * u, fill=k)
    elif name == "mail":
        d.rounded_rectangle(B(6, 20, 94, 80), radius=8 * u, fill=c)
        d.line(P((10, 26), (50, 56), (90, 26)), fill=k, width=lw)
    elif name == "check":
        d.ellipse(B(4, 4, 96, 96), fill=c)
        d.line(P((28, 52), (44, 68), (74, 36)), fill=k, width=lw + 3, joint="curve")
    elif name == "cross":
        d.ellipse(B(4, 4, 96, 96), fill=c)
        d.line(P((32, 32), (68, 68)), fill=k, width=lw + 3)
        d.line(P((68, 32), (32, 68)), fill=k, width=lw + 3)

    img = img.resize((size, size), Image.LANCZOS)
    _icon_cache[key] = img
    return img


KEYWORD_ICONS = [
    (r"hack|hacker|malware|virus|apk", "hacker"), (r"scam|fraud|fake|dhokha|sawdhan|saavdhan|savdhan", "warning"),
    (r"upi|payment|paisa|paise|rupay|money|₹|price|daam|mehng", "money"), (r"bank|account|khata", "bank"),
    (r"otp|password|pin", "lock"), (r"call|phone|mobile|smartphone", "phone"),
    (r"sms|message|whatsapp|mail|link", "mail"), (r"\bai\b|chatgpt|gemini|artificial", "ai"),
    (r"ram|memory", "ram"), (r"chip|processor|cpu|gpu", "chip"), (r"laptop|computer|pc\b", "laptop"),
    (r"internet|wifi|wi-fi|network|5g", "wifi"), (r"sim\b", "sim"), (r"safe|surakshit|bacho|bachein|secure|safety", "shield"),
    (r"website|online|google", "globe"), (r"bug|error|code", "bug"),
]


def guess_icon(text):
    t = text.lower()
    for pattern, name in KEYWORD_ICONS:
        if re.search(pattern, t):
            return name
    return "shield"


# ======================================================================= load script + beats
SR = 48000
USE_MASCOT = "--no-mascot" not in sys.argv
USE_SFX = "--no-sfx" not in sys.argv
VISUAL_TYPES = VISUAL_TYPES | {"kinetic", "host"}

script = json.load(open("scripts/script.json", encoding="utf-8"))
os.makedirs("output", exist_ok=True)


def choose(options, salt):
    h = int(hashlib.md5((script.get("title", "") + salt).encode()).hexdigest(), 16)
    return options[h % len(options)]


theme_name = None
if "--theme" in sys.argv and sys.argv.index("--theme") + 1 < len(sys.argv):
    theme_name = sys.argv[sys.argv.index("--theme") + 1]
theme_name = theme_name or script.get("theme") or choose(list(THEMES), "theme")
if theme_name not in THEMES:
    raise SystemExit(f"Unknown theme {theme_name}. Pick one of: {', '.join(THEMES)}")
TH = THEMES[theme_name]
ACCENT, ACCENT2 = TH["accent"], TH["accent2"]
BG_STYLE = script.get("background") if script.get("background") in BG_STYLES else choose(BG_STYLES, "bg")

MOODS = {"happy", "shock", "think", "warn", "explain"}
DEFAULT_MOOD = {"title": "shock", "warning": "shock", "phone_sms": "warn", "phone_call": "think",
                "stat": "shock", "icon": "happy", "kinetic": "explain", "chat": "think", "image": "explain",
                "host": "explain", "steps": "happy", "compare": "think", "flow": "explain", "chapter": "think"}
CORNER_OK = {"title", "chapter", "icon", "kinetic", "stat", "warning", "phone_call", "phone_sms", "chat", "image"}


def split_sentences(text):
    return [p.strip() for p in re.split(r"(?<=[.?!।])\s+", str(text).strip()) if p.strip()]


def shorten(text, n):
    words = re.sub(r"[.?!।,]+$", "", str(text).strip()).split()
    return " ".join(words[:n]) + ("..." if len(words) > n else "")


_auto = [0]


def auto_visual(say):
    """Pick a visual for a beat the script did not describe."""
    num = re.search(r"(₹\s?\d[\d,]*|\d[\d,]*(?:\.\d+)?\s?%)", say)
    if num:
        return {"type": "stat", "value": num.group(1).replace(" ", ""), "label": shorten(say, 8)}
    kind = ["host", "icon", "kinetic"][_auto[0] % 3]
    _auto[0] += 1
    if kind == "host":
        return {"type": "host", "text": shorten(say, 12)}
    if kind == "icon":
        return {"type": "icon", "icon": guess_icon(say)}
    return {"type": "kinetic", "text": shorten(say, 8)}


def auto_beats(narration):
    chunks, cur = [], ""
    for snt in split_sentences(narration) or [narration]:
        cur = f"{cur} {snt}".strip()
        if len(cur) >= 55:
            chunks.append(cur)
            cur = ""
    if cur:
        if chunks and len(cur) < 30:
            chunks[-1] += " " + cur
        else:
            chunks.append(cur)
    while len(chunks) > 4:
        chunks[-2] += " " + chunks.pop()
    return chunks


scenes = []
for i, s in enumerate(script["scenes"]):
    wav = f"audio/scene_{i:02d}.wav"
    if not os.path.exists(wav):
        print(f"  scene {i:02d}: no {wav}, skipping (run voice.py first)")
        continue
    raw = [b for b in (s.get("beats") if isinstance(s.get("beats"), list) else [])
           if isinstance(b, dict) and str(b.get("say", "")).strip()]
    narration = str(s.get("narration", "")).strip() or " ".join(str(b["say"]).strip() for b in raw)
    heading = str(s.get("on_screen") or "").strip() or shorten(narration, 6)
    image = next((p for p in (f"images/scene_{i:02d}.png", f"images/scene_{i:02d}.jpg")
                  if os.path.exists(p)), None)
    if raw:
        beats = [{"say": str(b["say"]).strip(),
                  "visual": dict(b["visual"]) if isinstance(b.get("visual"), dict) else {},
                  "mood": b.get("mood"), "pop": b.get("pop")} for b in raw[:5]]
    else:
        sv = s.get("visual") if isinstance(s.get("visual"), dict) else {}
        beats = [{"say": c, "visual": dict(sv) if j == 0 else {}, "mood": None, "pop": None}
                 for j, c in enumerate(auto_beats(narration) if narration else [heading])]
    scenes.append({"idx": i, "wav": wav, "dur": duration(wav), "heading": heading,
                   "narration": narration, "image": image, "beats": beats})

if not scenes:
    raise SystemExit("No scenes with audio found.")
if PREVIEW:
    scenes = scenes[:3]

# ----- check every beat's visual, mood and sticker
for k, s in enumerate(scenes):
    for j, b in enumerate(s["beats"]):
        v = b["visual"]
        t = str(v.get("type", "")).lower()
        if j == 0 and s["image"]:
            t = "image"
        elif t == "title" and j != 0:
            v.clear()
            v.update({"type": "kinetic", "text": shorten(b["say"], 8)})
            t = "kinetic"
        elif t not in VISUAL_TYPES:
            if j == 0 and k == 0:
                t = "title"
            else:
                v.clear()
                v.update(auto_visual(b["say"]))
                t = v["type"]
        if t == "icon" and v.get("icon") not in ICONS:
            v["icon"] = guess_icon(b["say"] + " " + s["heading"])
        v["type"] = t
        b["mood"] = b["mood"] if b["mood"] in MOODS else DEFAULT_MOOD.get(t, "explain")
        pop = str(b.get("pop") or "").strip()
        b["pop"] = pop if pop and len(pop.split()) <= 2 and len(pop) <= 16 else None

# ----- timing: scenes follow their audio, beats share the scene by text length
cursor = 0.0
BEATS = []
for s in scenes:
    s["start"], s["end"] = cursor, cursor + s["dur"] + GAP
    cursor = s["end"]
    # exact beat timing from voice.py (one clip per beat), else share by text length
    timing = None
    tpath = s["wav"][:-4] + ".json"
    if os.path.exists(tpath):
        try:
            timing = json.load(open(tpath)).get("beats") or None
        except (ValueError, OSError):
            timing = None
    if timing and len(timing) != len(s["beats"]):
        timing = None
    s["exact"] = bool(timing)
    weights = [len(b["say"]) + 8 for b in s["beats"]]
    acc = 0.0
    for j, b in enumerate(s["beats"]):
        if timing:
            b["start"] = s["start"] + timing[j]["start"]
            b["dur"] = timing[j]["dur"]
        else:
            share = weights[j] / sum(weights)
            b["start"] = s["start"] + s["dur"] * acc
            b["dur"] = s["dur"] * share
            acc += share
    for j, b in enumerate(s["beats"]):
        b["end"] = s["end"] if j == len(s["beats"]) - 1 else s["beats"][j + 1]["start"]
        b.update({"scene": s, "k": j, "idx": len(BEATS), "heading": s["heading"],
                  "narration": b["say"], "image": s["image"]})
        b["corner"] = USE_MASCOT and b["visual"]["type"] in CORNER_OK
        BEATS.append(b)
SCENES_END = cursor
TOTAL = SCENES_END + OUTRO
print(f"{len(scenes)} scenes, {len(BEATS)} beats (a new visual every {SCENES_END / len(BEATS):.1f}s, "
      f"exact voice timing in {sum(sc['exact'] for sc in scenes)}/{len(scenes)} scenes), "
      f"{TOTAL / 60:.1f} min, theme '{theme_name}', background '{BG_STYLE}'")

# ----- voice track (needed now for lip-sync)
print("Reading voice ...")


def decode(args):
    out = subprocess.run(["ffmpeg", "-v", "error", *args, "-f", "f32le", "-ac", "1", "-ar", str(SR), "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(out, np.float32).copy()


N_SAMPLES = int(TOTAL * SR) + SR
args, filters = [], []
for k, s in enumerate(scenes):
    args += ["-i", s["wav"]]
    pad = GAP + (OUTRO if k == len(scenes) - 1 else 0)
    filters.append(f"[{k}:a]aresample={SR},aformat=sample_fmts=fltp:channel_layouts=mono,apad=pad_dur={pad}[a{k}]")
filters.append("".join(f"[a{k}]" for k in range(len(scenes))) + f"concat=n={len(scenes)}:v=0:a=1[voice]")
VOICE = decode([*args, "-filter_complex", ";".join(filters), "-map", "[voice]"])
VOICE = np.pad(VOICE, (0, max(0, N_SAMPLES - len(VOICE))))[:N_SAMPLES]

HOP = SR // FPS
_frames = len(VOICE) // HOP
_rms = np.sqrt((VOICE[:_frames * HOP].reshape(_frames, HOP) ** 2).mean(axis=1))
_ref = np.percentile(_rms[_rms > 1e-4], 92) if np.any(_rms > 1e-4) else 1.0
MOUTH = np.clip(_rms / (_ref + 1e-9), 0, 1)
for _i in range(1, len(MOUTH)):  # quick open, softer close
    MOUTH[_i] = max(MOUTH[_i], MOUTH[_i - 1] * 0.55)


def mouth_at(T):
    i = int(T * FPS)
    return float(MOUTH[i]) if 0 <= i < len(MOUTH) else 0.0


EVENTS = []


def sfx(b, t, kind, vol=1.0):
    """Schedule a sound effect t seconds after beat b starts."""
    EVENTS.append((b["start"] + t, kind, vol))


def reveal_times(s, n, start=0.6, share=0.75):
    span = max(0.5, s["dur"] * share - start)
    return [start + span * k / max(1, n) for k in range(n)]


def as_list(x, limit):
    if isinstance(x, str):
        x = [x]
    if not isinstance(x, list):
        return []
    return [str(i).strip() for i in x if str(i).strip()][:limit]


# ======================================================================= background
def make_background():
    g = np.linspace(0, 1, H)[:, None]
    col = np.array(TH["top"]) * (1 - g) + np.array(TH["bot"]) * g
    img = Image.fromarray(np.repeat(col[:, None, :], W, axis=1).astype(np.uint8), "RGB")
    d = ImageDraw.Draw(img, "RGBA")
    faint = (255, 255, 255, 9)
    if BG_STYLE == "grid":
        for x in range(0, W, 64):
            d.line([(x, 0), (x, H)], fill=faint)
        for y in range(0, H, 64):
            d.line([(0, y), (W, y)], fill=faint)
    elif BG_STYLE == "dots":
        for y in range(24, H, 48):
            for x in range(24 + (y // 48 % 2) * 24, W, 48):
                d.ellipse([x - 2, y - 2, x + 2, y + 2], fill=(255, 255, 255, 18))
    elif BG_STYLE == "diagonal":
        for x in range(-H, W, 56):
            d.line([(x, H), (x + H, 0)], fill=faint, width=2)
    elif BG_STYLE == "circuit":
        rnd = random.Random(7)
        for _ in range(70):
            x, y = rnd.randrange(0, W, 40), rnd.randrange(0, H, 40)
            x2 = x + rnd.choice([-1, 1]) * rnd.randrange(80, 280, 40)
            y2 = y + rnd.choice([-1, 1]) * rnd.randrange(40, 200, 40)
            d.line([(x, y), (x2, y), (x2, y2)], fill=(255, 255, 255, 14), width=2)
            d.ellipse([x2 - 5, y2 - 5, x2 + 5, y2 + 5], outline=(255, 255, 255, 22), width=2)
    return img.convert("RGBA")


def draw_logo(d):
    d.text((60, 38), "</>", font=font(34, MONO), fill=BRAND)
    d.text((136, 36), "Snack Code", font=font(34), fill=WHITE)


BACKGROUND = make_background()
GLOW_A = make_glow(ACCENT, 760, 55)
GLOW_B = make_glow(ACCENT2, 900, 40)
GLOW_RED = make_glow(RED, 900, 210)
rnd = random.Random(108)
SYMBOLS = ["{ }", "</>", "01", "#", "( )", "=>", "[ ]", "&&", "AI", "5G", "UPI", "404", "OTP", "://"]
PARTICLES = [{"sym": rnd.choice(SYMBOLS), "x": rnd.uniform(0, W), "y": rnd.uniform(0, H),
              "v": rnd.uniform(10, 28), "size": rnd.choice([24, 28, 34]),
              "f": rnd.uniform(0.10, 0.18)} for _ in range(20)]


def draw_background(canvas, T):
    canvas.paste(BACKGROUND)
    comp(canvas, GLOW_B, W * 0.62 + 260 * math.sin(T * 0.11) - 450, H * 0.35 + 140 * math.cos(T * 0.08) - 450)
    comp(canvas, GLOW_A, W * 0.25 + 220 * math.cos(T * 0.13) - 380, H * 0.62 + 120 * math.sin(T * 0.1) - 380)
    d = ImageDraw.Draw(canvas)
    for p in PARTICLES:
        y = (p["y"] - p["v"] * T) % (H + 80) - 40
        if y < 100 and p["x"] < 460:
            continue
        d.text((p["x"], y), p["sym"], font=font(p["size"], MONO), fill=mix(TH["top"], MUTED, p["f"]))
    return d


# ======================================================================= heading layouts
def heading_layout(s, big, first):
    size = (104 if first else 92) if big else 58
    color = YELLOW if first else WHITE
    lines = wrap(s["heading"], font(size), 1400 if big else 1600, max_lines=3 if big else 2)
    lh = int(size * 1.2)
    top = int(H * 0.40 - lh * len(lines) / 2) if big else 104
    return {"lines": [text_sprite(l, size, color) for l in lines],
            "ys": [top + j * lh for j in range(len(lines))],
            "bottom": top + lh * len(lines),
            "width": max(text_sprite(l, size, color).width for l in lines) - 28,
            "color": RED if first else ACCENT}


def draw_heading(canvas, d, lay, t):
    for j, (img, y) in enumerate(zip(lay["lines"], lay["ys"])):
        p = ease((t - 0.1 - 0.12 * j) / 0.5)
        comp(canvas, faded(img, p), (W - img.width) / 2, y - 14 + 40 * (1 - p))
    g = ease((t - 0.35) / 0.6)
    if g > 0:
        half = lay["width"] * 0.3 * g / 2
        y = lay["bottom"] + 6
        d.rounded_rectangle([W / 2 - half, y, W / 2 + half, y + 8], radius=4, fill=lay["color"])


# ======================================================================= Byte, the mascot
BODY = (226, 232, 240)


def mascot_sprite(size, mood, mouth, T, wave=False, seed=0):
    S = size * 2
    img = Image.new("RGBA", (S, int(S * 1.12)), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    u = S / 100

    def B(x0, y0, x1, y1):
        return [x0 * u, y0 * u, x1 * u, y1 * u]

    body, edge = BODY + (255,), (100, 116, 139, 255)
    screen, eye = (15, 23, 42, 255), ACCENT + (255,)
    lw = max(2, int(3 * u))
    # antenna
    d.line([(50 * u, 18 * u), (50 * u, 7 * u)], fill=edge, width=lw)
    light = YELLOW if math.sin(T * 5 + seed) > 0 else ACCENT2
    d.ellipse(B(45.5, 1, 54.5, 10), fill=light + (255,))
    # body
    d.rounded_rectangle(B(30, 74, 70, 106), radius=10 * u, fill=body, outline=edge, width=max(1, lw // 2))
    d.ellipse(B(45, 84, 55, 94), fill=ACCENT2 + (255,))
    # head
    d.rounded_rectangle(B(6, 35, 13, 55), radius=3 * u, fill=edge)
    d.rounded_rectangle(B(87, 35, 94, 55), radius=3 * u, fill=edge)
    d.rounded_rectangle(B(12, 16, 88, 74), radius=18 * u, fill=body, outline=edge, width=max(1, lw // 2))
    d.rounded_rectangle(B(20, 24, 80, 66), radius=12 * u, fill=screen)
    # eyes
    blink = ((T + seed * 1.3) % 3.7) < 0.13
    lx, ly = (3, -3) if mood == "think" else (0, 0)
    for cx in (37, 63):
        if blink:
            d.line([((cx - 6) * u, 42 * u), ((cx + 6) * u, 42 * u)], fill=eye, width=lw)
        elif mood == "happy":
            d.arc(B(cx - 7, 37, cx + 7, 51), 190, 350, fill=eye, width=lw + 1)
        elif mood == "shock":
            d.ellipse(B(cx - 7, 35, cx + 7, 49), fill=eye)
            d.ellipse(B(cx - 2, 38, cx + 2, 42), fill=(255, 255, 255, 255))
        else:
            d.rounded_rectangle(B(cx - 5 + lx, 35 + ly, cx + 5 + lx, 49 + ly), radius=3 * u, fill=eye)
        if mood == "warn":
            sgn = -1 if cx < 50 else 1
            d.line([((cx - 8 * sgn) * u, 31 * u), ((cx + 6 * sgn) * u, 34 * u)], fill=RED + (255,), width=lw)
    # mouth: talks with the voice
    if mouth > 0.12:
        h = 1.5 + 6.5 * mouth
        d.rounded_rectangle(B(43, 57 - h, 57, 57 + h), radius=4 * u, fill=eye)
    elif mood == "shock":
        d.ellipse(B(46, 53, 54, 61), outline=eye, width=lw)
    elif mood == "think":
        d.line([(44 * u, 59 * u), (56 * u, 56 * u)], fill=eye, width=lw)
    elif mood == "warn":
        d.arc(B(42, 55, 58, 66), 200, 340, fill=eye, width=lw)
    else:
        d.arc(B(41, 47, 59, 61), 25, 155, fill=eye, width=lw)
    # arms
    d.line([(32 * u, 84 * u), (20 * u, 100 * u)], fill=body, width=int(7 * u))
    d.ellipse(B(15, 95, 25, 105), fill=body)
    wv = math.sin(T * 7)
    if wave or mood == "happy":
        hx, hy = 86 + 4 * wv, 64 - 6 * abs(wv)
    elif mood == "shock":
        hx, hy = 90, 56
    elif mood == "think":
        hx, hy = 62, 76
    elif mood == "explain":
        hx, hy = 88, 80 + 4 * math.sin(T * 3)
    else:
        hx, hy = 82, 100
    d.line([(68 * u, 84 * u), (hx * u, hy * u)], fill=body, width=int(7 * u))
    d.ellipse(B(hx - 5, hy - 5, hx + 5, hy + 5), fill=body)
    return img.resize((size, int(size * 1.12)), Image.LANCZOS)


def draw_corner_mascot(canvas, T, b, prev):
    """Byte in the bottom-left corner, sliding in/out when beats change."""
    now = 1.0 if b["corner"] else 0.0
    was = 1.0 if (prev is not None and prev["corner"]) else 0.0
    f = was + (now - was) * ease((T - b["start"]) / 0.45)
    if f <= 0.01:
        return
    m = mascot_sprite(190, b["mood"], mouth_at(T), T, wave=b["visual"]["type"] == "kinetic")
    x = 150 - 340 * (1 - f)
    y = 905 - m.height / 2 + 5 * math.sin(T * 2.4)
    comp_c(canvas, m, x, y)


# ======================================================================= new beat visuals
def prep_host(s):
    v = s["visual"]
    text = str(v.get("text") or shorten(s["narration"], 12))
    lines = wrap(text, font(50), 720, 4)
    lh = 64
    bw = int(max(font(50).getlength(l) for l in lines)) + 90
    bh = lh * len(lines) + 70
    bub = Image.new("RGBA", (bw + 40, bh), (0, 0, 0, 0))
    bd = ImageDraw.Draw(bub)
    fill = (30, 41, 59, 250)
    bd.polygon([(44, bh / 2 - 26), (2, bh / 2 + 8), (44, bh / 2 + 22)], fill=fill, outline=ACCENT + (255,))
    bd.rounded_rectangle([40, 0, bw + 39, bh - 1], radius=36, fill=fill, outline=ACCENT + (255,), width=4)
    bd.polygon([(46, bh / 2 - 22), (8, bh / 2 + 8), (46, bh / 2 + 18)], fill=fill)
    for j, l in enumerate(lines):
        bd.text((40 + 45, 35 + j * lh), l, font=font(50), fill=WHITE)
    v["_bubble"] = bub
    sfx(s, 0.35, "pop", 0.8)


def draw_host(canvas, d, s, t):
    v = s["visual"]
    x0, y0, x1, y1 = s["area"]
    cy = (y0 + y1) / 2
    T = s["start"] + t
    p = ease((t - 0.05) / 0.45)
    size = int(min(400, (y1 - y0) * 0.85))
    m = mascot_sprite(size, s["mood"], mouth_at(T), T, wave=t < 1.2, seed=1)
    mx = W * 0.27 - 260 * (1 - p)
    comp_c(canvas, faded(m, p), mx, cy + 8 * math.sin(T * 2.2))
    q = ease_back((t - 0.35) / 0.45)
    if q > 0:
        bub = v["_bubble"]
        sc = max(0.05, q)
        img = scaled(bub, sc)
        comp(canvas, img, mx + size * 0.45, cy - img.height / 2 - 40)


def word_sprite(text, size, color):
    """Word image that keeps the text baseline, so mixed words line up."""
    key = ("word", text, size, color)
    if key in _text_cache:
        return _text_cache[key]
    fnt = font(size)
    asc, desc = fnt.getmetrics()
    pad = 14
    img = Image.new("RGBA", (int(fnt.getlength(text)) + pad * 2, asc + desc + pad * 2), (0, 0, 0, 0))
    sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).text((pad + 3, pad + 5), text, font=fnt, fill=(0, 0, 0, 170))
    img = Image.alpha_composite(img, sh.filter(ImageFilter.GaussianBlur(6)))
    ImageDraw.Draw(img).text((pad, pad), text, font=fnt, fill=color + (255,))
    _text_cache[key] = img
    return img


def prep_kinetic(s):
    v = s["visual"]
    text = str(v.get("text") or shorten(s["narration"], 8))
    words = text.split()[:12]
    size = 92 if len(words) <= 6 else 78
    lines = wrap(" ".join(words), font(size), 1500, 3)
    hl = str(v.get("highlight") or "").lower().strip()
    clean = [re.sub(r"[^\w₹%]", "", w).lower() for w in words]
    if not hl or not any(hl in c for c in clean):
        hl = max(clean, key=len) if clean else ""
    placed, k = [], 0
    lh = int(size * 1.25)
    space = font(size).getlength(" ")
    for j, line in enumerate(lines):
        lw = font(size).getlength(line)
        x = (W - lw) / 2
        for w in line.split():
            is_hl = bool(hl) and hl in re.sub(r"[^\w₹%]", "", w).lower()
            spr = word_sprite(w, size, ACCENT2 if is_hl else WHITE)
            placed.append({"spr": spr, "x": x, "line": j, "hl": is_hl, "w": font(size).getlength(w)})
            x += font(size).getlength(w) + space
            k += 1
    step = min(0.22, 0.6 * s["dur"] / max(1, len(placed)))
    for i, pw in enumerate(placed):
        pw["t"] = 0.25 + i * step
        sfx(s, pw["t"], "tick", 0.5)
    v["_words"], v["_lh"], v["_nlines"], v["_size"] = placed, lh, len(lines), size


def draw_kinetic(canvas, d, s, t):
    v = s["visual"]
    x0, y0, x1, y1 = s["area"]
    top = (y0 + y1) / 2 - v["_lh"] * v["_nlines"] / 2
    for pw in v["_words"]:
        p = ease_back((t - pw["t"]) / 0.32)
        if p <= 0:
            continue
        y = top + pw["line"] * v["_lh"]
        if pw["hl"]:
            g = ease((t - pw["t"] - 0.15) / 0.35)
            if g > 0:
                d.rounded_rectangle([pw["x"] - 10, y + v["_size"] * 0.62, pw["x"] - 10 + (pw["w"] + 20) * g,
                                     y + v["_size"] * 1.18], radius=10, fill=mix(TH["top"], ACCENT2, 0.35))
        spr = scaled(pw["spr"], 0.5 + 0.5 * max(0.05, p))
        comp(canvas, faded(spr, clamp01(p * 1.5)), pw["x"] - 14 + (pw["spr"].width - spr.width) / 2,
             y - 14 + (pw["spr"].height - spr.height) / 2)


# ======================================================================= visuals
# Each visual has prep(s) (build sprites once) and draw(canvas, d, s, t).

def prep_title(s):
    pass


def draw_title(canvas, d, s, t):
    cx, cy, r = W // 2, int(H * 0.40), 360
    a = t * 20 + s["idx"] * 40
    d.arc([cx - r, cy - r, cx + r, cy + r], a, a + 110, fill=dim(ACCENT, 0.4, TH["top"]), width=5)
    d.arc([cx - r, cy - r, cx + r, cy + r], a + 180, a + 250, fill=dim(ACCENT, 0.4, TH["top"]), width=5)
    r2 = r - 44
    d.arc([cx - r2, cy - r2, cx + r2, cy + r2], -a * 1.4, -a * 1.4 + 70, fill=dim(ACCENT2, 0.4, TH["top"]), width=3)


def prep_chapter(s):
    v = s["visual"]
    part, total = v.get("part"), v.get("total")
    v["_pill"] = text_sprite(f"PART {part} / {total}" if total else f"PART {part}", 44, WHITE, shadow=False)
    sfx(s, 0.2, "ding", 0.8)


def draw_chapter(canvas, d, s, t):
    """The line break between two parts of the story; the question itself is the big heading."""
    draw_title(canvas, d, s, t)
    pill = s["visual"]["_pill"]
    q = ease_back(t / 0.45)
    if q > 0:
        cy = s["lay"]["ys"][0] - 80
        w2, h2 = (pill.width / 2 + 34) * max(0.05, q), 44 * max(0.05, q)
        d.rounded_rectangle([W / 2 - w2, cy - h2, W / 2 + w2, cy + h2], radius=int(h2), fill=ACCENT)
        comp_c(canvas, faded(pill, ease((t - 0.1) / 0.3)), W / 2, cy)


def prep_icon(s):
    v = s["visual"]
    size = 300
    disc = Image.new("RGBA", (520, 520), (0, 0, 0, 0))
    ImageDraw.Draw(disc).ellipse([10, 10, 510, 510], fill=dim(ACCENT, 0.22, TH["top"]) + (255,),
                                 outline=dim(ACCENT, 0.6, TH["top"]) + (255,), width=4)
    disc.alpha_composite(icon_sprite(v["icon"], size, RED if v["icon"] in ("hacker", "warning") else ACCENT),
                         dest=(110, 110))
    v["_disc"] = disc.resize((440, 440), Image.LANCZOS)
    text = str(v.get("text", "")).strip()
    v["_text"] = text_block(wrap(text, font(44, REGULAR), 1300, 2), 44, MUTED, path=REGULAR) if text else None
    sfx(s, 0.3, "pop", 0.9)


def draw_icon(canvas, d, s, t):
    v = s["visual"]
    x0, y0, x1, y1 = s["area"]
    cx = W / 2
    cy = y0 + (y1 - y0) * (0.42 if v["_text"] else 0.5)
    phase = (t * 0.6) % 1
    r = 190 + 160 * phase
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=mix(TH["top"], ACCENT, 0.5 * (1 - phase)), width=4)
    p = ease_back((t - 0.3) / 0.55)
    if p > 0:
        comp_c(canvas, scaled(v["_disc"], 0.3 + 0.7 * p), cx, cy + 10 * math.sin(t * 2))
    if v["_text"]:
        q = ease((t - 0.8) / 0.5)
        comp_c(canvas, faded(v["_text"], q), cx, cy + 285 + 20 * (1 - q))


def phone_frame(w=370, h=720):
    S = 2
    img = Image.new("RGBA", (w * S, h * S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, w * S - 1, h * S - 1], radius=52 * S, fill=(38, 44, 58, 255))
    d.rounded_rectangle([3 * S, 3 * S, w * S - 3 * S, h * S - 3 * S], radius=50 * S, fill=(20, 24, 34, 255))
    d.rounded_rectangle([12 * S, 12 * S, (w - 12) * S, (h - 12) * S], radius=42 * S, fill=(12, 16, 26, 255))
    d.rounded_rectangle([(w / 2 - 44) * S, 22 * S, (w / 2 + 44) * S, 40 * S], radius=9 * S, fill=(0, 0, 0, 255))
    return img, d, S


def prep_phone_call(s):
    v = s["visual"]
    w, h = 370, 720
    img, d, S = phone_frame(w, h)
    d.text((w / 2 * S, 96 * S), "Incoming call", font=font(22 * S, REGULAR), fill=MUTED, anchor="mm")
    d.ellipse([(w / 2 - 72) * S, (150) * S, (w / 2 + 72) * S, 294 * S], fill=dim(ACCENT2, 0.45) + (255,))
    av = icon_sprite("hacker" if v.get("scam", True) else "user", 96 * S, WHITE)
    img.alpha_composite(av, dest=(int((w / 2 - 48) * S), int(170 * S)))
    name = fit(v.get("caller") or "Unknown", font(34 * S), (w - 50) * S)
    d.text((w / 2 * S, 336 * S), name, font=font(34 * S), fill=WHITE, anchor="mm")
    num = fit(v.get("number") or "+91 98XXX XXXXX", font(24 * S, REGULAR), (w - 50) * S)
    d.text((w / 2 * S, 378 * S), num, font=font(24 * S, REGULAR), fill=MUTED, anchor="mm")
    for bx, col in ((w * 0.27, RED), (w * 0.73, GREEN)):
        d.ellipse([(bx - 40) * S, 520 * S, (bx + 40) * S, 600 * S], fill=col + (255,))
        ic = icon_sprite("phone", 44 * S, WHITE)
        img.alpha_composite(ic, dest=(int((bx - 22) * S), int(538 * S)))
    for j, lab in enumerate(("Decline", "Accept")):
        d.text(((w * (0.27 if j == 0 else 0.73)) * S, 622 * S), lab, font=font(18 * S, REGULAR),
               fill=MUTED, anchor="mm")
    v["_phone"] = img.resize((w, h), Image.LANCZOS)
    sfx(s, 0.2, "whoosh", 0.5)
    tr = 0.8
    while tr < s["dur"] - 0.4:
        sfx(s, tr, "ring", 1.0)
        tr += 1.6


def draw_phone_call(canvas, d, s, t):
    v = s["visual"]
    x0, y0, x1, y1 = s["area"]
    cx, cy = W / 2, (y0 + y1) / 2
    ph = v["_phone"]
    scale = min(1.0, (y1 - y0) / ph.height)
    img = scaled(ph, scale)
    p = ease((t - 0.2) / 0.6)
    ringing = t > 0.8 and (t % 1.6) < 1.0
    if ringing:
        for k in range(3):
            ph_ = ((t * 1.5) + k / 3) % 1
            r = img.width / 2 + 30 + 120 * ph_
            col = mix(TH["top"], ACCENT, 0.7 * (1 - ph_))
            box = [cx - r, cy - r, cx + r, cy + r]
            d.arc(box, -35, 35, fill=col, width=6)
            d.arc(box, 145, 215, fill=col, width=6)
        img = img.rotate(3.5 * math.sin(t * 28), resample=Image.BICUBIC, expand=True)
    comp_c(canvas, faded(img, p), cx, cy + 160 * (1 - p))


def prep_phone_sms(s):
    v = s["visual"]
    w, h = 370, 720
    img, d, S = phone_frame(w, h)
    d.text((34 * S, 34 * S), "10:24", font=font(20 * S), fill=WHITE, anchor="lm")
    rr = random.Random(s["idx"])
    for row in range(4):
        for col in range(4):
            x = 36 + col * 70
            y = 300 + row * 82
            c = mix((12, 16, 26), rr.choice([ACCENT, ACCENT2, (148, 163, 184), (251, 146, 60)]), 0.35)
            d.rounded_rectangle([x * S, y * S, (x + 52) * S, (y + 52) * S], radius=14 * S, fill=c + (255,))
    v["_phone"] = img.resize((w, h), Image.LANCZOS)
    # notification card
    cw = 336
    sender = fit(v.get("sender") or "VM-ALERT", font(23), cw - 90)
    msg = str(v.get("message") or s["heading"])
    lines = wrap(msg, font(22, REGULAR), cw - 36, 4)
    ch = 80 + 29 * len(lines)
    link = re.search(r"(https?://\S+|www\.\S+|\S+\.(?:com|in|xyz|link|ly|info|top)\S*)", msg)
    v["_link"] = text_sprite(fit(link.group(1), font(36, MONO), 640), 36, (96, 165, 250), MONO) if link else None
    card = Image.new("RGBA", (cw * 2, ch * 2), (0, 0, 0, 0))
    cd = ImageDraw.Draw(card)
    cd.rounded_rectangle([0, 0, cw * 2 - 1, ch * 2 - 1], radius=36, fill=(44, 52, 70, 250))
    cd.rounded_rectangle([28, 26, 76, 74], radius=12, fill=ACCENT + (255,))
    card.alpha_composite(icon_sprite("mail", 32, DARK), dest=(36, 34))
    cd.text((96, 50), sender, font=font(44), fill=WHITE, anchor="lm")
    cd.text((cw * 2 - 28, 50), "now", font=font(34, REGULAR), fill=MUTED, anchor="rm")
    for j, line in enumerate(lines):
        y = 106 + j * 58
        x = 32
        for word in line.split():
            link = bool(re.search(r"https?://|www\.|\.(com|in|xyz|link|ly)\b|bit\.ly", word))
            col = (96, 165, 250) if link else (226, 232, 240)
            cd.text((x, y), word, font=font(44, REGULAR), fill=col)
            wl = font(44, REGULAR).getlength(word + " ")
            if link:
                cd.line([(x, y + 52), (x + wl - 12, y + 52)], fill=col, width=3)
            x += wl
    v["_card"] = card.resize((cw, ch), Image.LANCZOS)
    v["_danger"] = v.get("danger", True)
    sfx(s, 0.95, "pop", 0.9)
    if v["_danger"] and s["dur"] > 2.6:
        sfx(s, 2.2, "alarm", 1.0)


def draw_phone_sms(canvas, d, s, t):
    v = s["visual"]
    x0, y0, x1, y1 = s["area"]
    cx, cy = W / 2 - (150 if v["_danger"] else 0), (y0 + y1) / 2
    base = v["_phone"]
    scale = min(1.0, (y1 - y0) / base.height)
    p = ease((t - 0.2) / 0.6)
    ph = base.copy()
    q = ease_back((t - 0.9) / 0.55)
    card = v["_card"]
    if q > 0:
        comp(ph, card, (ph.width - card.width) / 2, 56 - (card.height + 40) * (1 - q))
    img = scaled(ph, scale)
    px, py = cx - img.width / 2, cy - img.height / 2 + 160 * (1 - p)
    comp(canvas, faded(img, p), px, py)
    if v["_danger"] and t > 2.0:
        if math.sin(t * 7) > -0.3:
            cxl = px + (ph.width - card.width) / 2 * scale
            cyt = py + 56 * scale
            d.rounded_rectangle([cxl - 6, cyt - 6, cxl + card.width * scale + 6, cyt + card.height * scale + 6],
                                radius=22, outline=RED, width=5)
        w2 = ease_back((t - 2.2) / 0.5)
        if w2 > 0:
            comp_c(canvas, scaled(icon_sprite("warning", 220, RED), max(0.05, w2)), cx + 430, cy - 40)
            lab = text_sprite("FAKE LINK", 46, RED)
            comp_c(canvas, faded(lab, clamp01((t - 2.4) / 0.4)), cx + 430, cy + 120)
            if v["_link"] is not None:
                comp_c(canvas, faded(v["_link"], clamp01((t - 2.7) / 0.4)), cx + 430, cy + 185)


def prep_chat(s):
    v = s["visual"]
    msgs = []
    for m in v.get("messages", [])[:6] if isinstance(v.get("messages"), list) else []:
        if isinstance(m, dict) and str(m.get("text", "")).strip():
            msgs.append({"me": str(m.get("from", "them")).lower() in ("me", "user", "you", "aap"),
                         "text": str(m["text"]).strip()})
    if not msgs:
        msgs = [{"me": False, "text": s["heading"]}]
    pw, phh = 1000, 640
    panel = Image.new("RGBA", (pw, phh), (0, 0, 0, 0))
    pd = ImageDraw.Draw(panel)
    pd.rounded_rectangle([0, 0, pw - 1, phh - 1], radius=32, fill=(15, 20, 32, 245),
                         outline=dim(ACCENT, 0.5, (15, 20, 32)) + (255,), width=2)
    pd.rounded_rectangle([0, 0, pw - 1, 92], radius=32, fill=(30, 38, 54, 255))
    pd.rectangle([0, 60, pw - 1, 92], fill=(30, 38, 54, 255))
    pd.ellipse([28, 18, 84, 74], fill=dim(ACCENT2, 0.6) + (255,))
    panel.alpha_composite(icon_sprite("user", 36, WHITE), dest=(38, 28))
    pd.text((104, 34), fit(v.get("name") or "Unknown Number", font(30), 600), font=font(30), fill=WHITE, anchor="lm")
    pd.text((104, 66), "online", font=font(20, REGULAR), fill=GREEN, anchor="lm")
    v["_panel"] = panel
    bubbles = []
    for m in msgs:
        lines = wrap(m["text"], font(28, REGULAR), 560, 4)
        bw = int(max(font(28, REGULAR).getlength(l) for l in lines)) + 44
        bh = 38 * len(lines) + 30
        b = Image.new("RGBA", (bw, bh), (0, 0, 0, 0))
        bd = ImageDraw.Draw(b)
        col = mix(DARK, ACCENT, 0.55) if m["me"] else (51, 61, 80)
        bd.rounded_rectangle([0, 0, bw - 1, bh - 1], radius=22, fill=col + (255,))
        for j, l in enumerate(lines):
            bd.text((22, 15 + j * 38), l, font=font(28, REGULAR), fill=WHITE)
        bubbles.append((b, m["me"]))
    v["_bubbles"] = bubbles
    v["_times"] = reveal_times(s, len(bubbles), start=0.7)
    for (b_, me_), tm in zip(bubbles, v["_times"]):
        sfx(s, tm, "pop", 0.55)
        if not me_:
            for q in (0.6, 0.4, 0.2):
                if tm - q > 0:
                    sfx(s, tm - q, "tick", 0.6)
    dots = Image.new("RGBA", (110, 56), (0, 0, 0, 0))
    ImageDraw.Draw(dots).rounded_rectangle([0, 0, 109, 55], radius=22, fill=(51, 61, 80, 255))
    v["_typing"] = dots


def draw_chat(canvas, d, s, t):
    v = s["visual"]
    x0, y0, x1, y1 = s["area"]
    panel = v["_panel"]
    sc = min(1.0, (y1 - y0) / panel.height)
    p = ease((t - 0.15) / 0.5)
    pnl = panel.copy()
    pdr = ImageDraw.Draw(pnl)
    shown = [(b, me, tm) for (b, me), tm in zip(v["_bubbles"], v["_times"]) if t >= tm]
    nxt = next(((b, me, tm) for (b, me), tm in zip(v["_bubbles"], v["_times"]) if t < tm), None)
    ys, y = [], 112
    for b, me, tm in shown:
        ys.append(y)
        y += b.height + 16
    typing = nxt is not None and not nxt[1] and nxt[2] - t < 0.8
    bottom = y + (72 if typing else 0)
    off = max(0, bottom - (panel.height - 24))
    for (b, me, tm), yy in zip(shown, ys):
        a = ease((t - tm) / 0.3)
        x = panel.width - b.width - 28 if me else 28
        comp(pnl, faded(b, a), x, yy - off + 24 * (1 - a))
    if typing:
        comp(pnl, v["_typing"], 28, y - off)
        for k in range(3):
            jump = 6 * max(0, math.sin(t * 10 - k * 0.9))
            pdr.ellipse([28 + 24 + k * 24, y - off + 22 - jump, 28 + 36 + k * 24, y - off + 34 - jump], fill=MUTED)
    # keep the header on top of scrolled bubbles
    pnl.alpha_composite(panel.crop((0, 0, panel.width, 94)), dest=(0, 0))
    img = scaled(pnl, sc)
    comp_c(canvas, faded(img, p), W / 2, (y0 + y1) / 2 + 60 * (1 - p))


def prep_steps(s):
    v = s["visual"]
    items = as_list(v.get("items"), 5) or [s["heading"]]
    rows = []
    for k, it in enumerate(items):
        lines = wrap(it, font(44, REGULAR), 1180, 2)
        rh = 54 * len(lines) + 48
        r = Image.new("RGBA", (1400, rh), (0, 0, 0, 0))
        rd = ImageDraw.Draw(r)
        rd.rounded_rectangle([0, 0, 1399, rh - 1], radius=24, fill=(22, 30, 46, 235))
        rd.ellipse([24, rh / 2 - 34, 92, rh / 2 + 34], fill=ACCENT + (255,))
        rd.text((58, rh / 2), str(k + 1), font=font(36), fill=DARK, anchor="mm")
        for j, l in enumerate(lines):
            rd.text((124, 22 + j * 54), l, font=font(44, REGULAR), fill=WHITE)
        rows.append(r)
    v["_rows"] = rows
    v["_times"] = reveal_times(s, len(rows), start=0.5)
    for tm in v["_times"]:
        sfx(s, tm, "pop", 0.8)
    sfx(s, v["_times"][-1] + 0.35, "ding", 0.6)


def draw_steps(canvas, d, s, t):
    v = s["visual"]
    x0, y0, x1, y1 = s["area"]
    rows = v["_rows"]
    gap = 26
    total = sum(r.height for r in rows) + gap * (len(rows) - 1)
    sc = min(1.0, (y1 - y0) / total)
    y = (y0 + y1) / 2 - total * sc / 2
    current = max([k for k, tm in enumerate(v["_times"]) if t >= tm], default=-1)
    for k, (r, tm) in enumerate(zip(rows, v["_times"])):
        rs = scaled(r, sc)
        a = ease((t - tm) / 0.45)
        if a > 0:
            x = (W - rs.width) / 2 - 80 * (1 - a)
            comp(canvas, faded(rs, a if k == current else 0.75 * a + 0.0), x, y)
            if k == current:
                d.rounded_rectangle([x - 14, y + 10, x - 6, y + rs.height - 10], radius=4, fill=ACCENT)
        y += rs.height + gap * sc


def prep_compare(s):
    v = s["visual"]
    left = as_list(v.get("left"), 4) or ["..."]
    right = as_list(v.get("right"), 4) or ["..."]
    cw = 800

    def card(title, items, good):
        col = GREEN if good else RED
        rows = [wrap(it, font(40, REGULAR), cw - 130, 2) for it in items]
        ch = 140 + sum(50 * len(r) + 42 for r in rows) + 24
        c = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        cd = ImageDraw.Draw(c)
        cd.rounded_rectangle([0, 0, cw - 1, ch - 1], radius=28, fill=(20, 27, 42, 240), outline=col + (255,), width=3)
        cd.rounded_rectangle([0, 0, cw - 1, 108], radius=28, fill=dim(col, 0.35, (20, 27, 42)) + (255,))
        cd.rectangle([3, 80, cw - 4, 108], fill=dim(col, 0.35, (20, 27, 42)) + (255,))
        c.alpha_composite(icon_sprite("check" if good else "cross", 64, col), dest=(28, 22))
        cd.text((112, 54), fit(title, font(48), cw - 150), font=font(48), fill=WHITE, anchor="lm")
        pos, y = [], 142
        for r in rows:
            h = 50 * len(r) + 42
            pos.append((y, h, r))
            y += h
        return c, pos

    lc, lpos = card(v.get("left_title") or "Asli", left, True)
    rc, rpos = card(v.get("right_title") or "Fake", right, False)
    v["_cards"] = (lc, lpos, rc, rpos)
    order = []
    for k in range(max(len(lpos), len(rpos))):
        if k < len(lpos):
            order.append(("L", k))
        if k < len(rpos):
            order.append(("R", k))
    times = reveal_times(s, len(order), start=0.9)
    v["_reveal"] = {key: tm for key, tm in zip(order, times)}
    sfx(s, 0.15, "whoosh", 0.6)
    for (side, _), tm in zip(order, times):
        sfx(s, tm, "ding" if side == "L" else "pop", 0.35 if side == "L" else 0.7)


def draw_compare(canvas, d, s, t):
    v = s["visual"]
    x0, y0, x1, y1 = s["area"]
    lc, lpos, rc, rpos = v["_cards"]
    hh = max(lc.height, rc.height)
    sc = min(1.0, (y1 - y0) / hh)
    for side, c, pos, good in (("L", lc, lpos, True), ("R", rc, rpos, False)):
        img = c.copy()
        cd = ImageDraw.Draw(img)
        col = GREEN if good else RED
        for k, (y, h, lines) in enumerate(pos):
            a = ease((t - v["_reveal"][(side, k)]) / 0.4)
            if a <= 0:
                continue
            ic = faded(icon_sprite("check" if good else "cross", 40, col), a)
            comp(img, ic, 30, y + 6)
            for j, l in enumerate(lines):
                cd.text((90 + 30 * (1 - a), y + j * 50), l, font=font(40, REGULAR),
                        fill=mix((20, 27, 42), WHITE, a))
        p = ease((t - 0.15) / 0.55)
        img = scaled(img, sc)
        cx = W / 2 + (-1 if side == "L" else 1) * (img.width / 2 + 24)
        off = (-1 if side == "L" else 1) * 200 * (1 - p)
        comp(canvas, faded(img, p), cx - img.width / 2 + off, (y0 + y1) / 2 - hh * sc / 2)


def prep_stat(s):
    v = s["visual"]
    raw = str(v.get("value") or "")
    m = re.match(r"^(.*?)(\d[\d,]*(?:\.\d+)?)(.*)$", raw)
    if m:
        pre, num, suf = m.groups()
        v["_num"] = float(num.replace(",", ""))
        v["_dec"] = len(num.split(".")[1]) if "." in num else 0
        v["_comma"] = "," in num
        v["_pre"], v["_suf"] = pre, suf
    else:
        v["_num"] = None
        v["_raw"] = raw or s["heading"]
    v["_pct"] = v["_num"] if (m and "%" in v["_suf"] and v["_num"] <= 100) else None
    label = str(v.get("label") or "").strip()
    v["_label"] = text_block(wrap(label, font(42, REGULAR), 1200, 2), 42, MUTED, path=REGULAR) if label else None
    sfx(s, 0.3, "riser", 1.0)
    sfx(s, 1.7, "ding", 0.8)


def fmt_num(v, x):
    if v["_dec"]:
        s = f"{x:,.{v['_dec']}f}" if v["_comma"] else f"{x:.{v['_dec']}f}"
    else:
        s = f"{int(round(x)):,}" if v["_comma"] else f"{int(round(x))}"
    if v["_comma"] and v["_pre"].strip() in ("₹", "Rs", "Rs."):  # Indian grouping 1,00,000
        n = str(int(round(x)))
        if len(n) > 3:
            head, tail = n[:-3], n[-3:]
            head = ",".join(re.findall(r"\d{1,2}(?=(?:\d{2})*$)", head))
            s = head + "," + tail
    return v["_pre"] + s + v["_suf"]


def draw_stat(canvas, d, s, t):
    v = s["visual"]
    x0, y0, x1, y1 = s["area"]
    cx = W / 2
    cy = y0 + (y1 - y0) * (0.43 if v["_label"] else 0.5)
    r = min(250, (y1 - y0) * 0.42)
    c = ease((t - 0.3) / 1.4)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=dim(ACCENT, 0.3, TH["top"]), width=18)
    if v["_pct"] is not None:
        d.arc([cx - r, cy - r, cx + r, cy + r], -90, -90 + 360 * v["_pct"] / 100 * c, fill=ACCENT, width=18)
    else:
        a = t * 40
        d.arc([cx - r, cy - r, cx + r, cy + r], a, a + 80, fill=ACCENT, width=18)
    txt = fmt_num(v, v["_num"] * c) if v["_num"] is not None else v["_raw"]
    size = 150
    while font(size, SYMBOL).getlength(txt) > r * 1.7 and size > 50:
        size -= 6
    sp = ease_back((t - 0.2) / 0.5)
    if sp > 0:
        comp_c(canvas, scaled(text_sprite(txt, size, WHITE, SYMBOL), 0.5 + 0.5 * sp), cx, cy)
    if v["_label"]:
        q = ease((t - 1.0) / 0.5)
        comp_c(canvas, faded(v["_label"], q), cx, cy + r + 70 + 20 * (1 - q))


def prep_warning(s):
    v = s["visual"]
    text = str(v.get("text") or "").strip()
    v["_text"] = text_block(wrap(text, font(54), 1400, 2), 54, WHITE) if text else None
    sfx(s, 0.25, "alarm", 1.0)


def draw_warning(canvas, d, s, t):
    v = s["visual"]
    x0, y0, x1, y1 = s["area"]
    cx = W / 2
    cy = y0 + (y1 - y0) * (0.40 if v["_text"] else 0.5)
    pulse = 0.35 + 0.35 * (0.5 + 0.5 * math.sin(t * 5))
    comp_c(canvas, faded(GLOW_RED, pulse * ease(t / 0.5)), cx, cy)
    p = ease_back((t - 0.2) / 0.5)
    shake = 10 * math.sin(t * 45) if (t % 3.0) < 0.5 and t > 0.6 else 0
    if p > 0:
        comp_c(canvas, scaled(icon_sprite("warning", 340, RED), max(0.05, p)), cx + shake, cy)
    if v["_text"]:
        q = ease((t - 0.7) / 0.5)
        comp_c(canvas, faded(v["_text"], q), cx, cy + 250 + 20 * (1 - q))


def prep_flow(s):
    v = s["visual"]
    nodes = []
    for nd in v.get("nodes", [])[:4] if isinstance(v.get("nodes"), list) else []:
        if isinstance(nd, dict):
            lab = str(nd.get("label", "")).strip()
            ic = nd.get("icon") if nd.get("icon") in ICONS else guess_icon(lab)
        else:
            lab, ic = str(nd).strip(), guess_icon(str(nd))
        if lab:
            nodes.append((ic, lab))
    if len(nodes) < 2:
        nodes = [("user", "Aap"), (guess_icon(s["heading"] + s["narration"]), s["heading"][:24])]
    sprites = []
    for ic, lab in nodes:
        size = 240
        img = Image.new("RGBA", (340, 360), (0, 0, 0, 0))
        dd = ImageDraw.Draw(img)
        bad = ic in ("hacker", "warning", "bug")
        col = RED if bad else ACCENT
        dd.ellipse([50, 0, 290, 240], fill=dim(col, 0.25, TH["top"]) + (255,), outline=col + (255,), width=4)
        img.alpha_composite(icon_sprite(ic, 130, col), dest=(105, 55))
        lines = wrap(lab, font(32), 320, 2)
        for j, l in enumerate(lines):
            dd.text((170, 274 + j * 40), l, font=font(32), fill=WHITE, anchor="mm")
        sprites.append(img)
    v["_nodes"] = sprites
    v["_times"] = reveal_times(s, len(sprites), start=0.5, share=0.6)
    for k_, tm in enumerate(v["_times"]):
        sfx(s, tm, "pop", 0.8)
        if k_:
            sfx(s, tm - 0.35, "whoosh", 0.35)


def draw_flow(canvas, d, s, t):
    v = s["visual"]
    x0, y0, x1, y1 = s["area"]
    n = len(v["_nodes"])
    sc = min(1.0, (y1 - y0) / 380)
    xs = [W / 2 + (k - (n - 1) / 2) * min(460, 1600 / n) for k in range(n)]
    cy = (y0 + y1) / 2 - 20 * sc
    ccy = cy - 60 * sc  # circle centre
    r = 120 * sc
    for k in range(n - 1):
        g = ease((t - v["_times"][k + 1] + 0.35) / 0.4)
        if g <= 0:
            continue
        ax0, ax1 = xs[k] + r + 18, xs[k + 1] - r - 18
        end = ax0 + (ax1 - ax0) * g
        arrow(d, ax0, ccy, end, ccy, mix(TH["top"], ACCENT2, 0.9), width=8, head=28)
        if g >= 1:
            ph = ((t - k * 0.3) * 0.8) % 1
            px = ax0 + (ax1 - ax0 - 30) * ph
            d.ellipse([px - 11, ccy - 11, px + 11, ccy + 11], fill=WHITE)
    for k, (img, tm) in enumerate(zip(v["_nodes"], v["_times"])):
        p = ease_back((t - tm) / 0.5)
        if p > 0:
            comp_c(canvas, scaled(img, sc * max(0.05, p)), xs[k], cy)


def prep_image(s):
    v = s["visual"]
    x0, y0, x1, y1 = s["area"]
    ch = int(min(580, y1 - y0))
    cw = int(ch * 16 / 9)
    src = Image.open(s["image"]).convert("RGB")
    bw, bh = int(cw * 1.12), int(ch * 1.12)
    f = max(bw / src.width, bh / src.height)
    src = src.resize((int(src.width * f) + 1, int(src.height * f) + 1), Image.LANCZOS)
    lft, tp = (src.width - bw) // 2, (src.height - bh) // 2
    v["_src"] = src.crop((lft, tp, lft + bw, tp + bh))
    mask = Image.new("L", (cw, ch), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, cw - 1, ch - 1], radius=28, fill=255)
    v["_card"] = ((W - cw) // 2, int((y0 + y1) / 2 - ch / 2), cw, ch, mask)
    sfx(s, 0.25, "whoosh", 0.5)


def draw_image(canvas, d, s, t):
    v = s["visual"]
    x, y, cw, ch, mask = v["_card"]
    p = ease((t - 0.25) / 0.6)
    if p <= 0:
        return
    src = v["_src"]
    zoom = 1 + 0.1 * min(1.0, t / (s["end"] - s["start"]))
    ww, hh = src.width / zoom, src.height / zoom
    lft = (src.width - ww) / 2 + (src.width - ww) * 0.3 * math.sin(t * 0.2)
    tp = (src.height - hh) / 2
    frame = src.resize((cw, ch), Image.BILINEAR, box=(lft, tp, lft + ww, tp + hh))
    yy = int(y + 50 * (1 - p))
    canvas.paste(frame, (x, yy), mask if p >= 1 else mask.point(lambda val: int(val * p)))
    d.rounded_rectangle([x - 3, yy - 3, x + cw + 2, yy + ch + 2], radius=30, outline=ACCENT, width=3)


VISUALS = {
    "title": (prep_title, draw_title), "chapter": (prep_chapter, draw_chapter), "icon": (prep_icon, draw_icon),
    "phone_call": (prep_phone_call, draw_phone_call), "phone_sms": (prep_phone_sms, draw_phone_sms),
    "chat": (prep_chat, draw_chat), "steps": (prep_steps, draw_steps), "compare": (prep_compare, draw_compare),
    "stat": (prep_stat, draw_stat), "warning": (prep_warning, draw_warning), "flow": (prep_flow, draw_flow),
    "image": (prep_image, draw_image), "kinetic": (prep_kinetic, draw_kinetic), "host": (prep_host, draw_host),
}


# ======================================================================= captions
CAP_FONT = font(50)


def prepare_captions(s):
    """Captions per beat: each beat's words are spread over that beat's own speech."""
    s["captions"] = []
    for b in s["beats"]:
        words = b["say"].split()
        chunks, cur = [], []
        for w in words:
            cur.append(w)
            if len(cur) >= WORDS_PER_CAPTION or re.search(r"[.?!।]$", w):
                chunks.append(cur)
                cur = []
        if cur:
            chunks.append(cur)
        total_chars = sum(len(w) + 1 for w in words) or 1
        t = 0.0
        for chunk in chunks:
            times = []
            for w in chunk:
                times.append(b["start"] + t)
                t += b["dur"] * (len(w) + 1) / total_chars
            s["captions"].append({"words": chunk, "times": times, "end": b["start"] + t})


_cap_cache = {}


def caption_layout(key, cap):
    if key in _cap_cache:
        return _cap_cache[key]
    space = CAP_FONT.getlength(" ")
    lines, line, width = [], [], 0.0
    for w in cap["words"]:
        wl = CAP_FONT.getlength(w)
        if line and width + space + wl > 1300:
            lines.append((line, width))
            line, width = [], 0.0
        width += (space if line else 0) + wl
        line.append((w, wl))
    lines.append((line, width))
    box_w = int(max(w for _, w in lines) + 64)
    box_h = 66 * len(lines) + 28
    box = Image.new("RGBA", (box_w, box_h), (0, 0, 0, 0))
    ImageDraw.Draw(box).rounded_rectangle([0, 0, box_w - 1, box_h - 1], radius=22, fill=(0, 0, 0, 170))
    bx, by = (W - box_w) // 2, H - 52 - box_h
    placed, idx = [], 0
    for j, (ln, lw) in enumerate(lines):
        x = (W - lw) / 2
        for w, wl in ln:
            placed.append((w, x, by + 14 + j * 66, idx))
            x += wl + space
            idx += 1
    _cap_cache[key] = (box, bx, by, placed)
    return _cap_cache[key]


def draw_captions(canvas, d, s, T):
    current = None
    for c_i, cap in enumerate(s["captions"]):
        if cap["times"][0] <= T:
            current = (c_i, cap)
    if not current:
        return
    c_i, cap = current
    box, bx, by, placed = caption_layout((s["idx"], c_i), cap)
    canvas.alpha_composite(box, dest=(bx, by))
    spoken = max(k for k, tm in enumerate(cap["times"]) if tm <= T)
    for w, x, y, k in placed:
        d.text((x, y), w, font=CAP_FONT, fill=YELLOW if k == spoken else WHITE)


# ======================================================================= stickers + camera
def prep_sticker(b):
    if not b["pop"]:
        b["_pop_t"] = None
        return
    fnt = font(62)
    tw = int(fnt.getlength(b["pop"].upper()))
    img = Image.new("RGBA", (tw + 80, 120), (0, 0, 0, 0))
    dd = ImageDraw.Draw(img)
    dd.rounded_rectangle([4, 4, tw + 75, 115], radius=26, fill=YELLOW + (255,), outline=WHITE + (255,), width=6)
    dd.text((tw / 2 + 40, 60), b["pop"].upper(), font=fnt, fill=DARK, anchor="mm")
    b["_sticker"] = img.rotate(-6, resample=Image.BICUBIC, expand=True)
    # time it to the moment the word is spoken
    key = re.sub(r"[^\w₹%]", "", b["pop"].split()[0]).lower()
    when = None
    for cap in b["scene"]["captions"]:
        for w, tm in zip(cap["words"], cap["times"]):
            if b["start"] <= tm < b["end"] and key and key in re.sub(r"[^\w₹%]", "", w).lower():
                when = tm
                break
        if when is not None:
            break
    b["_pop_t"] = when if when is not None else b["start"] + 0.45 * b["dur"]
    EVENTS.append((b["_pop_t"], "pop", 1.0))


def draw_sticker(canvas, b, T):
    pt = b.get("_pop_t")
    if pt is None or not (pt <= T < pt + 1.8):
        return
    p = ease_back((T - pt) / 0.3)
    out = clamp01((pt + 1.8 - T) / 0.25)
    img = faded(scaled(b["_sticker"], max(0.05, p)), out)
    x = 380 if b["visual"]["type"] == "phone_sms" else W - 340
    comp_c(canvas, img, x, b["area"][1] + 110)


def bump(x, rise=0.12, fall=0.6):
    if x < 0:
        return 0.0
    if x < rise:
        return ease(x / rise)
    return max(0.0, 1 - (x - rise) / fall) ** 2


def camera(T, b):
    t = T - b["start"]
    z = 1.03 + 0.02 * math.sin(2 * math.pi * T / 16)  # slow breathing push
    ox = oy = 0.0
    typ = b["visual"]["type"]
    if typ in ("warning", "stat", "chapter") or (typ == "title" and b["k"] == 0):
        z += 0.06 * bump(t - 0.25)
    if b.get("_pop_t") is not None:
        z += 0.045 * bump(T - b["_pop_t"])
    if typ == "warning" and 0.25 < t < 0.9:
        k = 1 - (t - 0.25) / 0.65
        ox, oy = 12 * k * math.sin(t * 60), 6 * k * math.cos(t * 47)
    return z, ox, oy


def apply_camera(img, z, ox, oy):
    w, h = W / z, H / z
    x0 = min(max(0.0, (W - w) / 2 + ox), W - w)
    y0 = min(max(0.0, (H - h) / 2 + oy), H - h)
    return img.resize((W, H), Image.BILINEAR, box=(x0, y0, x0 + w, y0 + h))


# ======================================================================= sound effects (made in code)
def _env(n, tau):
    return np.exp(-np.arange(n) / (tau * SR))


def make_sfx():
    rng = np.random.default_rng(7)
    bank = {}
    n = int(0.09 * SR)
    f = np.linspace(950, 260, n)
    bank["pop"] = np.sin(2 * np.pi * np.cumsum(f) / SR) * _env(n, 0.025) * 0.45
    n = int(0.03 * SR)
    bank["tick"] = np.diff(np.concatenate([[0], rng.standard_normal(n)])) * _env(n, 0.006) * 0.12
    n = int(0.9 * SR)
    t = np.arange(n) / SR
    bank["ding"] = ((np.sin(2 * np.pi * 1318.5 * t) + 0.5 * np.sin(2 * np.pi * 1975.5 * t)
                     + 0.25 * np.sin(2 * np.pi * 2637 * t)) * _env(n, 0.22) * 0.2 * np.minimum(1, t / 0.004))

    def whoosh(length, gain):
        n = int(length * SR)
        noise = rng.standard_normal(n)
        a = 0.02 + 0.3 * np.sin(np.pi * np.arange(n) / n) ** 2
        y = np.empty(n)
        acc = 0.0
        for i in range(n):
            acc += a[i] * (noise[i] - acc)
            y[i] = acc
        y *= np.sin(np.pi * np.arange(n) / n) ** 1.5
        return y / (np.abs(y).max() + 1e-9) * gain

    bank["whoosh"] = whoosh(0.38, 0.22)
    bank["swoosh"] = whoosh(0.6, 0.32)
    parts = []
    for fr in (880, 660, 880, 660):
        n = int(0.11 * SR)
        t = np.arange(n) / SR
        parts += [np.sign(np.sin(2 * np.pi * fr * t)) * 0.5 * np.sin(np.pi * np.arange(n) / n) ** 0.3,
                  np.zeros(int(0.03 * SR))]
    bank["alarm"] = np.concatenate(parts) * 0.09
    n = int(0.35 * SR)
    t = np.arange(n) / SR
    burst = (np.sin(2 * np.pi * 440 * t) + np.sin(2 * np.pi * 480 * t)) * (0.6 + 0.4 * np.sin(2 * np.pi * 20 * t))
    burst *= np.minimum(1, np.minimum(t, t[::-1]) / 0.01)
    bank["ring"] = np.concatenate([burst, np.zeros(int(0.12 * SR)), burst]) * 0.06
    n = int(0.8 * SR)
    t = np.arange(n) / SR
    bank["riser"] = np.sin(2 * np.pi * np.cumsum(np.linspace(220, 880, n)) / SR) * (t / t[-1]) ** 2 * 0.08
    return {k: v.astype(np.float32) for k, v in bank.items()}


# ======================================================================= prepare everything
print("Preparing scenes ...")
for k, s in enumerate(scenes):
    prepare_captions(s)
    s["lay_big"] = heading_layout(s, True, k == 0)
    s["lay_small"] = heading_layout(s, False, k == 0)

prev_lay = None
for b in BEATS:
    s = b["scene"]
    big = b["visual"]["type"] in ("title", "chapter")
    b["lay"] = s["lay_big"] if big else s["lay_small"]
    if b["k"] == 0 or b["lay"] is not prev_lay:
        b["head_t0"] = b["start"]
    else:
        b["head_t0"] = BEATS[b["idx"] - 1]["head_t0"]
    prev_lay = b["lay"]
    b["area"] = (120, b["lay"]["bottom"] + 40, W - 120, H - 190)
    VISUALS[b["visual"]["type"]][0](b)
    prep_sticker(b)
    if b["k"] > 0:
        sfx(b, 0.0, "whoosh", 0.7)
    elif b["idx"] > 0:
        sfx(b, 0.0, "swoosh", 1.0)
EVENTS.append((SCENES_END + 0.35, "ding", 1.0))

OUTRO_BIG = text_sprite("Video pasand aayi?", 76, WHITE)
OUTRO_SMALL = text_sprite("Har Sunday nayi tech video", 40, MUTED, shadow=False)


def draw_outro(canvas, d, T):
    t = T - SCENES_END
    p = ease(t / 0.5)
    comp(canvas, faded(OUTRO_BIG, p), (W - OUTRO_BIG.width) / 2, 316 + 30 * (1 - p))
    q = ease_back((t - 0.3) / 0.5)
    if q > 0:
        sc = max(0.05, q) * (1 + 0.03 * math.sin(t * 6) * (t > 1))
        w2, h2 = 260 * sc, 52 * sc
        d.rounded_rectangle([W / 2 - w2, 520 - h2, W / 2 + w2, 520 + h2], radius=int(h2), fill=RED)
        d.text((W / 2, 520), "SUBSCRIBE", font=font(max(10, int(46 * sc))), fill=WHITE, anchor="mm")
    r = ease((t - 0.6) / 0.5)
    comp(canvas, faded(OUTRO_SMALL, r), (W - OUTRO_SMALL.width) / 2, 626)
    if USE_MASCOT:
        m = mascot_sprite(260, "happy", 0.0, T, wave=True)
        comp_c(canvas, faded(m, ease(t / 0.5)), 330, 640 + 6 * math.sin(T * 2.4))


def draw_wipe(d, k, t):
    if k == 0 or t >= WIPE:
        return
    p = t / WIPE
    col = ACCENT if k % 2 else ACCENT2
    edge = 260
    if k % 4 in (1, 2):
        if p < 0.5:
            x = (W + edge) * ease(p / 0.5)
            d.polygon([(0, 0), (x, 0), (x - edge, H), (0, H)], fill=col)
        else:
            x = (W + edge) * ease((p - 0.5) / 0.5)
            d.polygon([(x, 0), (W + edge, 0), (W, H), (x - edge, H)], fill=col)
    else:
        if p < 0.5:
            x = W - (W + edge) * ease(p / 0.5)
            d.polygon([(x + edge, 0), (W, 0), (W, H), (x, H)], fill=col)
        else:
            x = W - (W + edge) * ease((p - 0.5) / 0.5)
            d.polygon([(-edge, 0), (x + edge, 0), (x, H), (-edge, H)], fill=col)


BEAT_SLIDE = 0.35


def draw_beat(layer, b, t):
    VISUALS[b["visual"]["type"]][1](layer, ImageDraw.Draw(layer), b, t)


def render(T, canvas, bi):
    d = draw_background(canvas, T)
    if T >= SCENES_END:
        draw_outro(canvas, d, T)
        b = None
    else:
        b = BEATS[bi]
        t = T - b["start"]
        prev = BEATS[bi - 1] if bi > 0 else None
        if b["k"] > 0 and t < BEAT_SLIDE:  # slide the old visual out, the new one in
            p = ease(t / BEAT_SLIDE)
            old = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            draw_beat(old, prev, T - prev["start"])
            new = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            draw_beat(new, b, t)
            comp(canvas, faded(old, 1 - p), -260 * p, 0)
            comp(canvas, faded(new, p), 260 * (1 - p), 0)
        else:
            draw_beat(canvas, b, t)
        draw_heading(canvas, ImageDraw.Draw(canvas), b["lay"], T - b["head_t0"])
    if b is not None:
        z, ox, oy = camera(T, b)
        canvas = apply_camera(canvas, z, ox, oy)
    d = ImageDraw.Draw(canvas)
    if b is not None:
        if USE_MASCOT:
            draw_corner_mascot(canvas, T, b, BEATS[bi - 1] if bi > 0 else None)
        draw_sticker(canvas, b, T)
        draw_captions(canvas, d, b["scene"], T)
        if b["k"] == 0:
            draw_wipe(d, scenes.index(b["scene"]), T - b["start"])
    draw_logo(d)
    d.rectangle([0, H - 8, W, H], fill=mix(TH["bot"], MUTED, 0.2))
    d.rectangle([0, H - 8, int(W * T / TOTAL), H], fill=ACCENT)
    return canvas


# ======================================================================= final audio: voice + music + effects
print("Mixing audio ...")
audio = VOICE.copy()
music = next((p for p in ["music.mp3", "music.wav", "music.m4a"] if os.path.exists(p)), None)
if music:
    m = decode(["-stream_loop", "-1", "-i", music, "-t", f"{TOTAL + 1:.2f}"])
    m = np.pad(m, (0, max(0, N_SAMPLES - len(m))))[:N_SAMPLES]
    fade = np.ones(N_SAMPLES, np.float32)
    fs = int((TOTAL - 1.5) * SR)
    fade[fs:] = np.linspace(1, 0, N_SAMPLES - fs)
    audio += m * MUSIC_VOLUME * fade
if USE_SFX:
    bank = make_sfx()
    for when, kind, vol in EVENTS:
        clip = bank.get(kind)
        i = int(when * SR)
        if clip is None or i >= N_SAMPLES:
            continue
        j = min(N_SAMPLES, i + len(clip))
        audio[i:j] += clip[:j - i] * vol
audio = np.clip(audio, -0.98, 0.98).astype(np.float32)
subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "f32le", "-ar", str(SR), "-ac", "1", "-i", "-",
                "-c:a", "pcm_s16le", "output/voice_mix.wav"], input=audio.tobytes(), check=True)


# ======================================================================= subtitles
def srt_time(t):
    ms = int(round(t * 1000))
    return f"{ms // 3600000:02}:{ms // 60000 % 60:02}:{ms // 1000 % 60:02},{ms % 1000:03}"


with open(OUT.replace(".mp4", ".srt"), "w", encoding="utf-8") as f:
    n_cap = 1
    for s in scenes:
        for cap in s["captions"]:
            f.write(f"{n_cap}\n{srt_time(cap['times'][0])} --> {srt_time(cap['end'])}\n"
                    f"{' '.join(cap['words'])}\n\n")
            n_cap += 1

# ======================================================================= encode
cmd = ["ffmpeg", "-y", "-loglevel", "error",
       "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
       "-i", "output/voice_mix.wav",
       "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
       "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", OUT]
proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
frames = int(round(TOTAL * FPS))
canvas = Image.new("RGBA", (W, H))
started = time.time()
print(f"Rendering {frames} frames ...")
bi = 0
for fno in range(frames):
    T = fno / FPS
    while bi + 1 < len(BEATS) and T >= BEATS[bi + 1]["start"]:
        bi += 1
    frame = render(T, canvas, bi)
    proc.stdin.write(frame.convert("RGB").tobytes())
    if fno % (FPS * 10) == 0 and fno:
        done = fno / frames
        eta = (time.time() - started) / done * (1 - done)
        print(f"  {done * 100:5.1f}%   about {eta / 60:.1f} min left")
proc.stdin.close()
if proc.wait() != 0:
    raise SystemExit("FFmpeg failed while encoding.")
print(f"Done: {OUT} and {OUT.replace('.mp4', '.srt')}")