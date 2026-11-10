"""
Keeps the voice and the captions on the same words: Devanagari <-> Roman, one word at a time.

to_roman()  makes the on-screen caption from the Devanagari script, so captions always match the voice.
to_hindi()  goes the other way, for lines you write in Roman. It never translates or reorders: "users"
            becomes यूज़र्स, not उपयोगकर्ता.

Voice spellings are in hindi_words.json. Screen spellings the model has learned are in caption_words.json.
A spelling you fix in either file stays fixed in every video.

Captions ("say") and voice ("say_hi") are separate. From the video's folder:
    python ../../hinglish.py --sync          remake captions only for lines whose voice text you changed
    python ../../hinglish.py --sync --all    remake every caption
Check a line:  python hinglish.py "Data ka chhota tukda aapke phone tak pahunchta hai."
               python hinglish.py "डेटा का छोटा टुकड़ा आपके फ़ोन तक पहुंचता है।"
"""
import difflib
import itertools
import json
import os
import re
import sys
import unicodedata

MODEL = "qwen3:8b"
WORD_MODEL = "gemma3:4b"
HINDI_ENDINGS = re.compile(r"((?<!ll)enge|engi|yega|yegi|yenge|yengi|iye|aiye)$")
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
    w = word.lower()
    w = re.sub(r"tion|sion|sian|tian", "shn", w)   # station, potassium...
    w = re.sub(r"ti(?=um|al)", "sh", w)             # strontium, potential
    w = re.sub(r"(?<=[aeo])w$", "", w)              # show, flow: the w is silent
    w = re.sub(r"x", "ks", w)                       # oxygen -> oksygen
    w = re.sub(r"c(?=[eiy])", "s", w)               # cell, cyber
    w = re.sub(r"g(?=[eiy])", "j", w)               # oxygen, energy
    w = re.sub(r"(?<=[^aeiou])y|y(?=[^aeiou]|$)", "", w)   # a y that's only a vowel
    w = w.replace("ph", "f").replace("ch", "c").replace("sh", "s").replace("th", "t").replace("dh", "d")
    w = w.replace("kh", "k").replace("gh", "g").replace("bh", "b").replace("ck", "k")
    w = re.sub(r"(.)\1", r"\1", w)   # double letters
    w = re.sub(r"[aeiou']", "", w)
    return w.translate(_ROMAN_CLASSES).replace("s", "j")


def _hi_strict(hindi):
    """Hindi skeleton for the strict English check: ं counts as n/m (कंपनी = company), and the य glide is
    dropped (बेरियम = barium)."""
    out = []
    for i, ch in enumerate(hindi):
        if ch in _CONSONANTS:
            out.append(_CONSONANTS[ch])
        elif ch == "ं":
            out.append("m" if hindi[i + 1:i + 2] in ("प", "फ", "ब", "भ", "म") else "n")
    return re.sub(r"(.)\1+", r"\1", re.sub(r"y", "", "".join(out).translate(_ROMAN_CLASSES).replace("s", "j")))


def _edits(a, b):
    row = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        prev, row[0] = row[0], i
        for j, y in enumerate(b, 1):
            prev, row[j] = row[j], min(row[j] + 1, row[j - 1] + 1, prev + (x != y))
    return row[-1]


def _skeletons_en(word):
    """Every way the English spelling may be said: machine (ch = sh), gift (hard g), cell (soft c), exam (x = gz)."""
    w = word.lower().replace("-", "")
    w = re.sub(r"tion|sion|sian|tian", "Sn", w)
    w = re.sub(r"ti(?=um|al)", "S", w)
    w = re.sub(r"(?<=[aeo])w$", "", w)
    w = re.sub(r"gh(?=t|$)", "", w)                 # light, high: the gh is silent
    w = re.sub(r"mb$", "m", re.sub(r"^kn", "n", w))  # bomb, know
    w = re.sub(r"gn(?=$|[^aeiou])", "n", w)          # design, sign
    out = set()
    no_w = re.sub(r"(?<=[aeiou])w", "", w)   # powder = पाउडर: the w can be only a vowel sound
    for base, ch, soft_g, soft_c, x in itertools.product({w, no_w}, ("k", "S", "c"), "jg", "sk", ("ks", "gz")):
        v = base.replace("ch", ch)
        v = re.sub(r"g(?=[eiy])", soft_g, v)
        v = re.sub(r"c(?=[eiy])", soft_c, v)
        v = v.replace("x", x)
        v = re.sub(r"(?<=[^aeiou])y|y(?=[^aeiou]|$)", "", v)
        v = v.replace("ph", "f").replace("sh", "S").replace("th", "t").replace("dh", "d").replace("kh", "k")
        v = v.replace("gh", "g").replace("bh", "b").replace("ck", "k").replace("qu", "kv")
        v = re.sub(r"[aeiou']", "", v.replace("S", "s").lower())
        v = v.translate(_ROMAN_CLASSES).replace("s", "j").replace("y", "")
        out.add(re.sub(r"(.)\1+", r"\1", v))   # double sounds count once: system, cell
        out.add(re.sub(r"(.)\1+", r"\1", v.replace("c", "k")))
    return out - {""}


