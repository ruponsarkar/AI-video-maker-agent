"""
YouTube kit for a rhyme: youtube/details.json (edit it), thumbnail_a.jpg, thumbnail_b.jpg, description.txt, upload.md.
Run again after editing details.json; --redo makes details.json again.
"""
import json
import os
import sys

from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from critters import Critter  # noqa: E402
from stage import Stage  # noqa: E402
from video import WORD_COLOURS, font  # noqa: E402

TW, TH = 1280, 720


def make_details(script, settings):
    title = script["title"]
    playlist = settings.get("playlist", "Hindi Rhymes")
    kinds = list(dict.fromkeys(c for s in script["scenes"] for c in s["cast"]))
    names = [Critter(k).name for k in kinds][:4]
    titles = [f"{title} | Hindi Rhymes for Kids | Bachchon Ke Gaane"[:100],
              f"{title} Song | Hindi Nursery Rhyme | Bal Geet"[:100]]
    tags = [title, f"{title} song", f"{title} rhyme", "hindi rhymes", "hindi rhymes for kids", "nursery rhymes hindi",
            "bal geet", "bachchon ke gaane", "kids songs hindi", "hindi poem for kids", "balgeet",
            *(f"{n} song" for n in names), *(f"{n} rhyme" for n in names)]
    first = script["scenes"][0]["beats"][0].get("say", "")
    return {"titles": titles, "title": titles[0],
            "hook": f"{first.rstrip('.!?, ')}... Aao saath mein gaayein!",
            "tags": list(dict.fromkeys(tags)), "hashtags": ["#HindiRhymes", "#KidsSongs", "#BalGeet"],
            "category": "education", "playlist": playlist,
            "thumbnails": [{"layout": "hero", "text": title.upper()}, {"layout": "group", "text": title.upper()}]}


def own_picture(folder, spec):
    """Your picture for this thumbnail: spec 'picture' (a file in images/), else images/thumb.*, else the title
    picture p01 (thumbnail a) or the end picture (thumbnail b)."""
    import pictures
    names = [spec["picture"]] if spec.get("picture") else []
    names += ["thumb", "p01"] if spec.get("layout") != "group" else ["thumb_b", "thumb"]
    if spec.get("layout") == "group":
        path = os.path.join(folder, "pictures.json")
        if os.path.exists(path):
            names.append(json.load(open(path, encoding="utf-8"))["pictures"][-1]["id"])
        names.append("p01")
    for n in names:
        direct = os.path.join(folder, "images", n)
        if os.path.exists(direct) and not n.lower().endswith((".mp4", ".webm", ".mov")):
            return direct
        found = pictures.find_file(folder, os.path.splitext(n)[0])
        if found and not found.lower().endswith((".mp4", ".webm", ".mov")):
            return found
    return None


def thumbnail(spec, script, path, folder=None):
    scene = script["scenes"][0]
    stage = Stage(scene["place"], 0)
    img = stage.frame(2.0).resize((TW, TH)).convert("RGBA")
    kinds = list(dict.fromkeys(c for s in script["scenes"] for c in s["cast"]))
    d = ImageDraw.Draw(img)
    mine = own_picture(folder, spec) if folder else None
    if mine:
        from motion import compose_still, cover
        slot = None
        plan = os.path.join(folder, "pictures.json")   # not `path`: that is where the thumbnail is saved
        if os.path.exists(plan):
            pid = os.path.splitext(os.path.basename(mine))[0]
            slot = next((s for s in json.load(open(plan, encoding="utf-8"))["pictures"] if s["id"] == pid), None)
        img = compose_still(folder, slot, (TW, TH)) if slot else None   # the characters stand in the scene
        if img is None:
            img = cover(Image.open(mine).convert("RGB"), TW, TH).convert("RGBA")
        text_y, align = 30, "center"
    elif spec.get("layout") == "group":
        for k, kind in enumerate(kinds[:3]):
            spr = Critter(kind).image(0.7 if k == 0 else 0, False, 0.2)
            s = 380 / spr.height * (1.2 if k == 0 else 0.95)
            spr = spr.resize((int(spr.width * s), int(spr.height * s)), Image.LANCZOS)
            x = TW * (0.5, 0.2, 0.8)[k] - spr.width / 2
            y = TH * 0.3 if Critter(kind).floats else TH - spr.height - 10
            img.alpha_composite(spr, (int(x), int(y)))
        text_y, align = 30, "center"
    else:
        glow = Image.new("RGBA", (TW, TH), (0, 0, 0, 0))
        ImageDraw.Draw(glow).ellipse([TW * 0.5, 40, TW * 1.05, TH + 60], fill=(255, 255, 200, 170))
        img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(50)))
        spr = Critter(kinds[0]).image(0.7, False, 0.2)
        s = 620 / spr.height
        spr = spr.resize((int(spr.width * s), int(spr.height * s)), Image.LANCZOS)
        img.alpha_composite(spr, (int(TW * 0.74 - spr.width / 2), int(TH - spr.height + 20)))
        text_y, align = 60, "left"
    d = ImageDraw.Draw(img)
    rows, cur = [], ""
    for w in spec.get("text", "").split():
        if cur and len(cur) + len(w) > 12:
            rows.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    rows.append(cur)
    y = text_y
    for r in rows[:3]:
        size = 120
        f = font(size)
        limit = TW - 100 if align == "center" else TW * 0.55
        while f.getlength(r) > limit and size > 56:
            size -= 6
            f = font(size)
        x = (TW - f.getlength(r)) / 2 if align == "center" else 50
        for k, ch in enumerate(r):
            d.text((x, y), ch, font=f, fill=WORD_COLOURS[k % len(WORD_COLOURS)], stroke_width=9, stroke_fill=(255, 255, 255))
            x += f.getlength(ch)
        y += size + 6
    img.convert("RGB").save(path, "JPEG", quality=90)


