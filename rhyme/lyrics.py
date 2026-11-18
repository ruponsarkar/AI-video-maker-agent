"""
Lyrics for a rhyme: writing a new one (gemma), checking it (rhyme, line length, words for small children),
reading lyrics.txt and turning it into script.json for the voice and the video.

lyrics.txt (yours to edit; it is the only place the words live):

    title: Haathi Raja Ki Sair
    tempo: 100
    key: C

    [verse]                            <- or [verse place=pond cast=frog,duck] to choose the picture yourself
    हाथी राजा झूम के चलते
    ...
    [chorus]
    ...
    [chorus]                           <- an empty [chorus] repeats the last chorus
    Any line can end with " | Roman text" to set the on-screen spelling yourself.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)
from critters import KINDS  # noqa: E402
from stage import PLACES  # noqa: E402

AKSHARA = re.compile(r"(?:[क-हक़-य़]़?(?:्[क-हक़-य़]़?)*"
                     r"[ा-ौॅॉ]?[ँ-ः]?|[अ-औ][ँ-ः]?)")
DEVANAGARI = re.compile(r"[ऀ-ॿ]")
ENDINGS = {"है", "हैं", "था", "थी", "थे", "रे", "जी", "हो", "री", "भई", "रहा", "रही", "रहे"}
NOT_FOR_KIDS = {"मार", "मारो", "मारा", "मारेंगे", "डर", "डरा", "डरो", "खून", "भूत", "चुड़ैल", "मर", "मरा", "मरो", "मौत",
                "पिटाई", "सज़ा", "सजा", "ज़हर", "जहर", "चाकू", "बंदूक", "गोली", "शराब"}
# Hindi words -> who is in the picture
WHO = {"fish": ["मछली", "मछलियाँ", "मछलियां", "मछलियों", "मछलीरानी"], "elephant": ["हाथी"],
       "cat": ["बिल्ली", "बिल्लियाँ", "म्याऊँ", "म्याऊं", "मौसी"], "dog": ["कुत्ता", "कुत्ते", "पिल्ला", "पिल्ले", "भौं"],
       "rabbit": ["खरगोश"], "frog": ["मेंढक", "मेढक", "मेंढ़क", "टर्र"], "duck": ["बत्तख", "बतख", "बत्तखें"],
       "cow": ["गाय", "गैया", "गायें", "बछड़ा"], "lion": ["शेर", "शेरू"], "monkey": ["बंदर", "बन्दर", "बंदरिया"],
       "butterfly": ["तितली", "तितलियाँ", "तितलियां"], "sun": ["सूरज", "सूर्य", "धूप"],
       "moon": ["चंदा", "चंदामामा", "चाँद", "चांद", "चन्दा", "चंदा मामा"], "star": ["तारा", "तारे", "तारों", "सितारे"],
       "peacock": ["मोर", "मोरनी"], "parrot": ["तोता", "तोते", "मिट्ठू"],
       "train": ["रेल", "रेलगाड़ी", "छुक", "छुक-छुक", "इंजन", "ट्रेन", "गाड़ी"],
       "boy": ["मुन्ना", "बेटा", "राजा बेटा", "बच्चे", "बच्चा", "बच्चों"], "girl": ["मुन्नी", "गुड़िया", "दीदी", "बिटिया", "रानी बिटिया"]}
WHO_ROMAN = {"fish": ["machhli", "machli"], "elephant": ["haathi", "hathi"], "cat": ["billi"], "dog": ["kutta", "pilla"],
             "rabbit": ["khargosh"], "frog": ["mendhak", "medhak"], "duck": ["battakh", "batakh"], "cow": ["gaay", "gaiya", "gai"],
             "lion": ["sher"], "monkey": ["bandar"], "butterfly": ["titli"], "sun": ["suraj", "sooraj"],
             "moon": ["chanda", "chand", "chaand"], "star": ["tara", "taare", "tare"], "peacock": ["mor"],
             "parrot": ["tota", "mitthu"], "train": ["rail", "train", "gaadi", "gadi"], "boy": ["munna"], "girl": ["munni", "gudiya"]}
WHERE = {"underwater": ["समुंदर", "सागर", "समंदर"], "pond": ["तालाब", "पोखर", "नदी", "झील", "जल", "पानी"],
         "jungle": ["जंगल", "वन"], "farm": ["खेत", "गाँव", "गांव", "खलिहान"], "sky": ["आसमान", "आकाश", "बादल", "बादलों"],
         "night": ["रात", "सोजा", "नींद", "लोरी", "सपने"], "garden": ["बगीचा", "बगिया", "बाग", "फूल", "फूलों"],
         "beach": ["रेत", "किनारे", "लहरें"], "room": ["घर", "कमरा", "स्कूल", "कमरे"], "rail": ["स्टेशन", "पटरी"]}
# English words in titles ("Lion Ki Ladoo"): the title's animal is the song's main character
WHO_EN = {"fish": ["fish", "fishy"], "elephant": ["elephant"], "cat": ["cat", "kitten", "kitty"], "dog": ["dog", "puppy"],
          "rabbit": ["rabbit", "bunny"], "frog": ["frog"], "duck": ["duck", "duckling"], "cow": ["cow", "calf"],
          "lion": ["lion", "cub"], "monkey": ["monkey"], "butterfly": ["butterfly"], "sun": ["sun", "sunshine"],
          "moon": ["moon"], "star": ["star", "stars"], "peacock": ["peacock"], "parrot": ["parrot"],
          "train": ["train", "engine"], "boy": ["boy"], "girl": ["girl"]}
HOME = {"fish": "underwater", "frog": "pond", "duck": "pond", "cow": "farm", "lion": "jungle", "monkey": "jungle",
        "elephant": "jungle", "moon": "night", "star": "night", "train": "rail", "butterfly": "garden", "sun": "sky",
        "peacock": "garden", "parrot": "jungle", "rabbit": "garden", "cat": "room", "dog": "garden"}
MAX_CAST = 3


def kinds_in_title(title):
    t = title.lower()
    found = []
    for kind in KINDS:
        keys = WHO_ROMAN.get(kind, []) + WHO_EN.get(kind, [])
        pos = [m.start() for k in keys for m in [re.search(rf"\b{k}\b", t)] if m]
        if pos:
            found.append((min(pos), kind))
    return [k for _, k in sorted(found)]


# ------------------------------------------------------------------ checks
def aksharas(text):
    return AKSHARA.findall(re.sub(r"[^ऀ-ॿ ]", " ", text))


def words(text):
    return re.findall(r"[ऀ-ॿ]+", text)


def rhymes(a, b):
    """'strong', 'weak' or None: do two lines end with the same sound?"""
    wa, wb = words(a), words(b)
    while len(wa) > 1 and len(wb) > 1 and wa[-1] == wb[-1] and wa[-1] in ENDINGS:
        wa, wb = wa[:-1], wb[:-1]
    if not wa or not wb:
        return None
    ka, kb = aksharas(wa[-1]), aksharas(wb[-1])
    if not ka or not kb:
        return None
    plain = lambda s: s.replace("ं", "").replace("ँ", "")  # noqa: E731
    if plain(ka[-1]) != plain(kb[-1]):
        # same vowel + same final consonant sound (मोर / चोर -> 'र' after 'ो') counts too
        vowel = lambda k: (re.findall(r"[\u093E-\u094C]", k) or ["a"])[-1]  # noqa: E731
        if not (len(ka) > 1 and len(kb) > 1 and vowel(ka[-1]) == vowel(kb[-1]) and ka[-1][0] == kb[-1][0]):
            return None
    if wa[-1] == wb[-1]:
        return "weak"
    vowel = lambda k: (re.findall(r"[\u093E-\u094C]", k) or ["a"])[-1]  # noqa: E731
    return "strong" if len(ka) > 1 and len(kb) > 1 and vowel(ka[-2]) == vowel(kb[-2]) else "weak"


def check(sections):
    """Problems a person should look at, and a score (higher is better)."""
    problems, score = [], 0
    seen = {}
    for k, s in enumerate(sections):
        label = f"{s['kind']} {k + 1}"
        lines = [x["hi"] for x in s["lines"]]
        if len(lines) < 2:
            problems.append(f"{label}: only {len(lines)} line(s)")
            score -= 3
        for line in lines:
            if re.search(r"[A-Za-z]", line) or not DEVANAGARI.search(line):
                problems.append(f"{label}: not all Devanagari: {line}")
                score -= 3
            n = len(aksharas(line))
            if not 5 <= n <= 18:
                problems.append(f"{label}: line is {'too short' if n < 5 else 'too long'} to sing ({n} syllables): {line}")
                score -= 1
            bad = [w for w in words(line) if w in NOT_FOR_KIDS]
            if bad:
                problems.append(f"{label}: word(s) not for small children ({', '.join(bad)}): {line}")
                score -= 4
            if s["kind"] != "chorus" and line in seen and seen[line] != k:
                problems.append(f"{label}: line repeats an earlier verse: {line}")
                score -= 2
            seen.setdefault(line, k)
        sizes = [len(aksharas(x)) for x in lines]
        if sizes and max(sizes) - min(sizes) > 6:
            problems.append(f"{label}: lines very different in length ({sizes}), hard to sing to one tune")
            score -= 1
        # ABCB (lines 2 and 4 rhyme) or AABB (1 with 2, 3 with 4): both are usual in bal geet
        if len(lines) >= 4:
            abcb = rhymes(lines[1], lines[3])
            aabb = [rhymes(lines[0], lines[1]), rhymes(lines[2], lines[3])]
            if abcb or all(aabb):
                found = [abcb] if abcb else aabb
                score += sum(2 if r == "strong" else 1 for r in found) // len(found) + (1 if all(aabb) or
                                                                                      rhymes(lines[0], lines[2]) else 0)
            else:
                problems.append(f"{label}: no rhyme (lines 2 and 4, or 1-2 and 3-4): {' / '.join(lines[:4])}")
                score -= 2
        elif len(lines) >= 2:
            if rhymes(lines[-2], lines[-1]):
                score += 2
            else:
                problems.append(f"{label}: the last two lines don't rhyme: {lines[-2]} / {lines[-1]}")
                score -= 2
    return problems, score


# ------------------------------------------------------------------ lyrics.txt
def read(path):
    """lyrics.txt -> {"title", "tempo", "key", "sections": [{"kind", "place", "cast", "lines": [{"hi", "roman"}]}]}"""
    song = {"title": "", "tempo": 100, "key": "C", "sections": []}
    chorus = None
    current = None
    for raw in open(path, encoding="utf-8"):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        head = re.match(r"^\[(\w+)([^\]]*)\]$", line)
        if head:
            kind = head.group(1).lower()
            kind = "chorus" if kind in ("chorus", "mukhda", "refrain") else "verse"
            opts = dict(re.findall(r"(\w+)=([\w,]+)", head.group(2)))
            current = {"kind": kind, "lines": [], "place": opts.get("place"),
                       "cast": [c for c in opts.get("cast", "").split(",") if c]}
            song["sections"].append(current)
            continue
        meta = re.match(r"^(title|tempo|key|title_hi|about)\s*:\s*(.+)$", line, re.I)
        if meta and current is None:
            key, value = meta.group(1).lower(), meta.group(2).strip()
            song[key] = int(value) if key == "tempo" and value.isdigit() else value
            continue
        if current is None:
            current = {"kind": "verse", "lines": [], "place": None, "cast": []}
            song["sections"].append(current)
        hi, _, roman = line.partition("|")
        current["lines"].append({"hi": hi.strip(), "roman": roman.strip()})
    for s in song["sections"]:   # an empty [chorus] repeats the last one
        if s["kind"] == "chorus":
            if s["lines"]:
                chorus = s
            elif chorus:
                s["lines"] = [dict(x) for x in chorus["lines"]]
                s["place"] = s["place"] or chorus["place"]
                s["cast"] = s["cast"] or list(chorus["cast"])
    song["sections"] = [s for s in song["sections"] if s["lines"]]
    song["tempo"] = max(70, min(140, int(song.get("tempo") or 100)))
    return song


def write_file(path, song, note=""):
    out = ["# Rhyme lyrics: edit freely, then run: python rhyme.py make <slug>",
           "# Devanagari = what is sung. Add ' | Roman' after a line to set the on-screen spelling yourself.",
           f"# Choose the picture per section: [verse place=pond cast=frog,duck]",
           f"#   places: {' '.join(PLACES)}",
           f"#   cast:   {' '.join(KINDS)}",
           "# An empty [chorus] repeats the last chorus.", *([f"# {note}"] if note else []), "",
           f"title: {song['title']}", *([f"about: {song['about']}"] if song.get("about") else []),
           f"tempo: {song.get('tempo', 100)}", f"key: {song.get('key', 'C')}", ""]
    chorus_seen = None
    for s in song["sections"]:
        opts = (f" place={s['place']}" if s.get("place") else "") + (f" cast={','.join(s['cast'])}" if s.get("cast") else "")
        out.append(f"[{s['kind']}{opts}]")
        same = s["kind"] == "chorus" and chorus_seen == [x["hi"] for x in s["lines"]]
        if not same:
            out += [x["hi"] + (f" | {x['roman']}" if x.get("roman") else "") for x in s["lines"]]
            if s["kind"] == "chorus":
                chorus_seen = [x["hi"] for x in s["lines"]]
        out.append("")
    open(path, "w", encoding="utf-8").write("\n".join(out))


# ------------------------------------------------------------------ writing a new rhyme
# hand-checked rhyming word pairs children know: the small model rhymes far better when it picks line endings from these
RHYME_PAIRS = ["रानी / पानी", "गाना / खाना", "खेल / मेल", "मोर / शोर", "छोटा / मोटा", "आओ / गाओ", "प्यारा / न्यारा",
               "दाना / नाना", "चलो / मिलो", "डाल / ताल", "लाल / गाल", "हरा / भरा", "धूप / रूप", "तारे / सारे",
               "नाचे / बाँचे", "झूले / फूले", "पेड़ / भेड़", "बादल / पागल", "कूदा / सोया", "उछले / मचले", "रात / बात",
               "सुबह / जगह", "जागो / भागो", "मामा / जामा", "दूध / शुद्ध", "हाथ / साथ", "नहाए / गाए", "आया / लाया",
               "दोस्त / रोज़", "किनारे / सहारे", "चमके / दमके", "छलांग / टाँग", "टर्र / फर्र", "गोल / बोल",
               "मीठा / सीठा", "थैया / भैया", "ढोल / बोल", "फूल / झूल", "रंग / संग", "चूँ / क्यूँ"]
RHYME_PAIRS = [p for p in RHYME_PAIRS if p not in ("मीठा / सीठा", "दूध / शुद्ध", "दोस्त / रोज़", "कूदा / सोया", "बादल / पागल",
                                                 "मामा / जामा")]
WRITER = """You write ORIGINAL Hindi nursery rhymes (bal geet) for children aged 2 to 6, to be sung to a simple tune.
Rules:
- Write in Devanagari only. Very simple, everyday Hindi words a 3-year-old knows. No English words.
- 3 verses and 1 chorus. Each has exactly 4 short lines, 4 to 7 words per line, all lines about the same length.
- In every verse and in the chorus, line 2 and line 4 MUST rhyme (end with the same sound, like रानी / पानी,
  चलते / मिलते, गाना / खाना). Lines 1 and 3 should rhyme too if you can.
