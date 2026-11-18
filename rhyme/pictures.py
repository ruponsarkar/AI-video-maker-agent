"""
Pictures for a rhyme, made by you with any image tool, animated by video.py.

    python rhyme.py pictures <slug>     # pictures.json + pictures.md: one prompt per picture
    then save each picture as images/p01.jpg, images/p02.png ... (an image-to-video clip images/p03.mp4 also works)

The same characters come back in every song: their looks are fixed in rhymes/cast.json (edit it once, before the
first song; changing it later makes old and new videos look different). A picture that's missing is drawn by code.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from critters import KINDS  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CAST_FILE = os.path.join(ROOT, "rhymes", "cast.json")
EXTS = (".mp4", ".webm", ".mov", ".jpg", ".jpeg", ".webp", ".png")   # .png last: the AI writes pNN.png, yours win
# Golu and Chinki in a few words: image and video models follow a short phrase far better than a long description;
# the cast art, the acting pictures (draw_ai.py) and the clips (clips.py) all use this SAME phrase
KID = {"boy": "a chubby little Indian boy with brown skin and short black hair, in a sky-blue t-shirt and orange shorts",
       "girl": "a little Indian girl with brown skin and two black pigtails with red ribbons, in a yellow frock"}
# actions a standing cut-out can't show: those pictures are drawn with the character doing it (draw_ai.py)
ACTIONS = ("sleep", "sit", "swing", "wash", "bath", "eat", "drink", "read", "ride", "swim", "climb", "lie", "hug",
           "cook", "paint", "brush", "kick", "throw", "fly a kite", "plant", "water", "carry")
# how each action is drawn (it goes FIRST in the image prompt: the model reads only ~77 words)
ACTION_PHRASES = {
    "sleep": "sleeping peacefully in a cosy bed under a soft blanket, eyes closed, head on a pillow",
    "lie": "lying in a cosy bed under a soft blanket, sleepy",
    "swing": "sitting on a wooden swing hanging from a tree, swinging happily",
    "wash": "washing hands with soap and water at a wash basin, bubbles",
    "bath": "taking a bath in a tub full of bubbles",
    "brush": "brushing teeth with a toothbrush in front of a mirror",
    "eat": "eating food from a plate at a table",
    "drink": "drinking milk from a glass",
    "sit": "sitting on the floor, smiling",
    "read": "reading a colourful picture book",
    "ride": "riding a small bicycle",
    "swim": "swimming in a pool",
    "climb": "climbing a tree",
    "hug": "hugging each other happily",
    "cook": "cooking with a small pot in a kitchen",
    "paint": "painting a picture with colours",
    "kick": "kicking a football",
    "throw": "throwing a ball",
    "fly a kite": "flying a colourful kite in the sky",
    "plant": "planting a small plant in the soil",
    "water": "watering plants with a watering can",
    "carry": "carrying a basket",
}
EFFECTS = ("rain", "bubbles", "sparkles", "petals", "stars", "snow", "none")

DEFAULT_CAST = {
    "style": ("3D animated feature film still for a children's song video, high quality CGI render, cute characters "
              "with big expressive eyes, soft global illumination, cinematic lighting, vibrant colours, shallow depth "
              "of field"),
    "rules": ("wide 16:9 picture, characters in the middle third, keep the bottom fifth of the picture simple "
              "(song words go there), no text, no letters, no logo, no watermark"),
    "characters": {
        "girl": {"name": "Chinki", "look": "a little Indian girl, brown skin, two black pigtails with red ribbons, big brown eyes, yellow frock with small white flowers, red sandals"},
        "boy": {"name": "Golu", "look": "a chubby little Indian boy, brown skin, short straight black hair, round face, big brown eyes, sky-blue t-shirt with a yellow star, orange shorts"},
        "cat": {"name": "Minku", "look": "a small fluffy white kitten with orange patches, big green eyes, pink nose, "
                "a red collar with a little gold bell"},
        "dog": {"name": "Bholu", "look": "a small brown puppy with floppy darker ears, big black eyes, a white patch "
                "on its chest, a blue collar"},
        "rabbit": {"name": "Gullu", "look": "a soft white rabbit with long pink-lined ears, big black eyes, a tiny "
                   "pink nose"},
        "elephant": {"name": "Gajju", "look": "a friendly baby elephant, soft grey, big flappy ears with pink inside, "
                     "short trunk, small round eyes"},
        "lion": {"name": "Sheru", "look": "a cute lion cub with a fluffy golden mane, big amber eyes, a big smile"},
        "monkey": {"name": "Chunnu", "look": "a playful little brown monkey with a beige face, big ears and a "
                   "curly tail"},
        "cow": {"name": "Gauri", "look": "a gentle white cow with brown patches, short curved horns, a small brass "
                "bell on a red cord"},
        "frog": {"name": "Tarru", "look": "a small round bright-green frog with big bulging eyes, a pale yellow "
                 "belly and a wide smile"},
        "duck": {"name": "Bunty", "look": "a fluffy yellow duckling with an orange beak and orange feet"},
        "fish": {"name": "Meenu", "look": "a little orange-and-white fish with big eyes and flowing fins"},
        "butterfly": {"name": "Titli", "look": "a butterfly with big round wings in orange, pink and purple with "
                      "white dots"},
        "sun": {"name": "Suraj", "look": "a smiling cartoon sun with soft golden rays and rosy cheeks"},
        "moon": {"name": "Chanda", "look": "a glowing golden yellow crescent moon with a sleepy smiling face, C-shaped curved body, soft glow"},
        "star": {"name": "Tara", "look": "a cute five-pointed star shaped character, glowing golden yellow, star-shaped body with a smiling face in the middle, tiny arms, not a person"},
        "peacock": {"name": "Mor", "look": "a cute blue peacock with a huge open fan tail of green and gold eye feathers behind it, small crest on its head"},
        "parrot": {"name": "Mithu", "look": "a bright green parrot with a red curved beak and a touch of blue on "
                   "its wings"},
        "train": {"name": "Chhuk-Chhuk", "look": "a cute toy steam engine, red engine with a chimney and big round wheels, a smiling face on the front, one yellow coach behind it"},
    },
    "places": {
        "garden": "a sunny flower garden with a little wooden fence, butterflies and a blue sky",
        "jungle": "a friendly green jungle with big leaves, hanging vines and soft sunbeams",
        "farm": "an Indian village farm with green fields, a mud hut with a tiled roof and a haystack",
        "pond": "a calm village pond with lily pads, pink lotus flowers and tall grass",
        "underwater": "a bright underwater world with coral, seaweed and sunbeams through the water",
        "sky": "a blue sky with fluffy white clouds and a rainbow",
        "night": "a calm night sky over a small Indian village, many twinkling stars, soft blue light",
        "beach": "a sunny beach with soft sand, gentle waves and seashells",
        "room": "a cosy colourful Indian home with cushions, toys and a window",
        "rail": "green hills with a railway track running through fields",
    },
}

# words in the lines -> a moving effect on top of the picture
EFFECT_WORDS = {"rain": ["बारिश", "बरसा", "बरसे", "बूँद", "बूंद", "बादल", "छाता", "सावन", "भीग"],
                "snow": ["बर्फ", "ठंड", "सर्दी"],
                "bubbles": ["मछली", "समुंदर", "सागर", "बुलबुल", "नहा", "साबुन"],
                "stars": ["तारे", "तारा", "चंदा", "चाँद", "रात", "सपने", "लोरी", "नींद"],
                "petals": ["फूल", "फूलों", "तितली", "बगिया", "बाग"]}
PLACE_EFFECT = {"underwater": "bubbles", "night": "stars", "garden": "petals"}


def load_cast():
    """rhymes/cast.json, made from the defaults the first time (then it's yours to edit)."""
    if not os.path.exists(CAST_FILE):
        os.makedirs(os.path.dirname(CAST_FILE), exist_ok=True)
        json.dump(DEFAULT_CAST, open(CAST_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    cast = json.load(open(CAST_FILE, encoding="utf-8"))
    for key, value in DEFAULT_CAST.items():   # new kinds or places added later
        if isinstance(value, dict):
            cast.setdefault(key, {})
            for k, v in value.items():
                cast[key].setdefault(k, v)
        else:
            cast.setdefault(key, value)
    return cast


def pick_effect(text, place):
    for name, words in EFFECT_WORDS.items():
        if any(w in text for w in words):
            return name
    return PLACE_EFFECT.get(place, "sparkles")


def slots(script):
    """Which lines each picture covers: a title picture, one picture per line (a new shot every few seconds, like an
    animated video), an end picture."""
    scenes = script["scenes"]
    first = scenes[0]["beats"][0].get("story") if scenes[0]["beats"] else None
    lead = scenes[0]["cast"][:1]
    if first:   # the title shows the song's main character (story.py)
        lead = [k for k in (script.get("main") or []) if k in KINDS][:1] or first["who"][:1]
    out = [{"id": "p01", "role": "title", "scene": 0, "lines": [], "place": scenes[0]["place"],
            "cast": lead, "text": script["title"]}]
    for i, s in enumerate(scenes):
        n = len(s["beats"])
        groups = [[k] for k in range(n)]
        for g in groups:
            text = " / ".join(s["beats"][j]["say_hi"] for j in g)
            st = s["beats"][g[0]].get("story")
            slot = {"id": f"p{len(out) + 1:02d}", "role": s.get("kind", "verse"), "scene": i,
                    "lines": [[i, j] for j in g], "place": s["place"], "cast": s["cast"], "text": text}
            if st:   # what this line means and who is in it (story.json): the picture follows it
                slot.update(cast=[k for k in st["who"] if k in KINDS][:3] or s["cast"], place=st["where"] or s["place"],
                            story=st, story_key=story_key(st))
            out.append(slot)
    everyone = list(dict.fromkeys(c for s in scenes for c in s["cast"]))[:4]
    out.append({"id": f"p{len(out) + 1:02d}", "role": "end", "scene": len(scenes) - 1, "lines": [],
                "place": scenes[-1]["place"], "cast": everyone, "text": "everyone waves goodbye"})
    seen = {}
    for s in out:
        s["effect"] = pick_effect(s["text"], s["place"])
        key = (s["role"], s["text"])
        if key in seen:   # a repeated chorus reuses the first picture (save your own pNN file to change it)
            s["same_as"] = seen[key]
        else:
            seen[key] = s["id"]
    return out


def story_key(st):
    return "|".join([",".join(st.get("who", [])), st.get("where", ""), st.get("doing", "")])


def describe(plan, script, cast):
    """Per picture: "show" (one English sentence: who does what, where) and "setting" (the empty place with the
    things that show what the line is about: drawn as the background, the characters are put in front).
    qwen3 reads the Hindi; you check it in pictures.md."""
    sys.path.insert(0, ROOT)
    try:
        from auto_video import llm, MODEL
    except Exception as e:  # noqa: BLE001
        print(f"  (no model: {e}; pictures get a plain description)")
        return {}
    rows = []
    for s in plan:
        if s["role"] in ("title", "end"):
            continue
        roman = " / ".join(script["scenes"][a]["beats"][b].get("say", "") for a, b in s["lines"])
        who = ", ".join(f"{cast['characters'][k]['name']} the {k}" for k in s["cast"] if k in cast["characters"])
        st = s.get("story") or {}
        rows.append(f"{s['id']}: lines: {s['text']}  ({roman})  | characters: {who} | place: {s['place']}"
                    + (f" | meaning: {st['meaning']} | what we see: {st['doing']}" if st.get("doing") else ""))
    system = ("You plan pictures for a Hindi children's song video. For each picture id, read the Hindi lines and "
              "write: show = ONE short English sentence saying what the picture shows: who is there, what they are "
              "doing, where. setting = the BACKGROUND for that picture, 8-20 words: the place and the objects in it "
              "that show what the line is about (for example a cosy bedroom with a small bed and a window, a "
              "swing in a park, a wash basin with soap), with NO people, NO animals, NO characters in it. "
              "The setting comes from what the LINE is about, not only from the time of day: children sleeping -> "
              "a cosy bedroom; playing -> a park or courtyard; washing -> a bathroom with a bucket; a swing -> a "
              "swing under a tree; at night show it at night (window light, lamps). NEVER put the song's characters "
              "in the setting (if the moon or the stars are characters, the setting has no moon and no stars: "
              "they are put in front later). Every picture of the song must have a DIFFERENT setting (a different "
              "place, or a clearly different view: close-up of an object, from above, through a window). "
              "Show what the lines say, nothing scary, nothing sad. Use the character names given in show. "
              "When a row gives 'meaning' and 'what we see', show MUST picture exactly that, with exactly the "
              "characters listed (no others), and the setting must fit it (eating ladoos -> a plate of ladoos on a "
              "low table; dancing -> an open clearing). "
              "action = what the main person or animal in the picture DOES, in 1-3 English words (stand, dance, "
              "wave, sleep, sit, swing, wash hands, eat, read, ride, ...). "
              'Answer JSON: {"pictures": [{"id": "p02", "show": "...", "setting": "...", "action": "..."}]}')
    try:
        data = llm(system, f"Song: {script['title']}\n\n" + "\n".join(rows), model=MODEL, max_tokens=1500,
                   check=lambda d: isinstance(d, dict) and isinstance(d.get("pictures"), list))
    except Exception as e:  # noqa: BLE001
        print(f"  (model failed: {e}; pictures get a plain description)")
        return {}
    finally:
        try:
            import requests
            requests.post("http://localhost:11434/api/generate", json={"model": MODEL, "keep_alive": 0}, timeout=20)
        except Exception:  # noqa: BLE001
            pass
    clean = lambda v: re.sub(r"\s+", " ", str(v or "")).strip()  # noqa: E731
    # the song's characters must not be painted into a background: drop those phrases (they're put in front)
    words = {k for s in plan for k in s["cast"]} | {k + "s" for s in plan for k in s["cast"]}

    def no_cast(text):
        for k in {k for s in plan for k in s["cast"]}:   # starry sky -> night sky, moonlit field -> night-time field
            text = re.sub(rf"\b{k}(ry|lit|light)\b", "night-time", text, flags=re.I)
        parts = [p for p in re.split(r",| with | and ", text) if not (set(re.findall(r"[a-z]+", p.lower())) & words)]
        return ", ".join(p.strip() for p in parts if p.strip())

    for p in data["pictures"]:
        if isinstance(p, dict):
            p["setting"] = no_cast(clean(p.get("setting")))
    return {p.get("id"): {"show": clean(p.get("show")), "setting": clean(p.get("setting")),
                          "action": clean(p.get("action")).lower()} for p in data["pictures"] if isinstance(p, dict)}


def prompt_for(s, script, cast):
    chars = cast["characters"]
    names = [f"{chars[k]['name']} ({chars[k]['look']})" for k in s["cast"] if k in chars]
    who = "; ".join(names)
    place = cast["places"].get(s["place"], s["place"])
    if s["role"] == "title":
        show = (f"{chars.get(s['cast'][0], {}).get('name', 'a cute character')} smiling and waving at the viewer, "
                f"big and close, title picture of a song called '{script['title']}', empty bright sky in the top "
                f"third for the title")
    elif s["role"] == "end":
        show = "all the friends together, happy, waving goodbye at the viewer"
    else:
        show = s.get("show") or f"{', '.join(chars[k]['name'] for k in s['cast'] if k in chars)} in the scene, happy"
    show = show.rstrip(". ")
    return f"{cast['style']}. Scene: {show}. Characters: {who}. Place: {place}. {cast['rules']}."


def acting(slot):
    """True when the line's action needs the character drawn doing it (sleeping, swinging...), not a cut-out."""
    from critters import KINDS
    act = ((slot.get("action") or "") + " " + (slot.get("show") or "")).lower()
    ground = [k for k in slot.get("cast", []) if k in KINDS and not KINDS[k][4]]
    return bool(ground) and slot["role"] not in ("title", "end") and any(a in act for a in ACTIONS)


def action_phrase(slot):
    """The drawn action for an acting picture: the action word that comes first in the description."""
    act = ((slot.get("action") or "") + " " + (slot.get("show") or "")).lower()
    found = [(act.find(a), a) for a in ACTIONS if a in act]
    return ACTION_PHRASES[min(found)[1]] if found else ""


def find_file(folder, pid):
    for ext in EXTS:
        path = os.path.join(folder, "images", pid + ext)
        if os.path.exists(path):
            return path
    return None


def build(folder, ask_model=True):
    script = json.load(open(os.path.join(folder, "script.json"), encoding="utf-8"))
    cast = load_cast()
    plan = slots(script)
    path = os.path.join(folder, "pictures.json")
    old = {}
    if os.path.exists(path):   # keep your own edits for pictures whose lines didn't change
        for s in json.load(open(path, encoding="utf-8"))["pictures"]:
            old.setdefault((s["role"], s["text"]), s)
    for s in plan:   # the line's meaning or cast changed (story.json): plan it again and draw its AI picture again
        before = old.get((s["role"], s["text"]))
        if before and (before.get("story_key") != s.get("story_key") or before.get("cast") != s["cast"]):
            ai = find_file(folder, before["id"])
            if ai and os.path.basename(ai) == before.get("ai_file"):   # only the AI's own file, never yours
                os.remove(ai)
            del old[(s["role"], s["text"])]
    todo = [s for s in plan if "same_as" not in s and ((s["role"], s["text"]) not in old
                                                        or not old[(s["role"], s["text"])].get("setting")
                                                        or not old[(s["role"], s["text"])].get("action"))]
    shows = describe([s for s in todo], script, cast) if ask_model and any(
        s["role"] not in ("title", "end") for s in todo) else {}
    for s in plan:
        before = old.get((s["role"], s["text"]))
        if before:
            for key in ("show", "setting", "action", "effect", "prompt", "seed", "ai", "ai_file", "ai_layers", "sd_prompt"):
                if key in before:
                    s[key] = before[key]
            if "same_as" not in s and before.get("id") != s["id"] and find_file(folder, before["id"]):
                print(f"  note: '{s['text'][:40]}' was {before['id']}, now {s['id']}: rename its picture file")
        if s["id"] in shows and "same_as" not in s:
            got = shows[s["id"]]
            if got.get("setting") and not s.get("setting"):   # your edited setting is kept
                s["setting"] = got["setting"]
            if got.get("action"):
                s["action"] = got["action"]
            if got.get("show") and not before:
                s["show"] = got["show"]
        if before:
            pass
        elif "same_as" in s:
            first = next(x for x in plan if x["id"] == s["same_as"])
            s["show"], s["prompt"] = first.get("show", ""), first["prompt"]
        else:
            s["prompt"] = prompt_for(s, script, cast)
    for s in plan:   # a line about children shows children: Golu (and Chinki), if the part's cast has no child
        text = (s.get("show") or "").lower()
        if s["role"] in ("title", "end") or s.get("story") or any(k in s["cast"] for k in ("boy", "girl")):
            continue
        if re.search(r"\b(children|kids|friends|everyone)\b", text):
            s["cast"] = ["boy", "girl"] + s["cast"]
        elif re.search(r"\b(child|kid|golu|boy|baby)\b", text):
            s["cast"] = ["boy"] + s["cast"]
        elif re.search(r"\b(chinki|girl)\b", text):
            s["cast"] = ["girl"] + s["cast"]
        s["cast"] = s["cast"][:3]
    json.dump({"pictures": plan}, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    os.makedirs(os.path.join(folder, "images"), exist_ok=True)
    write_md(folder, script, plan, cast)
    need = [s for s in plan if "same_as" not in s]
    have = sum(1 for s in need if find_file(folder, s["id"]))
    print(f"  {len(need)} pictures to make ({have} already in images/; repeated choruses reuse theirs): read pictures.md")
    return plan


def write_md(folder, script, plan, cast):
    chars = cast["characters"]
    used = list(dict.fromkeys(k for s in plan for k in s["cast"] if k in chars))
    rows = [f"# Pictures: {script['title']}", "",
            f"{sum(1 for s in plan if 'same_as' not in s)} pictures. Make each one with an image tool, save it in images/ with the name shown "
            "(p01.jpg, p02.png, ...), then run `python rhyme.py render <slug>`. Any missing picture is drawn by code.",
            "",
            "- Pictures can be any size; wide (16:9) is best. The video slowly moves across each one.",
            "- A short clip made from a picture (image-to-video) also works: save it as p03.mp4.",
            "- Same characters every time: first make ONE clear picture of each character below and keep it. In "
            "tools that take a reference picture, upload it with every prompt.",
            "- Before a monetised upload, check the tool's terms allow commercial use on the plan you use, and "
            "never remove a tool's watermark. Song tools on a free plan (for example Suno's) are usually "
            "personal use only: the music stays ours.",
            "- Change the scene sentence or the effect (rain, bubbles, sparkles, petals, stars, snow, none) in "
            "pictures.json, then run `python rhyme.py pictures <slug>` again: your edits are kept.", "",
            "## Characters in this song (reference pictures)", ""]
    for k in used:
        rows += [f"**{chars[k]['name']} ({k})**", "```",
                 f"{cast['style']}. Character sheet: {chars[k]['name']}, {chars[k]['look']}, full body, standing, "
                 "smiling, facing the viewer, plain soft pastel background, no text.", "```", ""]
    rows += ["## Pictures", ""]
    for s in plan:
        have = find_file(folder, s["id"])
        if "same_as" in s and not have:
            rows += [f"- **{s['id']}** reuses {s['same_as']} (repeated chorus; save an {s['id']} file only if you "
                     "want a different picture)", ""]
            continue
        mark = "x" if have else " "
        lines = ("title" if s["role"] == "title" else "end card" if s["role"] == "end"
                 else " / ".join(script["scenes"][a]["beats"][b].get("say", "") for a, b in s["lines"]))
        rows += [f"- [{mark}] **{s['id']}** ({s['role']}, effect: {s['effect']}): {lines}"
                 + (f"  -> {os.path.basename(have)}" if have else ""), "```", s["prompt"], "```", ""]
    open(os.path.join(folder, "pictures.md"), "w", encoding="utf-8").write("\n".join(rows) + "\n")


if __name__ == "__main__":
    for f in sys.argv[1:]:
        build(f, ask_model="--no-model" not in sys.argv)
