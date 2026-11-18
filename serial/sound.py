"""
Music, ambience and sound effects for the serial, all made in code (no downloads, no licences to track).

    music(mood, seconds, seed)    background score: calm happy sad tense battle mystery divine
    ambience(place, time, weather, seconds, seed)
    effect(name)                  one sound effect, see EFFECTS

Your own music wins: put files in series/<slug>/music/<mood>.mp3 (or .wav) and render.py uses them instead.
"""
import math

import numpy as np

SR = 44100
SA = 220.0 * 2 ** (5 / 12)   # D3-ish tonic: a comfortable key for the drone

# scales as semitones above Sa (Indian ragas, roughly)
RAGAS = {"calm": [0, 2, 4, 6, 7, 9, 11, 12],        # Yaman
         "happy": [0, 2, 4, 7, 9, 12],               # Bhoopali
         "sad": [0, 1, 3, 5, 7, 8, 10, 12],          # Bhairavi
         "tense": [0, 1, 4, 5, 7, 8, 11, 12],        # Bhairav
         "battle": [0, 3, 5, 7, 10, 12],             # minor pentatonic
         "mystery": [0, 1, 4, 6, 7, 8, 11, 12],      # Marwa-ish
         "divine": [0, 2, 4, 5, 7, 9, 11, 12]}       # Bilawal
TEMPO = {"calm": 72, "happy": 104, "sad": 58, "tense": 84, "battle": 138, "mystery": 64, "divine": 66}
MOODS = tuple(RAGAS)


def _env(n, attack, release):
    e = np.ones(n, np.float32)
    a, r = min(n, int(attack * SR)), min(n, int(release * SR))
    if a:
        e[:a] = np.linspace(0, 1, a)
    if r:
        e[-r:] *= np.linspace(1, 0, r)
    return e


def _lowpass(x, cutoff):
    """A one-pole low-pass filter, enough to soften noise and buzz."""
    from scipy.signal import lfilter
    a = math.exp(-2 * math.pi * cutoff / SR)
    return lfilter([1 - a], [1, -a], x).astype(np.float32)


def _bandpass(x, lo, hi):
    from scipy.signal import butter, sosfilt
    sos = butter(2, [lo / (SR / 2), min(0.99, hi / (SR / 2))], btype="band", output="sos")
    return sosfilt(sos, x).astype(np.float32)


def _noise(n, rng):
    return rng.standard_normal(n).astype(np.float32)


def _place(out, clip, start):
    s = int(start * SR)
    if s >= len(out):
        return
    e = min(len(out), s + len(clip))
    out[s:e] += clip[:e - s]


# ------------------------------------------------------------------ instruments
def tanpura(seconds, rng, pitch=SA):
    """The drone that sits under Indian music: Pa Sa Sa Sa, over and over."""
    n = int(seconds * SR)
    out = np.zeros(n, np.float32)
    cycle = 3.6
    notes = [pitch * 2 ** (7 / 12) / 2, pitch, pitch, pitch / 2]
    t_len = int(3.4 * SR)
    t = np.arange(t_len) / SR
    k = 0
    start = 0.0
    while start < seconds:
        f = notes[k % 4] * (1 + rng.uniform(-0.001, 0.001))
        tone = sum((1 / h) * np.sin(2 * math.pi * f * h * t + rng.uniform(0, 6)) * np.exp(-t * (0.6 + h * 0.08))
                   for h in range(1, 14))
        buzz = np.sin(2 * math.pi * f * 7 * t) * np.exp(-t * 1.5) * 0.15   # the 'jawari' shimmer
        _place(out, ((tone + buzz) * 0.12).astype(np.float32) * _env(t_len, 0.01, 0.4), start)
        start += cycle / 4
        k += 1
    return out


