"""
Music for a rhyme, made in code: a bright children's arrangement on one tempo grid, so every line of the rhyme
lands on a bar. Kick + clap + shaker, a bouncy bass, ukulele-like chords, a marimba tune that is louder between
lines and softer under the voice, and bells at each new verse.

    backing(plan, seconds, seed)   the whole backing track for a timeline made by video.timeline()
    effect(name)                   pop boing twinkle splash whoosh clap
"""
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "serial"))
from sound import SR, _bandpass, _env, _lowpass, _noise, _place  # noqa: E402

KEYS = {"C": 261.63, "D": 293.66, "E": 329.63, "F": 349.23, "G": 392.00, "A": 220.00 * 2, "Bb": 233.08 * 2}
MAJOR = [0, 2, 4, 5, 7, 9, 11]
# chords as scale degrees (0 = I); verse and chorus get different progressions
PROGRESSIONS = {"verse": [0, 4, 5, 3], "chorus": [3, 4, 0, 0], "intro": [0, 3, 4, 0], "outro": [3, 4, 0, 0]}


def _f(root, semitones):
    return root * 2 ** (semitones / 12)


def _chord(root, degree):
    """Triad on a scale degree, as semitones above the key's root."""
    return [MAJOR[(degree + k) % 7] + 12 * ((degree + k) // 7) for k in (0, 2, 4)]


def _t(sec):
    return np.arange(int(sec * SR)) / SR


# ------------------------------------------------------------------ instruments
def kick():
    t = _t(0.35)
    f = 50 + 110 * np.exp(-t * 30)
    return (np.sin(2 * math.pi * np.cumsum(f) / SR) * np.exp(-t * 9) * 0.9).astype(np.float32)


def clap(rng):
    t = _t(0.25)
    burst = np.zeros(len(t), np.float32)
    for k, d in enumerate((0.0, 0.012, 0.024)):
        s = int(d * SR)
        burst[s:] += np.exp(-(t[:len(t) - s]) * (60 if k < 2 else 18)).astype(np.float32)
    return (_bandpass(_noise(len(t), rng), 900, 5000) * burst * 0.45).astype(np.float32)


def shaker(rng, accent=1.0):
    t = _t(0.07)
    return (_bandpass(_noise(len(t), rng), 5000, 12000) * np.exp(-t * 70) * 0.18 * accent).astype(np.float32)


def pluck(freq, sec, bright=1.0):
    """Ukulele-ish pluck: harmonics that die away faster the higher they are."""
    t = _t(sec)
    x = sum((1 / h) * np.sin(2 * math.pi * freq * h * t) * np.exp(-t * (3 + h * 2.2 / bright)) for h in range(1, 8))
    return (x * _env(len(t), 0.003, 0.05) * 0.16).astype(np.float32)


def marimba(freq, sec):
    t = _t(sec)
    x = np.sin(2 * math.pi * freq * t) * np.exp(-t * 4.5) + 0.35 * np.sin(2 * math.pi * freq * 4 * t) * np.exp(-t * 16)
    return (x * _env(len(t), 0.002, 0.04) * 0.3).astype(np.float32)


def bass(freq, sec):
    t = _t(sec)
    x = np.sin(2 * math.pi * freq * t) + 0.3 * np.sin(4 * math.pi * freq * t) + 0.1 * np.sin(6 * math.pi * freq * t)
    return (_lowpass(x.astype(np.float32), 900) * _env(len(t), 0.005, 0.08) * np.exp(-t * 2.5) * 0.45).astype(np.float32)


def glock(freq, sec=1.2):
    t = _t(sec)
    x = sum(a * np.sin(2 * math.pi * freq * r * t) * np.exp(-t * (3 + r)) for r, a in ((1, 1), (2.76, 0.4), (5.4, 0.15)))
    return (x * 0.14).astype(np.float32)


# ------------------------------------------------------------------ the tune
def motif(rng, bars=2):
    """A sing-song phrase: 8th-note steps on the scale, mostly stepwise, landing on chord tones.
    Returns [(beat, length in beats, scale step)]."""
    notes, beat, step = [], 0.0, int(rng.choice([0, 2, 4]))
    rhythm = [[1, 1, 1, 1], [0.5, 0.5, 1, 1, 1], [1, 0.5, 0.5, 2], [0.5, 0.5, 0.5, 0.5, 2], [1.5, 0.5, 1, 1]]
    for b in range(bars):
        for length in rhythm[int(rng.integers(0, len(rhythm)))]:
            notes.append((beat, length, step))
            beat += length
            step = int(np.clip(step + rng.choice([-2, -1, -1, 1, 1, 2, 0]), -2, 9))
        if b == bars - 1:   # end the phrase on the root or the third
            notes[-1] = (notes[-1][0], notes[-1][1], int(rng.choice([0, 2, 7])))
    return notes


def _step_semi(step):
    return MAJOR[step % 7] + 12 * (step // 7)


def backing(plan, seconds, seed=0):
    """plan: {"tempo", "key", "sections": [{"kind", "start", "end"}], "vocal": [(start, end)], "stanzas": [start]}"""
    rng = np.random.default_rng(seed)
    bpm = float(plan.get("tempo", 100))
    beat = 60.0 / bpm
    bar = beat * 4
    root = KEYS.get(plan.get("key", "C"), KEYS["C"])
    n = int(seconds * SR) + SR
    drums, low, chords, lead, sparkle = (np.zeros(n, np.float32) for _ in range(5))
    tunes = {"verse": motif(rng), "chorus": motif(rng), "intro": motif(rng), "outro": motif(rng)}
    tunes["outro"] = tunes["chorus"]
    k_kick, k_clap = kick(), clap(rng)

    def section_at(t):
        for s in plan["sections"]:
            if s["start"] <= t < s["end"]:
                return s
        return plan["sections"][-1]

    bars = int(math.ceil(seconds / bar))
    for b in range(bars):
        t0 = b * bar
        sec = section_at(t0 + 0.01)
        kind = sec["kind"] if sec["kind"] in PROGRESSIONS else "verse"
        in_sec = int(round((t0 - sec["start"]) / bar))
        degree = PROGRESSIONS[kind][in_sec % 4]
        chord = _chord(root, degree)
        last = sec["kind"] == "end"
        # drums: four-on-the-floor feel for chorus, lighter for verse, none on the end card's last bar
        for q in range(4):
            tq = t0 + q * beat
            if last and in_sec > 0:
                break
            if q in (0, 2) or kind == "chorus":
                _place(drums, k_kick * (1.0 if q in (0, 2) else 0.6), tq)
            if q in (1, 3):
                _place(drums, k_clap, tq)
            for e in (0, 0.5):
                _place(drums, shaker(rng, 1.0 if e else 0.6), tq + e * beat)
        # bass: root on 1, fifth on 3, a walk-up into the next bar
        r = _f(root / 4, chord[0])
        for q, semi in ((0, 0), (2, 7), (3, 12 if in_sec % 2 else 4)):
            _place(low, bass(r * 2 ** (semi / 12), beat * (1.6 if q == 0 else 0.9)), t0 + q * beat)
        # ukulele strum on the off-beats (and on 1)
        for q, accent in ((0, 1.0), (1.5, 0.7), (2.5, 0.8), (3.5, 0.6)):
            for k, semi in enumerate(chord):
                _place(chords, pluck(_f(root, semi), beat * 1.2) * accent, t0 + q * beat + k * 0.012)
    # the tune: 2-bar motifs from each section; where a sung melody exists, the motif rests and the melody is doubled
    melody = plan.get("melody") or []
    sung_spans = [(a, b + 0.2) for a, b in plan.get("vocal", [])] if melody else []
    for at, length, semi in melody:
        _place(lead, marimba(_f(root * 2, semi), length * 0.95 + 0.25) * 0.8, at)
    for s in plan["sections"]:
        kind = s["kind"] if s["kind"] in tunes else "verse"
        if s["kind"] == "end":
            continue
        t = s["start"]
        while t < s["end"] - 0.01:
            for at, length, step in tunes[kind]:
                when = t + at * beat
                if when >= s["end"]:
                    break
                if any(a - 0.1 <= when < b for a, b in sung_spans):
                    continue
                _place(lead, marimba(_f(root * 2, _step_semi(step)), length * beat + 0.4), when)
            t += 2 * bar
    for t in plan.get("stanzas", []):
        for k, semi in enumerate((0, 4, 7, 12)):
            _place(sparkle, glock(_f(root * 4, semi)), t + k * beat / 4)
    # the tune steps back while someone is singing
    duck = np.ones(n, np.float32)
    for a, b in plan.get("vocal", []):
        s, e = int(a * SR), min(n, int(b * SR))
        duck[s:e] = 0.5 if melody else 0.35
    from scipy.signal import lfilter
    k = math.exp(-1 / (0.08 * SR))
    duck = lfilter([1 - k], [1, -k], duck).astype(np.float32)
    out = drums * 0.9 + low * 1.0 + chords * 0.75 + lead * duck * 0.9 + sparkle * 0.8
    out = out[:int(seconds * SR)]
    return (out * _env(len(out), 0.05, 1.5)).astype(np.float32)


# ------------------------------------------------------------------ effects
def effect(name, seed=0):
    rng = np.random.default_rng(seed + sum(map(ord, name)))
    if name == "pop":
        t = _t(0.12)
        f = 400 + 900 * np.exp(-t * 60)
        return (np.sin(2 * math.pi * np.cumsum(f) / SR) * np.exp(-t * 35) * 0.5).astype(np.float32)
    if name == "boing":
        t = _t(0.5)
        f = 180 + 120 * np.sin(2 * math.pi * 9 * t) * np.exp(-t * 4) + 140 * t
        return (np.sin(2 * math.pi * np.cumsum(f) / SR) * np.exp(-t * 5) * 0.4).astype(np.float32)
    if name == "twinkle":
        out = np.zeros(int(0.9 * SR), np.float32)
        for k, semi in enumerate((24, 28, 31, 36)):
            _place(out, glock(_f(KEYS["C"], semi), 0.6) * 1.4, k * 0.07)
        return out
    if name == "splash":
        t = _t(0.6)
        return (_bandpass(_noise(len(t), rng), 600, 6000) * np.exp(-t * 7) * (1 - np.exp(-t * 80)) * 0.45).astype(np.float32)
    if name == "whoosh":
        t = _t(0.5)
        return (_bandpass(_noise(len(t), rng), 500, 3500) * np.sin(np.pi * t / t[-1]) ** 2 * 0.35).astype(np.float32)
    if name == "clap":
        out = np.zeros(int(0.6 * SR), np.float32)
        for k in range(3):
            _place(out, clap(rng), k * 0.16)
        return out
    return np.zeros(1, np.float32)


EFFECTS = ("pop", "boing", "twinkle", "splash", "whoosh", "clap")