def build(folder, settings, redo=False):
    script = json.load(open(os.path.join(folder, "script.json"), encoding="utf-8"))
    out = os.path.join(folder, "youtube")
    os.makedirs(out, exist_ok=True)
    details_path = os.path.join(out, "details.json")
    if redo and os.path.exists(details_path):
        os.replace(details_path, os.path.join(out, "details.old.json"))
    if not os.path.exists(details_path):
        json.dump(make_details(script, settings), open(details_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    info = json.load(open(details_path, encoding="utf-8"))
    for k, spec in enumerate(info.get("thumbnails", [])[:3]):
        thumbnail(spec, script, os.path.join(out, f"thumbnail_{'abc'[k]}.jpg"), folder)
    lyrics, last = [], None
    for s in script["scenes"]:
        block = "\n".join(b.get("say", "") for b in s["beats"])
        if s.get("kind") == "chorus" and block == last:
            lyrics.append("(Chorus)")
            continue
        lyrics.append(block)
        if s.get("kind") == "chorus":
            last = block
    own_voice = os.path.exists(os.path.join(folder, "audio", "vocals.wav"))
    ai_song = not own_voice and os.path.exists(os.path.join(folder, "audio", "song.wav"))
    if own_voice:
        made = "Aawaaz: hamari apni. Pictures AI tools ki madad se banayi gayi hain."
    elif ai_song:
        made = "Gaana (aawaaz aur sangeet) aur pictures AI tools ki madad se banaye gaye hain."
    else:
        made = "Aawaaz aur pictures AI tools ki madad se banayi gayi hain."
    clip_dir = os.path.join(folder, "images", "clips")
    if os.path.isdir(clip_dir) and any(f.endswith(".mp4") for f in os.listdir(clip_dir)):
        made += " Animation: WanGP (Wan 2.2) ki madad se."   # WanGP's licence asks for this credit
    handle = settings.get("channel") or ""
    name = settings.get("channel_name") or ""
    subscribe = (f"{name or 'Channel'} ko subscribe karein: https://www.youtube.com/{handle}?sub_confirmation=1"
                 if handle.startswith("@") else "")
    parts = [info.get("hook", ""), f"{script['title']} - Lyrics:\n\n" + "\n\n".join(lyrics),
             "Ye ek naya, original bal geet hai: bol (lyrics) hamare apne hain." if settings.get("original", True) else "",
             made + " Har video insaan dwara dekha aur jaancha gaya hai.",
             subscribe,
             " ".join(info.get("hashtags", []))]
    description = "\n\n".join(p for p in parts if p)
    open(os.path.join(out, "description.txt"), "w", encoding="utf-8").write(description + "\n")
    problems = []
    if not os.path.exists(os.path.join(folder, "output", "rhyme.mp4")):
        problems.append("output/rhyme.mp4 is missing: render first.")
    review = os.path.join(folder, "review.md")
    if os.path.exists(review) and "- [ ]" in open(review, encoding="utf-8").read():
        problems.append("review.md still has unticked items.")
    lines = [f"# Upload: {script['title']}", ""]
    if problems:
        lines += ["## Fix first", *[f"- {p}" for p in problems], ""]
    lines += ["## Titles", *[f"- {t}" for t in info.get("titles", [])], "", "## Description", "```", description, "```", "",
              "## Tags", ", ".join(info.get("tags", [])), "", "## Settings",
              "- Made for kids: Yes (required for nursery rhymes; comments and the bell are turned off by YouTube)",
              f"- Altered or synthetic content: {'No (your own voice)' if own_voice else 'Yes (AI voice)'}",
              "- Category: Education", "- Language: Hindi", f"- Playlist: {info.get('playlist', 'Hindi Rhymes')}", "",
              "## Before you publish", "- [ ] Watched it all with sound", "- [ ] Every word right for small children",
              "- [ ] The words are new (not copied from a film song or a modern published rhyme)",
              "- [ ] Thumbnail readable at phone size"]
    open(os.path.join(out, "upload.md"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print(f"  kit: {out} ({len(info.get('thumbnails', []))} thumbnails)" + "".join(f"\n  fix first: {p}" for p in problems))
    return problems