def flute(freqs, durs, rng, gap=0.0):
    """Bansuri-like line: sine with breath, vibrato and gentle slides between notes."""
    total = sum(durs) + gap
    n = int(total * SR)
    f_track = np.zeros(n, np.float32)
    amp = np.zeros(n, np.float32)
    pos = 0
    for k, (f, d) in enumerate(zip(freqs, durs)):
        m = int(d * SR)
        if f <= 0:
            pos += m
            continue
        prev = freqs[k - 1] if k and freqs[k - 1] > 0 else f
        glide = min(m, int(0.07 * SR))
        seg = np.full(m, f, np.float32)
        seg[:glide] = np.linspace(prev, f, glide)
        f_track[pos:pos + m] = seg
        amp[pos:pos + m] = _env(m, 0.06, min(0.25, d * 0.4))
        pos += m
    t = np.arange(n) / SR
    vib = 1 + 0.006 * np.sin(2 * math.pi * 5.2 * t) * np.clip(t % 1.5, 0, 1)
    phase = 2 * math.pi * np.cumsum(f_track * vib) / SR
    tone = np.sin(phase) + 0.18 * np.sin(2 * phase) + 0.05 * np.sin(3 * phase)
    breath = _bandpass(_noise(n, rng), 1200, 5000) * 0.05
    return ((tone + breath) * amp * 0.22).astype(np.float32)


def pad(seconds, chord, rng, bright=0.5):
    """A soft string pad on these frequencies."""
    n = int(seconds * SR)
    t = np.arange(n) / SR
    out = np.zeros(n, np.float32)
    for f in chord:
        for det in (-0.003, 0.0, 0.003):
            ff = f * (1 + det)
            wave = sum(((-1) ** (h + 1)) / h * np.sin(2 * math.pi * ff * h * t + rng.uniform(0, 6)) for h in range(1, 7))
            out += wave.astype(np.float32)
    out = _lowpass(out, 500 + 1500 * bright)
    swell = 0.7 + 0.3 * np.sin(2 * math.pi * t / 7.0)
    return (out * swell * _env(n, 1.5, 1.5) * 0.035).astype(np.float32)


def drum(kind, rng):
    """One hit: dha (tabla bass), na (tabla ring), dhol, nagara (big war drum), tick."""
    if kind == "na":
        n = int(0.35 * SR)
        t = np.arange(n) / SR
        return (np.sin(2 * math.pi * 620 * t) * np.exp(-t * 18) * 0.5
                + _bandpass(_noise(n, rng), 2000, 6000) * np.exp(-t * 60) * 0.3).astype(np.float32)
    if kind == "dha":
        n = int(0.6 * SR)
        t = np.arange(n) / SR
        f = 90 + 70 * np.exp(-t * 12)
        bass = np.sin(2 * math.pi * np.cumsum(f) / SR) * np.exp(-t * 6) * 0.8
        return _mix_pad(bass.astype(np.float32), drum("na", rng) * 0.5)
    if kind in ("dhol", "nagara"):
        n = int((0.9 if kind == "nagara" else 0.5) * SR)
        t = np.arange(n) / SR
        base = 55 if kind == "nagara" else 75
        f = base + 60 * np.exp(-t * 20)
        body = np.sin(2 * math.pi * np.cumsum(f) / SR) * np.exp(-t * (4 if kind == "nagara" else 7))
        slap = _bandpass(_noise(n, rng), 300, 2500) * np.exp(-t * 40) * 0.5
        return ((body + slap) * 0.9).astype(np.float32)
    n = int(0.08 * SR)
    t = np.arange(n) / SR
    return (_bandpass(_noise(n, rng), 3000, 9000) * np.exp(-t * 80) * 0.3).astype(np.float32)


def _mix_pad(a, b):
    out = np.zeros(max(len(a), len(b)), np.float32)
    out[:len(a)] += a
    out[:len(b)] += b
    return out


