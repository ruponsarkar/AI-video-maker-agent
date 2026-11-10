"""
Snack Code - the script editor: a second agent that rechecks a script before any audio or video is made.

auto_video.py runs it on every new script. To run it on a script you've edited, from the video's folder:
    python ../../script_review.py

It uses the local model, so it runs offline, and it does three jobs:
    1. Word match: captions are remade from the Hindi the voice reads, so the two can't differ.
    2. Line edit: fixes grammar and wrong words, and makes each line easy for a first-time listener.
    3. Whole-script read: finds repeated, confusing or off-topic lines, then fixes or removes them.

An edit is only accepted if it keeps the same numbers, short forms and web addresses, and is still clearly the
same line. On news videos it must also keep words like "आरोप" and "कहना है", so a claim can't become a fact.
The editor can't check facts: a person still has to compare the script with the sources.

Writes:  scripts/script.json (the fixed script) and scripts/review_report.md (every change it made, and why).
"""
import difflib
import json
import os
import re
import sys

from glossary import TERMS
from hinglish import english_pass, fix_screen_text, screen_text

MODEL = "gemma3:4b"
ATTRIBUTION = re.compile(r"कहना है|कहा|आरोप|दावा|मुताबिक|बताया|अनुसार|मानना है|पक्का नहीं")
BOOKISH = re.compile(r"वैश्विक|प्रणाली|गंतव्य|अनुरोध|प्रदान|विभाजित|सुगम|उपकरण|आदान-प्रदान|सूचनाओं|उपयोगकर्ता|"
                     r"जटिल|सिद्धांत|संप्रेषण|अभिगम|माध्यम से|विभिन्न|उपलब्ध|महत्वपूर्ण")
LOADED = re.compile(r"चोर|गद्दार|देशद्रोही|निकम्मा|घटिया|बेवकूफ़?|देश का दुश्मन")
# an editor's comment about the script, which must never reach the voice
EDITOR_TALK = re.compile(r"वाक्य|अनावश्यक|अप्रासंगिक|इस लाइन|ये लाइन|यह लाइन|वीडियो के लिए|मुख्य विषय|संपादक|सुधार|स्क्रिप्ट|\s-\s")
LOCKED_TEXT = {t["say_hi"] for t in TERMS}
MAX_REMOVED_SHARE = 0.25   # the whole-script read can't delete more than this


LINE_EDITOR = """तुम हिंदी वीडियो स्क्रिप्ट के संपादक हो। ये लाइन बोली जाएगी, और सुनने वाला इस विषय में बिल्कुल नया है।
इन चीज़ों को जांचो और ठीक करो:
- व्याकरण: लिंग, वचन, कारक (का/की/के, है/हैं, करता/करती)
- गलत या बना-बनाया शब्द, अधूरा वाक्य
- किताबी शब्द: उसकी जगह रोज़ की बोलचाल का शब्द
- मुश्किल बात: आसान शब्दों में, पर लंबी मत करो
नियम: वही बात, वही तथ्य, वही नंबर, वही नाम। कोई नई जानकारी मत जोड़ो। कैपिटल रोमन नाम (DNS, UPI) वैसे ही रखो।
आम इंग्लिश शब्द (फ़ोन, डेटा, वेबसाइट) देवनागरी में वैसे ही रहने दो।
लाइन ठीक है तो वही लौटाओ। JSON: {"text": "ठीक की हुई लाइन", "problem": "ok या grammar या word या hard"}"""

SCRIPT_EDITOR = """तुम हिंदी वीडियो स्क्रिप्ट के संपादक हो। नीचे नंबर वाली लाइनें हैं। सुनने वाला विषय में बिल्कुल नया है।
वही लाइनें बताओ जिनमें सच में समस्या है:
- repeat: यही बात पहले बोली जा चुकी है
- confusing: सुनने वाला समझ नहीं पाएगा, या वाक्य का मतलब साफ़ नहीं
- off_topic: विषय से हटकर है
repeat के लिए "fix" खाली रखो। बाकी के लिए "fix" में वही बात साफ़ और आसान शब्दों में लिखो: नए तथ्य या नंबर मत जोड़ो।
JSON: {"issues": [{"line": 3, "type": "confusing", "fix": "..."}]}"""


