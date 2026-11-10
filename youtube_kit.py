"""
Snack Code - everything YouTube Studio asks for, in one folder.

Run from inside a video's folder, after the final render:
    python ../../youtube_kit.py          # makes youtube/ (keeps your edits in details.json)
    python ../../youtube_kit.py --redo   # new details.json from metadata.md (old one -> details.old.json)

Reads:   youtube/details.json (your edits; created from metadata.md the first time),
         scripts/script.json, audio/scene_XX.json, output/animated.mp4
Writes:  youtube/thumbnail_a.jpg ... (1280x720), youtube/description.txt, youtube/upload.md

Chapter times come from the voice timing, so run this again after every re-render.
Nothing is uploaded: this only prepares the files.
"""
import json
import math
import os
import re
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 1280, 720
OUT_DIR = "youtube"
DETAILS = os.path.join(OUT_DIR, "details.json")
SCENE_GAP = 0.35   # must match GAP in animate.py
MAX_THUMB_BYTES = 2 * 1024 * 1024  # YouTube's limit
SCAM_WORDS = re.compile(r"scam|fraud|thag|nakli|phishing|otp|hack", re.I)
DEVANAGARI = re.compile(r"[\u0900-\u097F]")   # the thumbnail font can't draw it; titles stay Roman
ICON_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "icons")
TOPIC_ICONS = [(r"bank|rbi|loan|deposit|byaj|interest", "bank"), (r"paisa|money|rupee|rs\b|crore|salary", "money"),
               (r"upi|payment|card", "card"), (r"scam|fraud|thag|hack", "hacker"), (r"otp|sms|call|phone|sim", "phone"),
               (r"internet|wifi|online", "wifi"), (r"\bai\b|robot|chatgpt|naukri|job", "ai"),
               (r"court|kanoon|law", "court"), (r"election|vote|chunav", "ballot"), (r"news|khabar", "news"),
               (r"password|lock|safe|suraksh", "lock")]

WHITE = (248, 250, 252)
RED = (239, 68, 68)
YELLOW = (250, 204, 21)
ORANGE = (249, 115, 22)
BG_TOP, BG_BOTTOM = (30, 12, 22), (6, 4, 10)
BODY, EDGE, SCREEN = (226, 232, 240), (100, 116, 139), (15, 23, 42)
COLOURS = {"white": WHITE, "red": RED, "yellow": YELLOW, "orange": ORANGE}

FONT_PATHS = ["/usr/share/fonts/truetype/ubuntu/Ubuntu[wdth,wght].ttf",
              "/usr/share/fonts/truetype/ubuntu/Ubuntu-B.ttf",
              "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]
FONT_PATH = next((p for p in FONT_PATHS if os.path.exists(p)), None)
if not FONT_PATH:
    raise SystemExit("No font found. Run: sudo apt install fonts-dejavu-core")


def font(size):
    f = ImageFont.truetype(FONT_PATH, int(size))
    try:  # the Ubuntu font holds all its weights in one file
        f.set_variation_by_name("Extra Bold")
    except (OSError, ValueError):
        pass
    return f


# ---------------------------------------------------------------- drawing
def background(glow):
    img = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(img)
    for y in range(H):
        f = y / H
        d.line([(0, y), (W, y)], fill=tuple(int(a + (b - a) * f) for a, b in zip(BG_TOP, BG_BOTTOM)))
    light = Image.new("L", (W, H), 0)
    ImageDraw.Draw(light).ellipse([W * 0.45, -120, W + 160, H + 120], fill=125)
    light = light.filter(ImageFilter.GaussianBlur(130))
    return Image.composite(Image.new("RGB", (W, H), glow), img, light)


def text_line(img, text, x, y, max_w, max_size, colour, stroke=9):
    """Draw one line as big as fits, with a thick outline so it reads on a small phone. Returns its bottom."""
    size = max_size
    while size > 30 and font(size).getlength(text) + stroke * 2 > max_w:
        size -= 2
    f = font(size)
    box = f.getbbox(text)
    top = y - box[1]
    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).text((x + 6, top + 8), text, font=f, fill=(0, 0, 0, 190),
                                stroke_width=stroke, stroke_fill=(0, 0, 0, 190))
    img.paste(shadow.filter(ImageFilter.GaussianBlur(7)), (0, 0), shadow.filter(ImageFilter.GaussianBlur(7)))
    ImageDraw.Draw(img).text((x, top), text, font=f, fill=colour, stroke_width=stroke, stroke_fill=(8, 6, 12))
    return y + box[3] - box[1]


