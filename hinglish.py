"""
Keeps the voice and the captions on the same words: Devanagari <-> Roman, one word at a time.

to_roman()  makes the on-screen caption from the Devanagari script, so captions always match the voice.
to_hindi()  goes the other way, for lines you write in Roman. It never translates or reorders: "users"
            becomes यूज़र्स, not उपयोगकर्ता.

Voice spellings are in hindi_words.json. Screen spellings the model has learned are in caption_words.json.
A spelling you fix in either file stays fixed in every video.

After editing say_hi in a script:  python ../../hinglish.py --sync   (from the video's folder)
Check a line:  python hinglish.py "Data ka chhota tukda aapke phone tak pahunchta hai."
               python hinglish.py "डेटा का छोटा टुकड़ा आपके फ़ोन तक पहुंचता है।"
"""
import difflib
import json
import os
import re
import sys
import unicodedata

MODEL = "qwen3:8b"
WORD_MODEL = "gemma3:4b"
HINDI_ENDINGS = re.compile(r"(enge|engi|yega|yegi|yenge|yengi|iye|aiye)$")
# sound-spelled English that's too far off for the automatic correction
ROMAN_FIXES = {"oportyuniti": "opportunity", "oportuniti": "opportunity", "opportyuniti": "opportunity",
               "opportyunitiz": "opportunities", "oportyunitiz": "opportunities", "bailensad": "balanced", "bailensd": "balanced",
               "devlap": "develop", "ephishient": "efficient", "inportens": "importance", "kanpniyon": "companies", "levar": "lever",
               "prodakt": "product", "skils": "skills", "nukri": "naukri", "kampaniyon": "companies", "kanpni": "company"}
# Hindi words that look like English ones: never swap these for the English word
HINDI_LOOKALIKES = {"banana", "bana", "man", "mat", "par", "pad", "the", "do", "to", "hum", "main", "bat", "bar", "car", "kam", "come",
                    "are", "gun", "chai", "rail", "lake", "more", "bus", "sub", "song", "son", "sun", "pass", "pal", "pan", "nut",
                    "in", "is", "us", "un", "an", "he", "she", "we", "me", "my", "on", "or", "of", "at", "it", "so", "no", "ye", "am", "be"}
WORDS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hindi_words.json")
CAPTION_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "caption_words.json")   # Devanagari -> screen spelling
# stays as written; hindi_text.py turns these into spoken Hindi: numbers, money, short forms, web addresses
KEEP = re.compile(r"(?:₹\s?)?\d[\d,.:]*%?|\b[A-Z][A-Z0-9/]+s?\b|\bI4C\b|\b[\w-]+(?:\.[\w-]+)*\.(?:com|in|org|net|gov)\b")
WORD = re.compile(r"[A-Za-z][A-Za-z']*(?:-[A-Za-z]+)*")
TOKEN = re.compile(KEEP.pattern + "|" + WORD.pattern)

# rough sounds of Devanagari, only to catch a translation pretending to be a spelling
_CONSONANTS = dict(zip("कखगघचछजझटठडढतथदधपफबभयरलवशषसहञणनम",
                       "kkggccjjttddttddppbbyrlvsssnnnm"[:0] or
                       ["k", "k", "g", "g", "c", "c", "j", "j", "t", "t", "d", "d", "t", "t", "d", "d", "p", "f", "b",
                        "b", "y", "r", "l", "v", "s", "s", "s", "h", "n", "n", "n", "m"]))
_VOWEL_LETTERS = set("अआइईउऊएऐओऔऑऍ")
_ROMAN_CLASSES = str.maketrans({"z": "j", "q": "k", "x": "k", "w": "v", "c": "k", "y": "y"})


def _skeleton_hi(text):
    out = []
    for ch in text:
        if ch == "़":   # ज़ फ़: treated as ज फ
            continue
        if ch in _CONSONANTS:
            out.append(_CONSONANTS[ch])
    return "".join(out).translate(_ROMAN_CLASSES).replace("s", "j")


def _skeleton_en(word):
    w = word.lower().replace("ph", "f").replace("ch", "c").replace("sh", "s").replace("th", "t").replace("dh", "d")
    w = w.replace("kh", "k").replace("gh", "g").replace("bh", "b").replace("ck", "k")
    w = re.sub(r"(.)\1", r"\1", w)   # double letters
    w = re.sub(r"[aeiou']", "", w)
    return w.translate(_ROMAN_CLASSES).replace("s", "j")