def ask(system, user, max_tokens=500):
    import ollama
    reply = ollama.chat(model=MODEL, format="json", options={"temperature": 0.2, "num_predict": max_tokens, "num_ctx": 8192},
                        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
    return json.loads(reply["message"]["content"])


def kept_items(text):
    """What an edit must never change: numbers, short forms and web addresses."""
    return sorted(re.findall(r"\d[\d,.]*|[A-Z][A-Z0-9/]+|[\w-]+\.(?:gov|in|com|org|net)\b", text))


def why_rejected(old, new, kind, neighbours=()):
    """The reason an edit can't be trusted, or None if it's safe to use."""
    new = new.strip()
    if EDITOR_TALK.search(new) and not EDITOR_TALK.search(old):
        return "the editor's own comment"
    for other in neighbours:   # the model sometimes pastes in the line next to this one
        added = [w for w in new.split() if w not in old.split()]
        if len(added) >= 4 and sum(w in str(other).split() for w in added) >= len(added) * 0.6:
            return "copied a neighbouring line"
    if not re.search(r"[ऀ-ॿ]", new):
        return "not in Devanagari"
    if re.search(r"[\u0400-\u04FF\u0600-\u06FF\u0980-\u0DFF\u0E00-\u30FF\u4E00-\u9FFF]", new):
        return "letters from another language"
    if re.search(r"(^|\s)(तुम|तुम्हारे|तुम्हारा|तुम्हारी|तुम्हें)(\s|$)", new):
        return 'used "तुम" instead of "आप"'
    if re.search(r"\b[a-z]{3,}\b", re.sub(r"[\w-]+\.(?:gov|in|com|org|net)\b", "", new)):
        return "English letters in the voice text"
    if kept_items(old) != kept_items(new):
        return "changed a number, short form or web address"
    if not 0.6 <= len(new.split()) / max(1, len(old.split())) <= 1.7:
        return "too much longer or shorter"
    if difflib.SequenceMatcher(None, old.split(), new.split()).ratio() < 0.45:
        return "no longer the same line"
    if BOOKISH.search(new) and not BOOKISH.search(old):
        return "added bookish words"
    if kind == "news":
        if ATTRIBUTION.search(old) and not ATTRIBUTION.search(new):
            return "dropped who said it"
        if LOADED.search(new) and not LOADED.search(old):
            return "added a loaded word"
    return None


def is_locked(beat):
    """Hand-written lines: the glossary, part cards and endings."""
    return bool(beat.get("locked")) or beat.get("say_hi") in LOCKED_TEXT or (beat.get("visual") or {}).get("type") == "chapter"


def set_line(beat, hindi):
    beat["say_hi"] = hindi
    beat["say"], beat["say_from"] = screen_text(hindi), hindi


def edit_lines(scenes, kind, report):
    beats = [b for s in scenes for b in s["beats"]]
    fixed = 0
    for k, beat in enumerate(beats):
        old = str(beat.get("say_hi") or "").strip()
        if not old or is_locked(beat):
            continue
        context = (f"पिछली लाइन: {beats[k - 1].get('say_hi', '') if k else '-'}\n"
                   f"अगली लाइन: {beats[k + 1].get('say_hi', '') if k + 1 < len(beats) else '-'}\n\nये लाइन ठीक करो: {old}")
        try:
            answer = ask(LINE_EDITOR, context)
        except Exception as e:
            report.append(f"- Skipped a line ({type(e).__name__}): {old}")
            continue
        new = " ".join(str(answer.get("text") or "").split())
        if not new or new == old or str(answer.get("problem")) == "ok":
            continue
        reason = why_rejected(old, new, kind, [beats[n].get("say_hi", "") for n in (k - 1, k + 1) if 0 <= n < len(beats)])
        if reason:
            report.append(f"- Edit rejected ({reason}):\n  - script: {old}\n  - editor: {new}")
            continue
        set_line(beat, new)
        fixed += 1
        report.append(f"- Fixed ({answer.get('problem', 'edit')}):\n  - was: {old}\n  - now: {new}")
    return fixed


def remove_repeats(scenes, report):
    """Lines that say almost the same thing as an earlier line, caught by comparing the words."""
    seen, removed = [], 0
    for scene in scenes:
        for beat in list(scene["beats"]):
            hindi = str(beat.get("say_hi") or "")
            if is_locked(beat) or (beat.get("visual") or {}).get("type") == "title":
                continue
            words = hindi.split()
            if any(difflib.SequenceMatcher(None, words, s).ratio() > 0.65 for s in seen) and len(scene["beats"]) > 1:
                scene["beats"].remove(beat)
                removed += 1
                report.append(f"- Removed a repeat: {hindi}")
            else:
                seen.append(words)
    return removed


def remove_editor_talk(scenes, report):
    """Last safety net: any line still holding an instruction or comment goes."""
    for scene in scenes:
        for beat in list(scene["beats"]):
            hindi = str(beat.get("say_hi") or "")
            if not is_locked(beat) and EDITOR_TALK.search(hindi) and len(scene["beats"]) > 1:
                scene["beats"].remove(beat)
                report.append(f"- Removed a comment that wasn't script: {hindi}")


def read_whole(scenes, kind, report):
    """One read of the full script, for what a single line can't show: repeats and confusing ideas."""
    numbered = [(s, b) for s in scenes for b in s["beats"] if not is_locked(b) and b.get("say_hi")]
    if not numbered:
        return 0, 0
    text = "\n".join(f"{n + 1}. {b['say_hi']}" for n, (_, b) in enumerate(numbered))
    try:
        issues = ask(SCRIPT_EDITOR, text, max_tokens=1500).get("issues") or []
    except Exception as e:
        report.append(f"- Whole-script read skipped ({type(e).__name__})")
        return 0, 0
    fixed = removed = 0
    limit = int(len(numbered) * MAX_REMOVED_SHARE)
    for issue in issues if isinstance(issues, list) else []:
        if not isinstance(issue, dict) or not str(issue.get("line", "")).isdigit():
            continue
        n = int(issue["line"]) - 1
        if not 0 <= n < len(numbered):
            continue
        scene, beat = numbered[n]
        old = beat["say_hi"]
        kind_of = str(issue.get("type") or "")
        new = " ".join(str(issue.get("fix") or "").split())
        first_line = beat is scenes[0]["beats"][0]
        if kind_of == "repeat" and not first_line and removed < limit and len(scene["beats"]) > 1:
            scene["beats"].remove(beat)
            removed += 1
            report.append(f"- Removed a repeat: {old}")
        elif kind_of != "repeat" and new and new != old:
            reason = why_rejected(old, new, kind)
            if reason:
                report.append(f"- Flagged {kind_of}, fix rejected ({reason}): {old}")
            else:
                set_line(beat, new)
                fixed += 1
                report.append(f"- Rewrote ({kind_of}):\n  - was: {old}\n  - now: {new}")
    return fixed, removed


def final_checks(scenes, report):
    """Problems that remain, for the person who checks the script. Also makes captions match the voice."""
    left = []
    for i, scene in enumerate(scenes):
        for j, beat in enumerate(scene["beats"]):
            hindi = str(beat.get("say_hi") or "")
            if not hindi:
                left.append(f"Scene {i} line {j}: has no Hindi for the voice")
                continue
            if beat.get("say_from") != hindi:   # a caption is only remade when its voice line changed
                beat["say"], beat["say_from"] = screen_text(hindi), hindi
            if abs(len(beat.get("say", "").split()) - len(hindi.split())) > max(2, len(hindi.split()) * 0.2):
                left.append(f"Scene {i} line {j}: caption and voice have different words; check both")
            if len(hindi.split()) > 30:
                left.append(f"Scene {i} line {j}: very long, hard to follow: {hindi[:70]}")
            found = BOOKISH.findall(hindi)
            if found:
                left.append(f"Scene {i} line {j}: bookish words ({', '.join(sorted(set(found)))}): {hindi[:70]}")
        scene["narration_hi"] = " ".join(b.get("say_hi", "") for b in scene["beats"])
    fix_screen_text(scenes)
    fixed, unsure = english_pass(scenes)   # English words on screen in real English: machine, not mashin
    if fixed:
        report.append("English spellings on screen: " + ", ".join(fixed))
    left += [f"On screen: {u}" for u in unsure]
    return left


def review(scenes, kind="explainer", log=print):
    """Edit a script in place. Returns (report lines, problems a person still needs to look at)."""
    report = []
    log("    Editor: checking every line")
    fixed = edit_lines(scenes, kind, report)
    log("    Editor: reading the whole script")
    removed = remove_repeats(scenes, report)
    rewritten, more = read_whole(scenes, kind, report)
    removed += more
    remove_editor_talk(scenes, report)
    left = final_checks(scenes, report)
    log(f"    Editor: {fixed} lines fixed, {rewritten} rewritten, {removed} repeats removed, "
        f"{len(left)} left for you to check")
    return report, left


def write_report(folder, report, left):
    with open(os.path.join(folder, "review_report.md"), "w", encoding="utf-8") as f:
        f.write("# Script editor's report\n\nThe editor can't check facts: compare the script with the sources yourself.\n\n")
        f.write("## Still needs you\n\n" + ("\n".join(f"- {p}" for p in left) or "Nothing flagged.") + "\n\n")
        f.write("## What it changed\n\n" + ("\n".join(report) or "No changes.") + "\n")


if __name__ == "__main__":
    path = "scripts/script.json"
    if not os.path.exists(path):
        raise SystemExit("Run this from inside a video's folder (projects/<video>).")
    script = json.load(open(path, encoding="utf-8"))
    lines, remaining = review(script["scenes"], script.get("kind", "explainer"))
    json.dump(script, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    write_report("scripts", lines, remaining)
    print("Done: see scripts/review_report.md. If the script changed, redo the voice: voice.py --redo")
    sys.exit(0)