- Easiest: end lines 2 and 4 with a pair from this list: {pairs}
- Every line must make sense: animals only do what they really do (a frog says टर्र-टर्र, a cat says म्याऊँ).
- Playful sounds children love are good (छुक-छुक, टर्र-टर्र, म्याऊँ, ता-ता थैया).
- Warm, happy and safe: no fear, no fighting, no hurting, no punishment, no scary words. A small, gentle lesson is
  welcome (sharing, washing hands, counting, colours, kindness).
- Completely new words: do NOT copy or adapt any existing rhyme, poem or film song.
Answer in exactly this form and nothing else:
VERSE 1:
(4 lines)
CHORUS:
(4 lines)
VERSE 2:
(4 lines)
VERSE 3:
(4 lines)"""


def parse_model(text):
    parts, current = {}, None
    for raw in text.splitlines():
        line = raw.strip().strip("*").strip()
        head = re.match(r"^(verse|chorus|अंतरा|मुखड़ा)\s*(\d*)\s*[:：]?\s*$", line, re.I)
        if head:
            name = head.group(1).lower()
            current = "chorus" if name in ("chorus", "मुखड़ा") else f"verse{head.group(2) or len(parts) + 1}"
            parts[current] = []
            continue
        line = re.sub(r"\([^)]*[A-Za-z][^)]*\)", "", line)            # (Roman copy of the line)
        line = re.sub(r"^\(?\d+[.)]\s*", "", line).strip(" -–\"',")
        if current and DEVANAGARI.search(line) and not re.search(r"[A-Za-z]", line):
            parts[current].append(re.sub(r"[।.]+$", "", line).strip())
    verses = [parts[k][:4] for k in sorted(k for k in parts if k.startswith("verse"))][:3]
    chorus = parts.get("chorus", [])[:4]
    if len(verses) < 2 or not chorus:
        return None
    sections = []
    for v in verses:
        sections.append({"kind": "verse", "lines": [{"hi": x, "roman": ""} for x in v], "place": None, "cast": []})
        sections.append({"kind": "chorus", "lines": [{"hi": x, "roman": ""} for x in chorus], "place": None, "cast": []})
    return sections


def mend_rhymes(sections, title, log=print, model=None):
    """Ask once more for a last line that rhymes, where lines 2 and 4 don't."""
    from auto_video import WRITER_MODEL, llm
    model = model or WRITER_MODEL
    fixed_chorus = {}
    for s in sections:
        lines = s["lines"]
        if len(lines) < 4 or rhymes(lines[1]["hi"], lines[3]["hi"]) or (
                rhymes(lines[0]["hi"], lines[1]["hi"]) and rhymes(lines[2]["hi"], lines[3]["hi"])):
            continue
        key = tuple(x["hi"] for x in lines)
        if s["kind"] == "chorus" and key in fixed_chorus:
            lines[3]["hi"] = fixed_chorus[key]
            continue
        end = words(lines[1]["hi"])[-1] if words(lines[1]["hi"]) else ""
        for attempt in range(3):
            new = llm("Rewrite the LAST line of this Hindi children's rhyme so that it rhymes with line 2 (ends with the "
                      f"same sound as «{end}»), keeps the meaning simple and happy, and has about the same length. "
                      "Answer with the one new line in Devanagari only.",
                      f"Rhyme: {title}\n" + "\n".join(x["hi"] for x in lines), as_json=False, model=model,
                      max_tokens=80, temperature=0.6 + 0.2 * attempt, ctx=2048)
            new = next((re.sub(r"[।.]+$", "", x.strip(" \"'*-")) for x in new.splitlines() if DEVANAGARI.search(x)), "")
            if new and not re.search(r"[A-Za-z]", new) and rhymes(lines[1]["hi"], new):
                log(f"  rhyme fixed: {lines[3]['hi']} -> {new}")
                if s["kind"] == "chorus":
                    fixed_chorus[key] = new
                lines[3]["hi"] = new
                break