def sounds_like(roman, hindi):
    """False when the Devanagari can't be a spelling of the Roman word, e.g. users / उपयोगकर्ता."""
    if not re.fullmatch(r"[ऀ-ॿ-]+", hindi):
        return False
    a, b = _skeleton_en(roman), _skeleton_hi(hindi)
    if not a or not b:
        return len(hindi) <= len(roman) + 3
    return difflib.SequenceMatcher(None, a, b).ratio() >= 0.5


def load_words():
    if os.path.exists(WORDS_FILE):
        return json.load(open(WORDS_FILE, encoding="utf-8"))
    return {}


def save_words(words):
    with open(WORDS_FILE, "w", encoding="utf-8") as f:
        json.dump(dict(sorted(words.items())), f, ensure_ascii=False, indent=0)
        f.write("\n")


def ask_model(unknown):
    """Spell new words with the local model. Returns only the answers that pass the check."""
    import ollama
    system = ("Har Roman word ko us bolne wali awaaz ke hisaab se Devanagari mein likho, sahi matra ke saath. "
              "Translate mat karo. English word bhi waise hi likho jaise India mein bola jata hai.\n"
              "Sirf JSON: har word ke liye uski Devanagari spelling.\n"
              'Input: ["users", "help", "safe", "chhota", "pahunchta"]\n'
              'Output: {"users": "यूज़र्स", "help": "हेल्प", "safe": "सेफ़", "chhota": "छोटा", "pahunchta": "पहुंचता"}')
    found = {}
    for attempt in range(2):
        todo = [w for w in unknown if w not in found]
        if not todo:
            break
        try:
            reply = ollama.chat(model=MODEL, think=False, format="json",
                                options={"temperature": 0.1, "num_predict": 40 * len(todo) + 80},
                                messages=[{"role": "system", "content": system},
                                          {"role": "user", "content": json.dumps(todo, ensure_ascii=False)}])
            data = json.loads(reply["message"]["content"])
        except Exception as e:
            print(f"  spelling step failed: {type(e).__name__}")
            continue
        for w in todo:
            answer = str(data.get(w) or "").strip()
            if answer and sounds_like(w, answer):
                found[w] = answer
    return found


def to_hindi(say, words=None, use_model=True):
    """Devanagari for one line, same words in the same order. Unknown words stay in Roman and are returned."""
    words = load_words() if words is None else words
    unknown = sorted({m.group(0).lower() for m in TOKEN.finditer(say)
                      if not KEEP.fullmatch(m.group(0)) and m.group(0).lower() not in words})
    if unknown and use_model:
        new = ask_model(unknown)
        if new:
            words.update(new)
            save_words(words)
    missing = []

    def spell(m):
        token = m.group(0)
        if KEEP.fullmatch(token):
            return token
        answer = words.get(token.lower())
        if not answer:
            missing.append(token)
            return token
        return answer

    text = TOKEN.sub(spell, say)
    text = re.sub(r"\.(\s|$)", r"।\1", text)
    return " ".join(text.split()), missing


