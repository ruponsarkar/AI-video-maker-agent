"""
Snack Code - automatic research + script (+ optional render) for any title

Usage:
    python auto_video.py "Beta ki awaaz mein call aaya... par woh beta nahi tha"
    python auto_video.py --file topics.txt              # every title in the file
    python auto_video.py --file topics.txt --render     # also make voice + video
    python auto_video.py "Title" --force                # redo even if a script exists

topics.txt, one video per line:
    Title | extra direction for the AI (optional) | minutes=8 (optional)

Each video gets its own folder:
    projects/<title-slug>/
        research/notes.md       facts per source, with links
        scripts/outline.json    story plan
        scripts/review.md       problems the automatic checks could not fix (only if there are any)
        scripts/script.json     final beats script (used by voice.py / animate.py)
        metadata.md             YouTube titles, description, tags, thumbnail text
        audio/ output/          after --render

Needs: Ollama running with the model below, SearXNG on localhost:8080.
"""
import difflib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from urllib.parse import urlparse

import ollama
import requests
import trafilatura

from glossary import find_new_term, term_visual
from hinglish import to_hindi, to_roman
from india_places import places_in

MODEL = "qwen3:8b"            # research, planning, visuals: reliable JSON
WRITER_MODEL = "gemma3:4b"     # the words people hear: its Hindi grammar is far better
SEARXNG = "http://localhost:8080/search"
ROOT = os.path.dirname(os.path.abspath(__file__))
MAX_SOURCES = 8
CHARS_PER_SOURCE = 3500
SKIP_SITES = ("youtube.com", "youtu.be", "facebook.com", "instagram.com", "x.com", "twitter.com",
              "tiktok.com", "pinterest.", "quora.com", "reddit.com")
VISUAL_TYPES = ["title", "host", "kinetic", "icon", "phone_call", "phone_sms", "chat", "steps",
                "compare", "stat", "warning", "flow", "pen", "map", "photo"]
SCAM_WORDS = r"scam|fraud|dhokha|fake|nakli|phishing|hack|thagi|cyber"
WORDS_PER_MIN = 110   # measured: Chatterbox reads these scripts at about 105 words a minute
STORY_TRIES = 3       # rewrites allowed when a part fails story_problems()
BEAT_WORDS = 12       # a beat ends after this many words, so the picture changes every ~5 s
BEATS_PER_SCENE = 4
# every scam video answers the same questions: (part question, what the viewer has just learned)
SCAM_PARTS = [("Ye scam hota kaise hai?", "To ye tha scam ka poora khel."),
              ("Isko pehchanein aur bachein kaise?", "To ab aap iske nishan pehchante hain."),
              ("Agar fas gaye to kya karein?", "")]
# "what is it / how does it work" videos get a clear path through the topic
EXPLAINER_WORDS = r"how |kaise|kya hai|kya hota|what is|concept|explained|samjho|matlab"
NEWS_WORDS = (r"\b(news|khabar|samachar|election|chunav|congress|bjp|sansad|parliament|lok sabha|rajya sabha|budget|"
              r"sarkar|government|minister|mantri|protest|andolan|verdict|faisla|court|war|yuddh|rbi|economy)\b")
NEWS_PARTS = [("Hua kya hai?", "To ye thi poori khabar."),
              ("Ye kyun hua, aur iske peeche kya hai?", "To ab aap iski wajah jaante hain."),
              ("Kaun kya keh raha hai?", "To ye the alag alag paksh."),
              ("Aapke liye iska kya matlab hai?", "")]
# dictionary Hindi nobody says out loud; the writer gets asked to use everyday words instead
BOOKISH_WORDS = re.compile(r"वैश्विक|प्रणाली|गंतव्य|अनुरोध|प्रदान|विभाजित|सुगम|उपकरण|आदान-प्रदान|सूचनाओं|उपयोगकर्ता|"
                           r"जटिल|सिद्धांत|संप्रेषण|अभिगम|माध्यम से|विभिन्न|उपलब्ध|महत्वपूर्ण")
LOADED_WORDS = re.compile(r"चोर|गद्दार|देशद्रोही|निकम्मा|झूठे?\b|घटिया|बेवकूफ़?|देश का दुश्मन")
EXPLAINER_PARTS = [("{subject} hai kya?", "To ye tha iska seedha matlab."),
                   ("{subject} kaam kaise karta hai?", "To ab aap iska poora raasta jaante hain."),
                   ("Aapki zindagi mein {subject} ka kya matlab hai?", "")]
# instructions the model sometimes reads out instead of following
LEAKED_TEXT = re.compile(r"viewer ko|aapke saath ye hua|research notes|direction:|\bhissa\b|\bscene\b|"
                         r"\bkahani ka\b|\bsummary\b|रिसर्च नोट्स|व्यूअर|दर्शक को|ये हिस्सा|सारांश|दिशा\s*:|बोल चुके हो", re.I)
HINDI_WORDS = set("""hai hain ho hota hoti hote ka ki ke ko se mein me par aur ya to ye yeh wo woh is us nahi na kya kaise
kyun kyunki aap apna apne apni karo karein kar karna karta karte raha rahe rahi tha thi the lekin agar jab phir isliye
matlab bhi sab ek socho jo ab sirf bas""".split())


# ---------------------------------------------------------------- helpers
def log(msg):
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def slugify(text):
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return (s[:50].strip("-") or "video") + ""


def extract_json(text):
    """Find the JSON object inside a free-text answer."""
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M)
    a, b = text.find("{"), text.rfind("}")
    if a == -1 or b <= a:
        raise json.JSONDecodeError("no JSON object", text, 0)
    return json.loads(text[a:b + 1])


