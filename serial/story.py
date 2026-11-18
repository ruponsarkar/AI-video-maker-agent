"""
The serial's story brain: find stories, set up a series, plan it arc by arc, write episodes that remember
everything before them.

Models: qwen3:8b plans, directs and checks (reliable JSON); gemma3:4b writes the Hindi lines people hear.
"""
import datetime
import difflib
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

import trafilatura  # noqa: E402

from auto_video import MODEL, WRITER_MODEL, llm, log, search, slugify  # noqa: E402
from memory import Memory  # noqa: E402
from scenery import PLACES  # noqa: E402
import cartoon  # noqa: E402

SERIES_ROOT = os.path.join(ROOT, "series")
# Models, per series in series.json: "story_model" plans, writes and checks the English; "hindi_model" writes the
# Hindi. Bigger ones (gemma3:12b, qwen3:14b) write better and run slower: they don't fit in 6 GB, so they share RAM.
HINDI_MODEL, STORY_MODEL = WRITER_MODEL, MODEL
STORIES_FILE = os.path.join(HERE, "stories.txt")
WORDS_PER_EPISODE = 390       # about 4 minutes of voice; with title, recap and end card under 5 minutes
MAX_WORDS = 470
SLOTS = ("far_left", "left", "center", "right", "far_right")
EMOTIONS = ("calm", "happy", "sad", "angry", "surprised", "fear")
ACTIONS = ("none", "enter", "exit", "walk", "point", "raise", "namaste", "bless", "attack", "fall", "jump", "fly",
           "appear", "vanish", "bow")
MOODS = ("calm", "happy", "sad", "tense", "battle", "mystery", "divine")
TIMES = ("dawn", "day", "evening", "night")
WEATHER = ("clear", "rain", "storm", "fog", "wind")
VOICES = ("male_young", "male_adult", "male_old", "male_deep", "female_young", "female_adult", "female_old", "child",
          "demon", "bird")
SFX = ("whoosh", "fly", "clash", "arrow", "thunder", "magic", "gong", "drum_hit", "conch", "bell", "roar", "fall",
       "splash", "fire", "heartbeat", "crowd_gasp", "riser")
NARRATOR_NAMES = re.compile(r"^(कथावाचक|सूत्रधार|वाचक|narrator|कथाकार)$", re.I)

STARTER_STORIES = [
    ("Ramayan", "Shri Ram ka jeevan: Ayodhya, vanvas, Sita haran, Hanuman, Lanka yuddh aur Ram rajya", 150,
     "Valmiki Ramayana (traditional)"),
    ("Mahabharat", "Pandav aur Kaurav, Krishna, Draupadi, Kurukshetra ka yuddh aur Gita ka gyaan", 250,
     "Vyasa's Mahabharata (traditional)"),
    ("Panchatantra", "Jaanwaron ki kahaniyon mein chhupi samajhdaari: dosti, chalaki aur sabak", 80,
     "Vishnu Sharma's Panchatantra (traditional)"),
    ("Vikram Aur Betaal", "Raja Vikramaditya aur Betaal ki 25 paheliyan-bhari kahaniyan", 30, "Baital Pachisi (traditional)"),
    ("Singhasan Battisi", "Raja Vikramaditya ke singhasan ki 32 putliyon ki kahaniyan", 35, "Simhasana Dvatrimsika (traditional)"),
    ("Jataka Kathayein", "Buddh ke pichhle janmon ki kahaniyan: daya, sach aur himmat", 60, "Jataka tales (traditional)"),
    ("Hitopadesh", "Jaanwaron aur insaanon ki kahaniyon se jeevan ki seekh", 40, "Narayana's Hitopadesha (traditional)"),
    ("Shri Krishna Leela", "Krishna ka bachpan Gokul mein, Kans, Vrindavan aur Dwarka tak", 100,
     "Bhagavata Purana (traditional)"),
]


def now():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M")


def jload(path, default=None):
    return json.load(open(path, encoding="utf-8")) if os.path.exists(path) else default


