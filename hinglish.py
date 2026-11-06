"""
Keeps the voice and the captions on the same words: Devanagari <-> Roman, one word at a time.

to_roman()  makes the on-screen caption from the Devanagari script, so captions always match the voice.
to_hindi()  goes the other way, for lines you write in Roman. It never translates or reorders: "users"
            becomes यूज़र्स, not उपयोगकर्ता.

Spellings come from hindi_words.json. A spelling you fix in that file stays fixed in every video.

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
WORDS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hindi_words.json")
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


def to_roman(hindi):
    """The caption for a line of the script: same words, same order. Numbers and short forms stay as they are."""
    if not _reverse:
        for roman, spelled in load_words().items():
            key = _same_form(spelled)
            if key not in _reverse or len(roman) < len(_reverse[key]):
                _reverse[key] = roman
        _reverse.update({_same_form(k): v for k, v in PREFERRED.items()})

    def word(m):
        w = _same_form(m.group(0))
        return _reverse.get(w) or _sound_out(w)

    def spelled_out(m):   # आई-पी -> IP
        return "".join(_LETTERS[x] for x in m.group(0).split("-"))

    text = _same_form(hindi).replace("।", ".")
    names = "|".join(re.escape(k) for k in sorted(_LETTERS, key=len, reverse=True))
    text = re.sub(rf"(?<![ऀ-ॿ])(?:{names})(?:-(?:{names}))+(?![ऀ-ॿ])", spelled_out, text)
    text = _DEVANAGARI_WORD.sub(word, text)
    text = " ".join(text.split())
    return re.sub(r"(^|[.?!]\s+)([a-z])", lambda m: m.group(1) + m.group(2).upper(), text)


def sync_captions(path="scripts/script.json"):
    """After you edit say_hi by hand: remake every beat's caption from it, so the two still match."""
    script = json.load(open(path, encoding="utf-8"))
    changed = 0
    for scene in script["scenes"]:
        for beat in scene.get("beats") or []:
            if beat.get("say_hi") and to_roman(beat["say_hi"]) != beat.get("say"):
                beat["say"] = to_roman(beat["say_hi"])
                changed += 1
    json.dump(script, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"{changed} captions updated from say_hi")


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