def llm(system, user, as_json=True, ctx=12288, retries=4, temperature=0.7, check=None, max_tokens=2500, model=MODEL):
    """Ask the local model. Retries on model errors (like 'token repeat limit'),
    bad JSON or incomplete answers, nudging the settings each time."""
    last = ""
    for attempt in range(1, retries + 1):
        opts = {"num_ctx": ctx, "num_predict": max_tokens,
                "temperature": min(1.2, temperature + 0.15 * (attempt - 1)),
                "repeat_penalty": 1.1 + 0.05 * (attempt - 1)}
        # last try for JSON: let the model write freely, then pull the JSON out of the text
        free = as_json and attempt == retries
        kwargs = {"format": "json"} if as_json and not free else {}
        msgs = [{"role": "system", "content": system + ("\nSirf JSON object do, aur kuch nahi." if free else "")},
                {"role": "user", "content": user}]
        try:
            if model == MODEL:   # gemma has no thinking mode to turn off
                kwargs["think"] = False
            out = ollama.chat(model=model, options=opts, messages=msgs, **kwargs)
        except ollama.ResponseError as e:
            log(f"    model error ({str(e)[:70]}), retry {attempt}/{retries}")
            continue
        except Exception as e:  # Ollama not reachable, timeouts ...
            log(f"    could not reach Ollama ({str(e)[:70]}), waiting 10s, retry {attempt}/{retries}")
            time.sleep(10)
            continue
        last = out["message"]["content"].strip()
        if not as_json:
            if last:
                return last
            log(f"    empty answer, retry {attempt}/{retries}")
            continue
        try:
            data = json.loads(last) if not free else extract_json(last)
            if check is None or check(data):
                return data
            log(f"    answer incomplete, retry {attempt}/{retries}")
        except json.JSONDecodeError:
            log(f"    bad JSON, retry {attempt}/{retries}")
    raise RuntimeError(f"Model did not give a usable answer after {retries} tries. Last answer:\n{last[:300]}")


def has_devanagari(text):
    return bool(re.search(r"[ऀ-ॿ]", str(text)))


# ---------------------------------------------------------------- 1. research
def video_kind(title, hint=""):
    """scam, news or explainer. A topic line can also say it directly: type=news"""
    text = f"{title} {hint}".lower()
    if re.search(SCAM_WORDS, text):
        return "scam"
    if re.search(NEWS_WORDS, text):
        return "news"
    return "explainer"


def make_queries(title, hint):
    system = ("Tum research assistant ho. Diye gaye YouTube video topic ke liye 4 web search queries banao: "
              "2 English mein aur 2 Hindi/Hinglish mein. India par focus, latest facts, official sources "
              "(RBI, NPCI, I4C, CERT-In, police, news) mil sake aisi queries. 3-8 words each. "
              'JSON: {"queries": ["...", "...", "...", "..."]}')
    try:
        data = llm(system, f"Topic: {title}\nDirection: {hint or '-'}", ctx=4096, max_tokens=400,
                   check=lambda d: isinstance(d.get("queries"), list) and d["queries"])
        queries = [str(q).strip() for q in data["queries"] if str(q).strip()][:4]
    except RuntimeError:
        queries = []
    base = re.sub(r"[^\w\s₹%]", " ", title)
    return queries or [base, f"{base} India 2026"]


def search(queries, fresh=False):
    """fresh=True: news sites from the last month, falling back to a normal search if that finds nothing."""
    seen, per_domain, found = set(), {}, []
    extra = {"categories": "news", "time_range": "month"} if fresh else {}
    for q in queries:
        try:
            res = requests.get(SEARXNG, params={"q": q, "format": "json", **extra}, timeout=30).json()
            if fresh and not res.get("results"):
                res = requests.get(SEARXNG, params={"q": q, "format": "json"}, timeout=30).json()
        except Exception as e:
            log(f"    search failed for '{q}': {e}")
            continue
        for r in res.get("results", [])[:8]:
            url = r.get("url", "")
            dom = urlparse(url).netloc.replace("www.", "")
            if not url or url in seen or any(s in dom for s in SKIP_SITES):
                continue
            if per_domain.get(dom, 0) >= 2:
                continue
            seen.add(url)
            per_domain[dom] = per_domain.get(dom, 0) + 1
            found.append({"url": url, "title": r.get("title", "")})
    return found


