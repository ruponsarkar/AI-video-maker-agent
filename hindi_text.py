"""
Snack Code - make Hindi voice text safe to read aloud.

Chatterbox has no Hindi number or abbreviation handling: digits and Latin letters reach
the model as they are, so it guesses. voice.py runs every beat through spoken_hi() just
before speaking. script.json and the on-screen captions are not changed.

    1930             -> एक नौ तीन शून्य (helpline, digit by digit)
    ₹19,813 करोड़     -> उन्नीस हज़ार आठ सौ तेरह करोड़ रुपये
    I4C, OTP         -> आई-फ़ोर-सी, ओ-टी-पी
    cybercrime.gov.in -> साइबर क्राइम डॉट गव डॉट इन

Check any sentence without the GPU:
    python hindi_text.py "UPI PIN 1930 पर 25% ₹500"

Wrong word? Add it to WORDS, SPOKEN_AS_WORD or DOMAIN_PARTS below, or write it the way it
should sound in "say_hi" (text that is already in Hindi words is left alone).
"""
import re
import sys
import unicodedata


def _nfc(s):
    # one spelling for letters like ड़ / ज़, which can be typed in two ways
    return unicodedata.normalize("NFC", s)


ONES = _nfc("""शून्य एक दो तीन चार पाँच छह सात आठ नौ दस
ग्यारह बारह तेरह चौदह पंद्रह सोलह सत्रह अठारह उन्नीस बीस
इक्कीस बाईस तेईस चौबीस पच्चीस छब्बीस सत्ताईस अट्ठाईस उनतीस तीस
इकतीस बत्तीस तैंतीस चौंतीस पैंतीस छत्तीस सैंतीस अड़तीस उनतालीस चालीस
इकतालीस बयालीस तैंतालीस चौवालीस पैंतालीस छियालीस सैंतालीस अड़तालीस उनचास पचास
इक्यावन बावन तिरपन चौवन पचपन छप्पन सत्तावन अट्ठावन उनसठ साठ
इकसठ बासठ तिरसठ चौंसठ पैंसठ छियासठ सड़सठ अड़सठ उनहत्तर सत्तर
इकहत्तर बहत्तर तिहत्तर चौहत्तर पचहत्तर छिहत्तर सतहत्तर अठहत्तर उन्यासी अस्सी
इक्यासी बयासी तिरासी चौरासी पचासी छियासी सत्तासी अट्ठासी नवासी नब्बे
इक्यानवे बानवे तिरानवे चौरानवे पचानवे छियानवे सत्तानवे अट्ठानवे निन्यानवे""").split()

# inside an English short form (I4C, 5G) digits are said in English
EN_DIGITS = _nfc("ज़ीरो वन टू थ्री फ़ोर फ़ाइव सिक्स सेवन एट नाइन").split()

LETTERS = {k: _nfc(v) for k, v in {
    "A": "ए", "B": "बी", "C": "सी", "D": "डी", "E": "ई", "F": "एफ़", "G": "जी", "H": "एच", "I": "आई",
    "J": "जे", "K": "के", "L": "एल", "M": "एम", "N": "एन", "O": "ओ", "P": "पी", "Q": "क्यू", "R": "आर",
    "S": "एस", "T": "टी", "U": "यू", "V": "वी", "W": "डब्ल्यू", "X": "एक्स", "Y": "वाई", "Z": "ज़ेड"}.items()}

# capital short forms said as one word; every other capital word is spelled letter by letter
SPOKEN_AS_WORD = {k: _nfc(v) for k, v in {
    "PIN": "पिन", "SIM": "सिम", "RAM": "रैम", "ROM": "रॉम", "PAN": "पैन", "NASA": "नासा", "ISRO": "इसरो",
    "SEBI": "सेबी", "TRAI": "ट्राई", "AIIMS": "एम्स", "COVID": "कोविड", "OK": "ओके", "LAN": "लैन",
    "WIFI": "वाई फ़ाई", "GIF": "गिफ़", "CERT": "सर्ट"}.items()}

# English words the script writer leaves in Roman letters (lowercase keys)
WORDS = {k: _nfc(v) for k, v in {
    "wi-fi": "वाई फ़ाई", "wifi": "वाई फ़ाई", "whatsapp": "व्हाट्सऐप", "instagram": "इंस्टाग्राम",
    "facebook": "फ़ेसबुक", "telegram": "टेलीग्राम", "youtube": "यूट्यूब", "google": "गूगल",
    "gmail": "जीमेल", "paytm": "पेटीएम", "phonepe": "फ़ोनपे", "gpay": "जीपे", "iphone": "आईफ़ोन",
    "android": "एंड्रॉयड", "app": "ऐप", "apps": "ऐप्स", "online": "ऑनलाइन", "phone": "फ़ोन",
    "link": "लिंक", "scam": "स्कैम", "bank": "बैंक", "internet": "इंटरनेट", "password": "पासवर्ड",
    "email": "ईमेल", "deepfake": "डीपफ़ेक", "chatgpt": "चैट जी-पी-टी", "website": "वेबसाइट",
    "crore": "करोड़", "lakh": "लाख", "thousand": "हज़ार"}.items()}