# ---------------------------------------------------------------- Devanagari -> Roman captions
# when several Roman spellings map to one Hindi word, the caption uses this one
PREFERRED = {"में": "mein", "नहीं": "nahi", "ये": "ye", "वो": "wo", "वाला": "wala", "वैसे": "waise", "रास्ता": "raasta",
             "सवाल": "sawaal", "ताकि": "taaki", "चीज़": "cheez", "पूरा": "poora", "पूरे": "poore", "पूरी": "poori",
             "फिर": "phir", "अच्छा": "accha", "हां": "haan", "इसमें": "isme", "उसमें": "usme", "हमारे": "humare",
             "भारत": "Bharat", "इंडिया": "India", "दिल्ली": "Delhi", "मुंबई": "Mumbai", "मुम्बई": "Mumbai", "चेन्नई": "Chennai", "कोलकाता": "Kolkata",
             "बेंगलुरु": "Bengaluru", "बैंगलोर": "Bengaluru", "हैदराबाद": "Hyderabad", "कोचीन": "Kochi", "कोच्चि": "Kochi", "पुणे": "Pune",
             "अहमदाबाद": "Ahmedabad", "जयपुर": "Jaipur", "लखनऊ": "Lucknow", "पटना": "Patna", "भोपाल": "Bhopal", "गुवाहाटी": "Guwahati",
             "श्रीनगर": "Srinagar", "कश्मीर": "Kashmir", "प्रयागराज": "Prayagraj", "वाराणसी": "Varanasi", "मणिपुर": "Manipur", "असम": "Assam",
             "बिहार": "Bihar", "गुजरात": "Gujarat", "पंजाब": "Punjab", "केरल": "Kerala", "गोवा": "Goa", "महाराष्ट्र": "Maharashtra",
             "राजस्थान": "Rajasthan", "तमिलनाडु": "Tamil Nadu", "कर्नाटक": "Karnataka", "ओडिशा": "Odisha", "अमेरिका": "America",
             "गूगल": "Google", "यूट्यूब": "YouTube", "व्हाट्सएप": "WhatsApp", "फ़ेसबुक": "Facebook", "इंस्टाग्राम": "Instagram",
             "एसआईआर": "SIR", "स्क्रीन": "screen", "बीजेपी": "BJP", "कांग्रेस": "Congress", "भाजपा": "BJP", "ईएमआई": "EMI", "आईपी": "IP", "जहां": "jahan", "यहां": "yahan", "कहां": "kahan", "पहुंच": "pahunch", "फ़ोन": "phone", "पूछा": "pucha"}
_CONS = {unicodedata.normalize("NFD", k): v for k, v in {"क": "k", "ख": "kh", "ग": "g", "घ": "gh", "ङ": "n", "च": "ch", "छ": "chh", "ज": "j", "झ": "jh", "ञ": "n",
         "ट": "t", "ठ": "th", "ड": "d", "ढ": "dh", "ण": "n", "त": "t", "थ": "th", "द": "d", "ध": "dh", "न": "n",
         "प": "p", "फ": "ph", "ब": "b", "भ": "bh", "म": "m", "य": "y", "र": "r", "ल": "l", "व": "v", "श": "sh",
         "ष": "sh", "स": "s", "ह": "h", "क़": "q", "ख़": "kh", "ग़": "g", "ज़": "z", "ड़": "d", "ढ़": "dh", "फ़": "f"}.items()}
_VOWELS = {"अ": "a", "आ": "aa", "इ": "i", "ई": "i", "उ": "u", "ऊ": "u", "ए": "e", "ऐ": "ai", "ओ": "o", "औ": "au",
           "ऑ": "o", "ऍ": "e", "ऋ": "ri"}
_MATRAS = {"ा": "A", "ि": "i", "ी": "i", "ु": "u", "ू": "u", "े": "e", "ै": "ai", "ो": "o", "ौ": "au", "ॉ": "o",
           "ॅ": "e", "ृ": "ri"}
_DEVANAGARI_WORD = re.compile(r"[ऀ-ॿ]+")
_reverse = {}
_dictionary = set()
_LETTERS = {unicodedata.normalize("NFD", k): v for k, v in {
    "ए": "A", "बी": "B", "सी": "C", "डी": "D", "ई": "E", "एफ़": "F", "जी": "G", "एच": "H", "आई": "I", "जे": "J", "के": "K",
    "एल": "L", "एम": "M", "एन": "N", "ओ": "O", "पी": "P", "क्यू": "Q", "आर": "R", "एस": "S", "टी": "T", "यू": "U",
    "वी": "V", "डब्ल्यू": "W", "एक्स": "X", "वाई": "Y", "ज़ेड": "Z", "फ़ोर": "4"}.items()}


def _same_form(text):
    """ड़ can be typed two ways that look identical; use one, or the spelling list misses the word."""
    return unicodedata.normalize("NFD", text)


