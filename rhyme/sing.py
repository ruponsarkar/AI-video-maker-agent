"""
Turn the spoken (chanted) lines into a sung melody, offline: every syllable is put on the beat grid and re-pitched
to a note that fits the music's chords, with glides and a little vibrato (WORLD vocoder, pyworld).

It is not a real singer: it sounds like a clean, slightly robotic "auto-tuned" voice. Your own singing
(audio/vocals.wav) is still the best. Repeated lines (the chorus) always get the same tune.

Used by video.py; results are cached in audio/sung/ (deleted and remade when the lines or the timing change).
"""
import hashlib
import json
import math
import os
import warnings

import numpy as np
import soundfile as sf

warnings.filterwarnings("ignore", message="pkg_resources is deprecated")
import pyworld as pw  # noqa: E402

import tune  # noqa: E402

FP = 5.0          # WORLD frame period, ms
VERSION = 9       # bump to remake every cached sung line


def _scale_semi(step):
    return tune.MAJOR[step % 7] + 12 * (step // 7)


def _analyse(x, fs):
    x = x.astype(np.float64)
    f0, t = pw.harvest(x, fs, frame_period=FP, f0_floor=60, f0_ceil=700)   # slower than dio, far fewer pitch errors
    sp = pw.cheaptrick(x, f0, t, fs)
    ap = pw.d4c(x, f0, t, fs)
    hop = int(fs * FP / 1000)
    n = len(f0)
    energy = np.array([np.sqrt(np.mean(x[k * hop:(k + 1) * hop] ** 2)) if k * hop < len(x) else 0 for k in range(n)])
    return f0, sp, ap, energy


def _syllables(f0, energy, expected):
    """Split the line into syllable-like pieces at dips in loudness. Returns [(start, end)] in frames."""
    n = len(energy)
    k = 7
    smooth = np.convolve(energy, np.ones(k) / k, mode="same")
    floor = 0.08 * (smooth.max() + 1e-9)
    active = np.where(smooth > floor)[0]
    if len(active) == 0:
        return [(0, n)]
    a, b = int(active[0]), int(active[-1]) + 1
    peaks = [i for i in range(a + 1, b - 1) if smooth[i] >= smooth[i - 1] and smooth[i] > smooth[i + 1]
             and smooth[i] > 0.25 * smooth.max()]
    # keep peaks at least 70 ms apart, the louder one wins
    kept = []
    for p in sorted(peaks, key=lambda i: -smooth[i]):
        if all(abs(p - q) * FP >= 70 for q in kept):
            kept.append(p)
    kept.sort()
    target = max(1, min(len(kept), expected))
    while len(kept) > target:   # merge the two closest peaks
        gaps = [kept[i + 1] - kept[i] for i in range(len(kept) - 1)]
        i = int(np.argmin(gaps))
        kept.pop(i + 1 if smooth[kept[i]] >= smooth[kept[i + 1]] else i)
    if not kept:
        return [(a, b)]
    bounds = [a]
    for p, q in zip(kept, kept[1:]):
        bounds.append(p + int(np.argmin(smooth[p:q])))
    bounds.append(b)
    pieces = [[bounds[i], bounds[i + 1]] for i in range(len(bounds) - 1) if bounds[i + 1] > bounds[i]]
    short = int(80 / FP)
    while len(pieces) > 1:   # a piece under 80 ms is a split in the middle of a sound: join it to its neighbour
        k = min(range(len(pieces)), key=lambda i: pieces[i][1] - pieces[i][0])
        if pieces[k][1] - pieces[k][0] >= short:
            break
        if k == 0 or (k + 1 < len(pieces) and pieces[k + 1][1] - pieces[k + 1][0] < pieces[k - 1][1] - pieces[k - 1][0]):
            pieces[k + 1][0] = pieces[k][0]
        else:
            pieces[k - 1][1] = pieces[k][1]
        pieces.pop(k)
    return [tuple(x) for x in pieces]


def _rhythm(pieces, beat, bars):
    """Onsets and lengths (seconds) on an eighth-note grid (16ths if the line is crowded), keeping the speech's own
    long/short pattern."""
    per_bar = 8 if len(pieces) <= bars * 8 - 2 else 16
    q = beat * 4 / per_bar
    slots = bars * per_bar - per_bar // 8      # a short breath before the next line
    lens = np.array([max(1, e - s) for s, e in pieces], float)
    lens = lens / lens.sum() * max(len(pieces), slots - 3)   # the last syllable is held longer
    onsets, at = [], 0.0
    for k, L in enumerate(lens):
        o = int(round(at))
        if onsets and o <= onsets[-1]:
            o = onsets[-1] + 1
        onsets.append(min(o, slots - 1))
        at += L
    if len(set(onsets)) < len(onsets):          # too many syllables for the grid: squeeze evenly
        onsets = [int(k * slots / len(pieces)) for k in range(len(pieces))]
    ends = onsets[1:] + [slots]
    return [(o * q, (e - o) * q) for o, e in zip(onsets, ends)]


def _time_map(s, e, n_out, f0, energy):
    """Source frame for each output frame of one syllable. The consonants and the way into and out of the vowel
    keep their natural speed; only the steady middle of the vowel is stretched (or everything is squeezed evenly
    if the note is shorter than the spoken syllable)."""
    n_in = e - s
    if n_in <= 0:
        return [float(s)] * n_out
    seg_e = energy[s:e]
    loud = np.where((f0[s:e] > 0) & (seg_e > 0.5 * seg_e.max()))[0]
    if n_out <= n_in or len(loud) < 3:
        return [min(e - 1.0, s + j * n_in / n_out) for j in range(n_out)]
    ns, ne = s + int(loud[0]), s + int(loud[-1]) + 1
    keep_in, keep_out = 4, 4                       # 20 ms of natural speed inside each edge of the vowel
    core_a, core_b = min(ne - 1, ns + keep_in), max(ns + keep_in + 1, ne - keep_out)
    pre = [float(i) for i in range(s, core_a)]
    post = [float(i) for i in range(core_b, e)]
    core_len = n_out - len(pre) - len(post)
    if core_len < 2:
        return [min(e - 1.0, s + j * n_in / n_out) for j in range(n_out)]
    # in-between positions (not repeated frames): the held vowel moves smoothly instead of buzzing
    core = [core_a + (core_b - core_a - 1) * j / max(1, core_len - 1) for j in range(core_len)]
    return pre + core + post


def _chord_steps(degree):
    return [(degree + k) % 7 for k in (0, 2, 4)]


def _nearest(want, allowed):
    best = None
    for s in range(-3, 12):
        if s % 7 in allowed and (best is None or abs(s - want) < abs(best - want)):
            best = s
    return best


def _melody(text, line_no, last_line, rhythm, start, plan, beat):
    """Scale steps for each syllable. Chord tones on the beats, steps between, a shape like a nursery tune."""
    bar = beat * 4
    sections = plan["sections"]
    sec0 = next((s for s in sections if s["start"] <= start + 1e-3 < s["end"]), sections[-1])
    # the same tune for every verse (and for every chorus): it depends on the part and the line, not the words
    seed = f"{plan.get('tempo')}|{sec0['kind']}|{line_no % 2}|{last_line}"
    rng = np.random.default_rng(int(hashlib.md5(seed.encode()).hexdigest()[:8], 16))
    n = len(rhythm)
    base = 2 if line_no % 2 == 0 else 1
    height = float(rng.choice([2.5, 3, 3.5]))
    steps, prev = [], None
    for k, (t, d) in enumerate(rhythm):
        when = start + t
        sec = next((s for s in sections if s["start"] <= when + 1e-3 < s["end"]), sections[-1])
        kind = sec["kind"] if sec["kind"] in tune.PROGRESSIONS else "verse"
        in_sec = int((when - sec["start"] + 1e-3) // bar)
        chord = _chord_steps(tune.PROGRESSIONS[kind][in_sec % 4])
        p = k / max(1, n - 1)
        want = base + height * math.sin(math.pi * min(1.0, p * 1.15)) + float(rng.choice([-0.5, 0, 0, 0.5]))
        on_beat = abs((t / beat) - round(t / beat)) < 1e-3
        if k == n - 1:     # phrase endings: open (5th) on odd lines, home (root) on even lines and at the end
            want = 0 if (line_no % 2 == 1 or last_line) else 4
            s = _nearest(want, chord) if (want % 7) not in chord else want
        elif on_beat or d >= beat:
            s = _nearest(want, chord)
        else:
            s = int(round(want))
            if prev is not None and abs(s - prev) > 2:
                s = prev + (2 if s > prev else -2)
        steps.append(s)
        prev = s
    return steps


def sing_line(path, line, line_no, last_line, plan, beat, key, out_sr):
    """One chanted clip -> (sung audio at out_sr, [(time, dur, semitone above key root)])."""
    x, fs = sf.read(path, dtype="float64")
    if x.ndim > 1:
        x = x.mean(axis=1)
    f0, sp, ap, energy = _analyse(x, fs)
    voiced = f0[f0 > 0]
    speaker = float(np.median(voiced)) if len(voiced) else 220.0
    from lyrics import aksharas
    pieces = _syllables(f0, energy, len(aksharas(line["say_hi"])))
    bar = beat * 4
    dur = len(x) / fs
    bars = line.get("bars") or max(1, round(dur / (bar * 0.92)))
    rhythm = _rhythm(pieces, beat, bars)
    steps = _melody(line["say_hi"], line_no, last_line, rhythm, line["start"], plan, beat)
    root = tune.KEYS.get(key, tune.KEYS["C"])
    # the octave that needs the smallest change from the speaker's own voice
    # (the tune mostly moves between 2 and 9 semitones above the root: put that middle on the speaker's voice)
    root = min((root * 2 ** o for o in (-2, -1, 0, 1)), key=lambda r: abs(math.log(r * 2 ** (5 / 12) / speaker)))
    total = int(round(bars * bar * 1000 / FP)) + 1
    nf0, nsp, nap = np.zeros(total), np.zeros((total, sp.shape[1])), np.ones((total, ap.shape[1]))
    nsp[:] = sp[np.argmin(energy)] * 1e-3   # near-silence between syllables
    # the voice's own life, kept on top of the notes: small wobbles (detail) and a little of each syllable's rise/fall
    semi = np.where(f0 > 0, 12 * np.log2(np.maximum(f0, 1) / speaker), 0.0)
    filled = semi.copy()
    vi = np.where(f0 > 0)[0]
    if len(vi):
        filled = np.interp(np.arange(len(f0)), vi, semi[vi])
    slow = np.convolve(filled, np.ones(21) / 21, mode="same")          # ~100 ms average
    detail = np.clip(filled - slow, -0.8, 0.8) * 0.7
    rng = np.random.default_rng(line_no * 31 + 7)
    drift = np.convolve(rng.normal(0, 1, total + 200), np.ones(60) / 60, mode="same")[:total]
    drift = drift / (np.abs(drift).max() + 1e-9) * 0.12                # slow, tiny wandering on long notes

    logsp = np.log(sp + 1e-16)

    def at(arr, pos):
        i = int(pos)
        j = min(len(arr) - 1, i + 1)
        w = pos - i
        return arr[i] * (1 - w) + arr[j] * w

    prev_hz = None
    notes = []
    for (s, e), (t, d), step in zip(pieces, rhythm, steps):
        a = int(round(t * 1000 / FP))
        b = min(total, int(round((t + d) * 1000 / FP)))
        if b <= a:
            continue
        n_out = b - a
        idx = _time_map(s, e, n_out, f0, energy)
        hz = root * 2 ** (_scale_semi(step) / 12)
        notes.append((t, d, _scale_semi(step)))   # semitones above the key's root (octave left to the player)
        first_voiced = next((j for j, src in enumerate(idx) if f0[int(src)] > 0), 0)
        sv = [filled[i] for i in range(s, e) if f0[i] > 0]
        syl_mean = float(np.mean(sv)) if sv else 0.0
        for j, src in enumerate(idx):
            fr = a + j
            if fr >= total:
                break
            nsp[fr] = np.exp(at(logsp, src)) if src != int(src) else sp[int(src)]
            nap[fr] = at(ap, src)
            if f0[int(src)] > 0:   # only sounds that were voiced get the note: p, t, s, h stay as they were
                age = max(0, j - first_voiced) * FP / 1000
                glide = 1.0 if prev_hz is None else min(1.0, age / 0.07)
                glide = glide * glide * (3 - 2 * glide)          # eased slide into the note
                pitch = (prev_hz ** (1 - glide) * hz ** glide) if prev_hz else hz
                vib = 0.14 * min(1.0, max(0.0, (age - 0.28) / 0.2)) * math.sin(2 * math.pi * 5.2 * age)
                life = at(detail, src) + 0.25 * float(np.clip(at(filled, src) - syl_mean, -1.5, 1.5)) + drift[fr]
                nf0[fr] = pitch * 2 ** ((vib + life) / 12)
        prev_hz = hz
    y = pw.synthesize(nf0, np.ascontiguousarray(nsp), np.ascontiguousarray(nap), fs, FP)
    peak = np.abs(y).max()
    y = (y / peak * 0.9 if peak > 0 else y).astype(np.float32)
    if fs != out_sr:
        from scipy.signal import resample_poly
        g = math.gcd(fs, out_sr)
        y = resample_poly(y, out_sr // g, fs // g).astype(np.float32)
    fade = int(0.012 * out_sr)
    y[:fade] *= np.linspace(0, 1, fade)
    y[-fade:] *= np.linspace(1, 0, fade)
    return y, [(line["start"] + t, d, semi) for t, d, semi in notes]


def sing_all(folder, plan, script, out_sr):
    """{(scene, beat): audio} and the melody notes, using audio/sung/ as a cache."""
    beat = 60.0 / float(plan["tempo"])
    key = script.get("key", "C")
    cache_dir = os.path.join(folder, "audio", "sung")
    os.makedirs(cache_dir, exist_ok=True)
    index_path = os.path.join(cache_dir, "index.json")
    index = json.load(open(index_path)) if os.path.exists(index_path) else {}
    out, melody = {}, []
    lines = [x for x in plan["lines"] if x.get("file")]
    per_scene = {}
    for x in plan["lines"]:
        per_scene.setdefault(x["scene"], []).append(x["beat"])
    made = 0
    for x in lines:
        src = os.path.join(folder, x["file"])
        line_no = per_scene[x["scene"]].index(x["beat"])
        last = line_no == len(per_scene[x["scene"]]) - 1
        stamp = f"{VERSION}|{os.path.getmtime(src)}|{x['start']}|{plan['tempo']}|{key}|{x['say_hi']}|{line_no}|{last}"
        name = f"s{x['scene']:02d}_b{x['beat']:02d}"
        wav = os.path.join(cache_dir, name + ".wav")
        entry = index.get(name)
        if entry and entry.get("stamp") == stamp and os.path.exists(wav):
            audio, _ = sf.read(wav, dtype="float32")
            notes = [tuple(n) for n in entry["notes"]]
        else:
            audio, notes = sing_line(src, x, line_no, last, plan, beat, key, out_sr)
            sf.write(wav, audio, out_sr)
            index[name] = {"stamp": stamp, "notes": notes}
            made += 1
        out[(x["scene"], x["beat"])] = audio
        melody += notes
    json.dump(index, open(index_path, "w"), indent=1)
    if made:
        print(f"  sung {made} line(s) (cached in audio/sung/)")
    return out, melody