def write_new(title, about="", tries=4, log=print, model=None):
    """A new original rhyme: several drafts, the best by the checks, then one round of rhyme mending."""
    from auto_video import WRITER_MODEL, llm
    model = model or WRITER_MODEL
    best = None
    who = kinds_in_title(title)
    hint = "".join(f"\nMain character: a {k}, called «{WHO[k][0]}» in Hindi. Use the word «{WHO[k][0]}» (not an "
                   f"English name) in the verses and the chorus, so every child knows who the song is about."
                   for k in who if k in WHO)
    for attempt in range(tries):
        text = llm(WRITER.replace("{pairs}", ", ".join(RHYME_PAIRS)), f"Title: {title}\nWhat it is about: {about or title}{hint}\n"
                   "Write only the Devanagari lines, no Roman copy.", as_json=False, model=model,
                   max_tokens=900, temperature=0.75 + 0.1 * attempt, ctx=4096)
        sections = parse_model(text)
        if not sections:
            log(f"  draft {attempt + 1}: couldn't read it, trying again")
            continue
        problems, score = check(sections)
        log(f"  draft {attempt + 1}: score {score}, {len(problems)} thing(s) to look at")
        if best is None or score > best[0]:
            best = (score, sections)
        if not problems:
            break
    if not best:
        raise SystemExit("The model didn't write a rhyme in the expected form. Run again, or write lyrics.txt yourself "
                         "(python rhyme.py new \"Title\" --lyrics my_lyrics.txt).")
    sections = best[1]
    mend_rhymes(sections, title, log, model)
    return sections


