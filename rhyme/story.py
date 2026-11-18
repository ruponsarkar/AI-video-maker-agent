"""
What a rhyme MEANS, before any picture is made: two local agents (qwen3:8b) read the title, the idea and the lyrics.

  1. the explainer: in plain words, what the rhyme is about and its lesson, who is who ("Leo" -> the lion), and for
     every line: what it means, who is in it, where it happens, and what we SEE happen (the picture and the clip
     are made from this).
  2. the checker: reads the Hindi again next to the explainer's answer and corrects it (a character named in a
     line but missing from it, a meaning that isn't what the words say, a line that makes no sense).

Then code rules: only characters we can draw, a character named in a line is always in its picture, the main
character is in the title picture, at most 3 per picture.

    rhymes/songs/<slug>/story.md     <- read this first: the rhyme in plain words, line by line
    rhymes/songs/<slug>/story.json   <- what pictures.py / clips.py use. Edit it to correct a line (your edits stay
                                        until the lyrics change), or delete it to ask the agents again.

    python rhyme.py story <slug>     # (make, pictures and new run it for you)
"""
import hashlib
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

VERSION = 2          # bump when the agents' instructions change: every song is explained again once
MAX_WHO = 3
PEOPLE_WORDS = r"\b(children|child|kids?|boys?|girls?|people|persons?|friends|everyone|everybody|crowd|baby|babies|" \
               r"golu|chinki|mother|father|mummy|papa|others|another (?:child|kid|boy|girl))\b"


def lines_of(song):
    out = []
    for i, s in enumerate(song["sections"]):
        for j, x in enumerate(s["lines"]):
            out.append({"n": len(out) + 1, "section": i, "line": j, "kind": s["kind"], "hi": x["hi"],
                        "roman": x.get("roman", "")})
    return out


def key_of(song):
    text = song["title"] + "|" + song.get("about", "") + "|" + "\n".join(x["hi"] for x in lines_of(song))
    return hashlib.md5(f"{VERSION}|{text}".encode()).hexdigest()


def path_of(folder):
    return os.path.join(folder, "story.json")


def load(folder, song):
    """story.json if it belongs to these lyrics (None: the lyrics changed, or no story yet)."""
    p = path_of(folder)
    if not os.path.exists(p):
        return None
    data = json.load(open(p, encoding="utf-8"))
    return data if data.get("lyrics_key") == key_of(song) else None


def cast_list():
    import pictures
    chars = pictures.load_cast()["characters"]
    return "\n".join(f"- {k}: {chars[k]['name']}, {chars[k]['look'][:70]}" for k in KINDS if k in chars)


EXPLAIN = """You explain a Hindi children's rhyme in plain, simple English, so that a video maker can draw it.
Read the title, the idea and every line. Then answer JSON:
{
 "summary": "3-5 simple sentences: what happens in the rhyme, from start to end, and what it means",
 "lesson": "the small lesson or feeling for children (one sentence), or empty",
 "characters": [{"kind": "one kind from the list", "called": ["every name or word the song uses for it, as written in
   the lyrics, e.g. लियो, Leo"], "main": true or false}],
 "lines": [{"n": 1, "meaning": "what this line means, in plain English",
            "who": ["kinds that are in this line's picture"], "where": "one place from the list",
            "doing": "what we SEE happen, one short visual sentence with the kind words (e.g. 'the lion cub eats
             a round yellow ladoo and licks his lips')", "clear": true or false,
            "problem": "if not clear: what is wrong with the words, else empty"}]
}
Rules:
- kinds: ONLY these: {kinds}. A character the song calls by a name (Leo, Sheru, Raja...) is mapped to its kind:
  the title and the idea tell you what it is (Lion Ki Ladoo -> the lion). The title's animal is the main character.
- who: the characters this line is about. If the line names a character or speaks about it (he, she, his...), it
  is in who. If the line names nobody, use the main character. Add children (boy = Golu, girl = Chinki) only when
  the line is really about children. Never more than 3.
- where: ONLY one of: {places}. Keep the same place for lines that continue the same moment.
- doing: something a cartoon can show, done only by the characters in who. Concrete: eating, dancing, jumping,
  holding something, looking at something. No words like 'joy' or 'happiness' alone: show it (smiles, claps).
- clear = false when the words make no sense, are not real Hindi, or say something odd for children; say why.
- One entry in "lines" for EVERY numbered line, in order, with the same n."""

CHECK = """You are the checker. Below are a Hindi children's rhyme and another person's explanation of it (JSON).
Read every Hindi line again yourself, and correct the JSON:
- each "meaning" must be what the Hindi words really say (not a guess from the title);
- every character named or meant in a line must be in that line's "who" (names: see "characters");
- the main character must be the title's character (Lion Ki Ladoo -> lion), mapped from its song name;
- "doing" must show the meaning and use only the characters in "who";
- "clear" false (with "problem") for lines whose words make no sense.
Kinds allowed: {kinds}. Places allowed: {places}.
Answer with the full corrected JSON, same form, every line."""


