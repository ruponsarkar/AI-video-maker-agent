"""
Render one serial episode: python serial/render.py series/<slug>/episodes/ep001 [--preview] [--no-music]

Reads script.json, audio/lines.json (from voice_run.py) and the series bible. Writes output/episode.mp4 and
output/episode.srt. --preview renders the first 45 seconds only.
"""
import json
import math
import os
import random
import subprocess
import sys
import time

import numpy as np
import soundfile as sf
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from cartoon import Character, colour  # noqa: E402
from scenery import GROUND, Scenery  # noqa: E402
import sound  # noqa: E402

W, H, FPS = 1920, 1080, 24
SLOTS = {"far_left": 0.14, "left": 0.3, "center": 0.5, "right": 0.7, "far_right": 0.86}
CHAR_SCALE = 0.64          # a height-1.0 character in a wide shot is about 575 px tall
GAP = 0.3                  # silence after each line
SCENE_GAP = 0.6            # extra air when the scene changes
TITLE_SECONDS, END_SECONDS = 4.5, 5.0
FONT_BOLD = next((p for p in ("/usr/share/fonts/truetype/ubuntu/Ubuntu-B.ttf",
                              "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf") if os.path.exists(p)), None)
FONT_FANCY = os.path.join(os.path.dirname(HERE), "assets", "Kalam-Bold.ttf")


def font(size, fancy=False):
    path = FONT_FANCY if fancy and os.path.exists(FONT_FANCY) else FONT_BOLD
    return ImageFont.truetype(path, size)


def ease(x):
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


# ------------------------------------------------------------------ timeline
def build_timeline(script, lines, bible):
    """Start and length of every line, scene by scene, from the real voice lengths."""
    durations = {(x["scene"], x["beat"]): (x["dur"], x["file"]) for x in lines}
    t = TITLE_SECONDS
    scenes = []
    for i, scene in enumerate(script["scenes"]):
        start = t
        beats = []
        for j, beat in enumerate(scene["beats"]):
            dur, file = durations.get((i, j), (max(1.5, len(str(beat.get("say") or "").split()) / 2.4), None))
            action = beat.get("action") or {}
            lead = 0.8 if action.get("type") in ("enter", "appear") and j == 0 else 0.0
            beats.append({**beat, "start": t + lead, "dur": dur, "file": file, "i": i, "j": j})
            t += lead + dur + GAP
        t += SCENE_GAP
        scenes.append({**scene, "start": start, "end": t, "beats": beats, "i": i})
    return scenes, t + END_SECONDS


