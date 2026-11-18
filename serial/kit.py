"""
YouTube kit for a serial episode: youtube/details.json (edit it), thumbnail_a.jpg and thumbnail_b.jpg,
description.txt and upload.md. Run again after editing details.json; --redo starts details.json again.
"""
import json
import os
import re
import sys

from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)
from cartoon import Character, colour  # noqa: E402
from render import font  # noqa: E402
from scenery import Scenery  # noqa: E402

TW, TH = 1280, 720


def story_hook(script, bible, series):
    """Two lines of Roman Hinglish that make someone want to watch, from the episode itself."""
    try:
        from auto_video import llm
        lines = "\n".join(f"{b['speaker']}: {b.get('say') or ''}" for s in script["scenes"] if s.get("kind") == "story"
                          for b in s["beats"])[:3500]
        text = llm("Write a YouTube description opening for this cartoon serial episode: 2 short lines in Roman Hinglish "
                   "(Hindi in English letters), exciting but true to the episode, ending with a question. No hashtags, "
                   "no emojis, nothing that isn't in the episode.",
                   f"Series: {series['title']}\nEpisode {script['n']}: {script['title']}\n\n{lines}", as_json=False,
                   ctx=8192, max_tokens=200, temperature=0.6)
        text = " ".join(x.strip() for x in text.splitlines() if x.strip())[:400]
        if re.search(r"[ऀ-ॿ]", text):
            raise RuntimeError("Devanagari")
        return text
    except Exception:
        return f"{series['title']} ka Episode {script['n']}: {script['title']}. Aage kya hoga? Poori kahani dekhiye."


def make_details(folder, script, bible, series):
    n, title = script["n"], script["title"]
    show = series.get("title_screen") or series["title"]
    hi = series.get("title_hi") or ""
    main = [c for c, _ in sorted(count_lines(script).items(), key=lambda kv: -kv[1])][:4]
    names = [bible["characters"][c]["name"] for c in main if c in bible["characters"]]
    titles = [f"{show} Episode {n}: {title} | {hi or show} Hindi Kahani".strip()[:100],
              f"{title}! | {show} Ep {n} | Hindi Cartoon Story"[:100]]
    tags = [show, f"{show} episode {n}", f"{show} in hindi", f"{show} cartoon", "hindi kahani", "hindi cartoon",
            "animated story hindi", "kahaniyan", *names, *(f"{x} story" for x in names[:2])]
    words = [w for w in re.findall(r"[A-Za-z]+", title) if len(w) > 2][:3]
    return {"titles": titles, "title": titles[0], "hook": story_hook(script, bible, series),
            "tags": list(dict.fromkeys(tags)), "hashtags": [f"#{re.sub(r'[^A-Za-z0-9]', '', show)}", "#HindiKahani",
                                                            "#Cartoon"],
            "pinned_comment": f"Episode {n} mein aapko sabse achha pal kaun sa laga? Agle episode ke liye "
                              "Subscribe karke bell dabaiye!",
            "category": "story",
            "thumbnails": [{"chars": main[:2], "text": " ".join(words).upper() or title.upper(), "glow": "gold"},
                           {"chars": main[1:3] or main[:1], "text": f"EPISODE {n}", "glow": "red"}]}


def count_lines(script):
    out = {}
    for s in script["scenes"]:
        for b in s["beats"]:
            if b.get("speaker") not in (None, "narrator"):
                out[b["speaker"]] = out.get(b["speaker"], 0) + len(str(b.get("say_hi", "")).split())
    return out


def strongest_emotion(script, cid):
    for s in script["scenes"]:
        for b in s["beats"]:
            if b.get("speaker") == cid and b.get("emotion") in ("angry", "surprised", "fear", "sad"):
                return b["emotion"]
    return "happy"