def research(title, hint, proj, kind="explainer"):
    log("1/5 Research")
    queries = make_queries(title, hint)
    for q in queries:
        log(f"    query: {q}")
    results = search(queries, fresh=kind == "news")
    if not results:
        raise RuntimeError("No search results. Is SearXNG running? Try: docker start searxng")

    system = ("Tum fact checker ho. Source text se SIRF wahi facts nikalo jo video topic se related hain: "
              "numbers, dates, kaun/kya/kaise, real examples, official advice. Har fact ek bullet, simple "
              "Hinglish mein. Kuch bhi apne se mat jodo. Agar source topic se related nahi hai to sirf NONE likho.")
    if kind == "news":
        system += (" Har fact mein tareekh aur jagah likho, agar source mein ho. Kisi ka bayan ho to likho kisne kaha. "
                   "Bayan ya aarop ko pakki baat ki tarah mat likho.")
    notes, used = [], []
    for r in results:
        if len(used) >= MAX_SOURCES:
            break
        try:
            html = trafilatura.fetch_url(r["url"])
            text = trafilatura.extract(html) if html else None
        except Exception:
            text = None
        if not text or len(text) < 300:
            continue
        log(f"    reading {r['url'][:90]}")
        try:
            facts = llm(system, f"Video topic: {title}\nDirection: {hint or '-'}\n\nSOURCE TEXT:\n{text[:CHARS_PER_SOURCE]}",
                        as_json=False, ctx=6144, temperature=0.3, max_tokens=900, retries=2)
        except RuntimeError:
            log("    skipped this source (model could not summarise it)")
            continue
        if facts.strip().upper().startswith("NONE") or len(facts.strip()) < 30:
            continue
        notes.append(f"## Source: {r['title']}\n{r['url']}\n\n{facts.strip()}\n")
        used.append(r)
    if not notes:
        raise RuntimeError("Could not get facts from any source. Try a different title or direction.")
    md = f"# Research: {title}\n\n" + "\n".join(notes)
    open(os.path.join(proj, "research", "notes.md"), "w", encoding="utf-8").write(md)
    json.dump(used, open(os.path.join(proj, "research", "sources.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    log(f"    {len(used)} sources saved to research/notes.md")
    return md, used


# ---------------------------------------------------------------- 2. outline (the story plan)
def valid_visuals(scene):
    return [v for v in scene.get("visuals", []) if v in VISUAL_TYPES and v != "title"]


def make_outline(title, hint, notes, minutes, is_scam, kind="explainer"):
    """Plan: opening story -> a roadmap of questions -> one part per question -> ending."""
    log("2/5 Outline")
    n_scenes = max(5, min(18, round(minutes * 1.7)))
    set_parts = (SCAM_PARTS if is_scam else NEWS_PARTS if kind == "news"
                 else EXPLAINER_PARTS if re.search(EXPLAINER_WORDS, title.lower()) else None)
    fixed = ("Ye 3 parts bilkul isi order mein rakho:\n" + "\n".join(f"{i + 1}. {q}" for i, (q, _) in enumerate(set_parts))
             if set_parts else "3 parts banao. Har part ek aisa sawaal ho jo aam aadmi sach mein poochega.")
    system = f"""Tum Snack Code YouTube channel ke story planner ho (tech aur online safety, simple Hinglish).
Video ek kahani ki tarah chalega, jo koi bhi samajh sake. About {minutes} minute, kul {n_scenes} scenes.

Structure:
- opening (1-2 scenes): ek aam insaan ka pal, jaise "Socho, aap raat ko phone dekh rahe ho...", phir khatra kya hai.
  Ye "Socho" wali kalpana hai, asli case nahi: koi naam, rupaye ya number mat banao.
- parts: {fixed} Har part mein 1-3 scenes. Har scene pichhle scene se aage badhe.
- "recap": us part ke end par bolne wali 1 chhoti line, jo batati hai abhi kya samjha ("To ye tha ... ka tareeka.").
- "on_screen": bolchaal ki baat jo viewer turant samjhe, Roman script mein. "Stats & signs" jaisa label nahi.
- "goal": is scene mein kaunsi EK baat batani hai.
Sirf research notes ke facts. Notes mein koi asli case ho tabhi use karo, aur number bhi wahi jo notes mein hai.
Visuals inme se: {', '.join(v for v in VISUAL_TYPES if v != 'title')}.
"subject": video jis cheez ke baare mein hai, 1-2 words, jaise "Internet" ya "UPI".
JSON:
{{"subject": "...", "opening": [{{"on_screen": "...", "goal": "...", "visuals": ["..."]}}],
 "parts": [{{"question": "...", "recap": "...", "scenes": [{{"on_screen": "...", "goal": "...", "visuals": ["..."]}}]}}],
 "ending": {{"on_screen": "...", "goal": "poori kahani ki 1-2 line mein yaad"}}}}"""

    def ok(d):
        parts = d.get("parts")
        return (isinstance(d.get("opening"), list) and d["opening"] and isinstance(parts, list)
                and len(parts) >= 2 and (not set_parts or len(parts) == len(set_parts))
                and all(isinstance(p, dict) and p.get("question") and p.get("scenes") for p in parts))

    data = llm(system, f"Video title: {title}\nDirection: {hint or '-'}\n\nResearch notes:\n{notes[:9000]}",
               check=ok, max_tokens=3000)
    source = f"{title} {hint} {notes}"

    def scene(s):
        out = {"on_screen": str(s.get("on_screen") or "").strip(), "goal": str(s.get("goal") or "").strip(),
               "visuals": valid_visuals(s)}
        bad = unsupported_numbers(f"{out['on_screen']} {out['goal']}", source)
        if bad:  # the planner invented it: warn the writer instead of passing it on
            out["goal"] += f" (Ye number notes mein nahi hai, use mat karna: {', '.join(bad)})"
        return out

    parts = data["parts"][:4]
    if set_parts:
        subject = str(data.get("subject") or "").strip()
        subject = subject if subject and len(subject.split()) <= 3 else "Ye"
        for p, (q, recap) in zip(parts, set_parts):
            p["question"], p["recap"] = q.replace("{subject}", subject), recap
    questions = [str(p["question"]).strip() for p in parts]
    plan = [scene(s) for s in data["opening"][:2] if isinstance(s, dict) and s.get("on_screen")]
    plan[-1]["roadmap"] = questions
    for n, p in enumerate(parts):
        recap = str(parts[n - 1].get("recap") or "").strip() if n else ""
        plan.append({"kind": "part", "part": n + 1, "total": len(parts), "on_screen": questions[n], "recap": recap})
        plan += [scene(s) for s in p["scenes"][:3] if isinstance(s, dict) and s.get("on_screen")]
    end = data.get("ending") if isinstance(data.get("ending"), dict) else {}
    plan.append({"on_screen": str(end.get("on_screen") or "Yaad rakhne wali baat"),
                 "goal": str(end.get("goal") or "Poori kahani ki 1-2 line mein yaad"), "visuals": [], "ending": True})
    log(f"    {len(plan)} scenes planned, {len(parts)} parts: " + " / ".join(questions))
    return plan


# ---------------------------------------------------------------- 3. the story, then beats and visuals
# Written as plain text, not JSON, and one part at a time: the model tells a far better story this way.
STORY_STYLE = """तुम एक अच्छे कहानी सुनाने वाले हो, जो अपने मम्मी-पापा को चाय पर समझा रहे हो। उन्हें ये विषय पहली बार सुनना है।
सिर्फ़ बोलने वाला टेक्स्ट लिखो, देवनागरी में: बोलचाल की आसान हिंदी। कोई हेडिंग, लिस्ट, bold या JSON नहीं। सुनने वाले को "आप" कहो।
- इंग्लिश के आम शब्द वैसे ही देवनागरी में लिखो: फ़ोन, वेबसाइट, डेटा, सर्वर। उनका शुद्ध हिंदी अनुवाद मत करो।
- छोटे नाम कैपिटल रोमन में रखो: DNS, UPI, IP। नंबर अंकों में: 3, 1930। वेबसाइट के पते रोमन में।
- छोटे वाक्य, हर वाक्य 12 शब्दों से कम। लिंग और वचन सही रखो।
- हर बात ऐसे समझाओ: क्या है, क्यों होता है, और आपको इससे क्या फ़र्क पड़ता है। एक बार में एक बात।
- वाक्य पिछले वाक्य से आगे बढ़े: "लेकिन", "इसीलिए", "तो फिर", "यहीं से"।
- मुश्किल बात रोज़मर्रा की मिसाल से समझाओ। हर बात के लिए नई मिसाल।
- सवाल के बाद सवाल मत लिखो: जवाब दो। जो बोल चुके हो, दोबारा मत बोलो। अगले हिस्से की बात पहले मत बताओ।
- सिर्फ़ रिसर्च नोट्स के तथ्य। कोई नंबर, नाम, रकम या घटना अपने से मत बनाओ।
- "सोचो, आप..." वाली कल्पना को असली घटना की तरह मत बताओ।
ये निर्देश, योजना या "कहानी", "हिस्सा", "सीन" जैसे शब्द बोलने वाले टेक्स्ट में मत लिखो।
"""


NEWS_STYLE = """
ये खबर है, और तुम इसे बिना तरफ़ लिए समझा रहे हो। ये नियम सबसे ज़रूरी हैं:
- पहले साफ़ बताओ: क्या हुआ, कब, कहां, किसके साथ। सुनने वाले को पहले से कुछ नहीं पता।
- हर नाम का परिचय दो: कौन है, क्या करता है। सिर्फ़ वही जो नोट्स में है।
- किसी का बयान या आरोप पक्की बात नहीं है। हर बार लिखो: "पार्टी का कहना है", "... का आरोप है", "पुलिस के मुताबिक"।
- जहां दो पक्ष हैं, दोनों की बात नोट्स के हिसाब से रखो। जिसका पक्ष नोट्स में नहीं, साफ़ कहो कि उसका पक्ष नहीं मिला।
- अपनी राय, ताना या सही-गलत का फ़ैसला मत दो। किसी पार्टी, नेता या समुदाय के लिए बुरा शब्द मत लिखो।
- लोगों की राय सिर्फ़ तब, जब नोट्स में हो, और बताओ कहां से है। कोई बयान, सर्वे या जनता की राय खुद मत बनाओ।
- जो अभी पक्का नहीं, उसे "अभी पक्का नहीं" कहो।
"""


VISUAL_STYLE = """Tum video designer ho. Neeche video ke kuch beats hain, jo bola ja raha hai. Har beat ke liye
ek visual chuno jo wahi dikhaye jo us beat mein bola ja raha hai. Ek scene mein same type do baar nahi.
Screen ka har text sirf Roman script mein, bolchaal ki Hinglish mein ("Badi file", "Sahi jagah"), English sentence nahi, chhota (max 8 words per item). Koi nayi baat ya number mat jodo.
"on_screen": is scene ki 3-6 words ki bolchaal wali heading. "pop": sabse important 1-2 words, sirf ek beat mein.
"mood": happy, shock, think, warn, explain.

Har scene mein kam se kam ek "pen" ya "photo" rakho. "host" aur "kinetic" tabhi jab kuch aur fit na ho.
"photo" ki query mein kisi insaan, company ya logo ka naam nahi: sirf aam cheezein aur jagahein.

Visual types:
{"type": "host", "text": "Byte kya bolta hai (max 12 words)"}
{"type": "kinetic", "text": "screen par bade words (max 8)", "highlight": "ek word"}
{"type": "icon", "icon": "shield", "text": "chhota message"}
{"type": "phone_call", "caller": "Naam", "number": "+91 98XXX XXXXX"}
{"type": "phone_sms", "sender": "VM-ALERT", "message": "SMS text"}
{"type": "chat", "name": "Unknown Number", "messages": [{"from": "them", "text": "..."}, {"from": "me", "text": "..."}]}
{"type": "steps", "items": ["...", "...", "..."]}
{"type": "compare", "left_title": "...", "left": ["..."], "right_title": "...", "right": ["..."]}  (do cheezon ka farak. "Asli" aur "Fake" sirf scam video mein)
{"type": "stat", "value": "16%", "label": "number ka matlab"}  (sirf jab beat mein sach mein number ho)
{"type": "warning", "text": "kya kabhi nahi karna"}
{"type": "flow", "nodes": [{"icon": "hacker", "label": "..."}, {"icon": "phone", "label": "..."}, {"icon": "bank", "label": "..."}]}
{"type": "pen", "items": [{"label": "1-3 words", "icon": "phone"}, {"label": "...", "icon": "wifi"}, {"label": "...", "icon": "globe"}], "note": "ek chhoti line"}  (kalam se bana diagram: jab koi cheez A se B tak jaati ho, ya steps mein hoti ho)
{"type": "photo", "query": "2-3 English words", "caption": "1-4 words Roman"}  (asli photo: jab beat kisi cheez ya jagah ki baat kare, jaise "mobile tower", "hospital ward", "data center", "fiber optic cable")
Icons (sirf ye): phone, shield, lock, bank, money, warning, user, hacker, globe, laptop, wifi, chip, ram, bug, ai, key, sim, mail, check, cross

JSON, beats ki ginti utni hi jitni di gayi:
{"on_screen": "...", "beats": [{"visual": {"type": "..."}, "mood": "...", "pop": "..."}]}"""


def strings_in(obj, skip=("number",)):
    if isinstance(obj, dict):
        return [t for k, v in obj.items() if k not in skip for t in strings_in(v, skip)]
    if isinstance(obj, list):
        return [t for v in obj for t in strings_in(v, skip)]
    return [obj] if isinstance(obj, str) else []


def unsupported_numbers(text, source):
    """Numbers in text that the title, direction and research notes never mention."""
    known = set(re.findall(r"\d+", source.replace(",", "")))
    bad = []
    for n in re.findall(r"\d[\d,]*(?:\.\d+)?", text):
        raw = n.replace(",", "").split(".")[0]
        if raw and raw != "1930" and int(raw) > 10 and raw not in known:
            bad.append(n)
    return sorted(set(bad))


def sentences(text):
    return [p.strip() for p in re.split(r"(?<=[.?!।])\s+", text.strip()) if p.strip()]


def drop_repeats(text, earlier):
    """Remove sentences already said: the model repeats itself, and rewrites alone don't stop it."""
    kept, seen = [], [s for e in list(earlier) + list(FIXED_HI.values()) for s in sentences(e)]
    openings = set()
    for s in sentences(text):
        latin_words = re.findall(r"\b[a-z]{2,}\b", s)
        if LEAKED_TEXT.search(s) or len(latin_words) > max(2, len(s.split()) * 0.3):
            continue   # read-out instructions, or a sentence that slipped into Roman
        start = " ".join(s.lower().split()[:3])
        if len(s.split()) > 3 and start in openings:   # "Internet ke baare mein..." again and again
            continue
        openings.add(start)
        if not any(difflib.SequenceMatcher(None, s.lower(), e.lower()).ratio() > 0.75 for e in seen):
            kept.append(s)
        seen.append(s)
    return " ".join(kept)


def story_problems(text, words, source, earlier, opening, kind="explainer"):
    """What a human would reject in this part. Written so the model can act on it."""
    problems = []
    tokens = text.split()
    latin = re.findall(r"\b[a-z]{3,}\b", re.sub(WEB_ADDRESS, "", text))
    if not has_devanagari(text) or len(latin) > len(tokens) * 0.1:
        problems.append("सिर्फ़ देवनागरी में लिखो। इंग्लिश शब्द भी देवनागरी में।")
    bookish = sorted(set(BOOKISH_WORDS.findall(text)))
    if bookish:
        problems.append(f"ये किताबी शब्द हैं: {', '.join(bookish)}। रोज़ की बोलचाल के शब्द लिखो।")
    if len(tokens) < words * 0.6:
        problems.append(f"बहुत छोटा है ({len(tokens)} शब्द)। करीब {words} शब्द लिखो।")
    bad = unsupported_numbers(text, source)
    if bad:
        problems.append(f"ये नंबर रिसर्च नोट्स में नहीं हैं, हटाओ: {', '.join(bad)}।")
    if kind == "news" and LOADED_WORDS.search(text):
        problems.append(f'"{LOADED_WORDS.search(text).group(0)}" जैसा शब्द मत लिखो: बिना तरफ़ लिए समझाओ।')
    if not opening and text.startswith("सोचो"):
        problems.append('"सोचो" से शुरू मत करो: पिछली बात से आगे बढ़ो।')
    return problems


def explain_terms(made, explained):
    """Right after a hard word is first said, stop and explain it with its own visual."""
    out = []
    for sc in made:
        beats = []
        for k, b in enumerate(sc["beats"]):
            beats.append(b)
            if (b.get("visual") or {}).get("type") in ("title", "chapter"):
                continue
            entry = find_new_term(b["say"], explained)
            while entry:   # a line can bring in several hard words: explain each one
                explained.add(entry["term"])
                beats.append({"say": entry["say"], "say_hi": entry["say_hi"], "visual": term_visual(entry),
                              "mood": "explain"})
                entry = find_new_term(b["say"], explained)
        # animate.py shows at most 5 beats in a scene
        for k in range(0, len(beats), 5):
            out.append({**sc, "beats": beats[k:k + 5]})
    return out


def write_part(title, hint, notes, goal, words, told, opening, kind="explainer"):
    """One part of the story as plain text. Returns (best text, problems left in it)."""
    source = f"{title} {hint} {notes}"
    base = (f"वीडियो: {title}\n{hint}\n\nरिसर्च नोट्स:\n{notes[:7000]}\n\n"
            f"अब तक बोल चुके हो:\n{' '.join(told)[-1500:] or '-'}\n\n"
            f"अब सिर्फ़ ये हिस्सा लिखो, करीब {words} शब्द:\n{goal}")
    best, problems, feedback = "", [], ""
    for attempt in range(STORY_TRIES):
        try:
            style = STORY_STYLE + (f"{NEWS_STYLE}आज की तारीख: {time.strftime('%d-%m-%Y')}।\n" if kind == "news" else "")
            text = llm(style, base + feedback, as_json=False, ctx=8192, temperature=0.5 + 0.1 * attempt,
                       max_tokens=max(500, words * 8), model=WRITER_MODEL)
        except RuntimeError as e:
            log(f"    no usable answer: {str(e)[:80]}")
            continue
        text = text.translate(str.maketrans("०१२३४५६७८९", "0123456789"))
        text = re.sub(r"\s*\([^)]*\)", "", text)   # "DNS (DNS)", "SIR (Special Intensive Revision)"
        text = re.sub(r"(^|\s)-\s+", r"\1", text)   # list dashes
        text = re.sub(r"सोचो,?\s*आप(\.\.\.|!|,)", "सोचो,", text).replace("...", ",")
        text = to_hindi(text)[0]   # any stray English word gets its Devanagari spelling
        text = drop_repeats(" ".join(re.sub(r"[*_#\"“”‘’']", "", text).split()), told)
        found = story_problems(text, words, source, told, opening, kind)
        if not best or len(found) < len(problems):
            best, problems = text, found
        if not problems:
            break
        log(f"    needs a rewrite: {problems[0][:90]}")
        feedback = "\n\nपिछली कोशिश में ये गलतियां थीं, इन्हें ठीक करो:\n- " + "\n- ".join(found)
    return best, problems


def split_beats(text):
    """Group sentences into beats of 1-3 short sentences, so the picture changes every few seconds."""
    beats, cur = [], ""
    pieces = []
    for s in sentences(text):   # a long sentence breaks at its comma, so the picture still changes
        pieces += re.split(r"(?<=,)\s+", s) if len(s.split()) > 16 else [s]
    for s in pieces:
        cur = f"{cur} {s}".strip()
        if len(cur.split()) >= BEAT_WORDS:
            beats.append(cur)
            cur = ""
    if cur:
        if beats and len(cur.split()) < BEAT_WORDS / 2:
            beats[-1] += " " + cur
        else:
            beats.append(cur)
    return beats


def clean_visual(v, say, source):
    """Drop a visual viewers could not read or that adds a claim. animate.py then picks a safe one."""
    if not isinstance(v, dict) or not v.get("type"):
        return {}
    shown = strings_in(v)
    if any(has_devanagari(t) for t in shown) or unsupported_numbers(" ".join(shown), source):
        return {}
    digits = re.findall(r"\d+", str(v.get("value", "")))
    if v["type"] == "stat" and (not digits or not all(n in say for n in digits)):
        return {}   # a number card only when this line says that number
    if v["type"] == "photo" and not re.fullmatch(r"[A-Za-z][A-Za-z ,-]{2,50}", str(v.get("query", "")).strip()):
        return {}
    if v["type"] == "pen" and len(v.get("items") or []) < 2:
        return {}
    if v["type"] not in VISUAL_TYPES or v["type"] == "title":
        return {}
    for node in v.get("nodes") or v.get("items") or []:   # the hacker face only where there is a crime
        if isinstance(node, dict) and node.get("icon") == "hacker" and not re.search(r"hack|thug|scam|fraud|chor", say, re.I):
            node["icon"] = "user"
    return v


def add_visuals(says, heading, source):
    user = f"Scene ka topic: {heading}\n\nBeats:\n" + "\n".join(f"{i + 1}. {s}" for i, s in enumerate(says))
    try:
        data = llm(VISUAL_STYLE, user, ctx=4096, max_tokens=1200, retries=3, temperature=0.5,
                   check=lambda d: isinstance(d.get("beats"), list) and len(d["beats"]) == len(says))
    except RuntimeError:
        data = {"beats": [{} for _ in says]}
    beats = []
    for say, b in zip(says, data["beats"]):
        b = b if isinstance(b, dict) else {}
        visual = clean_visual(b.get("visual"), say, source)
        places = places_in(say)
        if places:   # a place was named: always show where it is
            visual = {"type": "map", "places": places}
        beat = {"say": say, "visual": visual, "mood": b.get("mood")}
        pop = b.get("pop")
        if isinstance(pop, str) and pop.strip() and not has_devanagari(pop):
            beat["pop"] = pop.strip()
        beats.append(beat)
    own = str(data.get("on_screen") or "").strip()
    keep = 2 <= len(own.split()) <= 8 and not has_devanagari(own)
    return {"on_screen": own if keep else " ".join(heading.split()[:7]), "beats": beats}


# fixed lines, written by hand so the voice is always right
FIXED_HI = {
    "Chaliye, pehle sawaal se shuru karte hain.": "चलिए, पहले सवाल से शुरू करते हैं।",
    "Ab agla sawaal.": "अब अगला सवाल।",
    "Ab aakhri aur sabse kaam ka sawaal.": "अब आखिरी और सबसे काम का सवाल।",
    "Ye scam hota kaise hai?": "ये स्कैम होता कैसे है?",
    "Isko pehchanein aur bachein kaise?": "इसको पहचानें और बचें कैसे?",
    "Agar fas gaye to kya karein?": "अगर फँस गए तो क्या करें?",
    "To ye tha scam ka poora khel.": "तो ये था स्कैम का पूरा खेल।",
    "To ab aap iske nishan pehchante hain.": "तो अब आप इसके निशान पहचानते हैं।",
    "Is video mein 3 sawaalon ke jawab milenge.": "इस वीडियो में तीन सवालों के जवाब मिलेंगे।",
    "Aur agar aapke ya kisi apne ke saath aisa ho jaye, to turant 1930 par call kijiye, aur cybercrime.gov.in par complaint kijiye.":
        "और अगर आपके या किसी अपने के साथ ऐसा हो जाए, तो तुरंत 1930 पर कॉल कीजिए, और cybercrime.gov.in पर शिकायत कीजिए।",
    "Comment mein batao, kya aapke paas kabhi aisa kuch aaya hai?": "कमेंट में बताओ, क्या आपके पास कभी ऐसा कुछ आया है?",
    "Comment mein batao, aapko sabse hairan kis baat ne kiya?": "कमेंट में बताओ, आपको सबसे हैरान किस बात ने किया?",
    "Aur aisi hi baatein jaanne ke liye Snack Code ko subscribe kar lo.": "और ऐसी ही बातें जानने के लिए स्नैक कोड को सब्सक्राइब कर लो।",
}
WEB_ADDRESS = r"[a-zA-Z0-9.-]*\.(?:gov|in|com|org|net)\b"


def to_devanagari(say):
    """Voice text for a line written in Roman: same words, same order, spelled by hinglish.py."""
    hindi, missing = to_hindi(" ".join(FIXED_HI.get(s, s) for s in sentences(say)))
    if missing:
        log(f"    no spelling yet for: {', '.join(missing)} (add to hindi_words.json)")
    return hindi


def fixed_beat(say, visual, mood="explain"):
    return {"say": say, "visual": visual, "mood": mood}


def part_scene(sc):
    """The line break: says what the viewer just learned, and which question comes next."""
    if sc["part"] == 1:
        lead = "Chaliye, pehle sawaal se shuru karte hain."
    else:
        nxt = "Ab aakhri aur sabse kaam ka sawaal." if sc["part"] == sc["total"] else "Ab agla sawaal."
        lead = f"{sc.get('recap', '')} {nxt}".strip()
    return {"on_screen": sc["on_screen"], "beats": [fixed_beat(
        f"{lead} {sc['on_screen']}", {"type": "chapter", "part": sc["part"], "total": sc["total"]}, "think")]}


def ending_scene(is_scam):
    beats = []
    if is_scam:
        beats.append(fixed_beat("Aur agar aapke ya kisi apne ke saath aisa ho jaye, to turant 1930 par call kijiye, "
                                "aur cybercrime.gov.in par complaint kijiye.",
                                {"type": "stat", "value": "1930", "label": "Cybercrime helpline | cybercrime.gov.in"}, "warn"))
        ask = "Comment mein batao, kya aapke paas kabhi aisa kuch aaya hai?"
    else:
        ask = "Comment mein batao, aapko sabse hairan kis baat ne kiya?"
    beats.append(fixed_beat(f"{ask} Aur aisi hi baatein jaanne ke liye Snack Code ko subscribe kar lo.",
                            {"type": "host", "text": "Comment karo aur subscribe karo"}, "happy"))
    return {"on_screen": "Ye yaad rakhna" if is_scam else "Aapko kya laga?", "beats": beats}


def write_scenes(title, hint, notes, outline, minutes, is_scam, proj, kind="explainer"):
    log("3/5 Story")
    partial = os.path.join(proj, "scripts", "scenes_partial.json")
    saved = json.load(open(partial, encoding="utf-8")) if os.path.exists(partial) else {}
    source = f"{title} {hint} {notes}"
    # consecutive planned scenes between part cards are told together as one flowing piece
    groups, cur = [], []
    for sc in outline:
        if sc.get("kind") == "part":
            if cur:
                groups.append(cur)
                cur = []
            groups.append([sc])
        else:
            cur.append(sc)
    if cur:
        groups.append(cur)
    n_content = max(1, sum(len(g) for g in groups if g[0].get("kind") != "part"))
    total = minutes * WORDS_PER_MIN
    scenes, told, review, explained = [], [], [], set()
    for gi, group in enumerate(groups):
        key = str(gi)
        if key in saved:
            log(f"    {gi + 1}/{len(groups)}: already written, reusing")
            made = saved[key] if isinstance(saved[key], list) else [saved[key]]
        elif group[0].get("kind") == "part":
            log(f"    {gi + 1}/{len(groups)}: PART {group[0]['part']}: {group[0]['on_screen']}")
            made = [part_scene(group[0])]
        else:
            opening = gi == 0
            ending = bool(group[-1].get("ending"))
            words = max(30, int(total * len(group) / n_content))
            goal = "\n".join(f"- {s.get('goal') or s['on_screen']}" for s in group)
            if opening and kind == "news":   # a made-up scene has no place in a news story
                goal = (f"सीधे असली खबर से शुरू करो: नोट्स के हिसाब से एक लाइन में क्या हुआ, और ये जानना क्यों ज़रूरी है। "
                        f"कोई कल्पना, किरदार या बातचीत मत बनाओ। ({title})\n" + goal)
            elif opening:
                goal = (f'"सोचो" शब्द से शुरू करो: एक रोज़मर्रा का पल जो इस विषय से जुड़ा हो ({title})। '
                        f"{hint}\n" + goal)
            if ending:
                goal += "\nसिर्फ़ याद दिलाओ, नई बात नहीं। सब्सक्राइब या हेल्पलाइन मत लिखो।"
            log(f"    {gi + 1}/{len(groups)}: writing {group[0]['on_screen'][:60]}")
            text, problems = write_part(title, hint, notes, goal, words, told, opening, kind)
            if not text:
                log(f"    skipped {gi + 1}: no text")
                continue
            spoken = split_beats(text)
            made = []
            for k in range(0, len(spoken), BEATS_PER_SCENE):
                part = spoken[k:k + BEATS_PER_SCENE]
                sc = add_visuals([to_roman(s) for s in part], group[min(k // BEATS_PER_SCENE, len(group) - 1)]["on_screen"],
                                 source)
                for beat, hindi in zip(sc["beats"], part):
                    beat["say_hi"] = hindi   # the caption was made from this, so voice and caption match
                made.append(sc)
            if opening:
                made[0]["beats"][0]["visual"] = {"type": "title"}
                made[0]["on_screen"] = title
                qs = group[-1].get("roadmap") or []
                if qs:
                    made.append({"on_screen": "Aaj in sawaalon ke jawab", "beats": [fixed_beat(
                        f"Is video mein {len(qs)} sawaalon ke jawab milenge. " + " ".join(qs),
                        {"type": "steps", "items": qs})]})
            if ending:
                made.append(ending_scene(is_scam))
            if problems:
                made[0]["review"] = problems
            made = explain_terms(made, explained)
        for sc in made:
            for b in sc["beats"]:
                if not has_devanagari(b.get("say_hi", "")):
                    b["say_hi"] = to_devanagari(str(b["say"]).strip())
            sc["narration_hi"] = " ".join(b["say_hi"] for b in sc["beats"] if b.get("say_hi"))
        saved[key] = made
        json.dump(saved, open(partial, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        for sc in made:
            told += [str(b.get("say_hi") or b["say"]).strip() for b in sc["beats"]]
            explained |= {str((b.get("visual") or {}).get("term") or (b.get("visual") or {}).get("title") or "")
                          for b in sc["beats"]} - {""}
            for problem in sc.pop("review", []):
                review.append(f"- {sc['on_screen']}: {problem}")
            scenes.append(sc)
    if not scenes:
        raise RuntimeError("No scenes were written.")
    review_path = os.path.join(proj, "scripts", "review.md")
    if kind == "news":   # a person has to check this every time, whatever the automatic checks say
        review.insert(0, "- Khabar hai: har naam, tareekh, bayan aur number source link se milao. Dekho ki har paksh "
                         "ki baat aayi hai, koi aarop pakki baat ki tarah nahi likha, aur photo us ghatna ki nahi "
                         "(wo sirf sanketik hai).")
    if review:
        open(review_path, "w", encoding="utf-8").write("# Check these before voicing\n\n" + "\n".join(review) + "\n")
        log(f"    {len(review)} problem(s) could not be fixed automatically: see scripts/review.md")
    elif os.path.exists(review_path):
        os.remove(review_path)
    return scenes


# ---------------------------------------------------------------- 4. metadata
def make_metadata(title, hint, scenes, sources, proj, kind="explainer"):
    log("4/5 YouTube metadata")
    summary = " ".join(b["say"] for s in scenes for b in s["beats"])[:5000]
    system = ("Tum YouTube SEO expert ho, Hindi tech aur news explainer channel Snack Code ke liye. Hinglish mein likho. "
              "Title wahi bole jo video mein hai: koi jhootha daava ya kisi ko doshi batana nahi. JSON:\n"
              '{"titles": ["3 title options, har ek 60 characters se kam, searchable Hinglish"], '
              '"description": "150-250 words: pehli 2 lines mein main keyword aur hook, phir video mein kya hai, '
              'phir subscribe line", "tags": ["15 tags, Hinglish + English search phrases"], '
              '"thumbnail_text": "3-4 bade words"}')
    try:
        m = llm(system, f"Video title: {title}\nDirection: {hint or '-'}\n\nScript:\n{summary}", ctx=8192,
                check=lambda d: d.get("titles") and d.get("description"), max_tokens=1500)
    except RuntimeError:
        m = {"titles": [title], "description": "", "tags": [], "thumbnail_text": ""}
    lines = [f"# {title}", "", "## Title options"] + [f"- {t}" for t in m.get("titles", [])]
    lines += ["", "## Thumbnail text", str(m.get("thumbnail_text", "")), "", "## Description", "",
              str(m.get("description", "")).strip(), "", "Sources:"]
    lines += [f"- {s['url']}" for s in sources]
    if kind == "scam":
        lines += ["", "Cybercrime helpline: 1930 | cybercrime.gov.in"]
    lines += ["", "## Tags", ", ".join(map(str, m.get("tags", [])))]
    open(os.path.join(proj, "metadata.md"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    return m


# ---------------------------------------------------------------- 5. render (optional)
def render(proj, redo=False):
    log("5/5 Voice + animation")
    for name in ("fonts", "music.mp3", "music.wav", "music.m4a"):
        src, dst = os.path.join(ROOT, name), os.path.join(proj, name)
        if os.path.exists(src) and not os.path.exists(dst):
            os.symlink(src, dst)
    # the realistic voice (Chatterbox) lives in its own environment: venv-voice
    voice_py = os.path.join(ROOT, "venv-voice", "bin", "python")
    for step in ("voice.py", "animate.py"):
        py = voice_py if step == "voice.py" and os.path.exists(voice_py) else sys.executable
        log(f"    running {step}")
        # a rewritten script must not reuse the old script's voice clips
        extra = ["--redo"] if redo and step == "voice.py" else []
        subprocess.run([py, os.path.join(ROOT, step)] + extra, cwd=proj, check=True)
    log(f"    video: {os.path.join(proj, 'output', 'animated.mp4')}")


# ---------------------------------------------------------------- main
def fetch_photos(proj):
    """Real photos for photo beats. Needs internet; without it those beats just get another visual."""
    import photos
    here = os.getcwd()
    try:
        os.chdir(proj)
        found, missed = photos.fetch_all()
        log(f"Photos: {found} found, {missed} without a photo. Check images/photos/review.jpg")
    except Exception as e:
        log(f"Photos skipped: {e}")
    finally:
        os.chdir(here)


def make_video(title, hint="", minutes=8, do_render=False, force=False, kind=None):
    try:
        ollama.show(WRITER_MODEL)
    except Exception:
        raise RuntimeError(f"The writing model is missing. Run: ollama pull {WRITER_MODEL}")
    proj = os.path.join(ROOT, "projects", slugify(title))
    for sub in ("research", "scripts", "audio", "images", "output"):
        os.makedirs(os.path.join(proj, sub), exist_ok=True)
    script_path = os.path.join(proj, "scripts", "script.json")
    print("\n" + "=" * 70)
    log(f"VIDEO: {title}\n         folder: {proj}")
    kind = kind or video_kind(title, hint)
    is_scam = kind == "scam"
    log(f"Type: {kind}")

    if os.path.exists(script_path) and not force:
        log("script.json already exists, skipping writing (use --force to redo)")
    else:
        notes_path = os.path.join(proj, "research", "notes.md")
        src_path = os.path.join(proj, "research", "sources.json")
        if os.path.exists(notes_path) and os.path.exists(src_path) and not force:
            log("1/5 Research: reusing research/notes.md")
            notes = open(notes_path, encoding="utf-8").read()
            sources = json.load(open(src_path, encoding="utf-8"))
        else:
            notes, sources = research(title, hint, proj, kind)
        outline_path = os.path.join(proj, "scripts", "outline.json")
        partial = os.path.join(proj, "scripts", "scenes_partial.json")
        if force:
            for f in (outline_path, partial):
                if os.path.exists(f):
                    os.remove(f)
        if os.path.exists(outline_path):
            log("2/5 Outline: reusing scripts/outline.json")
            outline = json.load(open(outline_path, encoding="utf-8"))
        else:
            outline = make_outline(title, hint, notes, minutes, is_scam, kind)
            json.dump(outline, open(outline_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        scenes = write_scenes(title, hint, notes, outline, minutes, is_scam, proj, kind)
        meta = make_metadata(title, hint, scenes, sources, proj, kind)
        script = {"title": (meta.get("titles") or [title])[0], "topic": title, "kind": kind,
                  "theme": "crimson" if is_scam else None, "scenes": scenes}
        if not script["theme"]:
            del script["theme"]
        json.dump(script, open(script_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        fetch_photos(proj)
        if os.path.exists(partial):
            os.remove(partial)
        beats = [b for s in scenes for b in s["beats"]]
        words = sum(len(b["say"].split()) for b in beats)
        log(f"Saved scripts/script.json: {len(scenes)} scenes, {len(beats)} beats, {words} words "
            f"(about {words / 150:.1f} min)")
        log("Visuals: " + ", ".join(str((b.get("visual") or {}).get("type", "-")) for b in beats))

    if do_render:
        reviewed = json.load(open(script_path, encoding="utf-8")).get("reviewed")
        if kind == "news" and not reviewed:
            log('News video not rendered: check scripts/review.md, then add "reviewed": true to scripts/script.json '
                "and run this again.")
        else:
            render(proj, redo=force)
    return proj


def read_topics(path):
    topics = []
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split("|")]
        title, hints, minutes, kind = parts[0], [], 8, None
        for p in parts[1:]:
            m = re.match(r"minutes\s*=\s*([\d.]+)", p)
            t = re.match(r"type\s*=\s*(news|scam|explainer)\s*$", p, re.I)
            if m:
                minutes = float(m.group(1))
            elif t:
                kind = t.group(1).lower()
            elif p:
                hints.append(p)
        topics.append((title, ". ".join(hints), minutes, kind))
    return topics


if __name__ == "__main__":
    argv = sys.argv[1:]
    do_render, force = "--render" in argv, "--force" in argv
    argv = [a for a in argv if a not in ("--render", "--force")]
    if "--file" in argv:
        topics = read_topics(argv[argv.index("--file") + 1])
    elif argv:
        topics = [(argv[0], argv[1] if len(argv) > 1 else "", 8, None)]
    else:
        print(__doc__)
        sys.exit(1)

    started, done, failed = time.time(), [], []
    for title, hint, minutes, kind in topics:
        try:
            done.append(make_video(title, hint, minutes, do_render, force, kind))
        except Exception as e:
            log(f"FAILED: {title}\n         {e}")
            failed.append(title)
    print("\n" + "=" * 70)
    log(f"Finished {len(done)} video(s) in {(time.time() - started) / 60:.0f} min")
    for p in done:
        print("   ", p)
    if failed:
        print("Failed:", *failed, sep="\n    ")