def mend_unclear(song, story, log=print, model=None):
    """New drafts only (never your edited lyrics): a line the story checker found senseless is written again ONCE,
    told what the verse is about; the new line must still rhyme where the old one had to. Returns lines changed."""
    from auto_video import WRITER_MODEL, llm
    model = model or WRITER_MODEL
    changed = 0
    bad = {(x["section"], x["line"]): x for x in story["lines"] if not x["clear"]}
    done = {}
    for i, s in enumerate(song["sections"]):
        lines = s["lines"]
        for j, ln in enumerate(lines):
            x = bad.get((i, j))
            if not x:
                continue
            if ln["hi"] in done:      # the same chorus line again: same fix
                ln["hi"] = done[ln["hi"]]
                continue
            partner = {1: 3, 3: 1}.get(j)
            must = lines[partner]["hi"] if partner is not None and partner < len(lines) else ""
            context = "\n".join(("-> " if k == j else "   ") + y["hi"] for k, y in enumerate(lines))
            for attempt in range(3):
                new = llm("You fix ONE line of a Hindi rhyme for children aged 2-6. Write the marked line again so it "
                          "makes clear, simple sense and fits the verse, about the same length, in simple Devanagari "
                          "Hindi (no English)." + (f" It MUST end with the same sound as «{words(must)[-1]}»."
                                                   if must and words(must) else "")
                          + " Answer with the one new line only.",
                          f"Song: {song['title']} ({song.get('about', '')})\nWhat the song is about: {story['summary']}\n"
                          f"Problem with the line: {x['problem'] or 'it makes no sense'}\n\n{context}",
                          as_json=False, model=model, max_tokens=80, temperature=0.5 + 0.2 * attempt, ctx=2048)
                new = next((re.sub(r"[।.]+$", "", y.strip(" \"'*-")) for y in new.splitlines() if DEVANAGARI.search(y)), "")
                if new and not re.search(r"[A-Za-z]", new) and (not must or rhymes(must, new)):
                    log(f"  line {x['n']} rewritten: {ln['hi']} -> {new}")
                    done[ln["hi"]] = new
                    ln["hi"], ln["roman"] = new, ""
                    changed += 1
                    break
    return changed