def english_matches(english, hindi):
    """True only when the Devanagari really is this English word said aloud: ऑक्सीजन = oxygen, मशीन = machine.
    Much stricter than sounds_like, so "beryllium" (बेरिलियम) or "potential" (पोटेंशियल) can't stand in for बेरियम or
    पोटेशियम. Same consonant sounds; in longer words one difference, but never in the last sound (मंत्रों is not "mantras")."""
    b = _hi_strict(_same_form(hindi).replace("-", ""))
    if not b:
        return False
    for a in _skeletons_en(english):
        if a[0] != b[0]:
            continue
        if a == b or (min(len(a), len(b)) >= 4 and a[-1] == b[-1] and _edits(a, b) <= 1):
            return True
    return False


def is_english_word(word):
    """A dictionary word, or two joined ones (shockwave, gunpowder)."""
    low = word.lower()
    if is_english(low):
        return True
    return any(is_english(low[:k]) and is_english(low[k:]) for k in range(4, len(low) - 3))   # not bat+aye


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
PREFERRED = {"बेरियम": "barium", "दिवाली": "Diwali", "हवा": "hawa", "जादू": "jaadu", "लो": "lo", "कम": "kam", "काम": "kaam", "में": "mein", "नहीं": "nahi", "ये": "ye", "वो": "wo", "वाला": "wala", "वैसे": "waise", "रास्ता": "raasta",
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
            nxt = chars[i + 1] if i + 1 < len(chars) else ""
            parts[-1][1] += "m" if ch == "ं" and nxt and nxt in "पफबभम" else "n"   # तांबा -> taamba, अंबर -> ambar
        i += 1
    if len(parts) > 1 and parts[-1][1] == "a" and not (parts[-1][0] == "y" and parts[-2][1] == ""):
        parts[-1][1] = ""   # a word's last "a" is silent, except after a joined य: मुख्य -> mukhya
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
        if not _usable_english(roman, key, strict=False):
            continue   # e.g. "low": "लो" was saved for the voice; on screen लो stays "lo"
        # keep an English spelling over a sound-spelled one: "automation", not "otomeshan"
        if key not in _reverse or (roman != _sound_out(key) and _reverse[key] == _sound_out(key)) or (
                len(roman) < len(_reverse[key]) and (roman != _sound_out(key)) == (_reverse[key] != _sound_out(key))):
            _reverse[key] = roman
    if os.path.exists(CAPTION_FILE):   # learned spellings fill gaps; they never replace one written in hindi_words.json
        saved = json.load(open(CAPTION_FILE, encoding="utf-8"))
        current = saved.pop(CHECK_KEY, 0) == CHECK_VERSION
        for k, v in saved.items():
            k = _same_form(k)
            if v != _sound_out(k) and not _usable_english(v, k):
                continue   # learned before the stricter check, and fails it
            if v == _sound_out(k) and not current:
                continue   # a guess from the old check: ask the model again once
            _reverse.setdefault(k, v)
    _reverse.update({_same_form(k): v for k, v in PREFERRED.items()})
    for key, roman in list(_reverse.items()):   # the same word typed with or without the dot
        _reverse.setdefault(_loose(key), roman)


CHECK_KEY, CHECK_VERSION = "_checked_with", 5


_known_hindi = set()


def _hindi_known():
    """Devanagari words that hindi_words.json spells the Hindi way (की = ki, घर = ghar): never English on screen."""
    if not _known_hindi:
        for roman, spelled in load_words().items():
            if not is_english(roman):
                _known_hindi.add(_same_form(spelled))
        _known_hindi.update(_same_form(k) for k, v in PREFERRED.items()
                            if v.islower() and not (len(v) >= 4 and is_english(v)))   # लो = lo, not "low"
        _known_hindi.add("")
    return _known_hindi


def _usable_english(english, hindi, strict=True):
    """May this English word stand on screen for this Devanagari word?"""
    if not isinstance(english, str):
        return False
    low = english.lower()
    if low == _sound_out(_same_form(hindi)).lower() or not re.fullmatch(r"[A-Za-z]+", english):
        return True   # a Hindi spelling, not an English word: nothing to check
    if not strict and not is_english(low):
        return True   # a hand-written voice spelling like "kaafi"
    if low in HINDI_LOOKALIKES or HINDI_ENDINGS.search(low) or not english_matches(low, hindi):
        return False
    if len(low) < 4 and (len(low) < 3 or _same_form(hindi) in _hindi_known() or not is_english(low)):
        return False   # gas = गैस is fine, but की is never "key"
    if is_english_word(low):
        return True
    # chemical salts the dictionary lacks (chlorate, perchlorate, chloride): exact sounds only
    exact = re.sub(r"y", "", _skeleton_en(low)) == _hi_strict(_same_form(hindi))
    chemical = r"^(per)?(chlor|nitr|sulf|sulph|phosph|carbon|brom|iod|fluor|hydr|ox|silic|chrom|mangan|bicarbon)"
    return exact and len(low) >= 7 and bool(re.search(r"(ate|ide|ite)$", low)) and bool(re.match(chemical, low))


def _ask_english(batch):
    """How is each word written in English letters? gemma 4b can't reliably say WHICH words are English, but it
    spells well; the strict sound check (_usable_english) then decides whether its answer is a real English word."""
    import ollama
    system = ("Write each Devanagari word in English letters. Many are English words used in Hindi: write those with their "
              "correct English spelling, for example ऑटोमेशन -> automation, कंपनी -> company, सर्वर -> server. Write Hindi "
              "words the usual Roman way, for example नौकरी -> naukri, करेंगे -> karenge. Never translate. "
              "Reply as JSON with each input word as a key.")
    words = [unicodedata.normalize("NFC", w) for w in batch]
    reply = ollama.chat(model=WORD_MODEL, format="json", options={"temperature": 0, "num_predict": 30 * len(batch) + 80},
                        messages=[{"role": "system", "content": system},
                                  {"role": "user", "content": json.dumps(words, ensure_ascii=False)}])
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
            usable = (isinstance(english, str) and re.fullmatch(r"[A-Za-z]{2,}", english)
                      and english.lower() != _sound_out(w) and _usable_english(english, w))
            learned[w] = english.lower() if usable else _sound_out(w)   # Hindi words keep the rule spelling
    if learned:
        _reverse.update(learned)
        saved = json.load(open(CAPTION_FILE, encoding="utf-8")) if os.path.exists(CAPTION_FILE) else {}
        if saved.get(CHECK_KEY) != CHECK_VERSION:   # drop the old check's guesses; they were asked again just now
            saved = {k: v for k, v in saved.items() if k != CHECK_KEY and (v != _sound_out(_same_form(k)) or k in learned)}
        saved.update({unicodedata.normalize("NFC", k): v for k, v in learned.items()})
        saved[CHECK_KEY] = CHECK_VERSION
        with open(CAPTION_FILE, "w", encoding="utf-8") as f:
            json.dump(dict(sorted(saved.items())), f, ensure_ascii=False, indent=0)
            f.write("\n")


def _letter_names(word):
    """पीवीसी -> PVC: a word made only of 3+ English letter names is a short form."""
    out, i = "", 0
    names = sorted(_LETTERS, key=len, reverse=True)
    while i < len(word):
        hit = next((n for n in names if word.startswith(n, i)), None)
        if not hit:
            return None
        out, i = out + _LETTERS[hit], i + len(hit)
    return out if len(out) >= 3 and out.isalpha() else None


def to_roman(hindi):
    """The caption for a line of the script: same words, same order. English words keep their real English spelling;
    numbers and short forms stay as they are."""
    learn_words(hindi)

    def word(m):
        w = _same_form(m.group(0))
        known = _reverse.get(w) or _reverse.get(_loose(w))
        if known and known != _sound_out(w):
            return known
        return _letter_names(w) or known or _sound_out(w)

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
            if (sound != roman and len(roman) >= 4 and difflib.SequenceMatcher(None, sound, roman).ratio() < 0.9
                    and _usable_english(roman, spelled)):   # English only: "kam" must never become "kaam"
                _english_fixes[sound] = roman
        _english_fixes.update(ROMAN_FIXES)

    def fix(m):
        w = m.group(0)
        low = w.lower()
        new = _english_fixes.get(low)
        if not new and len(low) >= 8:
            close = difflib.get_close_matches(low, _english_fixes, n=1, cutoff=0.84)
            # only a near spelling of the SAME sounds: "poteshiyam" must not become "potential"
            new = _english_fixes[close[0]] if close and _skeleton_en(close[0]) == _skeleton_en(low) else None
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


SETTINGS_KEYS = {"type", "icon", "file", "query", "backup", "credit", "part", "total", "broken", "places", "number", "from", "sender"}


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


SCREEN_WRITER = ("Write this Hindi line in Roman letters, for on-screen captions. Keep exactly the same words in the same order. "
                 "Write every English word in its correct English spelling, for example डिसीजन मेकिंग -> decision making, "
                 "क्रिएटिविटी -> creativity. Write Hindi words the common Roman way, for example नौकरी -> naukri. Keep numbers, "
                 "capital short forms like AI and UPI, and web addresses as they are. Reply as JSON: {\"text\": \"...\"}")


def same_word(roman, hindi):
    """Stricter than sounds_like: the caption word must start with the same sound and share most of its sounds,
    so a model can't swap in a different word (मौके -> "khoje")."""
    a = _skeleton_en(roman.replace("-", ""))
    b = _skeleton_hi(_same_form(hindi).replace("-", ""))
    if not a or not b:
        return roman.lower() == _sound_out(_same_form(hindi)).lower()
    return a[0] == b[0] and difflib.SequenceMatcher(None, a, b).ratio() >= 0.67


def _bare(token):
    return re.sub(r"^[^\wऀ-ॿ₹]+|[^\wऀ-ॿ%]+$", "", token)


def screen_text(hindi, use_model=True):
    """The caption for a line: its own correct spelling, checked word by word against the voice text.

    The model writes it with the whole sentence as context, so it knows "डिसीजन मेकिंग" is "decision making".
    Then every word is compared with the Hindi it stands for. Any word that doesn't match is replaced by the
    letter-by-letter spelling, so the caption can never show a word the voice doesn't say."""
    plain = to_roman(hindi)
    if not use_model or not _DEVANAGARI_WORD.search(hindi):
        return plain
    voice = hindi.replace("।", ". ").split()
    fallback = plain.split()
    if len(fallback) != len(voice):
        return plain
    for attempt in range(2):
        try:
            import ollama
            reply = ollama.chat(model=WORD_MODEL, format="json", options={"temperature": 0.1 * attempt, "num_predict": 400},
                                messages=[{"role": "system", "content": SCREEN_WRITER}, {"role": "user", "content": hindi}])
            written = str(json.loads(reply["message"]["content"]).get("text") or "").split()
        except Exception:
            return plain
        if len(written) == len(voice):
            break
    else:
        return plain
    out, learned = [], {}
    for said, wrote, safe in zip(voice, written, fallback):
        h, r = _bare(said), _bare(wrote)
        if not _DEVANAGARI_WORD.search(h) or not re.fullmatch(r"[A-Za-z'-]+", r) or _bare(safe).isupper():
            out.append(safe)   # numbers, short forms (आई-पी -> IP), addresses: the plain version has them right
        elif _bare(safe).lower() != _sound_out(_same_form(h)).lower():
            out.append(safe)   # the spelling list already knows this word (customer, Diwali, mein)
        elif r.lower() != _bare(safe).lower() and _usable_english(r, h) and r.lower() != _sound_out(_same_form(h)):
            out.append(safe.replace(_bare(safe), r.lower() if _bare(safe).islower() else r.capitalize()))
            learned[_same_form(h)] = r.lower()
        else:
            out.append(safe)   # a Hindi word: the rule spelling, never the model's (it writes "mishil", "ashal")
    if learned:
        remember(learned)
    text = fix_english(" ".join(out))
    return re.sub(r"(^|[.?!]\s+)([a-z])", lambda m: m.group(1) + m.group(2).upper(), text)


def remember(learned):
    """Save checked English spellings, so the word is right next time even without the model."""
    _reverse.update(learned)
    saved = json.load(open(CAPTION_FILE, encoding="utf-8")) if os.path.exists(CAPTION_FILE) else {}
    saved.update({unicodedata.normalize("NFC", k): v for k, v in learned.items()})
    with open(CAPTION_FILE, "w", encoding="utf-8") as f:
        json.dump(dict(sorted(saved.items())), f, ensure_ascii=False, indent=0)
        f.write("\n")


def _close(english, hindi):
    """Nearly the same sounds (not a translation): worth a person's look."""
    b = _hi_strict(_same_form(hindi))
    return bool(b) and any(a[:1] == b[:1] and difflib.SequenceMatcher(None, a, b).ratio() >= 0.6
                           for a in _skeletons_en(english))


def english_pass(scenes, log=print):
    """The English-word checker, run over a whole script after the captions are written.

    Finds every caption word that is still spelled by sound (mashin, shokvev), asks the model how each is written in
    English, and swaps in the English spelling where the strict sound check agrees (machine, shockwave). Hindi words
    stay as they are. Returns (words fixed, words a person should look at)."""
    spelled = {}
    for scene in scenes:
        for beat in scene.get("beats") or []:
            say = str(beat.get("say") or "")
            for w in set(_DEVANAGARI_WORD.findall(_same_form(str(beat.get("say_hi") or "")).replace("।", " "))):
                sound = _sound_out(w)
                if len(sound) >= 3 and re.search(rf"(?<![A-Za-z]){re.escape(sound)}(?![A-Za-z])", say, re.I) \
                        and _same_form(w) not in _hindi_known() and not is_english(sound):
                    spelled[w] = sound
    words = sorted(spelled)
    answers = {}
    for start in range(0, len(words), 12):
        try:
            answers.update(_ask_english(words[start:start + 12]))
        except Exception:
            log("    English check: the model didn't answer; captions left as they are")
            return [], []
    fixed, unsure = {}, []
    for w in words:
        english = answers.get(w)
        if not isinstance(english, str) or not re.fullmatch(r"[A-Za-z-]{2,}", english):
            continue
        english = english.replace("-", "").lower()
        if english == spelled[w]:
            continue
        if _usable_english(english, w):
            fixed[w] = english
        elif is_english_word(english) and english not in HINDI_LOOKALIKES and _close(english, w):
            unsure.append(f"{unicodedata.normalize('NFC', w)}: shown as \"{spelled[w]}\"; is it the English word \"{english}\"?")
    if fixed:
        remember(fixed)
        for scene in scenes:
            for beat in scene.get("beats") or []:
                hindi = _same_form(str(beat.get("say_hi") or ""))
                for w, english in fixed.items():
                    if w in hindi:
                        beat["say"] = re.sub(rf"(?<![A-Za-z]){re.escape(spelled[w])}(?![A-Za-z])",
                                             lambda m: english.capitalize() if m.group(0)[0].isupper() else english,
                                             str(beat.get("say") or ""), flags=re.I)
        _english_fixes.clear()
        fix_screen_text(scenes)   # headings and cards learn the new words too
    return [f"{spelled[w]} -> {e}" for w, e in fixed.items()], unsure


def sync_captions(path="scripts/script.json", everything=False):
    """Captions and voice are kept separately. This remakes a caption only where its voice line changed
    (or every caption, with --all), so captions you edited by hand stay as they are."""
    script = json.load(open(path, encoding="utf-8"))
    changed = 0
    for scene in script["scenes"]:
        for beat in scene.get("beats") or []:
            hindi = beat.get("say_hi")
            if hindi and (everything or beat.get("say_from") != hindi):
                beat["say"], beat["say_from"] = screen_text(hindi), hindi
                changed += 1
    _english_fixes.clear()
    fix_screen_text(script["scenes"])
    fixed, unsure = english_pass(script["scenes"])
    json.dump(script, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"{changed} captions written; headings and labels checked")
    if fixed:
        print("English spellings fixed: " + ", ".join(fixed))
    for line in unsure:
        print("Check:", line)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    if sys.argv[1] == "--sync":
        sync_captions(everything="--all" in sys.argv)
        raise SystemExit(0)
    line = " ".join(sys.argv[1:])
    if _DEVANAGARI_WORD.search(line):
        print(screen_text(line))
    else:
        hindi, left = to_hindi(line)
        print(hindi)
        if left:
            print("Not spelled yet (add to hindi_words.json):", ", ".join(left))