DOMAIN_PARTS = {k: _nfc(v) for k, v in {
    "www": "डब्ल्यू डब्ल्यू डब्ल्यू", "gov": "गव", "in": "इन", "com": "कॉम", "org": "ओ-आर-जी", "net": "नेट",
    "co": "को", "nic": "एन-आई-सी", "cybercrime": "साइबर क्राइम", "rbi": "आर-बी-आई", "npci": "एन-पी-सी-आई",
    "sci": "एस-सी-आई", "google": "गूगल", "youtube": "यूट्यूब"}.items()}

# short forms the AI already wrote in Hindi letters as one word
_JOINED = ["OTP", "UPI", "KYC", "ATM", "SMS", "RBI", "NPCI", "URL", "VPN", "QR", "AI", "CVV", "USB", "APK",
           "CBI", "UIDAI", "IRCTC", "SBI", "HDFC", "ICICI", "GB", "MB"]
_DEV = "ऀ-ॿ"
_NUM = r"\d{1,3}(?:,\d{2,3})+(?:\.\d+)?|\d+(?:\.\d+)?"
_UNIT = "|".join(map(_nfc, ["करोड़", "लाख", "हज़ार", "हजार", "अरब", "crore", "lakh", "thousand", "cr"]))
_UNIT_WORD = {"crore": "करोड़", "cr": "करोड़", "lakh": "लाख", "thousand": "हज़ार"}
_SIZE_UNITS = {"GB", "MB", "KB", "TB", "MBPS", "KM", "KG", "MM", "CM", "HZ"}
_ORDINAL = {1: "पहला", 2: "दूसरा", 3: "तीसरा", 4: "चौथा", 5: "पाँचवाँ", 6: "छठा"}


def number_words(n):
    """Whole number -> Hindi words, Indian style (हज़ार, लाख, करोड़, अरब)."""
    if n < 100:
        return ONES[n]
    # 1100-1999 the way people say it, which also covers years: उन्नीस सौ पचहत्तर
    if 1100 <= n <= 1999:
        rest = n % 100
        return f"{ONES[n // 100]} सौ" + (f" {ONES[rest]}" if rest else "")
    parts = []
    for size, name in ((10 ** 9, "अरब"), (10 ** 7, "करोड़"), (10 ** 5, "लाख"), (1000, "हज़ार"), (100, "सौ")):
        if n >= size:
            parts.append(f"{number_words(n // size)} {_nfc(name)}")
            n %= size
    if n:
        parts.append(ONES[n])
    return " ".join(parts)


def digits_hi(s):
    return " ".join(ONES[int(c)] for c in s if c.isdigit())


def digits_en(s):
    return " ".join(EN_DIGITS[int(c)] for c in s if c.isdigit())


def spell(word):
    """OTP -> ओ-टी-पी (hyphens were heard most clearly in tests), digits in English."""
    out = []
    for run in re.findall(r"\d+|[A-Za-z]", word):
        out.append(digits_en(run) if run.isdigit() else LETTERS[run.upper()])
    return "-".join(out)


def _number(raw):
    raw = raw.replace(",", "")
    whole, _, frac = raw.partition(".")
    if whole == "1930":  # the cybercrime helpline
        return digits_hi(whole)
    # phone numbers and codes are read digit by digit
    if len(whole) >= 10 or (len(whole) > 1 and whole[0] == "0"):
        return digits_hi(whole)
    words = number_words(int(whole))
    return f"{words} पॉइंट {digits_hi(frac)}" if frac else words


def _domain(m):
    spoken = []
    for part in m.group(0).lower().split("."):
        spoken.append(DOMAIN_PARTS.get(part) or WORDS.get(part) or spell(part))
    return " डॉट ".join(spoken)


def _money(name):
    def fix(m):
        unit = m.group(2)
        unit = f" {_nfc(_UNIT_WORD.get(unit.lower(), unit))}" if unit else ""
        return f"{_number(m.group(1))}{unit} {name}"
    return fix


def _ordinal(m):
    n = int(m.group(1))
    return _ORDINAL.get(n) or f"{number_words(n)}वाँ"