def ask(system, user, n_lines):
    from auto_video import MODEL, llm

    def ok(d):
        return (isinstance(d, dict) and isinstance(d.get("lines"), list) and len(d["lines"]) >= n_lines
                and isinstance(d.get("characters"), list))
    return llm(system, user, model=MODEL, max_tokens=3500, ctx=8192, temperature=0.3, check=ok)


HINDI = ("You are a Hindi teacher checking a children's rhyme. For each numbered line decide: is it correct, meaningful "
         "Hindi that a 4-year-old Indian child would understand? Made-up words, broken grammar, or a line that means "
         "nothing -> ok false. Answer JSON {\"lines\": [{\"n\": 1, \"ok\": true/false, \"why\": \"short reason in "
         "English\"}]}")


def hindi_check(song):
    """Agent 3, gemma (its Hindi is better than qwen's): does every line make sense as Hindi? {hi: why} for the bad."""
    from auto_video import WRITER_MODEL, llm
    uniq = list(dict.fromkeys(x["hi"] for x in lines_of(song)))
    try:
        d = llm(HINDI, "\n".join(f"{i + 1}. {x}" for i, x in enumerate(uniq)), model=WRITER_MODEL, max_tokens=2000,
                temperature=0.1, check=lambda d: isinstance(d, dict) and isinstance(d.get("lines"), list))
    except Exception as e:  # noqa: BLE001
        print(f"  (Hindi check failed: {e})")
        return {}
    finally:
        try:
            import requests
            requests.post("http://localhost:11434/api/generate", json={"model": WRITER_MODEL, "keep_alive": 0}, timeout=20)
        except Exception:  # noqa: BLE001
            pass
    bad = {}
    for x in d["lines"]:
        if isinstance(x, dict) and x.get("ok") is False and str(x.get("n", "")).isdigit() and 0 < int(x["n"]) <= len(uniq):
            bad[uniq[int(x["n"]) - 1]] = str(x.get("why") or "not clear Hindi").strip()
    return bad


def tidy(data, song, title_kinds):
    """Code rules on top of the agents: only drawable kinds, named characters always in their line, main first."""
    lines = lines_of(song)
    chars = [c for c in data.get("characters", []) if isinstance(c, dict) and c.get("kind") in KINDS]
    for k in title_kinds:   # the title's animal is the main character, whatever the agents said
        if not any(c["kind"] == k for c in chars):
            chars.insert(0, {"kind": k, "called": [], "main": True})
    if title_kinds:
        for c in chars:
            c["main"] = c["kind"] in title_kinds
    if chars and not any(c.get("main") for c in chars):
        chars[0]["main"] = True
    main = [c["kind"] for c in chars if c.get("main")][:2]
    import lyrics
    names = {}
    for c in chars:   # the song's own words for each character: its names + the usual Hindi words
        for w in list(c.get("called") or []) + lyrics.WHO.get(c["kind"], []):
            w = str(w).strip().lower()
            if w and len(w) > 1:
                names[w] = c["kind"]
    got = {int(x.get("n", 0)): x for x in data["lines"] if isinstance(x, dict) and str(x.get("n", "")).isdigit()}
    out, prev_where = [], None
    for ln in lines:
        x = got.get(ln["n"], {})
        who = [k for k in x.get("who", []) if k in KINDS] if isinstance(x.get("who"), list) else []
        text = f" {ln['hi']} {ln['roman']} ".lower()
        for w, k in names.items():   # named in the line -> in the picture
            if re.search(rf"(?<![\wऀ-ॿ]){re.escape(w)}(?![\wऀ-ॿ])", text) and k not in who:
                who.append(k)
        who = who or list(main) or ["boy", "girl"]
        who = sorted(dict.fromkeys(who), key=lambda k: (k not in main, who.index(k)))[:MAX_WHO]
        where = x.get("where") if x.get("where") in PLACES else (prev_where or lyrics.HOME.get(who[0]) or "garden")
        doing = re.sub(r"\s+", " ", str(x.get("doing") or "")).strip().rstrip(".")
        if not any(k in ("boy", "girl") for k in who):    # nobody else may walk into the clip
            doing = re.sub(PEOPLE_WORDS, "", doing, flags=re.I).replace("  ", " ").strip(" ,")
        out.append({"n": ln["n"], "section": ln["section"], "line": ln["line"], "kind": ln["kind"], "hi": ln["hi"],
                    "meaning": str(x.get("meaning") or "").strip(), "who": who, "where": where, "doing": doing,
                    "clear": x.get("clear", True) is not False, "problem": str(x.get("problem") or "").strip()})
        prev_where = where
    return {"summary": str(data.get("summary") or "").strip(), "lesson": str(data.get("lesson") or "").strip(),
            "characters": chars, "main": main, "lines": out}


