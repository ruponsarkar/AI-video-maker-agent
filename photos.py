"""
Snack Code - real photos for "photo" beats, from Wikimedia Commons.

Run from inside a video's folder (auto_video.py also runs it for you):
    python ../../photos.py          # fetch a photo for every photo beat that has none
    python ../../photos.py --redo   # choose again, for example after deleting a wrong one

Only uses CC0, public-domain and CC BY photos, so they're safe to use in a video when credited.
Writes:  images/photos/sXX_bYY.jpg, images/photos/credits.json, images/photos/review.jpg

Look at review.jpg before voicing: the search can pick the wrong picture. To use your own photo, set
"file" on the beat's visual in script.json to its path. No internet or no match: that beat just gets
a different visual, so the video still renders.
"""
import html
import json
import os
import re
import sys
import time

from PIL import Image, ImageDraw

SCRIPT = "scripts/script.json"
FOLDER = "images/photos"
API = "https://commons.wikimedia.org/w/api.php"
HEADERS = {"User-Agent": "SnackCodeVideoTool/1.0 (local video pipeline)"}
ALLOWED = re.compile(r"^(cc0|public domain|pd\b|pdm|no restrictions|cc[ -]by[ -]\d)", re.I)
BLOCKED_LICENCE = re.compile(r"\b(sa|nc|nd)\b|share", re.I)
NOT_A_PHOTO = re.compile(r"logo|\bmaps?\b|flag|diagram|chart|graph|portrait|signature|screenshot|icon|coat of arms|"
                         r"poster|stamp|drawing|painting|infographic|network\b.*\b\d{4}\b|illustration|cartogra|"
                         r"\bpeople\b|\bpersons?\b|politician|minister|president", re.I)
MIN_WIDTH = 1280
MIN_RATIO = 1.25   # landscape only: the video is 16:9


def plain(text):
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", str(text or ""))).split())


_last_call = [0.0]


def _get(url, **kwargs):
    """Wikimedia limits how fast a tool may ask: wait between calls, and back off when it says 'too many'."""
    import time
    import requests
    for attempt in range(5):
        wait = 1.0 - (time.time() - _last_call[0])
        if wait > 0:
            time.sleep(wait)
        _last_call[0] = time.time()
        reply = requests.get(url, headers=HEADERS, **kwargs)
        if reply.status_code in (429, 503) and attempt < 4:
            pause = reply.headers.get("Retry-After", "")
            time.sleep(min(60, int(pause)) if pause.isdigit() else 10 * (attempt + 1))
            continue
        reply.raise_for_status()
        return reply


def search(query):
    import requests
    query = re.sub(r"\b(map|diagram|logo|chart)\b", "", query, flags=re.I).strip()
    params = {"action": "query", "format": "json", "generator": "search", "gsrnamespace": 6,
              "gsrsearch": f"{query} filetype:bitmap", "gsrlimit": 30, "prop": "imageinfo",
              "iiprop": "url|extmetadata|size|mime", "iiurlwidth": 1920}
    reply = _get(API, params=params, timeout=30)
    return list(reply.json().get("query", {}).get("pages", {}).values())


def looks_right(path, query):
    """Ask the local vision model: does it fit, and is it free of faces, slides and big text? Fails open."""
    try:
        import ollama
        ask = ("Look at the photo. Reply JSON: {\"matches\": true/false (clearly shows the subject), "
               "\"people_main\": true/false (a person or face is a main part), \"text_heavy\": true/false (mostly a chart, "
               "map, slide, sign, poster, logo or big text), \"clear\": true/false (sharp, well lit, looks professional)}"
               f"\nSubject: {query}")
        reply = ollama.chat(model="gemma3:4b", format="json", options={"temperature": 0},
                            messages=[{"role": "user", "content": ask, "images": [path]}])
        seen = json.loads(reply["message"]["content"])
        return bool(seen.get("matches", True)) and not seen.get("people_main") and not seen.get("text_heavy") and seen.get("clear", True) is not False
    except Exception:
        return True