def envelope(path, fps=FPS):
    """How loud the voice is in each frame: drives the mouth."""
    audio, sr = sf.read(path, dtype="float32")
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    hop = int(sr / fps)
    frames = max(1, len(audio) // hop)
    rms = np.array([np.sqrt(np.mean(audio[k * hop:(k + 1) * hop] ** 2) + 1e-12) for k in range(frames)])
    return rms / (rms.max() + 1e-9)


# ------------------------------------------------------------------ the cast on stage
class Actor:
    def __init__(self, char, slot, facing):
        self.c = char
        self.x = W * SLOTS.get(slot, 0.5)
        self.home = self.x
        self.facing = facing
        self.visible = True
        self.fallen = False
        self.emotion = "calm"
        self.blink_seed = random.Random(char.id).uniform(0, 3)

    def blink(self, t):
        period = 3.2 + (hash(self.c.id) % 10) / 6
        return ((t + self.blink_seed) % period) < 0.12


class SceneState:
    """Who is where, from the start of the scene to time t, by replaying the actions."""

    def __init__(self, scene, cast):
        self.scene = scene
        self.actors = {}
        for c in scene.get("cast") or []:
            if c["id"] in cast:
                slot = c.get("slot", "center")
                facing = c.get("facing") or (1 if SLOTS.get(slot, 0.5) < 0.5 else -1)
                a = Actor(cast[c["id"]], slot, 1 if facing in (1, "right") else -1)
                a.visible = not c.get("hidden") and not any(
                    (b.get("action") or {}).get("type") in ("enter", "appear") and (b.get("action") or {}).get("who") == c["id"]
                    for b in scene["beats"])
                self.actors[c["id"]] = a
        self.spread()

    def spread(self):
        """Wide characters (ten heads, wings) need room: push neighbours apart, keep everyone on screen."""
        order = sorted(self.actors.values(), key=lambda a: a.home)

        def half(a):
            return a.c.width * CHAR_SCALE * a.c.height * (0.36 if a.c.width > 800 else 0.26)

        for _ in range(3):
            for left, right in zip(order, order[1:]):
                need = half(left) + half(right)
                gap = right.home - left.home
                if gap < need:
                    push = (need - gap) / 2
                    left.home -= push
                    right.home += push
            lo, hi = min(a.home - half(a) for a in order) if order else 0, max(a.home + half(a) for a in order) if order else W
            if lo < 20 or hi > W - 20:
                span = hi - lo
                k = min(1.0, (W - 40) / span) if span else 1
                for a in order:
                    a.home = 20 + (a.home - lo) * k + (half(a) * (1 - k))
        for a in order:
            a.x = a.home

    def at(self, t):
        """Each visible actor's look at time t: position, pose, walk frame, lift, rotation, alpha."""
        looks = {}
        for cid, a in self.actors.items():
            looks[cid] = {"x": a.home, "visible": a.visible, "pose": "idle", "walk": 0, "lift": 0.0, "rot": 0.0,
                          "alpha": 1.0, "emotion": "calm", "facing": a.facing, "lunge": 0.0}
        for b in self.scene["beats"]:
            if b["start"] > t:
                break
            local = t - b["start"]
            act = b.get("action") or {}
            kind, who = act.get("type"), act.get("who") or b.get("speaker")
            current = local <= b["dur"] + GAP
            for cid, e in (b.get("react") or {}).items():
                if cid in looks and current:
                    looks[cid]["emotion"] = e
            if b.get("speaker") in looks:
                looks[b["speaker"]]["emotion"] = b.get("emotion", "calm") if current else looks[b["speaker"]]["emotion"]
            if who not in looks:
                continue
            L = looks[who]
            target = act.get("target")
            if kind in ("enter", "appear"):
                L["visible"] = True
                if kind == "enter":
                    edge = -180 if L["x"] < W / 2 else W + 180
                    p = ease(local / 1.4)
                    L["x"] = edge + (self.actors[who].home - edge) * p
                    L["facing"] = 1 if edge < 0 else -1
                    if p < 1:
                        L["walk"] = 1 + int(local * 8) % 4
                    else:
                        L["facing"] = self.actors[who].facing
                else:
                    L["alpha"] = ease(local / 0.8)
            elif kind in ("exit", "vanish"):
                if kind == "exit":
                    edge = -220 if L["x"] < W / 2 else W + 220
                    p = ease(local / 1.4)
                    L["x"] = L["x"] + (edge - L["x"]) * p
                    L["facing"] = -1 if edge < 0 else 1
                    L["walk"] = 1 + int(local * 8) % 4 if p < 1 else 0
                    if p >= 1:
                        L["visible"] = False
                else:
                    L["alpha"] = 1 - ease(local / 0.8)
                    if local > 0.8:
                        L["visible"] = False
            elif kind == "walk" and act.get("to") in SLOTS:
                dest = W * SLOTS[act["to"]]
                p = ease(local / 1.4)
                start_x = L["x"]
                L["x"] = start_x + (dest - start_x) * p
                if p < 1:
                    L["walk"] = 1 + int(local * 8) % 4
                    L["facing"] = 1 if dest > start_x else -1
                self.actors[who].home = dest if p >= 1 else self.actors[who].home
            elif kind == "fall":
                L["rot"] = 85 * ease(local / 0.45) * (-L["facing"])
            elif kind == "jump" and current:
                L["lift"] = max(0.0, math.sin(min(1.0, local / 0.7) * math.pi)) * 160
            elif kind == "fly":
                p = ease(local / 1.6)
                L["lift"] = 200 * p
                if target in looks:
                    L["x"] = L["x"] + (looks[target]["x"] - L["x"]) * p * 0.3
            if current and kind in ("point", "raise", "namaste", "bless", "attack"):
                L["pose"] = kind
            if current and kind == "bow":
                L["pose"], L["rot"] = "namaste", 8 * L["facing"]
            if kind == "attack" and current:
                L["lunge"] = math.sin(min(1.0, local / 0.5) * math.pi) * 90
                if target in looks:
                    L["facing"] = 1 if looks[target]["x"] > L["x"] else -1
            # face whoever is spoken to
            if current and target in looks and kind not in ("enter", "exit", "walk"):
                L["facing"] = 1 if looks[target]["x"] > L["x"] else -1
        return looks


# ------------------------------------------------------------------ drawing helpers
def text_box(lines, size=46, fill=(255, 255, 255), name=None, name_fill=(250, 204, 21), width=1500):
    f = font(size)
    words = " ".join(lines).split()
    rows, cur = [], ""
    for w in words:
        if cur and f.getlength(cur + " " + w) > width:
            rows.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        rows.append(cur)
    rows = rows[:3]
    nf = font(38)
    lh = int(size * 1.28)
    top = 50 if name else 18
    bw = int(max([f.getlength(r) for r in rows] + [nf.getlength(name) if name else 0])) + 70
    bh = top + lh * len(rows) + 22
    img = Image.new("RGBA", (bw, bh), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, bw - 1, bh - 1], radius=24, fill=(10, 8, 20, 185))
    if name:
        d.text((35, 12), name, font=nf, fill=name_fill)
    for k, r in enumerate(rows):
        d.text((35, top + k * lh), r, font=f, fill=fill, stroke_width=2, stroke_fill=(0, 0, 0))
    return img