def _mixed(m):
    word = m.group(0)
    sized = re.fullmatch(r"(\d+)([A-Za-z]+)", word)
    if sized and sized.group(2).upper() in _SIZE_UNITS:  # 16GB -> सोलह जी बी
        return f"{_number(sized.group(1))} {spell(sized.group(2))}"
    return spell(word)


def _caps(m):
    word = m.group(0)
    plural = word.endswith("s")
    word = word[:-1] if plural else word
    return SPOKEN_AS_WORD.get(word) or spell(word) + (_nfc("ज़") if plural else "")


def spoken_hi(text):
    """Return text with numbers, symbols, short forms and web addresses as spoken Hindi."""
    t = _nfc(str(text))
    t = t.translate({0x0966 + i: str(i) for i in range(10)})  # ०-९ -> 0-9

    t = re.sub(r"\b(?:[A-Za-z0-9-]+\.)+(?:gov|in|com|org|net|co|ai|io)\b", _domain, t, flags=re.I)
    t = re.sub(rf"(?<=[{_DEV}])\.(?=(?:गव|इन|कॉम)(?![{_DEV}]))", " डॉट ", t)
    t = t.replace("24/7", _nfc("ट्वेंटी फ़ोर सेवन"))

    t = re.sub(rf"(?:₹|\bRs\.?|\bINR\b|रु\.?)\s*({_NUM})(?:\s*({_UNIT})(?![{_DEV}A-Za-z]))?",
               _money("रुपये"), t)
    t = re.sub(rf"\$\s*({_NUM})(?:\s*({_UNIT})(?![{_DEV}A-Za-z]))?", _money("डॉलर"), t)
    t = re.sub(rf"({_NUM})\s*%", lambda m: f"{_number(m.group(1))} प्रतिशत", t)
    t = re.sub(r"\+\s*(\d+)", lambda m: f"प्लस {digits_hi(m.group(1))}", t)
    t = re.sub(r"(?<![\d.,])(\d+)\s*-\s*(\d+)(?![\d.,])",
               lambda m: f"{_number(m.group(1))} से {_number(m.group(2))}", t)  # 5-10 -> पाँच से दस

    t = re.sub(r"\b(\d+)(?:st|nd|rd|th)\b", _ordinal, t, flags=re.I)
    t = re.sub(r"\b(?:[A-Za-z]\.){2,}", lambda m: m.group(0).replace(".", ""), t)  # U.P.I. -> UPI
    t = re.sub(r"\b(?=[A-Za-z0-9]*\d)(?=[A-Za-z0-9]*[A-Za-z])[A-Za-z0-9]+\b", _mixed, t)  # I4C 5G 16GB
    t = re.sub(r"\b[A-Z]{2,}s?\b", _caps, t)
    t = re.sub(r"\b[A-Za-z]+(?:-[A-Za-z]+)*\b", lambda m: WORDS.get(m.group(0).lower(), m.group(0)), t)
    t = re.sub(r"\b[A-Z]\b", lambda m: LETTERS[m.group(0)], t)

    # the AI's joined Hindi spellings: ओटीपी -> ओ-टी-पी
    for short in _JOINED:
        joined = _nfc("".join(LETTERS[c] for c in short))
        t = re.sub(rf"(?<![{_DEV}]){joined}(?![{_DEV}])", spell(short), t)

    # English short forms with a digit, written in Hindi letters: आई4सी, 5जी
    t = re.sub(rf"(?<![{_DEV}\d])({LETTERS['I']})(\d)({LETTERS['C']})(?![{_DEV}])",
               lambda m: f"{m.group(1)}-{digits_en(m.group(2))}-{m.group(3)}", t)
    t = re.sub(rf"(?<![{_DEV}\d])([2-6])\s?({LETTERS['G']})(?![{_DEV}])",
               lambda m: f"{digits_en(m.group(1))}-{m.group(2)}", t)
    t = re.sub(rf"(?<=\d)(?=[{_DEV}])|(?<=[{_DEV}])(?=\d)", " ", t)  # 24घंटे -> 24 घंटे
    t = re.sub(_NUM, lambda m: _number(m.group(0)), t)

    t = t.replace("&", " और ").replace("@", " ऐट ").replace("₹", " रुपये ").replace("%", " प्रतिशत ")
    return re.sub(r"\s+", " ", t).strip()


def leftovers(text):
    """English words spoken_hi() could not convert: the model will guess these."""
    return sorted(set(re.findall(r"[A-Za-z][A-Za-z'-]*", text)))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    result = spoken_hi(" ".join(sys.argv[1:]))
    print(result)
    if leftovers(result):
        print("Still in English:", ", ".join(leftovers(result)))