def thumbnail(spec, script, bible, series, path):
    story = [s for s in script["scenes"] if s.get("kind") == "story"] or script["scenes"]
    scene = story[min(len(story) - 1, 1)]
    place = bible["places"].get(scene["place"], {"type": "forest"})
    bg = Scenery(place.get("type", "forest"), scene.get("time", "day"), scene.get("weather", "clear"), scene["place"]).frame(1.0)
    img = bg.resize((TW, TH)).filter(ImageFilter.GaussianBlur(3)).convert("RGBA")
    img.alpha_composite(Image.new("RGBA", (TW, TH), (10, 6, 20, 90)))
    glow = colour(spec.get("glow", "gold"))
    halo = Image.new("RGBA", (TW, TH), (0, 0, 0, 0))
    ImageDraw.Draw(halo).ellipse([TW * 0.42, -80, TW * 1.15, TH + 120], fill=glow + (120,))
    img.alpha_composite(halo.filter(ImageFilter.GaussianBlur(60)))
    chars = [c for c in spec.get("chars", []) if c in bible["characters"]][:2]
    for k, cid in enumerate(chars):
        c = Character({**bible["characters"][cid], "id": cid})
        emo = strongest_emotion(script, cid)
        spr = c.image(emo, 2 if emo in ("angry", "surprised") else 0, False,
                      "attack" if emo == "angry" and c.spec.get("prop") not in (None, "none") else "raise" if emo == "surprised" else "idle",
                      0, -1 if k == 0 else 1)
        s = (1.05 if k == 0 else 0.85) * c.height
        spr = spr.resize((int(spr.width * s), int(spr.height * s)), Image.LANCZOS)
        x = TW * (0.78 if k == 0 else 0.55) - spr.width / 2
        img.alpha_composite(spr, (int(x), int(TH * 1.12 - spr.height * 0.88)))
    d = ImageDraw.Draw(img)
    text = spec.get("text", "")
    rows, cur = [], ""
    for w in text.split():
        if cur and len(cur) + len(w) > 12:
            rows.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    rows.append(cur)
    y = 90
    for k, r in enumerate(rows[:3]):
        size = 132
        f = font(size)
        while f.getlength(r) > 640 and size > 60:
            size -= 6
            f = font(size)
        d.text((44, y), r, font=f, fill=(255, 214, 60) if k == 0 else (255, 255, 255), stroke_width=10, stroke_fill=(20, 8, 6))
        y += size + 16
    show = series.get("title_screen") or series["title"]
    bf = font(46, fancy=True)
    w = bf.getlength(show) + 60
    d.rounded_rectangle([40, TH - 120, 40 + w, TH - 46], radius=30, fill=(232, 178, 40))
    d.text((70, TH - 116), show, font=bf, fill=(40, 20, 10))
    ef = font(54)
    badge = f"EP {script['n']}"
    bw = ef.getlength(badge) + 50
    d.rounded_rectangle([TW - bw - 40, 34, TW - 40, 112], radius=20, fill=(220, 30, 40))
    d.text((TW - bw - 15, 44), badge, font=ef, fill=(255, 255, 255))
    img.convert("RGB").save(path, "JPEG", quality=90)


def build(folder, redo=False):
    sdir = os.path.dirname(os.path.dirname(os.path.abspath(folder)))
    script = json.load(open(os.path.join(folder, "script.json"), encoding="utf-8"))
    bible = json.load(open(os.path.join(sdir, "bible.json"), encoding="utf-8"))
    series = json.load(open(os.path.join(sdir, "series.json"), encoding="utf-8"))
    out = os.path.join(folder, "youtube")
    os.makedirs(out, exist_ok=True)
    details_path = os.path.join(out, "details.json")
    if redo and os.path.exists(details_path):
        os.replace(details_path, os.path.join(out, "details.old.json"))
    if not os.path.exists(details_path):
        json.dump(make_details(folder, script, bible, series), open(details_path, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)
    info = json.load(open(details_path, encoding="utf-8"))
    for k, spec in enumerate(info.get("thumbnails", [])[:3]):
        thumbnail(spec, script, bible, series, os.path.join(out, f"thumbnail_{'abc'[k]}.jpg"))
    show = series.get("title_screen") or series["title"]
    source = series.get("source") or f"the traditional story of {series['title']}"
    parts = [info.get("hook", ""),
             f"{show} - Episode {script['n']}: {script['title']}" + (f"\nAgla episode: {script['next_title']}" if script.get("next_title") else ""),
             f"Ye kahani {source} par aadharit hai, bachchon aur parivaar ke liye saral roop mein.",
             "Animation, aawaaz aur sangeet AI tools ki madad se banaye gaye hain; har episode insaan dwara jaancha gaya hai.",
             " ".join(info.get("hashtags", []))]
    description = "\n\n".join(p for p in parts if p)
    open(os.path.join(out, "description.txt"), "w", encoding="utf-8").write(description + "\n")
    video = os.path.join(folder, "output", "episode.mp4")
    problems = []
    if not os.path.exists(video):
        problems.append("output/episode.mp4 is missing: render first.")
    if os.path.exists(os.path.join(folder, "review.md")) and "NOT fixed" in open(os.path.join(folder, "review.md"), encoding="utf-8").read():
        problems.append("review.md has continuity notes that weren't fixed.")
    lines = [f"# Upload: {show} episode {script['n']}", ""]
    if problems:
        lines += ["## Fix first", *[f"- {p}" for p in problems], ""]
    lines += ["## Titles", *[f"- {t}" for t in info.get("titles", [])], "", "## Description", "```", description, "```", "",
              "## Tags", ", ".join(info.get("tags", [])), "", "## Settings",
              f"- Made for kids: {'Yes' if series.get('made_for_kids') else 'No'} (set in series.json; it's a legal choice)",
              "- Altered or synthetic content: Yes", "- Category: Film & Animation", "- Language: Hindi",
              f"- Playlist: {show}", "", "## Before you publish",
              "- [ ] Watched it all with sound", "- [ ] Story matches the traditional telling",
              "- [ ] Voices clear (audio/voice_check.md)", "- [ ] Thumbnail readable at phone size"]
    open(os.path.join(out, "upload.md"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print(f"  kit: {out} ({len(info.get('thumbnails', []))} thumbnails)" + ("".join(f"\n  fix first: {p}" for p in problems)))
    return problems


if __name__ == "__main__":
    for f in [a for a in sys.argv[1:] if not a.startswith("--")]:
        build(f, redo="--redo" in sys.argv)