def jsave(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    json.dump(data, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)


def series_dir(slug):
    path = os.path.join(SERIES_ROOT, slug)
    if not os.path.exists(os.path.join(path, "series.json")):
        raise SystemExit(f"No series '{slug}'. See: python serial.py list")
    return path


def ep_dir(sdir, n):
    return os.path.join(sdir, "episodes", f"ep{int(n):03d}")


# ================================================================== 1. finding stories
def read_stories():
    rows = []
    if os.path.exists(STORIES_FILE):
        for line in open(STORIES_FILE, encoding="utf-8"):
            if line.strip() and not line.startswith("#"):
                parts = [p.strip() for p in line.split("|")]
                rows.append(parts + [""] * (4 - len(parts)))
    return rows


def find_stories(words=""):
    """Look for long, well-loved, traditional stories and add new ones to serial/stories.txt."""
    have = {r[0].lower() for r in read_stories()}
    new_rows = []
    if not os.path.exists(STORIES_FILE):
        new_rows += [list(s) for s in STARTER_STORIES]
    topic = words or "Indian mythology epics folk tales"
    queries = [f"best long {topic} stories for animated series", f"famous traditional {topic} story collections",
               f"{topic} kahaniyan list", "public domain classic story collections India"]
    log("Searching for stories ...")
    found = search(queries)
    pages = []
    for r in found[:8]:
        try:
            html = trafilatura.fetch_url(r["url"])
            text = trafilatura.extract(html) if html else ""
        except Exception:
            text = ""
        if text and len(text) > 400:
            pages.append(f"## {r['title']}\n{text[:2500]}")
    system = ("You pick stories for a Hindi animated cartoon serial on YouTube. Only REAL, WIDELY KNOWN stories that are "
              "traditional or public domain in India: epics and puranas, classic tale collections, folk tales, and "
              "books whose authors died before 1964 (for example Premchand, Rabindranath Tagore, Devaki Nandan Khatri's "
              "Chandrakanta, Kathasaritsagar, Alif Laila / Arabian Nights, Tenali Raman, Akbar-Birbal folk tales, "
              "Shiv Puran and Devi stories). Never a modern copyrighted book, film or TV show. Never a part of a story "
              "already listed. Each must have enough story for 20 or more 3-5 minute episodes. Write title and about in "
              "Roman letters (Hinglish), never Devanagari. Give 6-12 stories.\n"
              'JSON: {"stories": [{"title": "Roman Hindi title", "about": "one line in Roman Hinglish", '
              '"episodes": number, "source": "original text or author, and why it is traditional/public domain"}]}')
    listed = ", ".join(sorted({r[0] for r in read_stories()} | {r[0] for r in new_rows}))
    user = f"Viewer interest: {topic}\nAlready listed (don't repeat or split these): {listed}\n\nWeb notes:\n" \
        + "\n\n".join(pages)[:9000]
    try:
        data = llm(system, user, max_tokens=2500, check=lambda d: isinstance(d.get("stories"), list) and d["stories"])
        for s in data["stories"]:
            title = " ".join(str(s.get("title") or "").split())
            about = str(s.get("about", "")).strip()
            try:
                eps = int(str(s.get("episodes", "0")).split()[0])
            except ValueError:
                eps = 0
            known = {r[0].lower() for r in read_stories()} | {r[0].lower() for r in new_rows}
            if (not title or re.search(r"[\u0900-\u097f]", title + about) or eps < 20
                    or any(difflib.SequenceMatcher(None, title.lower(), k).ratio() > 0.7 or k in title.lower() for k in known)
                    or re.search(r"copyright|film|tv series|netflix|disney", str(s.get("source", "")), re.I)):
                continue
            if not is_real_story(title, str(s.get("source", "")), [r[0] for r in read_stories()] + [r[0] for r in new_rows]):
                log(f"  skipped (not a well-known story): {title}")
                continue
            new_rows.append([title, about, str(eps), str(s.get("source", "")).strip()])
    except RuntimeError as e:
        log(f"  the model couldn't list stories: {e}")
    first = not os.path.exists(STORIES_FILE)
    with open(STORIES_FILE, "a", encoding="utf-8") as f:
        if first:
            f.write("# Stories for the serial. One per line: Title | about | episodes | source\n"
                    "# Add your own the same way, then: python serial.py new \"Title\"  (or --pick N)\n")
        for r in new_rows:
            f.write(" | ".join(str(x) for x in r) + "\n")
    return new_rows


def quoted(evidence, notes):
    """Is this really (nearly) a sentence from the notes?"""
    words = re.findall(r"[a-z]{3,}", evidence.lower())
    if len(words) < 4:
        return False
    body = set(re.findall(r"[a-z]{3,}", notes.lower()))
    if sum(w in body for w in words) / len(words) < 0.85:
        return False
    flat = " " + " ".join(re.findall(r"[a-z]{3,}", notes.lower())) + " "
    return any(f" {' '.join(words[k:k + 4])} " in flat for k in range(len(words) - 3))


def fact_check(title, items, notes, what):
    """The fact-checking agent: every summary is checked against the research notes and rewritten where it's wrong."""
    log(f"    fact check: {len(items)} {what}s against the research notes")
    key = "summary" if what == "arc" else "beats"
    listing = "\n".join(f"{k + 1}. {a.get('title', '')}: {a.get(key) if what == 'arc' else '; '.join(a.get(key) or [])}"
                        for k, a in enumerate(items))
    system = (f"You fact-check the plan of a serial telling {title} faithfully. Compare each numbered {what} with the "
              "research NOTES. Only report a statement when the NOTES clearly say something different (wrong person, "
              "relationship, order or event), and quote the sentence from the NOTES that proves it. If the notes don't "
              "cover it, leave it alone. Rewrite only the wrong ones, in English, keeping everything that is right.\n"
              'JSON: {"fixes": [{"n": number, "problem": "what was wrong", "evidence": "exact quote from the NOTES", '
              '"text": "the corrected ' + ("summary" if what == "arc" else "beats, separated by ' ; '") + '"}]}')
    try:
        data = llm(system, f"NOTES:\n{notes[:9000]}\n\nPLAN:\n{listing}", max_tokens=3000, ctx=16384, temperature=0.1,
                   check=lambda d: isinstance(d.get("fixes"), list))
    except RuntimeError:
        return items
    for f in data["fixes"]:
        try:
            k = int(f.get("n")) - 1
        except (TypeError, ValueError):
            continue
        text = str(f.get("text") or "").strip()
        if not quoted(str(f.get("evidence") or ""), notes):
            continue   # a "fix" the notes don't back up: the checker may be the one that's wrong
        if 0 <= k < len(items) and text and not re.search(r"[\u0900-\u097f]", text):
            log(f"      {what} {k + 1}: {str(f.get('problem', ''))[:100]}")
            items[k][key] = text if what == "arc" else [x.strip() for x in text.split(";") if x.strip()]
    return items


def is_real_story(title, source, listed=()):
    """A second opinion: the model sometimes invents 'stories', or offers a piece of one already listed."""
    try:
        d = llm("Answer strictly. 1) Is this a real, widely known story, epic or story collection (not invented)? "
                "2) Is it traditional or public domain? 3) Is it the same story as, or a part or retelling of, any story "
                "in the list (for example Arjun's story is part of the Mahabharat, Bhagavata Puran overlaps Krishna Leela)? "
                'JSON: {"real": true/false, "public_domain": true/false, "overlaps": true/false}',
                f"Story: {title} ({source})\nList: {', '.join(listed)}", max_tokens=120, temperature=0.0, retries=2,
                check=lambda d: "real" in d)
        return bool(d.get("real")) and bool(d.get("public_domain", True)) and not d.get("overlaps")
    except RuntimeError:
        return False


# ================================================================== 2. research
def read_web(queries, about, limit=6, chars=3500):
    """Read a few pages and keep only what's about this part of the story."""
    notes = []
    for r in search(queries):
        if len(notes) >= limit:
            break
        try:
            html = trafilatura.fetch_url(r["url"])
            text = trafilatura.extract(html) if html else None
        except Exception:
            text = None
        if not text or len(text) < 500:
            continue
        log(f"    reading {r['url'][:90]}")
        try:
            facts = llm("Extract the story events, characters, places and relationships from this text that belong to the "
                        "part of the story described. Bullet points, in English, in story order. Add nothing that isn't "
                        "in the text. If nothing fits, write NONE.",
                        f"PART OF THE STORY: {about}\n\nTEXT:\n{text[:chars * 2]}", as_json=False, ctx=8192,
                        max_tokens=900, temperature=0.2, retries=2)
        except RuntimeError:
            continue
        if not facts.strip().upper().startswith("NONE") and len(facts) > 60:
            notes.append(f"## {r['title']}\n{r['url']}\n{facts.strip()}")
    return "\n\n".join(notes)


# ================================================================== 3. the series bible
def clean_spec(spec):
    """A character's look, made safe: every field from the lists the cartoon engine can draw."""
    opts = {"kind": ("human", "monkey", "bear", "bird", "demon"), "gender": ("male", "female"),
            "age": ("child", "young", "adult", "old"), "skin": tuple(cartoon.SKIN),
            "outfit": ("royal", "queen", "princess", "sage", "warrior", "common", "common_woman", "forest", "demon",
                       "monkey", "bear", "bird"),
            "hair": ("short", "long", "bun", "jata", "bald", "braid", "spiky", "none"),
            "headwear": ("none", "crown", "tiara", "turban", "horns", "helmet"),
            "beard": ("none", "moustache", "short", "long_white", "long_black", "long_grey"),
            "prop": ("none", "bow", "mace", "staff", "sword", "trident", "lotus", "kamandal", "conch", "flute"),
            "voice": VOICES}
    out = {}
    for key, allowed in opts.items():
        v = str(spec.get(key, "")).strip().lower()
        out[key] = v if v in allowed else allowed[0] if key not in ("skin", "voice", "outfit") else None
    out["skin"] = out["skin"] or ("monkey_orange" if out["kind"] == "monkey" else "bear" if out["kind"] == "bear" else "wheat")
    out["outfit"] = out["outfit"] or {"monkey": "monkey", "bear": "bear", "bird": "bird", "demon": "demon"}.get(out["kind"], "common")
    if not out["voice"]:
        out["voice"] = ("female_" if out["gender"] == "female" else "male_") + ("old" if out["age"] == "old" else "young")
        out["voice"] = "child" if out["age"] == "child" else "demon" if out["kind"] == "demon" else out["voice"]
    cs = [c for c in (spec.get("colors") or []) if c in cartoon.COLORS][:2]
    out["colors"] = cs + ["gold", "red"][len(cs):] if len(cs) < 2 else cs
    out["extras"] = [e for e in (spec.get("extras") or []) if e in
                     ("tilak", "bindi", "aura", "tail", "ten_heads", "fangs", "earrings", "mala")]
    if out["kind"] == "monkey" and "tail" not in out["extras"]:
        out["extras"].append("tail")
    try:
        out["height"] = max(0.75, min(1.3, float(spec.get("height", 1.0))))
    except (TypeError, ValueError):
        out["height"] = 1.0
    return out


DIVINE = re.compile(r"\b(god|goddess|deity|avatar|avatara|incarnation|divine|lord|bhagwan|bhagavan|devi|deva)\b", re.I)
ROYAL = re.compile(r"\b(king|queen|prince|princess|emperor|raja|rani|rajkumar|monarch)\b", re.I)
SAGE = re.compile(r"\b(sage|rishi|muni|hermit|guru|priest|ascetic|saint|yogi)\b", re.I)
TRADITIONAL_PROPS = ("Traditional iconography to follow: Ram and Lakshman carry a bow; Hanuman a mace; Bhim and Duryodhan "
                     "a mace; Arjun a bow; Krishna a flute; Shiva a trident; Vishnu a conch; Ravan a sword, ten heads and a "
                     "crown; sages a staff or kamandal; Ram, Krishna and Vishnu are blue-skinned.")


def apply_rules(spec, raw):
    """Fix looks that can't be right, whatever the model said: tails only on monkeys, fangs only on demons ..."""
    role = f"{raw.get('role', '')} {raw.get('name', '')}"
    kind, female = spec["kind"], spec["gender"] == "female"
    extras = set(spec["extras"])
    if kind == "monkey":
        spec["outfit"], extras = "monkey", extras | {"tail"}
    elif kind in ("bear", "bird"):
        spec["outfit"] = kind
        extras.discard("tail")
    else:
        extras.discard("tail")
    if kind != "demon":
        extras.discard("fangs")
        if spec["headwear"] == "horns":
            spec["headwear"] = "none"
    if not re.search(r"ravan|ravana|dashanan|dasanan|dashmukh", role, re.I):
        extras.discard("ten_heads")
    if not DIVINE.search(role):
        extras.discard("aura")
    if female:
        if spec["outfit"] not in ("queen", "princess", "common_woman", "sage", "demon", "monkey", "bear", "bird"):
            spec["outfit"] = "queen" if ROYAL.search(role) and re.search(r"queen|rani|mother", role, re.I) else \
                "princess" if ROYAL.search(role) else "common_woman"
        spec["beard"] = "none"
        if spec["headwear"] in ("crown", "turban", "helmet") and spec["outfit"] != "demon":
            spec["headwear"] = "tiara"
        if spec["hair"] in ("short", "bald", "spiky", "none"):
            spec["hair"] = "long"
    else:
        if spec["outfit"] in ("queen", "princess", "common_woman"):
            spec["outfit"] = "royal" if ROYAL.search(role) else "common"
        if spec["headwear"] == "tiara":
            spec["headwear"] = "crown"
    if ROYAL.search(role) and spec["headwear"] == "none" and kind in ("human", "demon") and spec["age"] != "child":
        spec["headwear"] = "tiara" if female else "crown"
    if SAGE.search(role) and kind == "human" and not female:
        spec["outfit"], spec["hair"] = "sage", "jata"
        if spec["beard"] == "none" and spec["age"] == "old":
            spec["beard"] = "long_white"
    if spec["age"] == "old" and spec["beard"] == "long_black":
        spec["beard"] = "long_white"
    if spec["age"] == "child":
        spec["beard"] = "none"
    if spec["prop"] == "flute" and not re.search(r"krishna|kanha|gopal", role, re.I):
        spec["prop"] = "none"
    # the voice follows who they are, not the model's guess
    if spec["age"] == "child":
        spec["voice"] = "child"
    elif kind == "demon":
        spec["voice"] = "female_adult" if female else "demon"
    elif kind == "bird":
        spec["voice"] = "bird" if not female else "female_old"
    elif female:
        spec["voice"] = {"old": "female_old", "young": "female_young"}.get(spec["age"], "female_adult")
    else:
        spec["voice"] = {"old": "male_old", "young": "male_young"}.get(spec["age"], "male_deep" if kind == "bear" else "male_adult")
    spec["extras"] = sorted(extras)
    return spec


CHARACTER_FORMAT = (
    '{"id": "short_latin_id", "name": "Roman name", "name_hi": "Devanagari name", "role": "who they are", '
    '"personality": "how they talk and behave", "kind": "human|monkey|bear|bird|demon", "gender": "male|female", '
    '"age": "child|young|adult|old", "skin": "' + "|".join(cartoon.SKIN) + '", '
    '"outfit": "royal|queen|princess|sage|warrior|common|common_woman|forest|demon|monkey|bear|bird", '
    '"colors": ["two of: ' + ", ".join(cartoon.COLORS) + '"], "hair": "short|long|bun|jata|bald|braid|spiky|none", '
    '"headwear": "none|crown|tiara|turban|horns|helmet", "beard": "none|moustache|short|long_white|long_black|long_grey", '
    '"prop": "none|bow|mace|staff|sword|trident|lotus|kamandal|conch|flute", '
    '"extras": ["any of: tilak bindi aura tail ten_heads fangs earrings mala"], "height": 0.8-1.2, '
    '"voice": "' + "|".join(VOICES) + '"}')
PLACE_FORMAT = '{"id": "short_latin_id", "name": "Roman name", "name_hi": "Devanagari", "type": "' + "|".join(PLACES) + '"}'


def add_to_bible(sdir, characters=(), places=()):
    """New characters and places join the bible; ones already there never change (so they look the same forever)."""
    bible = jload(os.path.join(sdir, "bible.json"), {"characters": {}, "places": {}})
    added = []
    for c in characters:
        if not isinstance(c, dict):
            continue
        cid = slugify(str(c.get("id") or c.get("name") or "")).replace("-", "_")[:24]
        if not cid or cid in bible["characters"] or cid == "narrator":
            continue
        name = " ".join(str(c.get("name") or cid).split())
        if any(difflib.SequenceMatcher(None, name.lower(), x["name"].lower()).ratio() > 0.85
               for x in bible["characters"].values()):
            continue   # the same person under a slightly different spelling
        spec = apply_rules(clean_spec(c), c)
        spec.update({"name": name, "name_hi": str(c.get("name_hi") or "").strip(), "role": str(c.get("role") or ""),
                     "personality": str(c.get("personality") or ""), "since": c.get("since")})
        bible["characters"][cid] = spec
        added.append(cid)
    for p in places:
        if not isinstance(p, dict):
            continue
        pid = slugify(str(p.get("id") or p.get("name") or "")).replace("-", "_")[:24]
        if not pid or pid in bible["places"]:
            continue
        bible["places"][pid] = {"name": str(p.get("name") or pid), "name_hi": str(p.get("name_hi") or ""),
                                "type": p.get("type") if p.get("type") in PLACES else "forest"}
        added.append(pid)
    jsave(os.path.join(sdir, "bible.json"), bible)
    return added


def new_series(title, about="", episodes=None, channel="", kids=False, language="hi"):
    slug = slugify(title)
    sdir = os.path.join(SERIES_ROOT, slug)
    if os.path.exists(os.path.join(sdir, "series.json")):
        raise SystemExit(f"Series '{slug}' already exists. Continue it with: python serial.py make {slug}")
    os.makedirs(sdir, exist_ok=True)
    log(f"New series: {title}  ({sdir})")
    overview = os.path.join(sdir, "research", "overview.md")
    if os.path.exists(overview):   # a run that stopped part-way: keep its research
        log("1/3 Research: reusing research/overview.md")
        notes = open(overview, encoding="utf-8").read()
    else:
        log("1/3 Research: the whole story")
        notes = read_web([f"{title} full story summary", f"{title} story in order all parts", f"{title} characters list",
                          f"{title} kahani saransh"], f"the whole of {title}: {about}", limit=6)
        os.makedirs(os.path.join(sdir, "research"), exist_ok=True)
        open(overview, "w", encoding="utf-8").write(f"# {title}\n\n{notes}")

    log("2/3 Plan: arcs of the story")
    system = ("You plan a Hindi animated cartoon serial for YouTube, told faithfully to the traditional story, for "
              "families. Split the WHOLE story, start to end, into 6-14 arcs (big chapters), in story order. Each arc gets "
              "the number of 3-5 minute episodes it needs to be told properly: big moments get more episodes. "
              "The research notes are the source of truth: every event you write must agree with them. "
              "Write titles in Roman letters (Hinglish) and summaries in ENGLISH.\n"
              'JSON: {"title_screen": "short Roman title for the screen", "title_hi": "Devanagari title", '
              '"tagline": "one Roman Hinglish line", "arcs": [{"title": "Roman Hinglish", "summary": "English, 2-4 '
              'sentences: what happens", "episodes": number}]}')
    user = f"Story: {title}\nWhat it's about: {about}\nWanted length: {episodes or 'as many as the story needs'} episodes\n\nNotes:\n{notes[:10000]}"
    arcs_path = os.path.join(sdir, "research", "arcs.json")
    plan = jload(arcs_path) or llm(system, user, max_tokens=3500, ctx=16384,
                                   check=lambda d: isinstance(d.get("arcs"), list) and len(d["arcs"]) >= 3
                                   and all(isinstance(a, dict) and not re.search(r"[\u0900-\u097f]",
                                                                                 str(a.get("summary", "")) + str(a.get("title", "")))
                                           for a in d["arcs"]))
    if not plan.get("checked"):
        plan["arcs"] = fact_check(title, plan["arcs"], notes, "arc")
        plan["checked"] = True
    jsave(arcs_path, plan)
    arcs = [{"n": k + 1, "title": str(a.get("title", f"Arc {k + 1}")), "summary": str(a.get("summary", "")),
             "episodes": max(2, min(30, int(a.get("episodes") or 5) if str(a.get("episodes", "")).isdigit() else 5)),
             "expanded": False} for k, a in enumerate(plan["arcs"])]
    if episodes:   # scale the arcs to the length asked for
        total = sum(a["episodes"] for a in arcs)
        for a in arcs:
            a["episodes"] = max(2, round(a["episodes"] * episodes / total))

    log("3/3 Bible: the cast and the places")
    system = ("Design the main cast and places of this cartoon serial. Characters must look right for the traditional "
              "story (respectful: gods and great sages get 'aura'; Ram and Krishna are traditionally blue-skinned; "
              "Ravan has ten_heads; Hanuman is a monkey with a mace). " + TRADITIONAL_PROPS + " Give 8-20 characters "
              "who appear early or often, "
              "and 5-12 places. Only the values listed.\n"
              f'JSON: {{"characters": [{CHARACTER_FORMAT}], "places": [{PLACE_FORMAT}]}}')
    cast = llm(system, f"Story: {title}\n{about}\n\nArcs:\n" + "\n".join(f"- {a['title']}: {a['summary']}" for a in arcs)
               + f"\n\nNotes:\n{notes[:6000]}", max_tokens=5000, ctx=16384,
               check=lambda d: isinstance(d.get("characters"), list)
               and sum(isinstance(c, dict) and bool(c.get("name")) for c in d["characters"]) >= 5)
    jsave(os.path.join(sdir, "bible.json"), {"characters": {}, "places": {}})
    add_to_bible(sdir, cast.get("characters", []), cast.get("places", []))
    series = {"title": title, "slug": slug, "about": about, "title_screen": plan.get("title_screen") or title,
              "title_hi": plan.get("title_hi", ""), "tagline": plan.get("tagline", ""), "channel": channel,
              "made_for_kids": bool(kids), "language": language, "created": now(), "target_episodes": episodes}
    jsave(os.path.join(sdir, "series.json"), series)
    jsave(os.path.join(sdir, "plan.json"), {"arcs": arcs, "episodes": []})
    Memory(sdir).save_state()
    log(f"Done: {len(arcs)} arcs, {sum(a['episodes'] for a in arcs)} episodes planned, "
        f"{len(jload(os.path.join(sdir, 'bible.json'))['characters'])} characters.")
    return slug


# ================================================================== 4. arcs -> episodes
def expand_arc(sdir, arc):
    """Plan every episode of one arc: first the arc's events in order (only this arc), then code shares them out
    evenly over its episodes, then each episode gets a title, cast, places and a hook."""
    series = jload(os.path.join(sdir, "series.json"))
    plan = jload(os.path.join(sdir, "plan.json"))
    bible = jload(os.path.join(sdir, "bible.json"))
    log(f"Planning arc {arc['n']}: {arc['title']}")
    research_path = os.path.join(sdir, "research", f"arc_{arc['n']:02d}.md")
    if os.path.exists(research_path):
        notes = open(research_path, encoding="utf-8").read()
    else:
        notes = read_web([f"{series['title']} {arc['title']} story", f"{series['title']} {arc['title']} summary in detail",
                          f"{series['title']} {arc['title']} kahani"], f"{arc['title']}: {arc['summary']}", limit=4)
        open(research_path, "w", encoding="utf-8").write(f"# {arc['title']}\n\n{notes}")
    prev_arc = next((a for a in plan["arcs"] if a["n"] == arc["n"] - 1), None)
    next_arc = next((a for a in plan["arcs"] if a["n"] == arc["n"] + 1), None)
    want = arc["episodes"] * 4
    system = (f"List the events of ONE arc of {series['title']}, in story order, faithful to the traditional story. "
              f"Short events (one sentence each, English), detailed enough to tell as scenes: who does what, where. "
              f"ONLY events that are part of this arc's summary: as many as it really has, at most {want}. Never pad it "
              "with events from the previous or the next arc (they are given so you know where to stop), and never add "
              "side stories that aren't in the arc summary. Use the notes for details; never contradict the arc summary.\n"
              'JSON: {"events": ["..."]}')
    user = (f"THIS ARC ({arc['n']}): {arc['title']}\n{arc['summary']}\n\n"
            + (f"PREVIOUS ARC (already told): {prev_arc['title']}: {prev_arc['summary']}\n" if prev_arc else "")
            + (f"NEXT ARC (do NOT include): {next_arc['title']}: {next_arc['summary']}\n" if next_arc else "")
            + f"\nNOTES:\n{notes[:8000]}")
    data = llm(system, user, max_tokens=4000, ctx=16384, temperature=0.3,
               check=lambda d: isinstance(d.get("events"), list) and len(d["events"]) >= arc["episodes"] * 2)
    events = [" ".join(str(e).split()) for e in data["events"] if len(str(e)) > 10]
    events = [e for k, e in enumerate(events) if not any(difflib.SequenceMatcher(None, e, x).ratio() > 0.8 for x in events[:k])]
    events = inside_arc(series["title"], arc, prev_arc, next_arc, events)
    # share the events out: every episode gets its own, in order, none repeated; about 3-4 events an episode
    count = max(1, min(arc["episodes"], round(len(events) / 3.5)))
    size = len(events) / count
    groups = [events[int(k * size):int((k + 1) * size)] for k in range(count)]
    cast = "\n".join(f"- {cid}: {c['name']} ({c.get('role', '')})" for cid, c in bible["characters"].items())
    places = "\n".join(f"- {pid}: {p['name']} ({p['type']})" for pid, p in bible["places"].items())
    listing = "\n".join(f"EPISODE {k + 1}:\n" + "\n".join(f"- {e}" for e in g) for k, g in enumerate(groups))
    system = ("These are the episodes of one arc of a Hindi cartoon serial, each already given its events. For each "
              "episode give: a title (Roman Hinglish, 2-6 words, exciting, all different), title_hi (Devanagari), the "
              "ids of the characters who are actually PRESENT in its events (not someone only mentioned, not someone not "
              "yet born), the place ids it needs (from the lists), and a hook: the moment it should end on, taken "
              "from its LAST event, that makes people want the next episode. Do not change or add events. A character "
              "or place that isn't listed goes into new_characters / new_places. " + TRADITIONAL_PROPS + "\n"
              'JSON: {"episodes": [{"title": "...", "title_hi": "...", "characters": ["id"], "places": ["id"], "hook": '
              f'"..."}}], "new_characters": [{CHARACTER_FORMAT}], "new_places": [{PLACE_FORMAT}]}}')
    meta = llm(system, f"{listing}\n\nCHARACTERS:\n{cast}\n\nPLACES:\n{places}", max_tokens=5000, ctx=16384,
               check=lambda d: isinstance(d.get("episodes"), list) and len(d["episodes"]) >= len(groups) * 0.8)
    start = max([e["n"] for e in plan["episodes"]] or [0]) + 1
    for c in meta.get("new_characters") or []:
        if isinstance(c, dict):
            c["since"] = start
    added = add_to_bible(sdir, meta.get("new_characters") or [], meta.get("new_places") or [])
    if added:
        log(f"    new in the bible: {', '.join(added)} (check their looks in bible.json)")
    bible = jload(os.path.join(sdir, "bible.json"))
    used_titles = {e["title"].lower() for e in plan["episodes"]}
    for k, g in enumerate(groups):
        e = meta["episodes"][k] if k < len(meta["episodes"]) and isinstance(meta["episodes"][k], dict) else {}
        title = str(e.get("title") or f"{arc['title']} {k + 1}")
        if title.lower() in used_titles:
            title = f"{title} {k + 1}"
        used_titles.add(title.lower())
        chars = [c for c in (e.get("characters") or []) if c in bible["characters"]]
        plan["episodes"].append({
            "n": start + k, "arc": arc["n"], "title": title, "title_hi": str(e.get("title_hi") or ""), "beats": g,
            "characters": chars[:8], "places": [p for p in (e.get("places") or []) if p in bible["places"]],
            "hook": str(e.get("hook") or g[-1]), "status": "planned"})
    for a in plan["arcs"]:
        if a["n"] == arc["n"]:
            a["expanded"] = True
            a["planned_episodes"] = len(groups)
    jsave(os.path.join(sdir, "plan.json"), plan)
    log(f"    {len(groups)} episodes planned (ep {start}-{start + len(groups) - 1}) from {len(events)} events")


def inside_arc(title, arc, prev_arc, next_arc, events):
    """The arc-boundary agent: drop events that belong to another arc or aren't part of this arc at all."""
    listing = "\n".join(f"{k + 1}. {e}" for k, e in enumerate(events))
    system = (f"You check the plan of {title}. Which numbered events do NOT belong in THIS ARC: they happen in the "
              "previous or next arc, or they are not part of this arc's summary at all? Be strict.\n"
              'JSON: {"outside": [numbers], "why": "short"}')
    user = (f"THIS ARC: {arc['title']}: {arc['summary']}\n"
            + (f"PREVIOUS ARC: {prev_arc['summary']}\n" if prev_arc else "")
            + (f"NEXT ARC: {next_arc['summary']}\n" if next_arc else "") + f"\nEVENTS:\n{listing}")
    try:
        data = llm(system, user, max_tokens=600, ctx=8192, temperature=0.0, check=lambda d: isinstance(d.get("outside"), list))
        drop = {int(x) for x in data["outside"] if str(x).isdigit()}
    except RuntimeError:
        return events
    kept = [e for k, e in enumerate(events) if k + 1 not in drop]
    if drop:
        log(f"    arc check: {len(drop)} events belong elsewhere, removed")
    return kept if len(kept) >= 2 else events


def next_episode_numbers(sdir, count):
    plan = jload(os.path.join(sdir, "plan.json"))
    todo = [e["n"] for e in plan["episodes"] if e["status"] == "planned"]
    while len(todo) < count:
        arc = next((a for a in plan["arcs"] if not a["expanded"]), None)
        if not arc:
            break
        expand_arc(sdir, arc)
        plan = jload(os.path.join(sdir, "plan.json"))
        todo = [e["n"] for e in plan["episodes"] if e["status"] == "planned"]
    return todo[:count]


# ================================================================== 5. writing an episode
# qwen understands the story; gemma writes Hindi well. So the story is written in English by qwen, checked in
# English, then gemma turns each line into spoken Hindi, and qwen checks the Hindi says the same thing.
def plan_scenes(sdir, ep, memory_text, bible):
    """Scenes for one episode: where, when, who, what happens."""
    places = "\n".join(f"- {pid}: {p['name']} ({p['type']})" for pid, p in bible["places"].items())
    allowed = [c for c in ep["characters"] if c in bible["characters"]] or list(bible["characters"])
    cast = "\n".join(f"- {cid}: {bible['characters'][cid]['name']}, {bible['characters'][cid].get('role', '')}" for cid in allowed)
    count = "2" if len(ep["beats"]) <= 3 else "2-3" if len(ep["beats"]) <= 5 else "3-4"
    system = (f"Split this episode of a Hindi cartoon serial into {count} scenes (each with something new happening; "
              "change the place or time when the story does), covering ALL its events in order and ending "
              "on its hook. Each scene: one place, a time of day, weather, music mood, the characters in it with a stage "
              "slot, which events it shows, and how many spoken words it gets (all scenes together about "
              f"{WORDS_PER_EPISODE - 70}). 'arrives': true if the character walks in during the scene.\n"
              'JSON: {"scenes": [{"place": "place id", "time": "' + "|".join(TIMES) + '", "weather": "'
              + "|".join(WEATHER) + '", "music": "' + "|".join(MOODS) + '", "cast": [{"id": "character id", "slot": "'
              + "|".join(SLOTS) + '", "arrives": false}], "what_happens": "English: the events of this scene", "words": number}]}')
    user = (f"EPISODE {ep['n']}: {ep['title']}\nEvents:\n" + "\n".join(f"- {b}" for b in ep["beats"])
            + f"\nEnds with: {ep['hook']}\nPlaces planned: {', '.join(ep['places'])}"
            + f"\n\nCharacters (ONLY these may appear; anyone else isn't in this episode or isn't born yet):\n{cast}"
            + f"\n\nPlaces:\n{places}\n\nMEMORY:\n{memory_text[:4000]}")
    data = llm(system, user, max_tokens=2500, ctx=12288,
               check=lambda d: isinstance(d.get("scenes"), list) and 1 <= len(d["scenes"]) <= 5)
    scenes = []
    for s in data["scenes"]:
        if not isinstance(s, dict):
            continue
        place = s.get("place") if s.get("place") in bible["places"] else (ep["places"] or list(bible["places"]))[0]
        cast, used = [], set()
        for c in s.get("cast") or []:
            cid = c.get("id") if isinstance(c, dict) else None
            if cid in allowed and cid not in used and len(cast) < 4:
                slot = c.get("slot") if c.get("slot") in SLOTS else SLOTS[len(cast) % 5]
                if slot in {x["slot"] for x in cast}:
                    slot = next(x for x in SLOTS if x not in {y["slot"] for y in cast})
                cast.append({"id": cid, "slot": slot, "arrives": bool(c.get("arrives"))})
                used.add(cid)
        if not cast:
            continue
        try:
            words = int(s.get("words") or 100)
        except (TypeError, ValueError):
            words = 100
        scenes.append({"place": place, "time": s.get("time") if s.get("time") in TIMES else "day",
                       "weather": s.get("weather") if s.get("weather") in WEATHER else "clear",
                       "music": s.get("music") if s.get("music") in MOODS else "calm", "cast": cast,
                       "what_happens": str(s.get("what_happens") or ""), "words": max(50, min(200, words))})
    total = sum(s["words"] for s in scenes) or 1
    for s in scenes:   # keep the episode inside its length
        s["words"] = int(s["words"] * (WORDS_PER_EPISODE - 70) / total)
    return scenes


SCREENWRITER = """You write one scene of a Hindi cartoon serial for families, told faithfully to the traditional {story}.
Write it in simple ENGLISH as a script; it will be translated into spoken Hindi later. About {words} words.
Format, one line each:
NARRATOR: short narration of what we see or what happens
character_id: what they say
Rules:
- Show ONLY the events given for this scene. Things listed under LATER happen in future scenes or episodes:
  never show, hint or skip ahead to them.
- Only these speakers: NARRATOR, {ids}. Use the ids exactly.
- Mostly dialogue; the narrator only links moments. Short sentences. Clear feelings: love, fear, anger, wonder.
- Every character in the scene speaks at least once. Every line moves the story forward: never repeat a line or an
  idea that was already said, in this scene or earlier.
- Each character talks in their own way. Respectful words for elders, gurus and gods.
- Show exactly the events given, in order, and nothing that isn't in them or in the traditional story.
- Keep everything consistent with the memory: who is alive, where people are, what they already know.
- No modern words or ideas. No stage directions in brackets. Nothing but the script lines."""


def name_index(bible):
    index = {"narrator": "narrator"}
    for cid, c in bible["characters"].items():
        index[cid] = cid
        for n in (c.get("name"), c.get("name_hi")):
            if n:
                index[n.strip().lower()] = cid
    return index


def parse_script(text, index, allowed):
    """'speaker: line' lines -> [(speaker id, line)]."""
    out = []
    for raw in text.splitlines():
        line = raw.strip().strip("*").strip()
        m = re.match(r"^([^:]{1,30}):\s*(.+)$", line)
        if not m:
            continue
        who, said = m.group(1).strip().strip("()[]*").lower(), re.sub(r"\([^)]*\)|\[[^\]]*\]", "", m.group(2)).strip()
        said = re.sub(r"[*_#`]+", "", said).strip('"“” ')
        if len(said) < 2:
            continue
        cid = index.get(who) or index.get(who.replace(" ", "_"))
        if not cid:
            close = difflib.get_close_matches(who, list(index), n=1, cutoff=0.72)
            cid = index[close[0]] if close else None
        if cid and (cid == "narrator" or cid in allowed):
            out.append((cid, said))
    return out


def write_scene(scene, ep, memory_text, bible, told, story_title, later=""):
    ids = [c["id"] for c in scene["cast"]]
    people = "\n".join(f"- {cid}: {bible['characters'][cid]['name']}, {bible['characters'][cid].get('role', '')}. "
                       f"Speaks: {bible['characters'][cid].get('personality', '')}" for cid in ids)
    system = SCREENWRITER.format(story=story_title, words=scene["words"], ids=", ".join(ids))
    user = (f"MEMORY OF THE STORY SO FAR:\n{memory_text[:3500]}\n\nEARLIER IN THIS EPISODE:\n"
            + ("\n".join(told[-10:]) or "(this is the first scene)")
            + f"\n\nCHARACTERS IN THIS SCENE:\n{people}\nPLACE: {bible['places'][scene['place']]['name']}, {scene['time']}\n"
            f"EVENTS OF THIS SCENE: {scene['what_happens']}\n\nLATER (do NOT show): {later or '-'}\n\nWrite the scene:")
    index = name_index(bible)
    best = []
    for attempt in range(3):
        try:
            text = llm(system, user, as_json=False, ctx=12288, max_tokens=1600, temperature=0.6 + 0.1 * attempt,
                       model=STORY_MODEL)
        except RuntimeError:
            continue
        lines = parse_script(text, index, set(ids))
        if len(lines) > len(best):
            best = lines
        if sum(len(x.split()) for _, x in lines) >= scene["words"] * 0.6 and any(w != "narrator" for w, _ in lines):
            return lines
    return best


DIRECTOR = ("You direct a Hindi cartoon serial. For each numbered line give: emotion of the speaker; an action (who does "
            "what, when it fits the line: enter, exit, walk (to a slot), point, raise (arms up), namaste, bless, attack "
            "(target), fall, jump, fly, appear, vanish, bow, or none); sound effects only when something happens "
            "(" + ", ".join(SFX) + "); and how listeners react (character id -> emotion). Keep actions sparse and "
            "meaningful: most lines are 'none'.\n"
            'JSON: {"lines": [{"n": 1, "emotion": "' + "|".join(EMOTIONS) + '", "action": {"type": "...", "who": "id", '
            '"target": "id", "to": "slot"}, "sfx": [], "react": {"id": "emotion"}}]}')


def direct(scene, lines):
    ids = [c["id"] for c in scene["cast"]]
    listing = "\n".join(f"{k + 1}. {who}: {said}" for k, (who, said) in enumerate(lines))
    try:
        data = llm(DIRECTOR, f"Characters on stage: {', '.join(ids)}\nScene: {scene['what_happens']}\n\n{listing}",
                   max_tokens=3000, ctx=8192, temperature=0.4,
                   check=lambda d: isinstance(d.get("lines"), list) and len(d["lines"]) >= len(lines) * 0.6)
        notes = {int(x.get("n", 0)): x for x in data["lines"] if isinstance(x, dict) and str(x.get("n", "")).isdigit()}
    except RuntimeError:
        notes = {}
    beats = []
    arrivals = {c["id"] for c in scene["cast"] if c.get("arrives")}
    for k, (who, said) in enumerate(lines):
        x = notes.get(k + 1, {})
        act = x.get("action") if isinstance(x.get("action"), dict) else {}
        kind = act.get("type") if act.get("type") in ACTIONS else "none"
        actor = act.get("who") if act.get("who") in ids else (who if who in ids else None)
        action = {}
        if kind != "none" and actor:
            action = {"type": kind, "who": actor}
            if act.get("target") in ids and act.get("target") != actor:
                action["target"] = act["target"]
            if kind == "walk":
                action["to"] = act.get("to") if act.get("to") in SLOTS else "center"
            if kind == "attack" and "target" not in action:
                action = {}
            if kind in ("enter", "appear") and actor not in arrivals:
                action = {}   # only characters planned to arrive walk in
        if who in arrivals:   # someone arriving walks in on their first line
            action = {"type": "enter", "who": who}
            arrivals.discard(who)
        emotion = x.get("emotion") if x.get("emotion") in EMOTIONS else "calm"
        react = {c: e for c, e in (x.get("react") or {}).items() if c in ids and e in EMOTIONS and c != who} \
            if isinstance(x.get("react"), dict) else {}
        beats.append({"speaker": who, "say_en": said, "emotion": emotion, "action": action,
                      "sfx": [s for s in (x.get("sfx") or []) if s in SFX][:2], "react": react})
    for cid in arrivals:   # planned to arrive but never spoke: walk in on the first free line
        for b in beats:
            if not b["action"]:
                b["action"] = {"type": "enter", "who": cid}
                break
    return beats


CHECKER = ("You are the continuity editor of a long serial telling the traditional {story}. The PLAN's events are "
           "the truth for this episode. Compare the script with the PLAN, the MEMORY of the story so far, the CHARACTERS "
           "and what happens LATER. Report real problems only: an event that is not in the PLAN (above all one from "
           "LATER, shown too early), something that contradicts the plan or the traditional story, a misunderstood event (for example 'has no "
           "children' written as 'children are missing'), a dead or absent character acting, a wrong relationship or "
           "name, a contradiction with an earlier episode, a modern word, or a line a child can't follow. For each, give "
           "the line number and the corrected line (same speaker, English).\n"
           'JSON: {{"issues": [{{"n": line number, "problem": "...", "line": "the corrected line"}}]}}')


def check_continuity(beats, memory_text, bible, plan_text, story_title, later=""):
    listing = "\n".join(f"{k + 1}. {b['speaker']}: {b['say_en']}" for k, b in enumerate(beats))
    cast = "\n".join(f"- {cid}: {c['name']} ({c.get('role', '')})" for cid, c in bible["characters"].items())
    try:
        data = llm(CHECKER.format(story=story_title),
                   f"MEMORY:\n{memory_text[:5000]}\n\nCHARACTERS:\n{cast}\n\nPLAN:\n{plan_text}\n\nLATER (must not happen "
                   f"yet):\n{later or '-'}\n\nSCRIPT:\n{listing}",
                   max_tokens=2500, ctx=16384, temperature=0.2, check=lambda d: isinstance(d.get("issues"), list))
    except RuntimeError:
        return []
    out = []
    for i in data["issues"]:
        if isinstance(i, dict) and str(i.get("n", "")).isdigit() and 1 <= int(i["n"]) <= len(beats) and str(i.get("line", "")).strip():
            out.append(i)
    return out[:10]


TRANSLATOR = """इन अंग्रेज़ी पंक्तियों को बोलचाल की आसान, सुंदर हिंदी में लिखो, जैसे पारिवारिक कार्टून सीरियल में बोली जाती है।
- हर पंक्ति का मतलब बिल्कुल वही रहे। कुछ जोड़ो या घटाओ मत।
- बड़ों, गुरुओं और देवताओं के लिए आदर के शब्द: आप, महाराज, गुरुदेव, माता।
- छोटे, साफ़ वाक्य, सही व्याकरण। सिर्फ़ देवनागरी, कोई अंग्रेज़ी शब्द नहीं, कोई * या चिह्न नहीं। अंक शब्दों में।
- पुराने ज़माने की कथा है: payasam = खीर, yagna = यज्ञ, sage = ऋषि, ashram = आश्रम।
- उसी नंबर के साथ लिखो: "1. ...", "2. ..."। कोई नाम, नोट या और कुछ नहीं।"""


def name_spellings(lines, bible, sdir=None):
    """Every proper name in these lines with one fixed Devanagari spelling: the bible's, then the series glossary,
    then asked once (spelling a name is easy, translating around it isn't) and saved to the glossary."""
    names = {}
    for c in bible["characters"].values():
        if c.get("name_hi"):
            names[c["name"]] = c["name_hi"]
            names[c["name"].split()[-1]] = c["name_hi"].split()[-1]
    for p in bible["places"].values():
        if p.get("name_hi"):
            names[p["name"]] = p["name_hi"]
    path = os.path.join(sdir, "glossary.json") if sdir else None
    glossary = jload(path, {}) if path else {}
    names.update(glossary)
    found = set()
    for _, text in lines:
        for w in re.findall(r"(?<![.!?]\s)(?<!^)\b([A-Z][a-z]{3,}(?:-[A-Z][a-z]+)?)\b", text):
            found.add(w)
        for w in re.findall(r"\b([a-z]+(?:yagna|yajna|astra|eshti|kanda|mantra))\b", text, re.I):
            found.add(w.lower())
    common = {"The", "This", "That", "There", "These", "They", "When", "With", "What", "Where", "Your", "Behold", "Come",
              "Let", "May", "King", "Queen", "Prince", "Princess", "Sage", "Lord", "Mother", "Father", "Brother", "Guru",
              "Maharaj", "Then", "Now", "Here", "Come", "Look", "Yes", "Who", "Why", "How", "Our", "Their", "From"}
    todo = sorted(w for w in found if w not in names and w not in common and not any(w in k for k in names))
    if todo:
        try:
            data = llm("Write each name or Sanskrit word from the Indian epics in Devanagari, spelled the traditional way "
                       "(for example Rishyashringa -> ऋष्यशृंग, putrakameshti -> पुत्रकामेष्टि, Ayodhya -> अयोध्या). Only "
                       "spell, never translate. JSON with each word as a key.", json.dumps(todo), max_tokens=60 * len(todo) + 100,
                       temperature=0.0, retries=2, model=HINDI_MODEL)
            for w in todo:
                v = str(data.get(w) or "").strip()
                if re.fullmatch(r"[\u0900-\u097f\s-]+", v):
                    names[w] = glossary[w] = v
            if path:
                jsave(path, glossary)
        except RuntimeError:
            pass
    return names


def missing_names(english, hindi, names):
    """Names in the English line whose fixed spelling isn't in the Hindi line, and names in the Hindi line that
    the English never says (a translator slipping in the wrong person)."""
    out = []
    words = [w.lower() for w in re.findall(r"[A-Za-z]{3,}", english)]

    def said(name):   # the English names this person, in any common spelling (Tadka, Tadaka)
        key = name.split()[-1].lower()
        return any(difflib.SequenceMatcher(None, key, w).ratio() >= 0.75 for w in words)

    for name, hi in names.items():
        stem = hi.split()[-1]
        if len(stem) >= 3 and stem in hindi and not said(name):
            if not any(stem in h2 and said(n2) for n2, h2 in names.items()):
                out.append((f"not {name}", hi))
    for name, hi in names.items():
        if re.search(rf"\b{re.escape(name)}\b", english, re.I if name.islower() else 0):
            core = hi.split()[-1][:-1] if len(hi.split()[-1]) > 3 else hi.split()[-1]   # allow the ending to change
            if core and core not in hindi and (name, hi) not in out:
                out.append((name, hi))
    return out


def translate(lines, bible, context="", names=None):
    """English lines -> spoken Hindi, gemma, in numbered batches. Every name comes out with its fixed spelling."""
    names = names if names is not None else name_spellings(lines, bible)
    names_text = "; ".join(f"{k} = {v}" for k, v in names.items())
    out = [None] * len(lines)
    for start in range(0, len(lines), 10):
        chunk = lines[start:start + 10]
        listing = "\n".join(f"{k + 1}. ({who}) {text}" for k, (who, text) in enumerate(chunk))
        for attempt in range(2):
            try:
                text = llm(TRANSLATOR, f"नाम ऐसे लिखो: {names_text}\n{context}\n\n{listing}", as_json=False, ctx=8192,
                           max_tokens=1600, temperature=0.3 + 0.2 * attempt, model=HINDI_MODEL)
            except RuntimeError:
                continue
            for m in re.finditer(r"^\s*(\d+)[.)]\s*(?:\([^)]*\)\s*)?(.+)$", text, re.M):
                k = int(m.group(1)) - 1
                hindi = clean_hindi(m.group(2))
                if 0 <= k < len(chunk) and hindi and out[start + k] is None:
                    out[start + k] = hindi
            if all(out[start:start + len(chunk)]):
                break
    for k, h in enumerate(out):   # anything still missing: one line at a time
        if h is None:
            try:
                h = clean_hindi(llm(TRANSLATOR.replace('उसी नंबर के साथ लिखो: "1. ...", "2. ..."।', "सिर्फ़ एक पंक्ति लिखो।"),
                                    f"नाम ऐसे लिखो: {names_text}\n{context}\n\n{lines[k][1]}", as_json=False, ctx=4096, max_tokens=300,
                                    temperature=0.3, model=HINDI_MODEL).splitlines()[0])
            except (RuntimeError, IndexError):
                h = None
            out[k] = h or ""
    return out


def clean_hindi(text):
    text = re.sub(r"^[^:：]{1,20}[:：]\s*", "", str(text).strip()) if re.match(r"^[^:：]{1,20}[:：]", str(text).strip()) else str(text).strip()
    text = re.sub(r"\([^)]*\)|\[[^\]]*\]|[*_#`‘’]", "", text).strip().strip('"“”\' ')
    return text if re.search(r"[ऀ-ॿ]", text) and not re.search(r"[A-Za-z]{3,}", text) else ""


MEANING = ("Check a translation. For each numbered pair, does the Hindi say the same thing as the English (same "
           "meaning, same people, nothing added or lost)? List only the pairs that don't, and why.\n"
           'JSON: {"wrong": [{"n": number, "why": "..."}]}')


def check_meaning(beats):
    listing = "\n".join(f"{k + 1}. EN: {b['say_en']}\n   HI: {b['say_hi']}" for k, b in enumerate(beats))
    try:
        data = llm(MEANING, listing, max_tokens=1500, ctx=12288, temperature=0.1, check=lambda d: isinstance(d.get("wrong"), list))
        return [w for w in data["wrong"] if isinstance(w, dict) and str(w.get("n", "")).isdigit() and 1 <= int(w["n"]) <= len(beats)]
    except RuntimeError:
        return []


def narration_en(system, user, max_words):
    try:
        text = llm(system + " Plain English sentences, one per line, nothing else.", user, as_json=False, ctx=6144,
                   max_tokens=300, temperature=0.5)
    except RuntimeError:
        return []
    lines = [re.sub(r"^(narrator|NARRATOR)\s*:\s*", "", x).strip() for x in text.splitlines()]
    lines = [x for x in lines if len(x.split()) >= 4 and not re.search(r"here is|teaser|recap|episode \d|sure|certainly", x, re.I)]
    out, words = [], 0
    for x in lines:
        if words + len(x.split()) > max_words:
            break
        out.append(x)
        words += len(x.split())
    return out


def write_episode(sdir, n, log_review=None):
    """Write episode n: scenes, English script, continuity check, direction, Hindi, meaning check, recap, teaser,
    captions, memory."""
    from hinglish import english_pass, screen_text

    global HINDI_MODEL, STORY_MODEL
    series = jload(os.path.join(sdir, "series.json"))
    HINDI_MODEL = series.get("hindi_model") or WRITER_MODEL
    STORY_MODEL = series.get("story_model") or MODEL
    plan = jload(os.path.join(sdir, "plan.json"))
    ep = next(e for e in plan["episodes"] if e["n"] == n)
    bible = jload(os.path.join(sdir, "bible.json"))
    mem = Memory(sdir)
    story_title = f"{series['title']} ({series.get('source', 'traditional')})"
    log(f"Episode {n}: {ep['title']}")
    query = f"{ep['title']}. " + " ".join(ep["beats"]) + " " + ep["hook"]
    memory_text = mem.context(query, chars=ep["characters"], before=n)
    plan_text = f"{ep['title']}\n" + "\n".join(f"- {b}" for b in ep["beats"]) + f"\nEnds: {ep['hook']}"

    upcoming = [e for e in plan["episodes"] if n < e["n"] <= n + 2]
    later_eps = " ".join(f"(ep {e['n']}) " + "; ".join(e["beats"]) for e in upcoming)
    log("    scenes")
    scenes = plan_scenes(sdir, ep, memory_text, bible)
    if not scenes:
        raise RuntimeError("the scene planner gave no usable scenes")
    told, review = [], []
    for k, sc in enumerate(scenes):
        log(f"    script, scene {k + 1}/{len(scenes)} at {bible['places'][sc['place']]['name']}")
        later = " ".join(x["what_happens"] for x in scenes[k + 1:]) + " " + later_eps
        lines = write_scene(sc, ep, memory_text, bible, told, story_title, later)
        if not lines:
            review.append(f"- Scene {k + 1}: the writer gave nothing usable")
            continue
        sc["lines"] = lines
        told += [f"{w}: {x}" for w, x in lines]
    scenes = [s for s in scenes if s.get("lines")]

    log("    continuity check")
    flat = [(sc, k) for sc in scenes for k in range(len(sc["lines"]))]
    issues = check_continuity([{"speaker": sc["lines"][k][0], "say_en": sc["lines"][k][1]} for sc, k in flat],
                              memory_text, bible, plan_text, story_title, later_eps)
    for issue in issues:
        sc, k = flat[int(issue["n"]) - 1]
        old = sc["lines"][k][1]
        new = re.sub(r"[*_#`]+", "", str(issue["line"]).strip())
        others = [x for s2 in scenes for j, (_, x) in enumerate(s2["lines"]) if not (s2 is sc and j == k)]
        if any(difflib.SequenceMatcher(None, new.lower(), x.lower()).ratio() > 0.8 for x in others) or new == old:
            continue   # a "fix" that only repeats another line
        sc["lines"][k] = (sc["lines"][k][0], new)
        review.append(f"- Line {issue['n']} ({sc['lines'][k][0]}): {issue.get('problem', '')}\n  - was: {old}\n  - now: {sc['lines'][k][1]}")

    seen = []
    for sc in scenes:   # no line said twice
        keep = []
        for who, x in sc["lines"]:
            if any(difflib.SequenceMatcher(None, x.lower(), y.lower()).ratio() > 0.75 for y in seen):
                review.append(f"- Repeat removed: {x}")
                continue
            seen.append(x)
            keep.append((who, x))
        sc["lines"] = keep
    scenes = [s for s in scenes if s["lines"]]

    log("    direction")
    for sc in scenes:
        sc["beats"] = direct(sc, sc.pop("lines"))

    # recap of the last episode, and a teaser for the next (in English first, like the rest)
    last = mem.state.get("last_episode")
    nxt = next((e for e in plan["episodes"] if e["n"] == n + 1), None)
    if last and n > 1:
        recap = narration_en("You are the narrator. In 2-3 short sentences, remind viewers what happened in the last "
                             "episode, so it flows into this one.", f"Last episode: {last.get('summary')}\nIt ended: "
                             f"{last.get('ending')}", 40)
        if recap:
            first = scenes[0]
            scenes.insert(0, {"kind": "recap", "place": first["place"], "time": first["time"], "weather": "clear",
                              "music": "mystery", "cast": [dict(c, arrives=False) for c in first["cast"]][:3],
                              "beats": [{"speaker": "narrator", "say_en": x, "emotion": "calm", "action": {}, "sfx": [],
                                         "react": {}} for x in recap]})
    if nxt:
        teaser = narration_en("You are the narrator. Write 1-2 short sentences that make viewers curious about the next "
                              "episode without giving it away; end with a question.",
                              f"Next episode: {nxt['title']}: " + "; ".join(nxt["beats"][:2]), 30)
        if teaser:
            lastsc = scenes[-1]
            scenes.append({"kind": "teaser", "place": lastsc["place"], "time": lastsc["time"], "weather": lastsc["weather"],
                           "music": "mystery", "cast": [dict(c, arrives=False) for c in lastsc["cast"]][:2],
                           "beats": [{"speaker": "narrator", "say_en": x, "emotion": "calm", "action": {}, "sfx": ["riser"],
                                      "react": {}} for x in teaser]})
    for s in scenes:
        s.setdefault("kind", "story")
        for c in s["cast"]:
            c["hidden"] = False

    log("    Hindi")
    beats = [b for s in scenes for b in s["beats"]]
    pairs = [(b["speaker"], b["say_en"]) for b in beats]
    names = name_spellings(pairs, bible, sdir)
    hindi = translate(pairs, bible, names=names)
    for b, h in zip(beats, hindi):
        b["say_hi"] = h
    wrong = []
    for round_ in range(2):   # meaning check, then names; anything still wrong goes to the review
        bad = {int(w["n"]) - 1: w.get("why", "") for w in check_meaning(beats)}
        for k, b in enumerate(beats):
            lost = missing_names(b["say_en"], b["say_hi"], names)
            if lost:
                bad[k] = (bad.get(k, "") + " names: " + ", ".join(f"{a} = {h}" for a, h in lost)).strip()
        if not bad:
            break
        wrong += list(bad)
        for k, why in bad.items():
            b = beats[k]
            lost = missing_names(b["say_en"], b["say_hi"], names)
            hint = f"ध्यान दें: {why}" + ("" if not lost else " | नाम: " + ", ".join(
                (f"'{h}' मत लिखो" if a.startswith("not ") else f"ठीक ऐसे लिखो: {h}") for a, h in lost))
            again = translate([(b["speaker"], b["say_en"])], bible, context=hint, names=names)[0]
            if again:
                b["say_hi"] = again
            if round_ == 1 and (missing_names(b["say_en"], b["say_hi"], names)):
                review.append(f"- CHECK the Hindi of: {b['say_en']}\n  - {b['say_hi']} ({why[:100]})")
    for s in scenes:
        s["beats"] = [b for b in s["beats"] if b.get("say_hi")]
    scenes = [s for s in scenes if s["beats"]]

    # length: drop narrator lines from the longest scene until it fits
    def words():
        return sum(len(b["say_hi"].split()) for s in scenes for b in s["beats"])
    while words() > MAX_WORDS:
        story = [s for s in scenes if s["kind"] == "story"]
        longest = max(story, key=lambda s: sum(len(b["say_hi"].split()) for b in s["beats"]))
        cut = next((b for b in reversed(longest["beats"][1:-1]) if b["speaker"] == "narrator"), None) \
            or (longest["beats"][-2] if len(longest["beats"]) > 2 else None)
        if not cut:
            break
        longest["beats"].remove(cut)
        review.append(f"- Cut for length: {cut['say_en']}")

    log("    captions")
    for s in scenes:
        for b in s["beats"]:
            b["say"] = screen_text(b["say_hi"])
            b["say_from"] = b["say_hi"]
    fixed, unsure = english_pass(scenes, log=log)
    review += [f"- On screen: {u}" for u in unsure]

    folder = ep_dir(sdir, n)
    os.makedirs(folder, exist_ok=True)
    script = {"series": series["title"], "n": n, "title": ep["title"], "title_hi": ep.get("title_hi", ""),
              "arc": ep["arc"], "next_title": nxt["title"] if nxt else "", "written": now(), "scenes": scenes}
    jsave(os.path.join(folder, "script.json"), script)
    with open(os.path.join(folder, "review.md"), "w", encoding="utf-8") as f:
        f.write(f"# Episode {n}: {ep['title']}\n\nEvery line has say_en (the story, English) and say_hi (the voice). "
                f"Read both in script.json before voicing. After editing, run: python serial.py remember "
                f"{series['slug']} {n}\n\n## Plan\n{plan_text}\n\n## Script (English)\n")
        for s in scenes:
            f.write(f"\n### {s['kind']}: {bible['places'].get(s['place'], {}).get('name', s['place'])}, {s['time']}\n")
            for b in s["beats"]:
                f.write(f"- **{b['speaker']}**: {b['say_en']}\n  - {b['say_hi']}\n")
        f.write("\n## Continuity and edits\n" + ("\n".join(review) if review else "- nothing found") + "\n")
    log(f"    {words()} words, {len(beats)} lines, {len(issues)} continuity fixes, {len(set(wrong))} retranslated")
    remember(sdir, n)
    plan = jload(os.path.join(sdir, "plan.json"))
    for e in plan["episodes"]:
        if e["n"] == n:
            e["status"] = "written"
    jsave(os.path.join(sdir, "plan.json"), plan)
    return folder


SUMMARISER = ("You keep the memory of a long serial. Everything you write is in ENGLISH. From this episode script give: "
              "a summary (80-130 words); how it ended (one sentence); 6-16 facts worth remembering later (events, who now "
              "knows what, promises, boons, curses, secrets, injuries, deaths, gifts, weapons, relationships, where people "
              "went), each with the character ids involved; each character's status now; story threads opened and "
              "closed; and the updated story so far (at most 350 words: the whole story up to now, the most recent part "
              "in the most detail).\n"
              'JSON: {"summary": "...", "ending": "...", "facts": [{"kind": "event|state|relation|place|object|promise|secret", '
              '"text": "...", "chars": ["id"]}], "characters": {"id": {"status": "alive|dead|missing|captive", "where": '
              '"...", "notes": "..."}}, "threads_opened": ["..."], "threads_closed": ["..."], "story_so_far": "..."}')


def remember(sdir, n):
    """Write (or rewrite, after an edit) what episode n added to the story's memory."""
    script = jload(os.path.join(ep_dir(sdir, n), "script.json"))
    mem = Memory(sdir)
    listing = "\n".join(f"{b['speaker']}: {b.get('say_en') or b['say_hi']}" for s in script["scenes"]
                        if s.get("kind") == "story" for b in s["beats"])
    prior = mem.state.get("story_so_far", "")
    data = llm(SUMMARISER, f"STORY SO FAR (before this episode):\n{prior or '(this is the first episode)'}\n\nOPEN THREADS:\n"
               + "\n".join(mem.state.get("open_threads", [])) + f"\n\nEPISODE {n}: {script['title']}\n{listing}",
               max_tokens=3000, ctx=16384, temperature=0.2,
               check=lambda d: d.get("summary") and isinstance(d.get("facts"), list)
               and not re.search(r"[ऀ-ॿ]", str(d.get("summary")) + str(d.get("story_so_far"))))
    mem.forget_episode(n)
    mem.add(n, [f for f in data.get("facts") or [] if isinstance(f, dict)])
    st = mem.state
    st["episodes"][str(n)] = {"title": script["title"], "summary": data["summary"], "ending": data.get("ending", "")}
    latest = max(int(k) for k in st["episodes"])
    if n >= latest:   # only the newest episode moves the story forward
        st["last_episode"] = {"n": n, "title": script["title"], "summary": data["summary"], "ending": data.get("ending", "")}
        st["story_so_far"] = str(data.get("story_so_far") or prior)
        for cid, c in (data.get("characters") or {}).items():
            if isinstance(c, dict):
                st["characters"][cid] = {k: str(v) for k, v in c.items() if k in ("status", "where", "notes")}
        closed = {str(x).lower() for x in data.get("threads_closed") or []}
        st["open_threads"] = [t for t in st.get("open_threads", [])
                              if not any(difflib.SequenceMatcher(None, t.lower(), c).ratio() > 0.6 for c in closed)]
        st["open_threads"] += [str(x) for x in data.get("threads_opened") or []]
        st["open_threads"] = st["open_threads"][-25:]
    mem.save_state()
    log(f"    memory: {len(data.get('facts') or [])} facts saved")