def from_text(path):
    """Your own lyrics, from a plain text file: stanzas split by blank lines (or the lyrics.txt form)."""
    text = open(path, encoding="utf-8").read()
    if re.search(r"^\[(verse|chorus)", text, re.I | re.M):
        return read(path)["sections"]
    out = []
    for block in re.split(r"\n\s*\n", text.strip()):
        lines = [x.strip() for x in block.splitlines() if x.strip() and DEVANAGARI.search(x)]
        if lines:
            out.append({"kind": "verse", "lines": [{"hi": x, "roman": ""} for x in lines], "place": None, "cast": []})
    return out


# ------------------------------------------------------------------ the picture for each section
def find_cast(text):
    toks = set(words(text))
    joined = " " + " ".join(words(text)) + " "
    found = []
    for kind, keys in WHO.items():
        for k in keys:
            if k in toks or (" " in k and f" {k} " in joined):
                found.append((joined.find(k), kind))
                break
    return [k for _, k in sorted(found)]


def find_place(text):
    toks = set(words(text))
    for place, keys in WHERE.items():
        if any(k in toks for k in keys):
            return place
    return None


def plan(song, story=None):
    """Fill place and cast for each section (yours in lyrics.txt always win). With story.json (rhyme/story.py: what
    each line means and who is in it) the cast comes from there; without it, from the words."""
    if story:
        song["main"] = story.get("main", [])
        by_section = {}
        for x in story["lines"]:
            by_section.setdefault(x["section"], []).append(x)
        for i, s in enumerate(song["sections"]):
            rows = by_section.get(i, [])
            fixed = [c for c in s.get("cast") or [] if c in KINDS]   # yours in lyrics.txt: every line uses it
            if not s.get("cast"):
                who = [k for x in rows for k in x["who"]]
                main = [k for k in story.get("main", []) if k in who]
                s["cast"] = list(dict.fromkeys(main + sorted(who, key=who.count, reverse=True)))[:MAX_CAST] or ["boy", "girl"]
            if not s.get("place") or s["place"] not in PLACES:
                wheres = [x["where"] for x in rows]
                s["place"] = max(set(wheres), key=wheres.count) if wheres else HOME.get(s["cast"][0], "garden")
            for x in rows:   # per line: the picture plan reads these (pictures.py)
                if x["line"] < len(s["lines"]):
                    s["lines"][x["line"]]["story"] = {"who": fixed[:MAX_CAST] or x["who"], "where": x["where"],
                                                      "doing": x["doing"], "meaning": x["meaning"]}
        return song
    kinds = kinds_in_title(song["title"])
    lead = kinds[0] if kinds else None
    everyone = find_cast(" ".join(x["hi"] for s in song["sections"] for x in s["lines"]))
    lead = lead or (everyone[0] if everyone else None)
    prev_place, prev_cast = None, []
    for s in song["sections"]:
        text = " ".join(x["hi"] for x in s["lines"])
        cast = [c for c in s.get("cast") or [] if c in KINDS]
        if not cast:
            cast = find_cast(text) or list(prev_cast)
            if lead and lead not in cast and (s["kind"] == "chorus" or not cast):
                cast = [lead] + cast
            if not cast:
                cast = ["boy", "girl"]
        cast = list(dict.fromkeys(cast))[:MAX_CAST]
        place = s.get("place") if s.get("place") in PLACES else None
        if not place:
            place = find_place(text)
            if "fish" in cast:
                place = "underwater"
            elif "train" in cast:
                place = "rail"
            place = place or HOME.get(cast[0]) or prev_place or "garden"
        s["cast"], s["place"] = cast, place
        prev_place, prev_cast = place, cast
    return song


def to_script(song, roman_of):
    """script.json in the form voice_run.py reads (scenes of beats spoken by 'singer')."""
    scenes = []
    for s in song["sections"]:
        beats = [dict({"say_hi": x["hi"], "say": x.get("roman") or roman_of(x["hi"]), "speaker": "singer",
                       "emotion": "happy"}, **({"story": x["story"]} if x.get("story") else {}))
                 for x in s["lines"]]
        scenes.append({"kind": s["kind"], "place": s["place"], "cast": s["cast"], "beats": beats})
    return {"title": song["title"], "n": 1, "tempo": song["tempo"], "key": song.get("key", "C"), "scenes": scenes,
            **({"main": song["main"]} if song.get("main") else {})}