def banner(text, fill=(232, 178, 40)):
    f = font(54, fancy=True)
    w = int(f.getlength(text)) + 90
    img = Image.new("RGBA", (w, 96), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, w - 1, 95], radius=48, fill=fill + (235,))
    d.text((45, 10), text, font=f, fill=(40, 20, 10))
    return img


def sparkle(d, cx, cy, t, n=14, r=140):
    for k in range(n):
        a = k / n * 6.283 + t * 2
        rr = r * (0.6 + 0.4 * math.sin(t * 3 + k))
        x, y = cx + math.cos(a) * rr, cy + math.sin(a) * rr * 0.8
        s = 5 + 4 * math.sin(t * 6 + k)
        d.polygon([(x, y - s * 2), (x + s * 0.5, y), (x, y + s * 2), (x - s * 0.5, y)], fill=(255, 236, 150, 230))
        d.polygon([(x - s * 2, y), (x, y + s * 0.5), (x + s * 2, y), (x, y - s * 0.5)], fill=(255, 236, 150, 230))


# ------------------------------------------------------------------ the renderer
class Episode:
    def __init__(self, folder, preview=False, music_on=True):
        self.folder = folder
        self.series_dir = os.path.dirname(os.path.dirname(os.path.abspath(folder)))
        self.script = json.load(open(os.path.join(folder, "script.json"), encoding="utf-8"))
        self.bible = json.load(open(os.path.join(self.series_dir, "bible.json"), encoding="utf-8"))
        series = json.load(open(os.path.join(self.series_dir, "series.json"), encoding="utf-8"))
        self.series_title = series.get("title_screen") or series["title"]
        listing = os.path.join(folder, "audio", "lines.json")
        self.lines = json.load(open(listing, encoding="utf-8"))["lines"] if os.path.exists(listing) else []
        self.cast = {cid: Character({**spec, "id": cid}) for cid, spec in self.bible["characters"].items()}
        self.scenes, self.total = build_timeline(self.script, self.lines, self.bible)
        self.preview = preview
        self.music_on = music_on
        self.length = min(self.total, 45.0) if preview else self.total
        self.sceneries, self.states, self.envs = {}, {}, {}
        self._char_cache = {}

    # --- per scene
    def place_of(self, scene):
        pid = scene.get("place")
        info = self.bible.get("places", {}).get(pid, {"type": pid or "forest"})
        return info.get("type", "forest"), pid or info.get("type", "forest")

    def scenery(self, scene):
        key = scene["i"]
        if key not in self.sceneries:
            ptype, seed = self.place_of(scene)
            self.sceneries = {k: v for k, v in self.sceneries.items() if abs(k - key) <= 1}
            self.sceneries[key] = Scenery(ptype, scene.get("time", "day"), scene.get("weather", "clear"), seed)
        return self.sceneries[key]

    def state(self, scene):
        if scene["i"] not in self.states:
            self.states[scene["i"]] = SceneState(scene, self.cast)
        return self.states[scene["i"]]

    def env(self, beat):
        f = beat.get("file")
        if not f:
            return None
        if f not in self.envs:
            self.envs[f] = envelope(os.path.join(self.folder, f))
        return self.envs[f]

    def scene_at(self, t):
        for s in self.scenes:
            if s["start"] <= t < s["end"]:
                return s
        return None

    def beat_at(self, scene, t):
        current = None
        for b in scene["beats"]:
            if b["start"] <= t:
                current = b
        return current

    # --- camera: wide shots and close-ups, cut on each line
    def camera(self, scene, t, looks):
        def shot(b, k):
            if b is None:
                return (W / 2, H / 2, 1.0)
            spk = b.get("speaker")
            close = spk in looks and looks[spk]["visible"] and b["dur"] > 2.2 and k % 3 != 0
            if close:
                a = self.cast[spk]
                x = looks[spk]["x"]
                head_y = GROUND - CHAR_SCALE * 900 * a.height * 0.72 - looks[spk]["lift"]
                return (x, head_y + 190, 1.42)
            return (W / 2, H / 2 + 20, 1.04 + 0.03 * (k % 2))

        beats = scene["beats"]
        idx = max([k for k, b in enumerate(beats) if b["start"] <= t] or [0])
        cx, cy, z = shot(beats[idx] if beats and beats[0]["start"] <= t else None, idx)
        if idx > 0 or (beats and t >= beats[0]["start"]):
            prev = shot(beats[idx - 1], idx - 1) if idx > 0 else (W / 2, H / 2, 1.0)
            p = ease((t - beats[idx]["start"]) / 0.5)
            cx, cy, z = (prev[0] + (cx - prev[0]) * p, prev[1] + (cy - prev[1]) * p, prev[2] + (z - prev[2]) * p)
        z = max(1.0, z + 0.012 * math.sin(t * 0.25))   # never quite still, never past the edge
        hw, hh = W / z / 2, H / z / 2
        cx, cy = min(max(cx, hw), W - hw), min(max(cy, hh), H - hh)
        return cx, cy, z

    # --- one frame
    def char_image(self, a, look, mouth, blink):
        key = (a.id, look["emotion"], mouth, blink, look["pose"], look["walk"], look["facing"])
        img = self._char_cache.get(key)
        if img is None:
            if len(self._char_cache) > 400:
                self._char_cache.clear()
            img = a.image(look["emotion"], mouth, blink, look["pose"], look["walk"], look["facing"])
            self._char_cache[key] = img
        return img

    def frame(self, t):
        scene = self.scene_at(t)
        if t < TITLE_SECONDS or scene is None:
            return self.title_card(t) if t < TITLE_SECONDS else self.end_card(t - self.scenes[-1]["end"])
        local = t - scene["start"]
        sc = self.scenery(scene)
        world = sc.frame(local)
        st = self.state(scene)
        looks = st.at(t)
        beat = self.beat_at(scene, t)
        cx, cy, z = self.camera(scene, t, looks)
        # background through the camera
        box = (cx - W / z / 2, cy - H / z / 2, cx + W / z / 2, cy + H / z / 2)
        canvas = world.resize((W, H), Image.BILINEAR, box=box).convert("RGBA")

        def to_screen(x, y):
            return (x - box[0]) * z, (y - box[1]) * z

        shake = 0.0
        d = ImageDraw.Draw(canvas)
        order = sorted(looks.items(), key=lambda kv: kv[1]["x"])
        for cid, look in order:
            if not look["visible"] or look["alpha"] <= 0.01:
                continue
            a = self.cast[cid]
            speaking = beat is not None and beat.get("speaker") == cid and beat["start"] <= t < beat["start"] + beat["dur"]
            mouth = 0
            if speaking:
                env = self.env(beat)
                if env is not None:
                    v = env[min(len(env) - 1, int((t - beat["start"]) * FPS))]
                    mouth = 2 if v > 0.5 else 1 if v > 0.16 else 0
                else:
                    mouth = int(t * 8) % 3
            img = self.char_image(a, look, mouth, st.actors[cid].blink(t))
            scale = CHAR_SCALE * a.height * z
            w, h = int(img.width * scale), int(img.height * scale)
            spr = img.resize((w, h), Image.BILINEAR)
            if look["rot"]:
                spr = spr.rotate(look["rot"], resample=Image.BILINEAR, expand=True, center=(w / 2, h))
            if look["alpha"] < 1:
                alpha = spr.getchannel("A").point(lambda v: int(v * look["alpha"]))
                spr.putalpha(alpha)
            bob = math.sin(t * (5.5 if speaking else 1.6) + hash(cid) % 7) * (5 if speaking else 2.5)
            x = look["x"] + look["lunge"] * look["facing"]
            sx, sy = to_screen(x, GROUND - look["lift"])
            # ground shadow
            d.ellipse([sx - w * 0.18, sy - 10 * z, sx + w * 0.18, sy + 12 * z], fill=(0, 0, 0, 60))
            canvas.alpha_composite(spr, (int(sx - spr.width / 2), int(sy - spr.height + bob * z)))
            if "aura" in (a.spec.get("extras") or []) and speaking:
                sparkle(d, sx, sy - h * 0.62, t, n=8, r=w * 0.45)
            if beat and (beat.get("action") or {}).get("type") in ("appear", "vanish", "magic", "bless") \
                    and (beat.get("action") or {}).get("who") == cid and t - beat["start"] < 1.6:
                sparkle(d, sx, sy - h * 0.5, t, n=16, r=w * 0.6)
            if beat and (beat.get("action") or {}).get("type") == "attack" and (beat.get("action") or {}).get("target") == cid:
                hit = t - beat["start"]
                if 0.25 < hit < 0.55:
                    shake = 14 * (1 - (hit - 0.25) / 0.3)
                    d.ellipse([sx - 90, sy - h * 0.6 - 90, sx + 90, sy - h * 0.6 + 90], fill=(255, 250, 200, 140))
        canvas = sc.weather_overlay(canvas, local)
        if shake:
            canvas = canvas.transform(canvas.size, Image.AFFINE, (1, 0, random.uniform(-shake, shake), 0, 1,
                                                                  random.uniform(-shake, shake)))
        # banners for recap and teaser
        kind = scene.get("kind")
        if kind in ("recap", "teaser") and local < 3.5:
            b = banner("Pichhle episode mein..." if kind == "recap" else "Agle episode mein...")
            q = ease(local / 0.4) * (1 - ease((local - 3.0) / 0.5))
            canvas.alpha_composite(b, (int(W / 2 - b.width / 2), int(60 - 140 * (1 - q))))
        # fade in and out of scenes
        fade = min(ease(local / 0.4), ease((scene["end"] - t) / 0.4))
        if fade < 1:
            canvas = Image.blend(Image.new("RGBA", (W, H), (0, 0, 0, 255)), canvas, fade)
        # captions
        if beat and beat["start"] <= t < beat["start"] + beat["dur"] + GAP * 0.5:
            spk = beat.get("speaker", "narrator")
            name = None if spk == "narrator" else self.bible["characters"].get(spk, {}).get("name", spk)
            cs = self.bible["characters"].get(spk, {}).get("colors") or ["yellow"]
            cap = self._caption(beat, name, cs[0])
            canvas.alpha_composite(cap, (int(W / 2 - cap.width / 2), H - cap.height - 46))
        self.chrome(canvas)
        return canvas

    def _caption(self, beat, name, col):
        key = ("cap", beat["i"], beat["j"])
        if key not in self._char_cache:
            nf = colour(col)
            if sum(nf) / 3 < 120:   # a dark costume colour can't be read on the dark box
                nf = (250, 204, 21)
            nf = tuple(min(255, int(v * 1.15) + 40) for v in nf)
            self._char_cache[key] = text_box([str(beat.get("say") or "")], name=name, name_fill=nf)
        return self._char_cache[key]

    def chrome(self, canvas):
        if not hasattr(self, "_tag"):
            n = self.script.get("n", 1)
            self._tag = text_box([f"{self.series_title}  |  Episode {n}"], size=30, width=900)
        canvas.alpha_composite(self._tag, (30, 26))

    def title_card(self, t):
        first = self.scenes[0] if self.scenes else {"i": 0, "place": "forest", "time": "day"}
        sc = self.scenery(first)
        img = sc.frame(t).filter(ImageFilter.GaussianBlur(6)).convert("RGBA")
        img.alpha_composite(Image.new("RGBA", (W, H), (10, 6, 20, 120)))
        d = ImageDraw.Draw(img)
        p = ease(t / 0.8)
        big = font(130, fancy=True)
        title = self.series_title
        tw = big.getlength(title)
        d.text((W / 2 - tw / 2, 300 - 60 * (1 - p)), title, font=big, fill=(255, 214, 90),
               stroke_width=6, stroke_fill=(60, 20, 10))
        sub = f"Episode {self.script.get('n', 1)}"
        f2 = font(64)
        q = ease((t - 0.6) / 0.6)
        d.text((W / 2 - f2.getlength(sub) / 2, 500), sub, font=f2, fill=(255, 255, 255, int(255 * q)))
        name = self.script.get("title", "")
        f3 = font(72, fancy=True)
        r = ease((t - 1.1) / 0.6)
        d.text((W / 2 - f3.getlength(name) / 2, 600 + 30 * (1 - r)), name, font=f3, fill=(255, 240, 200, int(255 * r)),
               stroke_width=3, stroke_fill=(40, 20, 10))
        lead = [c["id"] for c in (first.get("cast") or [])][:3]
        for k, cid in enumerate(lead):
            if cid in self.cast:
                a = self.cast[cid]
                spr = a.image("happy", 0, False, "namaste" if k == 1 else "idle", 0, 1 if k == 0 else -1)
                s = 0.46 * a.height
                spr = spr.resize((int(spr.width * s), int(spr.height * s)), Image.BILINEAR)
                x = [280, W / 2, W - 280][k] if len(lead) == 3 else [360, W - 360, W / 2][k]
                img.alpha_composite(spr, (int(x - spr.width / 2), int(H - spr.height + 30 + 200 * (1 - ease((t - 0.3 * k) / 0.9)))))
        if t > TITLE_SECONDS - 0.5:
            img = Image.blend(img, Image.new("RGBA", (W, H), (0, 0, 0, 255)), ease((t - TITLE_SECONDS + 0.5) / 0.5))
        return img

    def end_card(self, t):
        last = self.scenes[-1]
        sc = self.scenery(last)
        img = sc.frame(t).filter(ImageFilter.GaussianBlur(8)).convert("RGBA")
        img.alpha_composite(Image.new("RGBA", (W, H), (10, 6, 20, 140)))
        d = ImageDraw.Draw(img)
        p = ease(t / 0.6)
        f = font(92, fancy=True)
        line1 = "Kahani abhi baaki hai..."
        d.text((W / 2 - f.getlength(line1) / 2, 320), line1, font=f, fill=(255, 214, 90, int(255 * p)),
               stroke_width=5, stroke_fill=(50, 20, 10))
        f2 = font(56)
        line2 = f"Agla episode: {self.script.get('next_title') or 'jald aa raha hai'}"
        d.text((W / 2 - f2.getlength(line2) / 2, 470), line2, font=f2, fill=(255, 255, 255, int(255 * p)))
        bw, bh = 420, 110
        q = ease((t - 0.8) / 0.5)
        pulse = 1 + 0.05 * math.sin(t * 6)
        x0, y0 = W / 2 - bw * pulse / 2, 640
        d.rounded_rectangle([x0, y0, x0 + bw * pulse, y0 + bh], radius=26, fill=(220, 30, 40, int(255 * q)))
        f3 = font(54)
        d.text((W / 2 - f3.getlength("SUBSCRIBE") / 2, y0 + 24), "SUBSCRIBE", font=f3, fill=(255, 255, 255, int(255 * q)))
        if t > END_SECONDS - 0.8:
            img = Image.blend(img, Image.new("RGBA", (W, H), (0, 0, 0, 255)), ease((t - END_SECONDS + 0.8) / 0.8))
        return img

    # ------------------------------------------------------------------ sound
    def mix(self):
        n = int(self.length * sound.SR) + sound.SR
        voice = np.zeros(n, np.float32)
        sr_cache = {}
        for s in self.scenes:
            for b in s["beats"]:
                if not b.get("file") or b["start"] >= self.length:
                    continue
                audio, sr = sf.read(os.path.join(self.folder, b["file"]), dtype="float32")
                if audio.ndim > 1:
                    audio = audio.mean(axis=1)
                if sr != sound.SR:
                    from scipy.signal import resample_poly
                    g = math.gcd(sr, sound.SR)
                    audio = resample_poly(audio, sound.SR // g, sr // g).astype(np.float32)
                sound._place(voice, audio * 0.95, b["start"])
        bed = np.zeros(n, np.float32)
        fx = np.zeros(n, np.float32)
        music_dir = os.path.join(self.series_dir, "music")
        for s in self.scenes:
            if s["start"] >= self.length:
                break
            length = min(s["end"], self.length) - s["start"] + 1.2
            mood = s.get("music", "calm")
            m = None
            if self.music_on:
                for ext in ("mp3", "wav", "ogg"):
                    p = os.path.join(music_dir, f"{mood}.{ext}")
                    if os.path.exists(p):
                        m = load_audio(p, length)
                        break
                if m is None:
                    m = sound.music(mood, length, seed=hash((self.script.get("n", 1), s["i"])) % 10000)
                m = m / (np.sqrt(np.mean(m ** 2)) + 1e-6) * 0.09
                sound._place(bed, m * sound._env(len(m), 0.8, 1.2), s["start"])
            ptype, _ = self.place_of(s)
            amb = sound.ambience(ptype, s.get("time", "day"), s.get("weather", "clear"), length, seed=s["i"])
            sound._place(bed, amb * 0.8 * sound._env(len(amb), 0.5, 0.8), s["start"])
            sound._place(fx, sound.effect("whoosh") * 0.35, s["start"])
            sc = self.scenery(s)
            for f in sc.flash_at:
                if s["start"] + f < s["end"]:
                    sound._place(fx, sound.effect("thunder") * 0.6, s["start"] + f + 0.15)
            for b in s["beats"]:
                act = (b.get("action") or {}).get("type")
                auto = {"enter": ["step"], "exit": ["step"], "walk": ["step"], "attack": ["clash"], "appear": ["magic"],
                        "vanish": ["magic"], "bless": ["magic"], "fall": ["fall"], "fly": ["fly"], "jump": ["whoosh"]}
                names = list(dict.fromkeys(auto.get(act, []) + [x for x in (b.get("sfx") or []) if x in sound.EFFECTS]))
                for name in names:
                    if name == "step":
                        for k in range(5):
                            sound._place(fx, sound.effect("step", k) * 0.4, b["start"] + k * 0.25)
                    elif name == "clash":
                        weapon = self.bible["characters"].get((b.get("action") or {}).get("who", ""), {}).get("prop")
                        sound._place(fx, sound.effect("arrow" if weapon == "bow" else "clash") * 0.7, b["start"] + 0.25)
                    else:
                        sound._place(fx, sound.effect(name) * 0.6, b["start"] + 0.1)
        sound._place(fx, sound.effect("gong") * 0.6, 0.2)
        sound._place(fx, sound.effect("conch") * 0.4, 1.2)
        end = self.scenes[-1]["end"] if self.scenes else 0
        if end < self.length:
            sound._place(fx, sound.effect("bell") * 0.5, end + 0.3)
        # duck the bed under the voice
        from scipy.signal import lfilter
        level = np.abs(voice)
        a = math.exp(-1 / (0.15 * sound.SR))
        level = lfilter([1 - a], [1, -a], level)
        duck = 1 - 0.55 * np.clip(level / 0.05, 0, 1)
        out = voice + bed * duck + fx
        peak = np.abs(out).max()
        out = out / peak * 0.92 if peak > 0 else out
        return out[:int(self.length * sound.SR)]

    def subtitles(self, path):
        def ts(x):
            ms = int(round(x * 1000))
            return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"
        rows = []
        for s in self.scenes:
            for b in s["beats"]:
                if b["start"] >= self.length or not b.get("say"):
                    continue
                spk = b.get("speaker", "narrator")
                name = "" if spk == "narrator" else self.bible["characters"].get(spk, {}).get("name", spk) + ": "
                rows.append(f"{len(rows) + 1}\n{ts(b['start'])} --> {ts(b['start'] + b['dur'])}\n{name}{b['say']}\n")
        open(path, "w", encoding="utf-8").write("\n".join(rows))

    def render(self):
        out_dir = os.path.join(self.folder, "output")
        os.makedirs(out_dir, exist_ok=True)
        name = "preview" if self.preview else "episode"
        wav = os.path.join(out_dir, f"{name}.wav")
        sf.write(wav, self.mix(), sound.SR)
        mp4 = os.path.join(out_dir, f"{name}.mp4")
        cmd = ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
               "-i", "-", "-i", wav, "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
               "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", mp4]
        pipe = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        frames = int(self.length * FPS)
        started = time.time()
        for k in range(frames):
            img = self.frame(k / FPS)
            pipe.stdin.write(img.convert("RGB").tobytes())
            if k % (FPS * 15) == 0 and k:
                done = k / frames
                left = (time.time() - started) / done * (1 - done)
                print(f"   {done * 100:4.1f}%   about {left / 60:.1f} min left", flush=True)
        pipe.stdin.close()
        pipe.wait()
        os.remove(wav)
        self.subtitles(os.path.join(out_dir, f"{name}.srt"))
        print(f"Done: {mp4} ({self.length / 60:.1f} min)")
        return mp4


def load_audio(path, seconds):
    """Your own music file, looped to the scene length."""
    out = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-f", "f32le", "-ac", "1", "-ar", str(sound.SR), "-"],
                         capture_output=True)
    audio = np.frombuffer(out.stdout, np.float32)
    if not len(audio):
        return None
    n = int(seconds * sound.SR)
    return np.tile(audio, n // len(audio) + 1)[:n].copy()


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        raise SystemExit(__doc__)
    for folder in args:
        Episode(folder, preview="--preview" in sys.argv, music_on="--no-music" not in sys.argv).render()