def _sound_out(word):
    """Spell an unknown Hindi word in Roman letters, dropping the silent 'a' the way Hindi speakers do."""
    parts = []   # (consonant, vowel) pairs; vowel "a" is the unwritten one
    i, chars = 0, word
    while i < len(chars):
        ch = chars[i]
        nukta = chars[i:i + 2]
        if nukta in _CONS:
            parts.append([_CONS[nukta], "a"])
            i += 2
            continue
        if ch in _CONS:
            parts.append([_CONS[ch], "a"])
        elif ch in _VOWELS:
            parts.append(["", _VOWELS[ch]])
        elif ch in _MATRAS and parts:
            parts[-1][1] = _MATRAS[ch]
        elif ch == "्" and parts:
            parts[-1][1] = ""
        elif ch in "ंँ" and parts:
            parts[-1][1] += "n"
        i += 1
    if len(parts) > 1 and parts[-1][1] == "a":   # a word's last "a" is silent
        parts[-1][1] = ""
    for k in range(1, len(parts) - 1):   # so is one between a vowel and a consonant + vowel: "samajhna"
        if parts[k][1] == "a" and parts[k - 1][1] and parts[k + 1][0] and parts[k + 1][1]:
            parts[k][1] = ""
    return "".join(c + v for c, v in parts).replace("A", "a")


def _loose(word):
    """फ़ and फ, or ड़ and ड, are often swapped: match a word either way."""
    return _same_form(word).replace("़", "")


def is_english(word):
    """A real dictionary word? If this machine has no dictionary, trust the other checks."""
    if not _dictionary:
        for path in ("/usr/share/dict/words", "/usr/share/dict/american-english"):
            if os.path.exists(path):
                _dictionary.update(w.strip().lower() for w in open(path, encoding="utf-8", errors="ignore"))
                break
        _dictionary.add("")
    return len(_dictionary) < 2 or word.lower() in _dictionary


def _load_reverse():
    if _reverse:
        return
    for roman, spelled in load_words().items():
        key = _same_form(spelled)
        # keep an English spelling over a sound-spelled one: "automation", not "otomeshan"
        if key not in _reverse or (roman != _sound_out(key) and _reverse[key] == _sound_out(key)) or (
                len(roman) < len(_reverse[key]) and (roman != _sound_out(key)) == (_reverse[key] != _sound_out(key))):
            _reverse[key] = roman
    if os.path.exists(CAPTION_FILE):
        _reverse.update({_same_form(k): v for k, v in json.load(open(CAPTION_FILE, encoding="utf-8")).items()})
    _reverse.update({_same_form(k): v for k, v in PREFERRED.items()})
    for key, roman in list(_reverse.items()):   # the same word typed with or without the dot
        _reverse.setdefault(_loose(key), roman)


def _ask_english(batch):
    """Which of these are English words, and how are they really spelled?"""
    import ollama
    system = ("These words are written in Devanagari. Some are English words spoken in Hindi, like ऑटोमेशन or कंपनी. Others are real "
              "Hindi words, like नौकरी or करेंगे. For each English word give its correct English spelling. For each Hindi word give "
              "null, and never translate it. Reply as JSON with each input word as a key.")
    reply = ollama.chat(model=WORD_MODEL, format="json", options={"temperature": 0, "num_predict": 30 * len(batch) + 80},
                        messages=[{"role": "system", "content": system},
                                  {"role": "user", "content": json.dumps(batch, ensure_ascii=False)}])
    return {_same_form(k): v for k, v in json.loads(reply["message"]["content"]).items()}


def learn_words(hindi_text):
    """Find out once which unknown words are English, and save the spelling. Hindi words keep their sound."""
    _load_reverse()
    found = _DEVANAGARI_WORD.findall(_same_form(hindi_text).replace("।", " "))
    unknown = sorted({w for w in map(_same_form, found) if w not in _reverse and _loose(w) not in _reverse})
    if not unknown:
        return
    learned = {}
    for start in range(0, len(unknown), 12):   # small batches: in big ones the model skips words
        batch = unknown[start:start + 12]
        try:
            answers = _ask_english(batch)
        except Exception:   # no model right now: spell by sound, and ask again next time
            continue
        for w in batch:
            english = answers.get(w)
            usable = (isinstance(english, str) and re.fullmatch(r"[A-Za-z]{2,}", english) and sounds_like(english, w)
                      and english.lower() not in HINDI_LOOKALIKES and not HINDI_ENDINGS.search(english.lower())
                      and is_english(english))
            learned[w] = english.lower() if usable else _sound_out(w)
    if learned:
        _reverse.update(learned)
        saved = json.load(open(CAPTION_FILE, encoding="utf-8")) if os.path.exists(CAPTION_FILE) else {}
        saved.update({unicodedata.normalize("NFC", k): v for k, v in learned.items()})
        with open(CAPTION_FILE, "w", encoding="utf-8") as f:
            json.dump(dict(sorted(saved.items())), f, ensure_ascii=False, indent=0)
            f.write("\n")