def bell(freq=880, length=2.5, rng=None):
    n = int(length * SR)
    t = np.arange(n) / SR
    partials = [(1, 1), (2.76, 0.5), (5.4, 0.25), (8.9, 0.12)]
    return (sum(a * np.sin(2 * math.pi * freq * r * t) * np.exp(-t * (1.6 + r * 0.6)) for r, a in partials)
            * 0.25).astype(np.float32)


# ------------------------------------------------------------------ the score
PATTERNS = {"happy": ["dha", "na", "na", "dha", "na", "na"],                     # dadra, 6 beats
            "battle": ["nagara", "dhol", "dhol", "nagara", "dhol", "nagara", "dhol", "dhol"],
            "tense": ["dhol", None, None, "dhol", None, None, None, None],
            "calm": ["dha", None, "na", None, "na", None, "dha", "na"]}


def music(mood, seconds, seed=0):
    """Background score for one scene: drone, a melody that breathes, and drums for some moods."""
    mood = mood if mood in RAGAS else "calm"
    rng = np.random.default_rng(seed)
    n = int(seconds * SR)
    out = np.zeros(n, np.float32)
    scale = RAGAS[mood]
    beat = 60.0 / TEMPO[mood]
    out += tanpura(seconds, rng) * (0.6 if mood != "battle" else 0.35)
    if mood in ("sad", "tense", "mystery", "divine", "battle"):
        root = SA / 2
        chord = [root, root * 2 ** (scale[2] / 12), root * 2 ** (7 / 12)]
        out += pad(seconds, chord, rng, bright=0.3 if mood != "divine" else 0.7) * (1.3 if mood == "mystery" else 1.0)
    # melody: phrases with rests, so it never fights the voice
    if mood not in ("battle", "tense"):
        t = rng.uniform(1.0, 3.0)
        deg = 0
        while t < seconds - 2:
            freqs, durs = [], []
            for _ in range(int(rng.integers(3, 7))):
                deg = int(np.clip(deg + rng.choice([-2, -1, -1, 1, 1, 2]), 0, len(scale) - 1))
                freqs.append(SA * 2 ** (scale[deg] / 12))
                durs.append(beat * float(rng.choice([1, 1, 2, 1.5, 3] if mood != "happy" else [0.5, 0.5, 1, 1, 2])))
            phrase = flute(freqs, durs, rng)
            _place(out, phrase * (0.7 if mood == "sad" else 0.6), t)
            t += sum(durs) + beat * float(rng.choice([2, 3, 4, 6]))
    else:   # short horn stabs for battle, low notes for tension
        t = 0.5
        while t < seconds - 1:
            f = SA / 2 * 2 ** (scale[int(rng.integers(0, 3))] / 12)
            _place(out, flute([f], [beat * 2], rng) * 0.5, t)
            t += beat * (4 if mood == "battle" else 8)
    pattern = PATTERNS.get(mood)
    if pattern:
        t, k = 0.0, 0
        step = beat / (2 if mood == "battle" else 1)
        while t < seconds:
            hit = pattern[k % len(pattern)]
            if hit:
                _place(out, drum(hit, rng) * (0.5 if mood in ("calm", "happy") else 0.7), t)
            t += step
            k += 1
    if mood == "divine":
        for t in np.arange(1.5, seconds, 6.0):
            _place(out, bell(SA * 4 * 2 ** (scale[int(rng.integers(0, len(scale)))] / 12)) * 0.5, float(t))
    if mood == "mystery":
        for t in np.arange(2.0, seconds, 5.0):
            _place(out, bell(SA * 3 * 2 ** (scale[int(rng.integers(0, len(scale)))] / 12), 3.5) * 0.25, float(t))
    fade = _env(n, 1.2, 1.5)
    return (out * fade).astype(np.float32)


