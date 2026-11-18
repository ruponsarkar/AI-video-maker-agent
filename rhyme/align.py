"""
When is each lyric line sung in the AI song (audio/song.wav)? Whisper (CPU, venv) hears the song with word times,
then every line is matched to the words in order. The model sometimes skips or repeats a line: a line it skipped
gets a time between its neighbours. Writes audio/song_timing.json (the same shape as video.py's timeline).

    python rhyme/align.py <song folder>
"""
import difflib
import hashlib
import json
import math
import os
import sys

import numpy as np
import soundfile as sf

# sounds Whisper (and singers) mix up are one letter here: aspirated/plain, retroflex/dental, nukta forms
_SAME = {"ख": "क", "घ": "ग", "छ": "च", "झ": "ज", "ठ": "ट", "ढ": "ड", "थ": "त", "ध": "द", "फ": "प", "भ": "ब",
         "ट": "त", "ड": "द", "ण": "न", "श": "स", "ष": "स", "ङ": "न", "ञ": "न", "ं": "न", "ँ": "न",
         "क़": "क", "ख़": "क", "ग़": "ग", "ज़": "ज", "ड़": "द", "ढ़": "द", "फ़": "प", "य़": "य", "व": "ब"}


def skeleton(text):
    out = []
    for ch in text.replace("़", ""):
        ch = _SAME.get(ch, ch)
        if "क" <= ch <= "ह" or ch == "न":
            out.append(_SAME.get(ch, ch))
    return "".join(out)


def stamp(folder):
    song = os.path.join(folder, "audio", "song.wav")
    script = open(os.path.join(folder, "script.json"), "rb").read()
    return f"{os.path.getmtime(song)}|{hashlib.md5(script).hexdigest()}"