def badge(img, text, x, y, fill=RED, colour=WHITE, size=62):
    d = ImageDraw.Draw(img)
    f = font(size)
    box = f.getbbox(text)
    w, h = box[2] - box[0], box[3] - box[1]
    d.rounded_rectangle([x, y, x + w + 56, y + h + 40], radius=18, fill=fill)
    d.text((x + 28 - box[0], y + 20 - box[1]), text, font=f, fill=colour)
    return y + h + 40


def byte(size, eye=(244, 63, 94)):
    """Byte the mascot with a shocked face (same drawing as animate.py), hands up."""
    S = size * 2
    img = Image.new("RGBA", (S, int(S * 1.12)), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    u = S / 100

    def B(x0, y0, x1, y1):
        return [x0 * u, y0 * u, x1 * u, y1 * u]

    lw = max(2, int(3 * u))
    d.line([(50 * u, 18 * u), (50 * u, 7 * u)], fill=EDGE, width=lw)
    d.ellipse(B(45.5, 1, 54.5, 10), fill=YELLOW)
    d.rounded_rectangle(B(30, 74, 70, 106), radius=10 * u, fill=BODY, outline=EDGE, width=lw // 2)
    d.ellipse(B(45, 84, 55, 94), fill=YELLOW)
    d.rounded_rectangle(B(6, 35, 13, 55), radius=3 * u, fill=EDGE)
    d.rounded_rectangle(B(87, 35, 94, 55), radius=3 * u, fill=EDGE)
    d.rounded_rectangle(B(12, 16, 88, 74), radius=18 * u, fill=BODY, outline=EDGE, width=lw // 2)
    d.rounded_rectangle(B(20, 24, 80, 66), radius=12 * u, fill=SCREEN)
    for cx in (37, 63):
        d.ellipse(B(cx - 8, 33, cx + 8, 49), fill=eye)
        d.ellipse(B(cx - 3, 37, cx + 2, 42), fill=WHITE)
    d.ellipse(B(44, 52, 56, 63), outline=eye, width=lw + 1)
    for x0, hx in ((32, 8), (68, 92)):
        d.line([(x0 * u, 84 * u), (hx * u, 68 * u)], fill=BODY, width=int(7 * u))
        d.ellipse(B(hx - 5, 63, hx + 5, 73), fill=BODY)
    return img.resize((size, int(size * 1.12)), Image.LANCZOS)


def paste(img, sprite, x, y):
    img.paste(sprite, (int(x), int(y)), sprite)


def wifi_off(size):
    """A Wi-Fi symbol struck through in red: says 'no internet' with no words."""
    S = size * 2
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx, cy = S / 2, S * 0.76
    for r in (0.62, 0.42, 0.22):
        R = S * r
        d.arc([cx - R, cy - R, cx + R, cy + R], 222, 318, fill=WHITE, width=int(S * 0.075))
    dot = S * 0.075
    d.ellipse([cx - dot, cy - dot, cx + dot, cy + dot], fill=WHITE)
    a, b = (S * 0.13, S * 0.14), (S * 0.87, S * 0.88)
    d.line([a, b], fill=(8, 6, 12), width=int(S * 0.13))
    d.line([a, b], fill=RED, width=int(S * 0.075))
    return img.resize((size, size), Image.LANCZOS)


def phone(height, label, status):
    """A phone showing a failed action, e.g. UPI + a red cross + 'FAILED'."""
    w = int(height * 0.54)
    S = 2
    img = Image.new("RGBA", (w * S, height * S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, w * S - 1, height * S - 1], radius=54 * S, fill=(30, 41, 59), outline=(148, 163, 184), width=5 * S)
    d.rounded_rectangle([14 * S, 14 * S, (w - 14) * S, (height - 14) * S], radius=42 * S, fill=SCREEN)
    cx, cross_y, r = w * S / 2, height * S * 0.47, w * S * 0.27
    f = font(int(w * 0.25) * S)
    d.text((cx, height * S * 0.19), label, font=f, fill=WHITE, anchor="mm")
    d.ellipse([cx - r, cross_y - r, cx + r, cross_y + r], fill=RED)
    k = r * 0.5
    for p, q in (((cx - k, cross_y - k), (cx + k, cross_y + k)), ((cx - k, cross_y + k), (cx + k, cross_y - k))):
        d.line([p, q], fill=WHITE, width=int(r * 0.26))
    f = font(int(w * 0.17) * S)
    d.text((cx, height * S * 0.77), status, font=f, fill=RED, anchor="mm")
    return img.resize((w, height), Image.LANCZOS)


def big_icon(name, size):
    path = os.path.join(ICON_DIR, f"{name}.png")
    if not os.path.exists(path):
        return None
    icon = Image.open(path).convert("RGBA")
    return icon.resize((size, size * icon.height // icon.width), Image.LANCZOS)


def make_thumbnail(spec, path):
    layout = spec.get("layout", "byte")
    glow = COLOURS.get(spec.get("glow"), RED)
    img = background(glow)
    icon = big_icon(spec.get("icon", "question"), 470) if layout == "icon" else None
    if layout == "wifi":
        paste(img, wifi_off(470), 790, 30)
    elif layout == "phone":
        paste(img, phone(640, spec.get("phone_label", ""), spec.get("phone_status", "")), 880, 40)
    elif icon:
        paste(img, icon, 770, 60)
        paste(img, byte(190), 1030, 470)   # small Byte, clear of the timestamp corner
    else:
        paste(img, byte(500), 760, 90)

    width = {"wifi": 730, "phone": 830}.get(layout, 760)
    y = spec.get("top", 48)
    for line in spec.get("lines", []):
        y = text_line(img, line["text"], 44, y, width, line.get("size", 170), COLOURS.get(line.get("colour"), WHITE)) + 34
    if spec.get("badge"):
        badge(img, spec["badge"], 48, y + 6, fill=COLOURS.get(spec.get("badge_fill"), RED),
              colour=(8, 6, 12) if spec.get("badge_fill") == "yellow" else WHITE)
    if layout == "wifi":  # small Byte reacting; kept clear of YouTube's timestamp at the bottom right
        paste(img, byte(205), 850, 480)
    img.save(path, "JPEG", quality=92, optimize=True)
    if os.path.getsize(path) > MAX_THUMB_BYTES:
        img.save(path, "JPEG", quality=80, optimize=True)


# ---------------------------------------------------------------- details
def section(text, name):
    m = re.search(rf"^## {name}\s*\n(.*?)(?=^## |\Z)", text, re.S | re.M)
    return m.group(1).strip() if m else ""


def roman_only(text):
    """Drop Devanagari words (e.g. a trailing 'जानिए') and tidy what's left."""
    text = " ".join(w for w in text.split() if not DEVANAGARI.search(w))
    return re.sub(r"\s+([?!.,])", r"\1", text).strip(" -|:")


def unique(items):
    seen, out = set(), []
    for item in items:
        key = re.sub(r"\W+", "", item.lower())
        if item and key not in seen:
            seen.add(key)
            out.append(item)
    return out


def short_lines(text, max_chars=14, max_lines=3):
    """'Paisa Bank Mein Kahan Rehta Hai?' -> ['PAISA BANK', 'MEIN KAHAN', 'REHTA HAI?']: big words read on a phone."""
    lines = []
    for word in text.upper().split():
        if lines and len(lines[-1]) + 1 + len(word) <= max_chars:
            lines[-1] += " " + word
        else:
            lines.append(word)
    return lines[:max_lines]


def topic_icon(text):
    low = text.lower()
    return next((icon for pattern, icon in TOPIC_ICONS if re.search(pattern, low)), "question")


def thumbnail_specs(texts, title):
    """Two different looks: A = Byte with white/yellow text, B = big 3D topic icon with yellow/white text."""
    texts = (texts + [title, title])[:2]
    a_lines, b_lines = short_lines(texts[0]), short_lines(texts[1])
    return [{"layout": "byte", "glow": "red",
             "lines": [{"text": t, "colour": "yellow" if i == len(a_lines) - 1 else "white"}
                       for i, t in enumerate(a_lines)]},
            {"layout": "icon", "icon": topic_icon(title + " " + texts[1]), "glow": "yellow",
             "lines": [{"text": t, "colour": "white" if i == len(b_lines) - 1 else "yellow"}
                       for i, t in enumerate(b_lines)]}]


def details_from_metadata(script):
    """First draft of details.json from metadata.md, for you to edit."""
    meta = open("metadata.md", encoding="utf-8").read() if os.path.exists("metadata.md") else ""
    titles = unique([roman_only(t) for t in re.findall(r"^- (.+)$", section(meta, "Title options"), re.M)]
                    + [roman_only(script.get("title", ""))])
    titles = [t for t in titles if 0 < len(t) <= 100][:2]
    words = unique([roman_only(w) for w in re.findall(r"'([^']+)'", section(meta, "Thumbnail text"))])
    words = [w for w in words if len(w.split()) >= 2]
    description = section(meta, "Description")
    title = titles[0] if titles else script.get("title", "")
    if not SCAM_WORDS.search(title):  # the helpline line belongs on scam videos only
        description = re.sub(r"\n*Cybercrime helpline:.*", "", description).strip()
    return {"title": title,
            "titles": titles,
            "description": description,
            "hashtags": ["#SnackCode"],
            "tags": [t.strip() for t in section(meta, "Tags").split(",") if t.strip()],
            "pinned_comment": "Aapko is video mein sabse hairan kis baat ne kiya? Comment mein batao.",
            "category": "news" if script.get("kind") == "news" else "tech",
            "chapter_names": {},
            "thumbnails": thumbnail_specs(words, title)}


def load_details(script, redo=False):
    os.makedirs(OUT_DIR, exist_ok=True)
    if redo and os.path.exists(DETAILS):
        os.replace(DETAILS, os.path.join(OUT_DIR, "details.old.json"))
        print(f"Old details saved as {OUT_DIR}/details.old.json")
    if not os.path.exists(DETAILS):
        json.dump(details_from_metadata(script), open(DETAILS, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print(f"Created {DETAILS}: check it, edit it, then run this again.")
    return json.load(open(DETAILS, encoding="utf-8"))


# ---------------------------------------------------------------- chapters
def stamp(seconds):
    s = int(seconds)
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60:02d}:{s % 60:02d}"


def video_length():
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                          "output/animated.mp4"], capture_output=True, text=True)
    return float(out.stdout.strip()) if out.returncode == 0 and out.stdout.strip() else None


def make_chapters(script, names, length):
    """One chapter per part card, plus the intro. Same timeline as animate.py."""
    chapters, cursor = [("Intro", 0.0)], 0.0
    for i, scene in enumerate(script["scenes"]):
        beats = scene.get("beats") or [{}]
        visual = beats[0].get("visual") or {}
        if visual.get("type") == "chapter":
            part = str(visual.get("part", ""))
            chapters.append((names.get(part) or scene.get("on_screen", f"Part {part}"), cursor))
        timing = f"audio/scene_{i:02d}.json"
        if not os.path.exists(timing):
            return [], f"{timing} is missing, so chapters were skipped."
        cursor += json.load(open(timing))["total"] + SCENE_GAP
    if len(chapters) < 3:
        return [], "This video has too few parts for YouTube chapters (minimum 3)."
    ends = [c[1] for c in chapters[1:]] + [length or cursor]
    if any(end - start < 10 for (_, start), end in zip(chapters, ends)):
        return [], "A chapter would be under 10 seconds, which YouTube rejects, so chapters were skipped."
    if length and abs(length - cursor) > 5:
        return [], (f"Voice timing ({cursor:.0f} s) doesn't match the video ({length:.0f} s). "
                    "Render again, then rerun this, to get chapters.")
    return chapters, ""


# ---------------------------------------------------------------- output
def main():
    if not os.path.exists("scripts/script.json"):
        raise SystemExit("Run this from inside a video's folder (projects/<video>).")
    script = json.load(open("scripts/script.json", encoding="utf-8"))
    info = load_details(script, redo="--redo" in sys.argv)
    titles = info.get("titles") or [info["title"]]
    length = video_length()
    video_ok = length is not None
    chapters, chapter_note = make_chapters(script, info.get("chapter_names", {}), length)

    parts = [info.get("hook", "").strip() or info["description"].split("\n\nSources:")[0].strip()]
    if chapters:
        parts.append("Chapters:\n" + "\n".join(f"{stamp(t)} {name}" for name, t in chapters))
    if "\n\nSources:" in info["description"]:
        parts.append("Sources:" + info["description"].split("\n\nSources:", 1)[1])
    if os.path.exists("images/photos/credits.json"):
        used = json.load(open("images/photos/credits.json", encoding="utf-8"))
        if used:
            parts.append("Photo credits (Wikimedia Commons):\n" + "\n".join(
                f"- {c['artist'][:60]}, {c['licence']}: {c['page']}" for c in used))
    if info.get("hashtags"):
        parts.append(" ".join(info["hashtags"]))
    description = "\n\n".join(parts)
    open(f"{OUT_DIR}/description.txt", "w", encoding="utf-8").write(description + "\n")

    names = []
    for k, spec in enumerate(info.get("thumbnails", [])):
        name = f"thumbnail_{'abc'[k]}.jpg"
        make_thumbnail(spec, f"{OUT_DIR}/{name}")
        names.append(name)

    tags = ", ".join(info.get("tags", []))
    problems = []
    for t in titles:
        if len(t) > 100:
            problems.append(f"Title is {len(t)} characters; the limit is 100: {t}")
    for spec in info.get("thumbnails", []):
        if any(DEVANAGARI.search(line["text"]) for line in spec.get("lines", [])):
            problems.append("A thumbnail line has Devanagari, which the thumbnail font can't draw: write it in Roman.")
    if len(description) > 5000:
        problems.append(f"Description is {len(description)} characters; the limit is 5000.")
    if len(tags) > 500:
        problems.append(f"Tags are {len(tags)} characters; the limit is 500.")
    if not video_ok:
        problems.append("output/animated.mp4 is missing: render the video first.")
    if not os.path.exists("output/animated.srt"):
        problems.append("output/animated.srt is missing: render the video first.")
    if chapter_note:
        problems.append(chapter_note)
    if os.path.exists("scripts/review.md"):
        problems.append("scripts/review.md lists script problems the automatic checks couldn't fix.")

    scam = bool(SCAM_WORDS.search(info["title"]))
    lines = [f"# Upload details: {info['title']}", ""]
    if problems:
        lines += ["## Fix first", *[f"- {p}" for p in problems], ""]
    lines += ["## Files",
              "- Video: `output/animated.mp4`" + (f" ({stamp(length)})" if length else ""),
              "- Subtitles: `output/animated.srt`",
              *[f"- Thumbnail option: `{OUT_DIR}/{n}`" for n in names], "",
              "## Title" if len(titles) == 1 else "## Titles (upload.py uses A; --title b for the other)",
              *[x for k, t in enumerate(titles) for x in (f"{'ABCDE'[k]}:", "```", t, "```")], "",
              f"## Description (also in `{OUT_DIR}/description.txt`)", "```", description, "```", "",
              "## Tags", "```", tags, "```", "",
              "## Pinned comment", "```", info.get("pinned_comment", ""), "```", "",
              "## Studio settings",
              "- Audience: No, it's not made for kids",
              "- Altered or synthetic content: Yes (AI-generated voice)",
              "- Video language: Hindi",
              "- Subtitles: upload the .srt as Hindi (Latin) if listed, otherwise Hindi",
              "- Category: " + ("News & Politics" if info.get("category") == "news" else "Science & Technology"),
              "- Thumbnail and title: upload A, or use Studio's Test & Compare (if offered) to try both",
              "- End screen: add a Subscribe element and a video over the last 5 to 9 seconds",
              "- Visibility: schedule it at the time shown under \"When your viewers are on YouTube\"", "",
              "## Before you publish",
              "- [ ] Watched the whole video with sound",
              "- [ ] Checked every fact against the source links",
              "- [ ] Looked at the thumbnail at phone size"]
    if scam:
        lines.append("- [ ] Video and description give helpline 1930 and cybercrime.gov.in")
    open(f"{OUT_DIR}/upload.md", "w", encoding="utf-8").write("\n".join(lines) + "\n")

    print(f"Done: {OUT_DIR}/upload.md, {OUT_DIR}/description.txt, " + ", ".join(names))
    for p in problems:
        print("  Fix first:", p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