def to_roman(hindi):
    """The caption for a line of the script: same words, same order. English words keep their real English spelling;
    numbers and short forms stay as they are."""
    learn_words(hindi)

    def word(m):
        w = _same_form(m.group(0))
        return _reverse.get(w) or _reverse.get(_loose(w)) or _sound_out(w)

    def spelled_out(m):   # आई-पी -> IP
        return "".join(_LETTERS[x] for x in m.group(0).split("-"))

    text = _same_form(hindi).replace("।", ".")
    names = "|".join(re.escape(k) for k in sorted(_LETTERS, key=len, reverse=True))
    text = re.sub(rf"(?<![ऀ-ॿ])(?:{names})(?:-(?:{names}))+(?![ऀ-ॿ])", spelled_out, text)
    text = _DEVANAGARI_WORD.sub(word, text)
    text = fix_english(" ".join(text.split()))
    return re.sub(r"(^|[.?!]\s+)([a-z])", lambda m: m.group(1) + m.group(2).upper(), text)


_english_fixes = {}


def fix_english(text):
    """Corrects sound-spelled English in headings and card labels: "Otomeshan" -> "Automation"."""
    if not _english_fixes:
        _load_reverse()
        known = {_same_form(spelled): roman for roman, spelled in load_words().items()}
        known.update({k: v for k, v in _reverse.items() if re.fullmatch(r"[a-z]+", v)})
        for spelled, roman in known.items():
            sound = _sound_out(spelled)
            if sound != roman and len(roman) >= 4 and difflib.SequenceMatcher(None, sound, roman).ratio() < 0.9:
                _english_fixes[sound] = roman
        _english_fixes.update(ROMAN_FIXES)

    def fix(m):
        w = m.group(0)
        low = w.lower()
        new = _english_fixes.get(low)
        if not new and len(low) >= 8:
            close = difflib.get_close_matches(low, _english_fixes, n=1, cutoff=0.84)
            new = _english_fixes[close[0]] if close else None
        if not new:
            return w
        return new.capitalize() if w[0].isupper() else new

    return re.sub(r"[A-Za-z]{3,}", fix, str(text))


def _fix_strings(value):
    """Every piece of screen text in a visual. Settings like icon names and file paths are left alone."""
    if isinstance(value, str):
        return fix_english(value)
    if isinstance(value, list):
        return [_fix_strings(v) for v in value]
    if isinstance(value, dict):
        return {k: (v if k in SETTINGS_KEYS else _fix_strings(v)) for k, v in value.items()}
    return value


SETTINGS_KEYS = {"type", "icon", "file", "query", "credit", "part", "total", "broken", "places", "number", "from", "sender"}


def fix_screen_text(script_scenes):
    """Headings and card labels: real English spelling everywhere on screen."""
    for scene in script_scenes:
        if scene.get("on_screen"):
            scene["on_screen"] = fix_english(scene["on_screen"])
        for beat in scene.get("beats") or []:
            if isinstance(beat.get("visual"), dict):
                beat["visual"] = _fix_strings(beat["visual"])
            if beat.get("pop"):
                beat["pop"] = fix_english(beat["pop"])


def sync_captions(path="scripts/script.json"):
    """Remake every caption from say_hi, and correct English on screen. The voice text isn't touched."""
    script = json.load(open(path, encoding="utf-8"))
    changed = 0
    for scene in script["scenes"]:
        for beat in scene.get("beats") or []:
            if beat.get("say_hi") and to_roman(beat["say_hi"]) != beat.get("say"):
                beat["say"] = to_roman(beat["say_hi"])
                changed += 1
    _english_fixes.clear()
    fix_screen_text(script["scenes"])
    json.dump(script, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"{changed} captions updated from say_hi; headings and labels checked")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    if sys.argv[1] == "--sync":
        sync_captions()
        raise SystemExit(0)
    line = " ".join(sys.argv[1:])
    if _DEVANAGARI_WORD.search(line):
        print(to_roman(line))
    else:
        hindi, left = to_hindi(line)
        print(hindi)
        if left:
            print("Not spelled yet (add to hindi_words.json):", ", ".join(left))