def choose(pages, query, used):
    """Usable photos, best title match first."""
    words = [w for w in re.findall(r"[a-z]+", query.lower()) if len(w) > 2 and w not in ("map", "diagram", "logo")]
    ranked = []
    for page in pages:
        info = (page.get("imageinfo") or [{}])[0]
        meta = info.get("extmetadata", {})
        licence = plain(meta.get("LicenseShortName", {}).get("value"))
        title = page.get("title", "")
        about = " ".join([title, plain(meta.get("Categories", {}).get("value")),
                          plain(meta.get("ObjectName", {}).get("value")),
                          plain(meta.get("ImageDescription", {}).get("value"))[:400]])
        ok = (info.get("mime") == "image/jpeg" and info.get("width", 0) >= MIN_WIDTH
              and info.get("width", 0) / max(1, info.get("height", 1)) >= MIN_RATIO
              and ALLOWED.search(licence) and not BLOCKED_LICENCE.search(licence)
              and not NOT_A_PHOTO.search(about) and title not in used)
        if not ok:
            continue
        lowered = title.lower()
        score = sum(w in lowered for w in words)
        if words and score >= max(1, len(words) // 2):
            ranked.append((score, len(ranked), page, info, licence))
    return [r[2:] for r in sorted(ranked, key=lambda r: (-r[0], r[1]))][:5]


def download(info, path):
    import requests
    reply = _get(info.get("thumburl") or info["url"], timeout=60)
    from io import BytesIO
    Image.open(BytesIO(reply.content)).convert("RGB").save(path, "JPEG", quality=88)


def contact_sheet(credits):
    if not credits:
        return
    cols, cell_w, cell_h = 3, 480, 300
    rows = (len(credits) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cell_w, rows * cell_h), (24, 24, 32))
    d = ImageDraw.Draw(sheet)
    for k, c in enumerate(credits):
        x, y = k % cols * cell_w, k // cols * cell_h
        if os.path.exists(c["file"]):
            thumb = Image.open(c["file"])
            thumb.thumbnail((cell_w - 12, cell_h - 44))
            sheet.paste(thumb, (x + 6, y + 6))
        d.text((x + 8, y + cell_h - 34), f"{os.path.basename(c['file'])}: {c['query']}"[:64], fill=(255, 255, 255))
    sheet.save(os.path.join(FOLDER, "review.jpg"), quality=85)


def fetch_all(redo=False):
    """Fill in every photo beat. Returns how many were found and how many weren't."""
    script = json.load(open(SCRIPT, encoding="utf-8"))
    os.makedirs(FOLDER, exist_ok=True)
    credits_path = os.path.join(FOLDER, "credits.json")
    credits = json.load(open(credits_path, encoding="utf-8")) if os.path.exists(credits_path) and not redo else []
    used = {c["title"] for c in credits}
    found = missed = 0
    for i, scene in enumerate(script["scenes"]):
        for j, beat in enumerate(scene.get("beats") or []):
            v = beat.get("visual") or {}
            if v.get("type") not in ("photo", "title") or (not redo and v.get("file") and os.path.exists(v["file"])):
                continue
            if v.get("type") == "title" and not v.get("query"):
                continue   # a title card without a hook photo
            query = str(v.get("query") or "").strip()
            if not query:
                missed += 1
                continue
            try:
                path = os.path.join(FOLDER, f"s{i:02d}_b{j:02d}.jpg")
                pick, rejected = None, set()
                short = " ".join(query.split()[:2])
                backups = [str(q).strip() for q in (v.get("backup") or []) if str(q).strip()]
                for attempt in dict.fromkeys([f"{query} India", query, short, *backups]):   # Indian places first
                    for page, info, licence in choose(search(attempt), query, used | rejected):
                        rejected.add(page["title"])   # checked once is enough, whichever query found it
                        download(info, path)
                        if looks_right(path, query):
                            pick = (page, info, licence)
                            break
                        print(f"  scene {i:02d} beat {j:02d}: rejected {page['title'][:50]}")
                    if pick:
                        break
                if not pick:
                    print(f"  scene {i:02d} beat {j:02d}: no good photo for '{query}'")
                    v.pop("file", None)
                    if os.path.exists(path):
                        os.remove(path)
                    missed += 1
                    continue
                page, info, licence = pick
            except Exception as e:  # no internet or a bad reply: the video still renders without it
                print(f"  scene {i:02d} beat {j:02d}: couldn't fetch '{query}' ({type(e).__name__})")
                missed += 1
                continue
            artist = plain(info.get("extmetadata", {}).get("Artist", {}).get("value")) or "Wikimedia Commons"
            v["file"], v["credit"] = path, f"{artist[:40]} / {licence}"
            used.add(page["title"])
            credits = [c for c in credits if c["file"] != path]
            credits.append({"file": path, "query": query, "title": page["title"], "artist": artist,
                            "licence": licence, "page": info.get("descriptionurl", "")})
            found += 1
            print(f"  scene {i:02d} beat {j:02d}: {page['title'][:70]} ({licence})")
            time.sleep(1)   # be polite to a free service
    json.dump(script, open(SCRIPT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    json.dump(credits, open(credits_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    contact_sheet(credits)
    return found, missed


if __name__ == "__main__":
    if not os.path.exists(SCRIPT):
        raise SystemExit("Run this from inside a video's folder (projects/<video>).")
    got, lost = fetch_all("--redo" in sys.argv)
    print(f"Photos: {got} found, {lost} without a photo. Check {FOLDER}/review.jpg before voicing.")
