"""
Render a rhyme: python rhyme/video.py rhymes/songs/<slug> [--preview] [--no-music] [--guide]

Every line starts on a bar of the music. The chant voice (audio/lines.json from voice_run.py) is fitted to its bars
without changing its pitch. If audio/vocals.wav exists (you singing along to output/guide.wav), it is used instead,
with the same timing (audio/timing.json).

Pictures: if pictures.json exists and images/p01.jpg ... are there (made by you with an image tool, see
rhyme/pictures.py), they are animated instead of the drawn cartoons; a missing picture is drawn by code. --drawn
ignores the pictures.

Singing: the chant is turned into a sung melody on the music's chords (sing.py); --chant keeps the plain chant.

Writes output/rhyme.mp4 + output/rhyme.srt (--preview: the first 30 seconds; --guide: only output/guide.wav and
output/guide.txt, to sing along to).
"""
import json
import math
import os
import subprocess
import sys
import time

import numpy as np
import soundfile as sf
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import tune  # noqa: E402
from critters import Critter  # noqa: E402
from motion import PictureTrack  # noqa: E402
from lyrics import aksharas  # noqa: E402
from stage import H, W, Stage  # noqa: E402

FPS = 24
SR = tune.SR
FONT_ROUND = next((p for p in ("/usr/share/fonts/truetype/ubuntu/Ubuntu-B.ttf",
                               "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf") if os.path.exists(p)), None)
FONT_FUN = os.path.join(os.path.dirname(HERE), "assets", "Kalam-Bold.ttf")
WORD_COLOURS = [(255, 90, 90), (255, 160, 40), (60, 170, 80), (40, 140, 240), (170, 90, 230)]
END_TEXT = "Phir milenge!"


def channel_name():
    """The kids' channel's name (rhymes/settings.json "channel_name"), shown in the corner and on the end card."""
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "rhymes", "settings.json")
    try:
        return json.load(open(path, encoding="utf-8")).get("channel_name", "")
    except (OSError, ValueError):
        return ""


def font(size, fun=True):
    path = FONT_FUN if fun and os.path.exists(FONT_FUN) else FONT_ROUND
    return ImageFont.truetype(path, size)


def back_out(x):   # overshoot, then settle: things pop in
    x = max(0.0, min(1.0, x))
    c = 1.9
    return 1 + (c + 1) * (x - 1) ** 3 + c * (x - 1) ** 2


def ease(x):
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


# ------------------------------------------------------------------ timing
def sung_bars(say_hi):
    """Bars a sung line needs: about one syllable per eighth note, the last one held."""
    return max(1, math.ceil((len(aksharas(say_hi)) + 2) / 8))


def timeline(script, lines, beat, sing=False):
    """Every line on a bar: [{scene, beat, start, len, rate, bars, file}], sections, length.
    sing: lines get bars by their syllables (sing.py fits them); else by the chant's length (time-stretched)."""
    bar = beat * 4
    durs = {(x["scene"], x["beat"]): x for x in lines}
    t = 2 * bar
    sections = [{"kind": "intro", "start": 0.0, "end": t}]
    out, stanzas = [], []
    for i, scene in enumerate(script["scenes"]):
        start = t
        stanzas.append(t)
        for j, b in enumerate(scene["beats"]):
            known = durs.get((i, j))
            dur = known["dur"] if known else max(1.2, len(aksharas(b["say_hi"])) * 0.21)
            if sing:
                bars = sung_bars(b["say_hi"])
                rate, length = 1.0, bars * bar - bar / 8
            else:
                bars = max(1, round(dur / (bar * 0.92)))
                rate = min(1.25, max(0.8, dur / (bars * bar * 0.9)))
                length = dur / rate
            out.append({"scene": i, "beat": j, "start": round(t, 3), "len": round(length, 3), "rate": round(rate, 3),
                        "bars": bars,
                        "file": known["file"] if known else None, "say": b.get("say") or "", "say_hi": b["say_hi"]})
            t += math.ceil((length + 0.12) / bar) * bar
        t += bar   # a bar of music before the next part
        sections.append({"kind": scene.get("kind", "verse"), "start": start, "end": t, "scene": i})
    sections.append({"kind": "outro", "start": t, "end": t + 2 * bar})
    t += 2 * bar
    sections.append({"kind": "end", "start": t, "end": t + 2 * bar})
    t += 2 * bar
    return {"tempo": round(60 / beat, 2), "lines": out, "sections": sections, "stanzas": stanzas, "length": round(t, 3)}