def understand(folder, song, quiet=False):
    """The two agents, then the code rules. Saves story.json + story.md. Keeps an existing story for these lyrics."""
    have = load(folder, song)
    if have:
        return have
    import lyrics
    lines = lines_of(song)
    title_kinds = lyrics.kinds_in_title(song["title"])
    numbered = "\n".join(f"{x['n']}. [{x['kind']}] {x['hi']}" + (f"   ({x['roman']})" if x["roman"] else "")
                         for x in lines)
    user = (f"Title: {song['title']}\nIdea: {song.get('about') or '(none)'}\n"
            + (f"The title's character: {', '.join(title_kinds)}\n" if title_kinds else "")
            + f"Characters we can draw:\n{cast_list()}\n\nLyrics ({len(lines)} lines):\n{numbered}")
    fill = lambda t: t.replace("{kinds}", ", ".join(KINDS)).replace("{places}", ", ".join(PLACES))  # noqa: E731
    if not quiet:
        print("  story: the explainer reads the rhyme ...", flush=True)
    first = ask(fill(EXPLAIN), user, len(lines))
    if not quiet:
        print("  story: the checker reads it again ...", flush=True)
    try:
        checked = ask(fill(CHECK), user + "\n\nThe explanation to check:\n" + json.dumps(first, ensure_ascii=False),
                      len(lines))
    except Exception as e:  # noqa: BLE001
        print(f"  (checker failed: {e}; the explainer's answer is used)")
        checked = first
    unload()
    story = tidy(checked, song, title_kinds)
    if not quiet:
        print("  story: the Hindi checker reads every line ...", flush=True)
    import lyrics
    bad_words = {}
    for x in story["lines"]:   # words not for small children (lyrics.NOT_FOR_KIDS): always a problem
        hit = [w for w in lyrics.words(x["hi"]) if w in lyrics.NOT_FOR_KIDS]
        if hit:
            bad_words[x["hi"]] = f"not a word for small children: {', '.join(hit)}"
    for hi, why in {**hindi_check(song), **bad_words}.items():
        for x in story["lines"]:
            if x["hi"] == hi:
                x["clear"] = False
                x["problem"] = "; ".join(p for p in (x["problem"], why) if p)
    story["lyrics_key"], story["title"] = key_of(song), song["title"]
    json.dump(story, open(path_of(folder), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    write_md(folder, story)
    return story


def unload():
    try:
        import requests
        from auto_video import MODEL
        requests.post("http://localhost:11434/api/generate", json={"model": MODEL, "keep_alive": 0}, timeout=20)
    except Exception:  # noqa: BLE001
        pass


def unclear(story):
    return [x for x in story["lines"] if not x["clear"]]


def write_md(folder, story):
    import pictures
    chars = pictures.load_cast()["characters"]
    rows = [f"# {story['title']}: what this rhyme means", "",
            "Read this BEFORE the video is made. Pictures and clips are drawn from it. Wrong? Fix the line in "
            "lyrics.txt, or correct `meaning` / `who` / `doing` in story.json (kept until the lyrics change).", "",
            "## In plain words", "", story["summary"] or "(no summary)", ""]
    if story["lesson"]:
        rows += [f"**Lesson:** {story['lesson']}", ""]
    rows += ["## Characters", ""]
    for c in story["characters"]:
        name = chars.get(c["kind"], {}).get("name", c["kind"])
        called = ", ".join(c.get("called") or [])
        rows.append(f"- **{name}** the {c['kind']}" + (" (main character)" if c.get("main") else "")
                    + (f": called {called} in the song" if called else ""))
    bad = unclear(story)
    if bad:
        rows += ["", "## Lines that don't make sense (rewrite them in lyrics.txt)", ""]
        rows += [f"- [ ] {x['n']}. {x['hi']}: {x['problem'] or 'unclear'}" for x in bad]
    rows += ["", "## Line by line", ""]
    section = None
    for x in story["lines"]:
        if x["section"] != section:
            section = x["section"]
            rows += ["", f"**{x['kind'].capitalize()}**", ""]
        who = ", ".join(chars.get(k, {}).get("name", k) for k in x["who"])
        rows.append(f"{x['n']}. {x['hi']}" + ("  ⚠" if not x["clear"] else ""))
        rows.append(f"   - means: {x['meaning']}")
        rows.append(f"   - picture: {who} in the {x['where']}: {x['doing']}")
    open(os.path.join(folder, "story.md"), "w", encoding="utf-8").write("\n".join(rows) + "\n")


def print_summary(story):
    print(f"\n  What the rhyme means: {story['summary']}")
    if story["lesson"]:
        print(f"  Lesson: {story['lesson']}")
    print(f"  Main character: {', '.join(story['main']) or '-'}")
    bad = unclear(story)
    if bad:
        print(f"  {len(bad)} line(s) don't make sense: " + "; ".join(f"{x['n']}. {x['hi']}" for x in bad[:6]))


if __name__ == "__main__":
    import lyrics
    for f in sys.argv[1:]:
        s = lyrics.read(os.path.join(f, "lyrics.txt"))
        st = understand(f, s)
        print_summary(st)