# ------------------------------------------------------------------ ambience
def ambience(place, time, weather, seconds, seed=0):
    rng = np.random.default_rng(seed + 7)
    n = int(seconds * SR)
    out = np.zeros(n, np.float32)
    outdoor = place not in ("throne_room", "cave", "temple")
    if outdoor:   # wind under everything outside
        w = _lowpass(_noise(n, rng), 400) * 0.05
        w *= 0.6 + 0.4 * np.sin(2 * math.pi * np.arange(n) / SR / 9.0)
        out += w
    if place in ("river", "sea"):
        wave = _lowpass(_noise(n, rng), 900) * 0.08
        if place == "sea":
            wave *= 0.5 + 0.5 * np.sin(2 * math.pi * np.arange(n) / SR / 6.5) ** 2
        out += wave
    if place in ("forest", "garden", "ashram", "village", "river") and time != "night":
        for t in rng.uniform(0, seconds, int(seconds / 2.5)):
            _place(out, _birdsong(rng) * 0.18, float(t))
    if time == "night" and outdoor:
        m = int(0.03 * SR)
        chirp = np.sin(2 * math.pi * 4400 * np.arange(m) / SR) * _env(m, 0.005, 0.01)
        for t in np.arange(0, seconds, 0.09):
            if rng.random() < 0.55:
                _place(out, chirp.astype(np.float32) * 0.025, float(t + rng.uniform(0, 0.02)))
    if place in ("market", "battlefield", "palace"):
        crowd = _bandpass(_noise(n, rng), 250, 1600) * (0.05 if place == "market" else 0.03)
        crowd *= 0.7 + 0.3 * np.sin(2 * math.pi * np.arange(n) / SR / 3.1)
        out += crowd
    if place in ("throne_room", "temple", "cave"):
        out += _lowpass(_noise(n, rng), 150) * 0.03
    if place == "cave":
        for t in rng.uniform(0, seconds, int(seconds / 3)):
            _place(out, bell(1400 + rng.uniform(-300, 300), 0.4) * 0.15, float(t))
    if place == "temple":
        for t in np.arange(3.0, seconds, 9.0):
            _place(out, bell(660, 3.0) * 0.3, float(t))
    if weather in ("rain", "storm"):
        out += _bandpass(_noise(n, rng), 800, 7000) * 0.09
    return out


def _birdsong(rng):
    n = int(rng.uniform(0.15, 0.4) * SR)
    t = np.arange(n) / SR
    f = rng.uniform(2500, 4200) + rng.uniform(400, 1200) * np.sin(2 * math.pi * rng.uniform(8, 20) * t)
    return (np.sin(2 * math.pi * np.cumsum(f) / SR) * _env(n, 0.01, 0.05)).astype(np.float32)