def envelope(audio, fps=FPS):
    hop = SR // fps
    n = len(audio) // hop
    if n == 0:
        return np.zeros(1)
    rms = np.sqrt(np.mean(audio[:n * hop].reshape(n, hop) ** 2, axis=1))
    return np.clip(rms / (np.percentile(rms[rms > 1e-4], 90) + 1e-6 if np.any(rms > 1e-4) else 1), 0, 1)


def read_audio(path, stereo=False):
    audio, sr = sf.read(path, dtype="float32", always_2d=stereo)
    if stereo and audio.shape[1] == 1:
        audio = np.repeat(audio, 2, axis=1)
    elif not stereo and audio.ndim > 1:
        audio = audio.mean(axis=1)
    if sr != SR:
        from scipy.signal import resample_poly
        g = math.gcd(sr, SR)
        audio = resample_poly(audio, SR // g, sr // g, axis=0).astype(np.float32)
    return audio


def loudness(wav, target=-14.0):
    """YouTube plays music at about -14 LUFS: measure the mix, then set it there in one clean step (no pumping)."""
    probe = subprocess.run(["ffmpeg", "-hide_banner", "-i", wav, "-af", f"loudnorm=I={target}:TP=-1.5:LRA=11:"
                            "print_format=json", "-f", "null", "-"], capture_output=True, text=True).stderr
    try:
        m = json.loads(probe[probe.rindex("{"):probe.rindex("}") + 1])
    except ValueError:
        return []
    return ["-af", f"loudnorm=I={target}:TP=-1.5:LRA=11:measured_I={m['input_i']}:measured_TP={m['input_tp']}:"
            f"measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:offset={m['target_offset']}:"
            "linear=true", "-ar", "48000"]


def room(voice, wet=0.18):
    """A small, warm room around the AI-sung voice (a dry WORLD voice sounds like a machine)."""
    from scipy.signal import fftconvolve
    rng = np.random.default_rng(3)
    n = int(0.9 * SR)
    t = np.arange(n) / SR
    ir = rng.normal(0, 1, n) * np.exp(-t / 0.22)          # ~0.7 s tail
    ir[: int(0.012 * SR)] = 0                               # 12 ms gap before the reflections
    k = int(SR / 4000)                                      # soften the tail (darker, less hiss)
    ir = np.convolve(ir, np.ones(k) / k, mode="same")
    ir /= np.sqrt((ir ** 2).sum()) + 1e-9
    tail = fftconvolve(voice, ir)[: len(voice)].astype(np.float32)
    out = voice + wet * tail
    peak = np.abs(out).max()
    return (out / peak * np.abs(voice).max() if peak > 0 else out).astype(np.float32)


def word_times(line, tokens):
    """When each word of a line is sung: Whisper's word times when they fit, else spread by word length."""
    heard = line.get("words") or []
    if len(heard) == len(tokens):
        return [(a, b) for a, b in heard]
    a0, a1 = (heard[0][0], heard[-1][1]) if heard else (line["start"], line["start"] + line["len"])
    weights = [len(w) + 1 for w in tokens]
    total, acc, times = sum(weights), 0, []
    for wt in weights:
        times.append((a0 + (a1 - a0) * acc / total, a0 + (a1 - a0) * (acc + wt) / total))
        acc += wt
    return times


# words that make a sticker pop up when they're sung (besides the characters' own names: lyrics.WHO)
STICKER_WORDS = {"heart": ["प्यार", "प्यारी", "प्यारा", "प्यारे", "प्रेम", "ममता", "दुलार", "लाड़"],
                 "zzz": ["सो", "सोए", "सोओ", "सोना", "सोजा", "नींद", "निंदिया", "लोरी", "सपने", "सपनों"]}
STICKER_LIFE = 1.8   # seconds on screen


class Song:
    def __init__(self, folder, preview=False, music_on=True, pictures_on=True, sing=True):
        self.folder = folder
        self.sing = sing
        self.preview = preview
        self.music_on = music_on
        self.script = json.load(open(os.path.join(folder, "script.json"), encoding="utf-8"))
        self.beat = 60.0 / float(self.script.get("tempo", 100))
        self.bar = self.beat * 4
        listing = os.path.join(folder, "audio", "lines.json")
        lines = json.load(open(listing))["lines"] if os.path.exists(listing) else []
        self.vocals = os.path.join(folder, "audio", "vocals.wav")
        timing_path = os.path.join(folder, "audio", "timing.json")
        self.song_wav = os.path.join(folder, "audio", "song.wav")
        song_timing = os.path.join(folder, "audio", "song_timing.json")
        self.ai_song = (sing and not os.path.exists(self.vocals) and os.path.exists(self.song_wav)
                        and os.path.exists(song_timing))
        if self.ai_song:
            self.plan = json.load(open(song_timing, encoding="utf-8"))   # the AI song (song_ai.py + align.py)
            edited = os.path.join(folder, "audio", self.plan.get("audio", "song.wav"))
            if os.path.exists(edited):          # align.py's edit: short intro, breaks and ending
                self.song_wav = edited
            print(f"  sound: the AI-sung song (audio/{os.path.basename(self.song_wav)}"
                  + (f", {self.plan['cut']:.0f} s of long music-only parts cut" if self.plan.get("cut") else "") + ")")
        elif os.path.exists(self.vocals) and os.path.exists(timing_path):
            self.plan = json.load(open(timing_path, encoding="utf-8"))   # you sang to this timing: keep it
        else:
            self.plan = timeline(self.script, lines, self.beat, sing=sing)
            os.makedirs(os.path.dirname(timing_path), exist_ok=True)
            json.dump(self.plan, open(timing_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        self.full = self.plan["length"]
        self.length = min(self.full, 30.0) if preview else self.full
        self.stages = {}
        self.cast = {}
        self.env = np.zeros(1)
        self.melody = []
        self.channel = channel_name()
        self.badge = None
        self.stickers = self.find_stickers()
        self.sticker_art = {}
        self.pics = (PictureTrack(folder, self.script, self.plan, FPS, clips="--no-clips" not in sys.argv)
                     if pictures_on else None)
        if self.pics is not None and self.pics.slots:
            clips = sum(1 for s in self.pics.slots if s["file"] and "/clips/" in s["file"].replace(os.sep, "/"))
            print(f"  pictures: {self.pics.found} of {len(self.pics.slots)} found in images/"
                  + ("" if self.pics.found == len(self.pics.slots) else " (the rest are drawn by code)")
                  + (f", {clips} of them as AI animated clips" if clips else ""))

    # ---------------------------------------------------------------- sound
    def voice_track(self):
        n = int(self.full * SR) + SR
        voice = np.zeros(n, np.float32)
        if os.path.exists(self.vocals):
            v = read_audio(self.vocals)[:n]
            voice[:len(v)] = v
            return voice
        if self.ai_song:
            st = read_audio(self.song_wav, stereo=True)[:n]   # kept in stereo for the final mix
            fade = int(2.5 * SR)                       # the song's end fades under the end card
            end = min(len(st), int(self.full * SR))
            if end > fade:
                st[end - fade:end] *= np.linspace(1, 0.25, fade, dtype=np.float32)[:, None]
            self.song_st = np.zeros((n, 2), np.float32)
            self.song_st[:len(st)] = st
            return self.song_st.mean(axis=1)
        sung = {}
        if self.sing:
            try:
                import sing
                sung, self.melody = sing.sing_all(self.folder, self.plan, self.script, SR)
            except ImportError as e:
                print(f"  (can't sing: {e}; using the chant. Install: pip install pyworld 'setuptools<81')")
        import librosa
        for x in self.plan["lines"]:
            if not x.get("file"):
                continue
            if (x["scene"], x["beat"]) in sung:
                tune._place(voice, sung[(x["scene"], x["beat"])], x["start"])
                continue
            audio = read_audio(os.path.join(self.folder, x["file"]))
            if abs(x["rate"] - 1) > 0.01:
                audio = librosa.effects.time_stretch(audio, rate=x["rate"]).astype(np.float32)
            tune._place(voice, audio, x["start"])
        return room(voice) if sung else voice

    def mix(self, voice):
        n = len(voice)
        if self.ai_song:   # the song already has its music: only the sound effects go on top, quietly
            fx = np.zeros(n, np.float32)
            for sec in (s for s in self.plan["sections"] if "scene" in s):
                tune._place(fx, tune.effect("whoosh") * 0.35, max(0, sec["start"] - 0.3))
            end = next(s for s in self.plan["sections"] if s["kind"] == "end")
            tune._place(fx, tune.effect("boing") * 0.5, end["start"] + 0.1)
            for ts, kind, _ in self.stickers:          # a little pop (a twinkle for the sky) with every sticker
                tune._place(fx, tune.effect("twinkle" if kind in ("moon", "star", "sun") else "pop") * 0.3,
                            max(0.0, ts - 0.05))
            rms = np.sqrt(np.mean(voice[voice != 0] ** 2)) if np.any(voice) else 1
            out = self.song_st[:n] / (rms + 1e-6) * 0.2 + (fx * 0.5)[:, None]   # stereo: the song's own width
            peak = np.abs(out).max()
            return (out / peak * 0.95 if peak > 1 else out).astype(np.float32)
        plan = {"tempo": self.plan["tempo"], "key": self.script.get("key", "C"), "sections": self.plan["sections"],
                "stanzas": self.plan["stanzas"], "melody": self.melody, "vocal": [(x["start"], x["start"] + x["len"]) for x in self.plan["lines"]]}
        music = np.zeros(n, np.float32)
        if self.music_on:
            own = next((p for p in (os.path.join(self.folder, f"music.{e}") for e in ("mp3", "wav")) if os.path.exists(p)), None)
            if own:
                raw = subprocess.run(["ffmpeg", "-v", "error", "-i", own, "-f", "f32le", "-ac", "1", "-ar", str(SR), "-"],
                                     capture_output=True).stdout
                m = np.frombuffer(raw, np.float32)[:n]
            else:
                m = tune.backing(plan, self.full, seed=sum(map(ord, self.script["title"])))
            music[:len(m)] = m[:n]
        fx = np.zeros(n, np.float32)
        for k, sec in enumerate(s for s in self.plan["sections"] if "scene" in s):
            scene = self.script["scenes"][sec["scene"]]
            tune._place(fx, tune.effect("whoosh") * 0.5, max(0, sec["start"] - 0.3))
            for c in range(len(scene["cast"])):
                tune._place(fx, tune.effect("pop", c) * 0.6, sec["start"] + 0.1 + c * 0.14)
            if any(c in ("star", "moon", "butterfly") for c in scene["cast"]):
                tune._place(fx, tune.effect("twinkle") * 0.5, sec["start"] + 0.6)
            if scene.get("place") in ("underwater", "pond", "beach"):
                tune._place(fx, tune.effect("splash") * 0.5, sec["start"] + 0.2)
            if scene.get("kind") == "chorus":
                tune._place(fx, tune.effect("clap") * 0.5, sec["end"] - self.bar)
        tune._place(fx, tune.effect("twinkle") * 0.6, 0.3)
        end = next(s for s in self.plan["sections"] if s["kind"] == "end")
        tune._place(fx, tune.effect("boing") * 0.6, end["start"] + 0.1)
        v_rms = np.sqrt(np.mean(voice[voice != 0] ** 2)) if np.any(voice) else 1
        m_rms = np.sqrt(np.mean(music ** 2)) + 1e-6
        out = voice / (v_rms + 1e-6) * 0.16 + music / m_rms * 0.075 + fx * 0.8
        peak = np.abs(out).max()
        return (out / peak * 0.92 if peak > 0 else out).astype(np.float32)

    def guide(self):
        """A sing-along track: the music, the chant (if voiced) and a count-in, plus the line times."""
        out_dir = os.path.join(self.folder, "output")
        os.makedirs(out_dir, exist_ok=True)
        voice = np.zeros(int(self.full * SR) + SR, np.float32)
        if not os.path.exists(self.vocals):
            voice = self.voice_track()
        audio = self.mix(voice)
        sf.write(os.path.join(out_dir, "guide.wav"), audio, SR)
        with open(os.path.join(out_dir, "guide.txt"), "w", encoding="utf-8") as f:
            f.write(f"Tempo {self.plan['tempo']} bpm. Record audio/vocals.wav from the very start of guide.wav "
                    "(wear headphones), the same length, then render again.\n\n")
            for x in self.plan["lines"]:
                f.write(f"{x['start']:7.2f}s  {x['say_hi']}   ({x['say']})\n")
        print(f"Sing-along: {out_dir}/guide.wav and guide.txt")

    # ---------------------------------------------------------------- picture
    def section_at(self, t):
        for s in self.plan["sections"]:
            if s["start"] <= t < s["end"]:
                return s
        return self.plan["sections"][-1]

    def stage(self, i):
        if i not in self.stages:
            self.stages[i] = Stage(self.script["scenes"][i]["place"], seed=i)
        return self.stages[i]

    def critter(self, kind):
        if kind not in self.cast:
            self.cast[kind] = Critter(kind)
        return self.cast[kind]

    def draw_cast(self, img, kinds, t, since, stage, singing, wave_all=False):
        n = len(kinds)
        xs = {1: [0.5], 2: [0.34, 0.66], 3: [0.22, 0.5, 0.78]}.get(n, [0.2 + 0.6 * k / max(1, n - 1) for k in range(n)])
        mouth = float(self.env[min(len(self.env) - 1, int(t * FPS))]) if singing else 0.0
        bp = ((t - self.plan["sections"][0]["start"]) / self.beat) % 1
        for k, kind in enumerate(kinds):
            c = self.critter(kind)
            lead = k == 0
            pop = back_out((t - since - 0.1 - k * 0.14) / 0.45)
            if pop <= 0.01:
                continue
            blink = ((t + k * 1.3) % 3.7) < 0.13
            phase = (t / (2 * self.beat) + k * 0.31) % 1
            spr = c.image(mouth if lead else (0.4 if wave_all and bp < 0.5 else 0), blink, phase)
            h = (500 if c.floats else 660) * c.size * pop * (1.12 if lead and n > 1 else 1)
            sx = 1 - 0.03 * math.cos(2 * math.pi * bp) if not c.floats else 1
            sy = 1 + 0.04 * math.cos(2 * math.pi * bp) if not c.floats else 1
            w2, h2 = max(1, int(spr.width * h / spr.height * sx)), max(1, int(h * sy))
            spr = spr.resize((w2, h2), Image.BILINEAR)
            if c.floats:
                y0, y1 = stage.sky_band
                swim = math.sin(t * 0.6 + k * 2)
                if kind == "fish" and math.cos(t * 0.6 + k * 2) < 0:
                    spr = spr.transpose(Image.FLIP_LEFT_RIGHT)
                cx = W * xs[k] + swim * 70
                cy = (y0 + y1) / 2 + math.sin(t * 1.4 + k) * 28 + (k % 2) * 60
                if kind in ("sun", "moon") and n > 1:
                    cx, cy = W * (0.82 if k % 2 else 0.16), H * 0.24
                img.paste(spr, (int(cx - w2 / 2), int(cy - h2 / 2)), spr)
            else:
                angle = 3.5 * math.sin(2 * math.pi * (t / (2 * self.beat) + k * 0.5))
                hop = abs(math.sin(math.pi * bp)) * (22 if lead else 12)
                spr = spr.rotate(angle, resample=Image.BICUBIC, expand=True)
                cx = W * xs[k]
                ground = stage.ground
                shadow = Image.new("RGBA", (int(w2 * 0.8), 40), (0, 0, 0, 0))
                ImageDraw.Draw(shadow).ellipse([0, 0, shadow.width, 40], fill=(0, 0, 0, int(60 - hop)))
                img.paste(shadow, (int(cx - shadow.width / 2), int(ground - 22)), shadow)
                img.paste(spr, (int(cx - spr.width / 2), int(ground - spr.height + (spr.height - h2) / 2 - hop + 6)), spr)

    def lyric(self, img, t):
        """Karaoke: the line's words light up as they're sung (Whisper's word times for the AI song), the word being
        sung now jumps and grows a little. Lines the AI song didn't sing get no text."""
        cur = None
        for x in self.plan["lines"]:
            if x["start"] - 0.35 <= t and x.get("heard", True) is not False:
                cur = x
        if not cur or t > cur["start"] + cur["len"] + self.bar * 0.8:
            return
        text = cur["say"]
        tokens = text.split()
        if not tokens:
            return
        times = word_times(cur, tokens)
        size = 54
        f = font(size)
        while f.getlength(text) > W - 420 and size > 36:
            size -= 3
            f = font(size)
        big = font(int(size * 1.22))
        now_k = next((k for k, (ws, we) in enumerate(times) if ws - 0.05 <= t < we + 0.1), None)
        widths = [(big if k == now_k else f).getlength(w) for k, w in enumerate(tokens)]
        gap = f.getlength(" ")
        width = sum(widths) + gap * (len(tokens) - 1)
        room = max(big.getlength(w) - f.getlength(w) for w in tokens)   # the box doesn't jump as words grow
        appear = back_out((t - cur["start"] + 0.35) / 0.3)
        box = Image.new("RGBA", (int(f.getlength(text) + room + 80), size + 46), (0, 0, 0, 0))
        ImageDraw.Draw(box).rounded_rectangle([0, 0, box.width - 1, box.height - 1], radius=30, fill=(255, 255, 255, 215),
                                              outline=(255, 190, 60, 255), width=5)
        x0, y0 = int((W - box.width) / 2), int(H - box.height - 30 + (1 - min(1.0, appear)) * 60)
        img.alpha_composite(box, (x0, y0))
        d = ImageDraw.Draw(img)
        x = x0 + (box.width - width) / 2
        for k, w in enumerate(tokens):
            ws, we = times[k]
            on = t >= ws - 0.05
            now = k == now_k
            col = WORD_COLOURS[k % len(WORD_COLOURS)] if on else (95, 85, 110)
            if now:
                ph = min(1.0, (t - ws + 0.05) / 0.25)
                lift = 14 * math.sin(math.pi * ph)
                d.text((x, y0 + 14 - lift - (big.size - size) / 2), w, font=big, fill=col,
                       stroke_width=4, stroke_fill=(255, 255, 255))
            else:
                d.text((x, y0 + 14), w, font=f, fill=col, stroke_width=3 if on else 0, stroke_fill=(255, 255, 255))
            x += widths[k] + gap

    def find_stickers(self):
        """[(time, kind, side)]: a character's name, a love word or a sleep word, sung -> a sticker pops up then."""
        from lyrics import WHO
        art = os.path.join(os.path.dirname(HERE), "rhymes", "cast_art")
        words = {k: v for k, v in WHO.items() if os.path.exists(os.path.join(art, f"{k}_cut.png"))}
        words.update(STICKER_WORDS)
        # who is already in each line's picture: no sticker for them (two moons side by side look wrong)
        shown = {}
        path = os.path.join(self.folder, "pictures.json")
        if os.path.exists(path):
            for slot in json.load(open(path, encoding="utf-8"))["pictures"]:
                for ln in slot.get("lines", []):
                    shown[tuple(ln)] = set(slot.get("cast") or [])
        out, last = [], -9.0
        for x in self.plan["lines"]:
            if x.get("heard", True) is False:
                continue
            there = shown.get((x["scene"], x["beat"]), set())
            toks = [w.strip("।,.!?\"'") for w in x["say_hi"].split()]
            for tok, (ws, _) in zip(toks, word_times(x, toks)):
                kind = next((k for k, ws_ in words.items() for w in ws_ if " " not in w
                             and (tok == w or (len(w) > 2 and tok.startswith(w)))), None)
                if kind in there:
                    continue
                if kind and ws - last >= STICKER_LIFE + 0.3:
                    out.append((ws, kind, len(out) % 2))
                    last = ws
                    break                       # one sticker a line is plenty
        return out

    def sticker_image(self, kind):
        if kind not in self.sticker_art:
            size = 300
            im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
            d = ImageDraw.Draw(im)
            if kind == "heart":
                r = size * 0.24
                c = (255, 70, 120)
                d.ellipse([size * 0.5 - 2 * r, size * 0.2, size * 0.5, size * 0.2 + 2 * r], fill=c, outline="white", width=8)
                d.ellipse([size * 0.5, size * 0.2, size * 0.5 + 2 * r, size * 0.2 + 2 * r], fill=c, outline="white", width=8)
                d.polygon([(size * 0.5 - 2 * r + 4, size * 0.2 + r * 1.3), (size * 0.5 + 2 * r - 4, size * 0.2 + r * 1.3),
                           (size * 0.5, size * 0.92)], fill=c)
                d.ellipse([size * 0.3, size * 0.3, size * 0.4, size * 0.4], fill=(255, 255, 255, 200))
            elif kind == "zzz":
                for k, (z, fs) in enumerate((("Z", 110), ("z", 80), ("z", 60))):
                    d.text((size * (0.15 + 0.27 * k), size * (0.55 - 0.22 * k)), z, font=font(fs),
                           fill=(90, 120, 255), stroke_width=7, stroke_fill=(255, 255, 255))
            else:
                art = Image.open(os.path.join(os.path.dirname(HERE), "rhymes", "cast_art", f"{kind}_cut.png"))
                art = art.convert("RGBA")
                art = art.crop(art.getbbox() or (0, 0, art.width, art.height))
                art.thumbnail((size, size), Image.LANCZOS)
                im.alpha_composite(art, ((size - art.width) // 2, (size - art.height) // 2))
            self.sticker_art[kind] = im
        return self.sticker_art[kind]

    def sticker(self, img, t):
        """The sticker of a word being sung: pops in at the side, wiggles, bobs, shrinks away."""
        for ts, kind, side in self.stickers:
            age = t - ts + 0.1
            if not 0 <= age < STICKER_LIFE:
                continue
            grow = back_out(age / 0.35) if age < STICKER_LIFE - 0.35 else max(0.0, (STICKER_LIFE - age) / 0.35)
            if grow < 0.03:
                continue
            im = self.sticker_image(kind)
            sz = max(4, int(im.width * grow))
            im = im.resize((sz, sz), Image.BILINEAR).rotate(math.sin(age * 9) * 10, expand=True, resample=Image.BILINEAR)
            cx = W * (0.13 if side == 0 else 0.87)
            cy = H * 0.40 + math.sin(age * 5) * 18 - (age * 40 if kind == "zzz" else 0)
            img.alpha_composite(im, (int(cx - im.width / 2), int(cy - im.height / 2)))

    def notes(self, img, t):
        d = ImageDraw.Draw(img, "RGBA")
        for k in range(6):
            life = (t * 0.25 + k / 6) % 1
            x = W * (0.08 + 0.84 * ((k * 0.37) % 1)) + math.sin(t * 2 + k) * 30
            y = H * 0.75 - life * H * 0.6
            a = int(200 * math.sin(math.pi * life))
            c = WORD_COLOURS[k % len(WORD_COLOURS)] + (a,)
            d.ellipse([x - 16, y - 12, x + 16, y + 12], fill=c)
            d.line([(x + 14, y), (x + 14, y - 60)], fill=c, width=6)
            d.line([(x + 14, y - 60), (x + 36, y - 45)], fill=c, width=6)

    def title_card(self, img, t):
        title = self.script["title"]
        f = font(104)
        while f.getlength(title) > W - 200:
            f = font(f.size - 8)
        x = (W - f.getlength(title)) / 2
        d = ImageDraw.Draw(img)
        for k, ch in enumerate(title):
            appear = back_out((t - 0.15 - k * 0.035) / 0.3)
            if appear <= 0:
                break
            bob = math.sin(t * 5 + k * 0.6) * 10
            d.text((x, H * 0.18 + (1 - appear) * -200 + bob), ch, font=f, fill=WORD_COLOURS[k % len(WORD_COLOURS)],
                   stroke_width=10, stroke_fill=(255, 255, 255))
            x += f.getlength(ch)

    def end_card(self, img, t, since):
        f = font(112)
        text = END_TEXT
        x = (W - f.getlength(text)) / 2
        d = ImageDraw.Draw(img)
        for k, ch in enumerate(text):
            bob = math.sin(t * 6 + k * 0.7) * 14
            d.text((x, H * 0.12 + bob), ch, font=f, fill=WORD_COLOURS[k % len(WORD_COLOURS)], stroke_width=10,
                   stroke_fill=(255, 255, 255))
            x += f.getlength(ch)
        # a Subscribe button that pops in and pulses
        pop = back_out((t - since - 0.4) / 0.5)
        if pop > 0.01:
            pulse = 1 + 0.05 * math.sin(t * 6)
            bf = font(int(84 * pop * pulse), fun=False)
            label = "SUBSCRIBE"
            tw = bf.getlength(label)
            bw, bh = tw + 130 * pop, 140 * pop * pulse
            x0, y0 = (W - bw) / 2, H * 0.80 - bh / 2   # low: the characters stand in the middle
            shade = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            ImageDraw.Draw(shade).rounded_rectangle([x0 + 6, y0 + 10, x0 + bw + 6, y0 + bh + 10], radius=bh / 2,
                                                    fill=(0, 0, 0, 90))
            img.alpha_composite(shade)
            d.rounded_rectangle([x0, y0, x0 + bw, y0 + bh], radius=bh / 2, fill=(230, 40, 40), outline=(255, 255, 255),
                                width=8)
            d.text((W / 2, y0 + bh / 2), label, font=bf, fill=(255, 255, 255), anchor="mm")
            if self.channel:
                nf = font(int(64 * pop))
                d.text((W / 2, y0 - 60 * pop), self.channel, font=nf, fill=(255, 220, 60), anchor="mm",
                       stroke_width=7, stroke_fill=(120, 40, 160))

    def frame(self, t):
        sec = self.section_at(t)
        scenes = self.script["scenes"]
        if "scene" in sec:
            i, since = sec["scene"], sec["start"]
        elif sec["kind"] == "intro":
            i, since = 0, 0.0
        else:
            i, since = len(scenes) - 1, sec["start"]
        stage = self.stage(i)
        pic = self.pics.frame(t) if self.pics else None
        drawn = pic is None
        img = stage.frame(t).convert("RGBA") if drawn else pic
        if sec["kind"] == "intro":
            if drawn:
                self.draw_cast(img, scenes[0]["cast"][:1], t, 0.6, stage, False, wave_all=True)
            self.title_card(img, t)
            if self.pics:
                img = self.pics.effects.burst(img, t - 0.9, W / 2, H * 0.25)
        elif sec["kind"] in ("outro", "end"):
            everyone = list(dict.fromkeys(c for s in scenes for c in s["cast"] if not Critter(c).floats))[:3] or scenes[-1]["cast"]
            start = next(s["start"] for s in self.plan["sections"] if s["kind"] == "outro")
            self.notes(img, t)
            if drawn:
                self.draw_cast(img, everyone, t, start, stage, False, wave_all=True)
            if sec["kind"] == "end":
                self.end_card(img, t, sec["start"])
        else:
            if scenes[i].get("kind") == "chorus":
                self.notes(img, t)
            if drawn:
                self.draw_cast(img, scenes[i]["cast"], t, since, stage, True)
            self.lyric(img, t)
            self.sticker(img, t)
        # a circle wipe into each new part (pictures crossfade instead)
        if drawn and "scene" in sec and i > 0 and t - since < 0.45:
            prev = self.stage(i - 1).frame(t).convert("RGBA")
            r = ease((t - since) / 0.45) * math.hypot(W, H) / 2
            mask = Image.new("L", (W, H), 0)
            ImageDraw.Draw(mask).ellipse([W / 2 - r, H / 2 - r, W / 2 + r, H / 2 + r], fill=255)
            prev.paste(img, (0, 0), mask)
            img = prev
        if self.channel and sec["kind"] != "end":   # the channel's name, small, in the corner (like a logo)
            if self.badge is None:
                bf = font(40)
                tw = int(bf.getlength(self.channel))
                self.badge = Image.new("RGBA", (tw + 48, 66), (0, 0, 0, 0))
                bd = ImageDraw.Draw(self.badge)
                bd.rounded_rectangle([0, 0, tw + 47, 65], radius=33, fill=(255, 255, 255, 190))
                bd.text((24, 33), self.channel, font=bf, fill=(230, 60, 60), anchor="lm", stroke_width=2,
                        stroke_fill=(255, 255, 255))
            img.alpha_composite(self.badge, (36, 30))
        # a punch to the music: every beat in the chorus (kids bounce with it), every bar in the verses
        chorus = sec.get("kind") == "chorus"
        step = self.beat if chorus else self.bar
        into = ((t - sec["start"]) % step) if "scene" in sec else 1
        z = 1 + (0.022 if chorus else 0.012) * math.exp(-into / 0.12)
        if z > 1.001:
            cw, ch = int(W / z), int(H / z)
            img = img.crop(((W - cw) // 2, (H - ch) // 2, (W - cw) // 2 + cw, (H - ch) // 2 + ch)).resize((W, H), Image.BILINEAR)
        return img

    def subtitles(self, path):
        def ts(x):
            ms = int(round(x * 1000))
            return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"
        rows = [f"{k + 1}\n{ts(x['start'])} --> {ts(x['start'] + x['len'] + 0.3)}\n{x['say']}\n"
                for k, x in enumerate(self.plan["lines"]) if x["start"] < self.length]
        open(path, "w", encoding="utf-8").write("\n".join(rows))

    def render(self):
        out_dir = os.path.join(self.folder, "output")
        os.makedirs(out_dir, exist_ok=True)
        voice = self.voice_track()
        self.env = envelope(voice)
        audio = self.mix(voice)[:int(self.length * SR)]
        name = "preview" if self.preview else "rhyme"
        wav = os.path.join(out_dir, f"{name}.wav")
        sf.write(wav, audio, SR)
        mp4 = os.path.join(out_dir, f"{name}.mp4")
        cmd = ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
               "-i", "-", "-i", wav, "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
               *loudness(wav), "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", mp4]
        pipe = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        frames = int(self.length * FPS)
        started = time.time()
        for k in range(frames):
            pipe.stdin.write(self.frame(k / FPS).convert("RGB").tobytes())
            if k % (FPS * 15) == 0 and k:
                done = k / frames
                print(f"   {done * 100:4.1f}%   about {(time.time() - started) / done * (1 - done) / 60:.1f} min left", flush=True)
        pipe.stdin.close()
        pipe.wait()
        if self.pics is not None:
            self.pics.close()
        os.remove(wav)
        self.subtitles(os.path.join(out_dir, f"{name}.srt"))
        print(f"Done: {mp4} ({self.length / 60:.1f} min)")
        return mp4


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        raise SystemExit(__doc__)
    for folder in args:
        song = Song(folder, preview="--preview" in sys.argv, music_on="--no-music" not in sys.argv,
                    pictures_on="--drawn" not in sys.argv, sing="--chant" not in sys.argv)
        song.guide() if "--guide" in sys.argv else song.render()