def hear(path, size="medium"):
    from faster_whisper import WhisperModel
    from scipy.signal import resample_poly
    x, fs = sf.read(path, dtype="float32")
    if x.ndim > 1:
        x = x.mean(axis=1)
    g = math.gcd(fs, 16000)
    y = resample_poly(x, 16000 // g, fs // g).astype(np.float32)
    model = WhisperModel(size, device="cpu", compute_type="int8")
    segs, _ = model.transcribe(y, language="hi", word_timestamps=True, vad_filter=False, beam_size=5)
    words = []
    for s in segs:
        for w in s.words or []:
            sk = skeleton(w.word)
            if sk:
                words.append({"sk": sk, "start": float(w.start), "end": float(w.end), "text": w.word.strip()})
    return words, len(x) / fs


def match(lines, words):
    """[(first word, last word) or None] per line: the best in-order match, skipping what doesn't fit."""
    cands = []
    for ln in lines:
        target = skeleton(ln)
        n = max(1, len(ln.split()))
        found = []
        for s in range(len(words)):
            for L in range(max(1, n - 2), n + 3):
                if s + L > len(words):
                    break
                got = "".join(w["sk"] for w in words[s:s + L])
                r = difflib.SequenceMatcher(None, target, got).ratio()
                if r >= 0.5:
                    found.append((r, s, s + L - 1))
        found.sort(reverse=True)
        cands.append(found[:12])
    # dynamic programme: lines in order, each takes one candidate after the previous one's end, or is skipped
    best = {-1: (0.0, [])}         # last used word -> (score, choices)
    for i, found in enumerate(cands):
        nxt = {}
        for last, (score, picks) in best.items():
            key = last
            if key not in nxt or nxt[key][0] < score:
                nxt[key] = (score, picks + [None])
            for r, s, e in found:
                if s > last:
                    sc = score + r
                    if e not in nxt or nxt[e][0] < sc:
                        nxt[e] = (sc, picks + [(s, e)])
        # keep it small: the best few end points
        best = dict(sorted(nxt.items(), key=lambda kv: -kv[1][0])[:60])
    return max(best.values(), key=lambda v: v[0])[1]


INTRO_KEEP = 3.0    # seconds of music before the first sung line (the title pops up over moving pictures)
MAX_GAP = 4.0       # a music-only break longer than this between lines ...
GAP_KEEP = (1.2, 1.3)   # ... keeps this much after the line before and before the next line
END_CARD = 5.0      # the end card (Subscribe) after the last line, while the music fades out
XF = 0.25           # crossfade at every cut, so the music doesn't click


def edit_plan(times, seconds, heard=None, bar=2.4):
    """Parts of the AI song to keep (in its own seconds): a short intro, short breaks, a short ending.
    Times Whisper only guessed (a line it didn't hear) are never cut close: 2 bars more intro if the first line is
    a guess, and a break is only shortened when the lines on both sides were heard."""
    heard = heard or [True] * len(times)
    first = min(a for a, _ in times)
    last = max(b for _, b in times)
    segs, start = [], max(0.0, first - INTRO_KEEP - (0 if heard[0] else 2 * bar))
    for k, ((a0, b0), (a1, b1)) in enumerate(zip(times, times[1:])):
        if a1 - b0 > MAX_GAP and heard[k] and heard[k + 1]:
            segs.append((start, b0 + GAP_KEEP[0]))
            start = a1 - GAP_KEEP[1]
    end_extra = 0 if heard[-1] else 2 * bar
    segs.append((start, min(seconds, last + 1.0 + END_CARD + end_extra)))
    return segs


def remap(t, segs):
    """A time in the AI song -> the same moment in the edited song (pieces joined with XF crossfades)."""
    off = 0.0                       # where piece k starts in the edited song
    for k, (a, b) in enumerate(segs):
        if t < a:                   # inside a cut: the moment the next piece starts
            return off
        if t <= b:
            return off + (t - a)
        off += (b - a) - XF         # the next piece overlaps this one by XF
    return off + XF


def write_edit(folder, segs):
    """audio/song_edit.wav: the kept pieces of song.wav, crossfaded, faded in and out. Returns its length."""
    x, fs = sf.read(os.path.join(folder, "audio", "song.wav"), dtype="float32", always_2d=True)
    xf = int(XF * fs)
    out = None
    for a, b in segs:
        piece = x[int(a * fs):int(b * fs)].copy()
        if out is None:
            out = piece
            continue
        ramp = np.linspace(0, 1, xf, dtype=np.float32)[:, None]
        mixed = out[-xf:] * (1 - ramp) + piece[:xf] * ramp
        out = np.concatenate([out[:-xf], mixed, piece[xf:]])
    if segs[0][0] > 0:                         # the song now starts mid-intro: a quick fade in
        n = int(0.3 * fs)
        out[:n] *= np.linspace(0, 1, n, dtype=np.float32)[:, None]
    n = int(min(3.0, len(out) / fs / 3) * fs)  # and it fades out under the end card
    out[-n:] *= np.linspace(1, 0, n, dtype=np.float32)[:, None]
    sf.write(os.path.join(folder, "audio", "song_edit.wav"), out, fs)
    return len(out) / fs


def listen_again(folder, texts, times, picks):
    """Lines Whisper missed in the whole song (often the first: the long intro confuses it): listen again to just
    the few seconds where each should be. {line: ((start, end), word times)} for those found, in song.wav's time."""
    todo = [k for k, p in enumerate(picks) if p is None]
    if not todo:
        return {}
    from faster_whisper import WhisperModel
    from scipy.signal import resample_poly
    x, fs = sf.read(os.path.join(folder, "audio", "song.wav"), dtype="float32", always_2d=True)
    x = x.mean(axis=1)
    g = math.gcd(fs, 16000)
    model = WhisperModel("small", device="cpu", compute_type="int8")
    found = {}
    for k in todo:
        a = max(0.0, times[k][0] - 2.0)
        b = min(len(x) / fs, times[k][1] + 2.0)
        y = resample_poly(x[int(a * fs):int(b * fs)], 16000 // g, fs // g).astype(np.float32)
        segs, _ = model.transcribe(y, language="hi", word_timestamps=True, vad_filter=False, beam_size=5)
        ws = [{"sk": skeleton(w.word), "start": a + float(w.start), "end": a + float(w.end)}
              for s in segs for w in (s.words or []) if skeleton(w.word)]
        p = match([texts[k]], ws)[0] if ws else None
        if p:
            before = times[k - 1][1] if k else 0.0
            after = times[k + 1][0] if k + 1 < len(times) else 1e9
            span = (ws[p[0]]["start"], ws[p[1]]["end"])
            if span[0] >= before - 0.2 and span[1] <= after + 0.2 and span[1] - span[0] >= 0.5:
                found[k] = (span, [[round(w["start"], 3), round(w["end"], 3)] for w in ws[p[0]:p[1] + 1]])
    if found:
        print(f"  listened again: found {len(found)} more line(s) Whisper missed the first time")
    return found


def build(folder, words, seconds):
    script = json.load(open(os.path.join(folder, "script.json"), encoding="utf-8"))
    beat = 60.0 / float(script.get("tempo", 100))
    bar = beat * 4
    flat = [(i, j, b) for i, sc in enumerate(script["scenes"]) for j, b in enumerate(sc["beats"])]
    picks = match([b["say_hi"] for _, _, b in flat], words)
    for _ in range(2):   # a line "heard" in a tiny slot is a mis-match: drop it
        bad = [k for k, p in enumerate(picks) if p and words[p[1]]["end"] - words[p[0]]["start"] < 0.5]
        for k in bad:
            picks[k] = None
    times = [(words[p[0]]["start"], words[p[1]]["end"]) if p else None for p in picks]
    heard = sum(1 for t in times if t)
    # lines the model skipped (or Whisper missed): between their neighbours, 2 bars apart from the nearest known line
    known = [k for k, t in enumerate(times) if t]
    if not known:
        raise SystemExit("  Whisper couldn't find the lyrics in the song: make another take (python rhyme.py song <slug>)")
    for k in range(len(times)):
        if times[k]:
            continue
        before = max((q for q in known if q < k), default=None)
        after = min((q for q in known if q > k), default=None)
        if before is not None and after is not None:
            a, b = times[before][1], times[after][0]
            step = (b - a) / (after - before)
            start = a + step * (k - before - 1) + 0.1
            times[k] = (start, start + max(0.8, step - 0.2))
        elif after is not None:
            start = max(0.0, times[after][0] - (after - k) * 2 * bar)
            times[k] = (start, start + 2 * bar - 0.3)
        else:
            start = min(seconds - 1, times[before][1] + (k - before - 1) * 2 * bar + 0.2)
            times[k] = (start, start + 2 * bar - 0.3)
    for k in range(1, len(times)):      # never go backwards
        if times[k][0] < times[k - 1][0] + 0.3:
            s = times[k - 1][0] + 0.3
            times[k] = (s, max(s + 0.5, times[k][1]))
    # children leave during a long music-only start or break: cut them short (audio/song_edit.wav)
    found = listen_again(folder, [b["say_hi"] for _, _, b in flat], times, picks)
    for k, (t, _) in found.items():
        times[k] = t
    orig, segs = seconds, edit_plan(times, seconds, [p is not None or k in found for k, p in enumerate(picks)], bar)
    words = [dict(w, start=remap(w["start"], segs), end=remap(w["end"], segs)) for w in words]
    times = [(remap(a, segs), remap(b, segs)) for a, b in times]
    found = {k: (t, [[round(remap(a, segs), 3), round(remap(b, segs), 3)] for a, b in wt])
             for k, (t, wt) in found.items()}
    seconds = write_edit(folder, segs)
    heard = sum(1 for p in picks if p) + len(found)
    lines = []
    for k, (i, j, b) in enumerate(flat):
        s, e = times[k]
        nxt = times[k + 1][0] if k + 1 < len(times) else seconds
        e = min(e, nxt - 0.05)
        word_times = ([[round(w["start"], 3), round(w["end"], 3)] for w in words[picks[k][0]:picks[k][1] + 1]]
                      if picks[k] else found[k][1] if k in found else [])
        lines.append({"scene": i, "beat": j, "start": round(s, 3), "len": round(max(0.6, e - s), 3), "rate": 1.0,
                      "bars": max(1, round((e - s) / bar)), "file": None, "say": b.get("say") or "", "say_hi": b["say_hi"],
                      "heard": picks[k] is not None or k in found, "words": word_times})
    first = lines[0]["start"]
    sections = [{"kind": "intro", "start": 0.0, "end": round(max(0.1, first - 0.4), 3)}]
    stanzas = []
    for i, sc in enumerate(script["scenes"]):
        mine = [x for x in lines if x["scene"] == i]
        start = sections[-1]["end"]
        stanzas.append(start)
        nxt = next((x["start"] for x in lines if x["scene"] == i + 1), None)
        end = round(nxt - 0.4, 3) if nxt is not None else round(mine[-1]["start"] + mine[-1]["len"] + 0.5, 3)
        sections.append({"kind": sc.get("kind", "verse"), "start": start, "end": max(end, start + 0.5), "scene": i})
    last = sections[-1]["end"]
    length = max(seconds, last + END_CARD + 0.5)
    end_card = max(last + 0.5, length - END_CARD)
    sections.append({"kind": "outro", "start": last, "end": end_card})
    sections.append({"kind": "end", "start": end_card, "end": length})
    plan = {"tempo": round(60 / beat, 2), "lines": lines, "sections": sections, "stanzas": stanzas,
            "length": round(length, 3), "source": "ai_song", "stamp": stamp(folder), "heard": heard,
            "audio": "song_edit.wav", "edit": EDIT_VERSION, "cut": round(orig - seconds, 1)}
    json.dump(plan, open(os.path.join(folder, "audio", "song_timing.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"  song edited: {orig:.0f} s -> {seconds:.0f} s (short intro, breaks and ending; audio/song_edit.wav)")
    print(f"  song timing: {heard} of {len(lines)} lines heard in the song"
          + ("" if heard == len(lines) else " (the rest are placed between them; the model may have skipped them)"))
    return plan


def cpu_only(fn):
    """Whisper runs on the CPU here. The GPU is hidden only while fn runs: left hidden, it also hid the GPU from
    the clip maker that rhyme.py starts later in the same `make` (\"GPU is not reachable\", no 3D clips)."""
    import functools

    @functools.wraps(fn)
    def wrapped(*a, **k):
        before = os.environ.get("CUDA_VISIBLE_DEVICES")
        os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")
        try:
            return fn(*a, **k)
        finally:
            if before is None:
                os.environ.pop("CUDA_VISIBLE_DEVICES", None)
            else:
                os.environ["CUDA_VISIBLE_DEVICES"] = before
    return wrapped


@cpu_only
def score(folder, wav):
    """How well a take follows the lyrics: (lines heard, average match). Whisper small: quick."""
    script = json.load(open(os.path.join(folder, "script.json"), encoding="utf-8"))
    lines = [b["say_hi"] for sc in script["scenes"] for b in sc["beats"]]
    words, _ = hear(wav, "small")
    picks = match(lines, words)
    got = []
    for ln, p in zip(lines, picks):
        if p:
            heard = "".join(w["sk"] for w in words[p[0]:p[1] + 1])
            got.append(difflib.SequenceMatcher(None, skeleton(ln), heard).ratio())
    return len(got), (sum(got) / len(got) if got else 0.0), len(lines)


EDIT_VERSION = 3   # bump when the song editing (edit_plan) changes: old songs are re-edited, without Whisper again


@cpu_only
def run(folder):
    """Whisper hears the song once (audio/song_words.json keeps what it heard), then the timing + edit are built."""
    song = os.path.join(folder, "audio", "song.wav")
    cache = os.path.join(folder, "audio", "song_words.json")
    key = f"{os.path.getmtime(song)}"
    got = json.load(open(cache, encoding="utf-8")) if os.path.exists(cache) else {}
    if got.get("song") == key:
        words, seconds = got["words"], got["seconds"]
    else:
        words, seconds = hear(song)
        json.dump({"song": key, "words": words, "seconds": seconds}, open(cache, "w", encoding="utf-8"),
                  ensure_ascii=False)
    return build(folder, words, seconds)


def fresh(folder):
    """Is audio/song_timing.json up to date with the song, the lyrics and the editing code?"""
    path = os.path.join(folder, "audio", "song_timing.json")
    if not os.path.exists(path):
        return False
    plan = json.load(open(path, encoding="utf-8"))
    return plan.get("stamp") == stamp(folder) and plan.get("edit") == EDIT_VERSION


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    run(os.path.abspath(sys.argv[1]))