# ------------------------------------------------------------------ effects
def effect(name, seed=0):
    rng = np.random.default_rng(seed + hash(name) % 1000)

    def tt(sec):
        return np.arange(int(sec * SR)) / SR

    if name in ("whoosh", "swoosh", "fly"):
        t = tt(0.6 if name != "fly" else 1.2)
        x = _bandpass(_noise(len(t), rng), 400, 3000) * np.sin(np.pi * t / t[-1]) ** 2
        return (x * 0.5).astype(np.float32)
    if name == "step":
        t = tt(0.12)
        return (_lowpass(_noise(len(t), rng), 600) * np.exp(-t * 40) * 0.6).astype(np.float32)
    if name == "clash":
        t = tt(1.0)
        partials = [1, 2.4, 3.9, 5.6, 7.3]
        x = sum(np.sin(2 * math.pi * 900 * p * t + rng.uniform(0, 6)) * np.exp(-t * (5 + p)) for p in partials)
        return ((x * 0.18 + _bandpass(_noise(len(t), rng), 2000, 9000) * np.exp(-t * 30) * 0.5) * 0.9).astype(np.float32)
    if name == "arrow":
        twang_t = tt(0.3)
        twang = np.sin(2 * math.pi * 180 * twang_t) * np.exp(-twang_t * 14) * 0.5
        whoosh = effect("whoosh", seed)
        return _mix_pad(twang.astype(np.float32), np.concatenate([np.zeros(int(0.1 * SR), np.float32), whoosh * 0.7]))
    if name == "thunder":
        t = tt(3.0)
        x = _lowpass(_noise(len(t), rng), 160) * (np.exp(-t * 1.2) + 0.6 * np.exp(-((t - 0.4) ** 2) * 20)) * 2.5
        return x.astype(np.float32)
    if name in ("magic", "shimmer", "blessing"):
        t = tt(1.6)
        out = np.zeros(len(t), np.float32)
        for k, semi in enumerate([0, 4, 7, 12, 16, 19, 24]):
            _place(out, bell(SA * 4 * 2 ** (semi / 12), 1.2) * 0.35, k * 0.07)
        return out
    if name == "gong":
        t = tt(4.0)
        x = sum(a * np.sin(2 * math.pi * 110 * r * t) * np.exp(-t * d) for r, a, d in
                [(1, 1, 0.6), (1.48, 0.6, 0.8), (2.1, 0.4, 1.0), (2.9, 0.3, 1.4), (4.1, 0.2, 2)])
        return (x * 0.35).astype(np.float32)
    if name == "drum_hit":
        return drum("nagara", rng)
    if name == "conch":
        t = tt(2.2)
        f = 233 * (1 + 0.01 * np.sin(2 * math.pi * 5 * t))
        ph = 2 * math.pi * np.cumsum(f) / SR
        x = sum(np.sin(ph * h) / h ** 0.7 for h in range(1, 9))
        return (_lowpass(x.astype(np.float32), 1800) * _env(len(t), 0.25, 0.6) * 0.25).astype(np.float32)
    if name == "bell":
        return bell(990, 2.5)
    if name == "roar":
        t = tt(1.4)
        f = 90 + 30 * np.sin(2 * math.pi * 3 * t)
        x = np.sin(2 * math.pi * np.cumsum(f) / SR) * 0.6 + _bandpass(_noise(len(t), rng), 200, 1200) * 0.8
        return (x * _env(len(t), 0.1, 0.5) * 0.5).astype(np.float32)
    if name in ("fall", "thud"):
        t = tt(0.5)
        f = 70 * np.exp(-t * 3) + 40
        return ((np.sin(2 * math.pi * np.cumsum(f) / SR) * np.exp(-t * 8)
                 + _lowpass(_noise(len(t), rng), 500) * np.exp(-t * 20)) * 0.8).astype(np.float32)
    if name == "splash":
        t = tt(0.9)
        return (_bandpass(_noise(len(t), rng), 500, 6000) * np.exp(-t * 5) * 0.5).astype(np.float32)
    if name == "fire":
        t = tt(2.0)
        x = _lowpass(_noise(len(t), rng), 700) * 0.15
        for c in rng.uniform(0, 2.0, 30):
            _place(x, (_noise(400, rng) * 0.3).astype(np.float32), float(c))
        return x.astype(np.float32)
    if name == "heartbeat":
        out = np.zeros(int(1.6 * SR), np.float32)
        for t0 in (0.0, 0.22, 0.8, 1.02):
            _place(out, drum("dhol", rng) * 0.6, t0)
        return out
    if name == "crowd_gasp":
        t = tt(1.0)
        return (_bandpass(_noise(len(t), rng), 300, 2500) * _env(len(t), 0.05, 0.6) * 0.4).astype(np.float32)
    if name == "riser":
        t = tt(1.5)
        f = 200 + 800 * t / t[-1]
        return (np.sin(2 * math.pi * np.cumsum(f) / SR) * (t / t[-1]) * 0.2).astype(np.float32)
    return np.zeros(1, np.float32)


EFFECTS = ("whoosh", "fly", "step", "clash", "arrow", "thunder", "magic", "gong", "drum_hit", "conch", "bell", "roar",
           "fall", "splash", "fire", "heartbeat", "crowd_gasp", "riser")
