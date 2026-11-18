"""
Moving pictures for a rhyme: your pictures (images/p01.jpg ...) or clips (images/p03.mp4) brought to life with slow
camera moves, soft crossfades and a moving effect on top (rain, bubbles, sparkles, petals, stars, snow).
Used by video.py when pictures.json exists; a slot without a file returns None and is drawn by code instead.
"""
import json
import math
import os
import random
import subprocess

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

import pictures
from stage import H, W

CAST_ART = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "rhymes", "cast_art")
FEET = 0.83          # characters stand with their feet here (fraction of the height), just above the words box
_sprites = {}


def back_out(x):   # overshoot, then settle: things pop in
    x = max(0.0, min(1.0, x))
    return 1 + 2.9 * (x - 1) ** 3 + 1.9 * (x - 1) ** 2


def sprite(kind):
    """The character's cut-out picture (rhymes/cast_art/<kind>_cut.png, made from <kind>.png on first use)."""
    if kind not in _sprites:
        raw = os.path.join(CAST_ART, f"{kind}.png")
        cut = os.path.join(CAST_ART, f"{kind}_cut.png")
        if not os.path.exists(raw):
            _sprites[kind] = None
        else:
            if not os.path.exists(cut) or os.path.getmtime(cut) < os.path.getmtime(raw):
                import cutout
                cutout.cut(Image.open(raw)).save(cut)
            _sprites[kind] = Image.open(cut).convert("RGBA")
    return _sprites[kind]


def cast_kinds(slot):
    return slot["cast"][:1] if slot["role"] == "title" else slot["cast"][:3]


_halos = {}


def halo(w, h, colour=(255, 236, 150)):
    """A soft glow to put behind a sky character (cached by size)."""
    key = (w // 8, h // 8, colour)
    if key not in _halos:
        g = Image.new("RGBA", (int(w * 1.9), int(h * 1.9)), (0, 0, 0, 0))
        ImageDraw.Draw(g).ellipse([g.width * 0.2, g.height * 0.2, g.width * 0.8, g.height * 0.8], fill=colour + (150,))
        _halos[key] = g.filter(ImageFilter.GaussianBlur(max(4, w / 7)))
    return _halos[key]


def place_cast(img, kinds, local, beat_phase, lead_big=False, still=False, appear=None, cam=None, accent=None,
               dance=False, corner=False):
    """Draw the characters onto img (any size): pop in one after another, hop and squash on the beat, sway, a jump when
    a line starts (accent: seconds since), now and then a quick turn round, and they move with the 3D camera
    (cam: dx, dy, scale of things at their depth). dance (chorus): bigger hops, side steps and wiggles. Sky characters
    glow, twinkle and rock."""
    from critters import KINDS
    sc = img.height / H
    kinds = [k for k in kinds if sprite(k) is not None]
    ground = [k for k in kinds if not KINDS[k][4]]
    xs = {1: [0.5], 2: [0.33, 0.67], 3: [0.2, 0.5, 0.8]}
    dx, dy, zoom = cam if cam else (0.0, 0.0, 1.0)

    def placed(x, y):   # a point of the picture after the camera move
        return img.width / 2 + (x - img.width / 2) * zoom + dx * sc, img.height / 2 + (y - img.height / 2) * zoom + dy * sc

    for k, kind in enumerate(kinds):
        floats = KINDS[kind][4]
        size = KINDS[kind][3]
        since = local if appear is None else appear
        pop = 1.0 if still else back_out((since - 0.15 - k * 0.18) / 0.45)
        if pop <= 0.02:
            continue
        lead = k == 0
        if floats:
            h = H * (0.17 if corner else 0.26) * size   # corner: small, high up (over a picture with children in it)
        else:
            h = H * (0.42 if lead_big else 0.5) * size * (1.08 if lead and len(kinds) > 1 else 1)  # title: smaller
        h *= zoom
        bp = 0.0 if still else (beat_phase + k * 0.25) % 1
        sx = 1 - 0.035 * math.cos(2 * math.pi * bp) if not floats else 1
        sy = 1 + 0.045 * math.cos(2 * math.pi * bp) if not floats else 1
        jump = 0.0
        if not still and accent is not None and not floats:
            a = accent - k * 0.12                       # one after another
            if 0 <= a < 0.55:
                jump = math.sin(math.pi * a / 0.55)      # up and down
            elif 0.55 <= a < 0.75:                       # landing: squash
                q = math.sin(math.pi * (a - 0.55) / 0.2)
                sx, sy = sx * (1 + 0.12 * q), sy * (1 - 0.12 * q)
        # now and then a quick turn round (the picture flips through its edge, like turning in 3D)
        facing, turn = 1, 1.0
        if not still and not floats:
            period = 7.0 + k * 1.7
            ph = (local + 2.3 + k * 2.9) / period
            n, u = int(ph), (ph % 1) * period
            facing = -1 if n % 2 else 1
            if u < 0.36:
                turn = max(0.08, abs(math.cos(math.pi * u / 0.36)))
                if u < 0.18:
                    facing = -facing
        if floats and not still:   # twinkle: a gentle grow-and-shrink
            tw = 1 + 0.07 * math.sin(local * 4.2 + k * 1.7)
            sx, sy = sx * tw, sy * tw
        spr = sprite(kind)
        hh = max(2, int(h * pop * sy * sc))
        ww = max(2, int(spr.width * h / spr.height * pop * sx * turn * sc))
        im = spr.resize((ww, hh), Image.BILINEAR)
        if facing < 0:
            im = im.transpose(Image.FLIP_LEFT_RIGHT)
        if floats:
            others = [q for q in kinds if KINDS[q][4] and q not in ("sun", "moon")]   # moon/sun right, the rest left
            cx = img.width * (0.8 if kind in ("sun", "moon") else (0.2, 0.45, 0.62)[min(2, others.index(kind))])
            if corner:
                cx = img.width * (0.9 if kind in ("sun", "moon") else 0.1 + 0.1 * others.index(kind))
            cy = img.height * (0.12 if corner else 0.22) + (0 if still else math.sin(local * 1.3 + k) * 18 * sc)
            if not still:
                cx += math.sin(local * 0.6 + k * 2) * 40 * sc
            cx, cy = placed(cx, cy)
            if not still:
                im = im.rotate(6 * math.sin(local * 1.1 + k), resample=Image.BILINEAR, expand=True)
                g = halo(ww, hh)
                glow = g.copy()
                glow.putalpha(glow.getchannel("A").point(lambda v, f=0.65 + 0.35 * math.sin(local * 2.6 + k): int(v * f)))
                img.alpha_composite(glow, (int(cx - g.width / 2), int(cy - g.height / 2)))
            img.alpha_composite(im, (int(cx - im.width / 2), int(cy - im.height / 2)))
            continue
        spots = xs.get(len(ground), [0.5])
        cx = img.width * spots[min(ground.index(kind), len(spots) - 1)]
        energy = 1.8 if dance else 1.0
        hop = 0 if still else (abs(math.sin(math.pi * bp)) * (20 if lead else 11) * energy + jump * (70 if lead else 50)) * sc
        if dance and not still:   # side steps to the music
            cx += math.sin(local * 2.6 + k * 1.3) * 34 * sc
        if not still:
            lean = 3.0 * (0.5 - cx / img.width) * 2 * math.sin(math.pi * min(1.0, local / 1.5))   # lean to the middle
            angle = (6.0 if dance else 2.5) * math.sin(2 * math.pi * (local / (1.2 if dance else 2.4) + k * 0.5)) + lean
            im = im.rotate(angle, resample=Image.BILINEAR, expand=True)
        cx, feet = placed(cx, img.height * FEET)
        shadow = Image.new("RGBA", (max(2, int(ww * 0.75)), max(2, int(36 * sc))), (0, 0, 0, 0))
        ImageDraw.Draw(shadow).ellipse([0, 0, shadow.width - 1, shadow.height - 1], fill=(0, 0, 0, int(70 - hop / sc)))
        shadow = shadow.filter(ImageFilter.GaussianBlur(6 * sc))
        img.alpha_composite(shadow, (int(cx - shadow.width / 2), int(feet - shadow.height / 2)))
        img.alpha_composite(im, (int(cx - im.width / 2), int(feet - im.height + (im.height - hh) / 2 - hop)))
    return img


def compose_still(folder, slot, size):
    """A slot's picture at rest, characters in place (review sheet, thumbnails)."""
    f = pictures.find_file(folder, slot["id"]) or (pictures.find_file(folder, slot["same_as"]) if slot.get("same_as") else None)
    if not f or f.lower().endswith((".mp4", ".webm", ".mov")):
        return None
    img = cover(Image.open(f).convert("RGB"), *size).convert("RGBA")
    if slot.get("ai_layers") and os.path.basename(f) == slot.get("ai_file"):
        place_cast(img, cast_kinds(slot), 5.0, 0.0, lead_big=slot["role"] == "title", still=True)
    return img


def review_sheet(folder):
    """images/review.jpg: every picture of the song on one sheet, as it will look."""
    path = os.path.join(folder, "pictures.json")
    if not os.path.exists(path):
        return None
    slots = json.load(open(path, encoding="utf-8"))["pictures"]
    tiles = [(s["id"], compose_still(folder, s, (640, 360))) for s in slots if "same_as" not in s]
    tiles = [(i, im) for i, im in tiles if im is not None]
    if not tiles:
        return None
    tw, th, cols = 448, 252, 3
    sheet = Image.new("RGB", (tw * cols, th * ((len(tiles) + cols - 1) // cols)), (30, 30, 30))
    for k, (pid, im) in enumerate(tiles):
        im = im.convert("RGB").resize((tw, th))
        ImageDraw.Draw(im).text((8, 6), pid, fill=(255, 255, 0), font_size=28, stroke_width=3, stroke_fill=(0, 0, 0))
        sheet.paste(im, ((k % cols) * tw, (k // cols) * th))
    out = os.path.join(folder, "images", "review.jpg")
    sheet.save(out, quality=88)
    return out

FADE = 0.4      # seconds of crossfade between pictures
TRANS = 0.5     # seconds of a transition (fade, iris, push, zoom) between pictures
MARGIN = 1.14   # pictures are made this much bigger than the frame, so the camera has room to move
MOVES = ("in", "pan_right", "out", "pan_left", "in_up", "pan_down")   # flat moves (no depth model)
CHAR_DEPTH = 0.8   # the cut-out characters stand this near the camera (0 far .. 1 near) for the 3D moves


def cover(img, w, h):
    s = max(w / img.width, h / img.height)
    img = img.resize((max(w, round(img.width * s)), max(h, round(img.height * s))), Image.LANCZOS)
    x, y = (img.width - w) // 2, (img.height - h) // 2
    return img.crop((x, y, x + w, y + h))


def smooth(x):
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


def clip_seconds(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                       capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def loop_file(path):
    """The clip forwards then backwards (images/clips/.loop/pNN.mp4, made once): played in a loop it never freezes
    and never jumps, however long its picture stays on screen."""
    out = os.path.join(os.path.dirname(path), ".loop", os.path.basename(path))
    if not os.path.exists(out) or os.path.getmtime(out) < os.path.getmtime(path):
        os.makedirs(os.path.dirname(out), exist_ok=True)
        done = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", path, "-filter_complex",
                               "[0:v]split[a][b];[b]reverse,trim=start_frame=1[r];[a][r]concat=n=2:v=1[v]", "-map",
                               "[v]", "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "17", out])
        if done.returncode != 0:
            return path
    return out


class Clip:
    """Reads a video file frame by frame, in order. Plays once, then holds its last frame (no jump back);
    loop=True plays it again and again (for the forwards-backwards AI clips)."""

    def __init__(self, path, fps, loop=False, stretch=1.0):
        self.path, self.fps, self.loop, self.stretch = path, fps, loop, stretch
        self.proc, self.index, self.last, self.ended = None, -1, None, False

    def _open(self):
        if self.proc:
            self.proc.kill()
        slow = f"setpts={self.stretch:.4f}*PTS," if abs(self.stretch - 1) > 0.01 else ""
        vf = f"{slow}scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={self.fps}"
        self.proc = subprocess.Popen(["ffmpeg", "-v", "error", *(["-stream_loop", "-1"] if self.loop else []),
                                      "-i", self.path, "-an", "-vf", vf, "-f", "rawvideo",
                                      "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
        self.index, self.ended = -1, False

    def at(self, local_t):
        """(frame, seconds past the end of the clip)."""
        want = max(0, int(local_t * self.fps))
        if self.proc is None or want < self.index:
            self._open()
        size = W * H * 3
        while self.index < want and not self.ended:
            raw = self.proc.stdout.read(size)
            if len(raw) < size:
                self.ended = True
                self.proc.kill()
                break
            self.index += 1
            self.last = raw
        if self.last is None:
            return Image.new("RGB", (W, H), (0, 0, 0)), 0.0
        return Image.frombytes("RGB", (W, H), self.last), max(0.0, local_t - (self.index + 1) / self.fps)


class Effects:
    """Particles drawn in code on top of a picture. Same t -> same picture (no hidden state)."""

    def __init__(self, seed=3):
        rng = random.Random(seed)
        self.p = [(rng.random(), rng.random(), rng.random(), rng.random()) for _ in range(140)]

    def draw(self, img, kind, t, strength=1.0):
        if kind in (None, "none") or strength <= 0:
            return img
        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        a = lambda v: int(v * strength)  # noqa: E731
        if kind == "rain":
            for k, (x, y, s, ph) in enumerate(self.p[:120]):
                speed = 1.4 + s
                yy = ((y + t * speed) % 1.1 - 0.05) * H
                xx = (x * 1.2 - 0.1) * W + (yy * 0.18)
                d.line([(xx, yy), (xx - 10, yy - 46 - 30 * s)], fill=(220, 235, 255, a(150)), width=3)
            for k, (x, y, s, ph) in enumerate(self.p[:14]):   # splashes on the ground
                life = (t * 1.3 + ph) % 1
                cx, cy = x * W, H * (0.86 + 0.1 * y)
                r = 8 + 40 * life
                d.ellipse([cx - r, cy - r * 0.3, cx + r, cy + r * 0.3], outline=(230, 240, 255, a(170 * (1 - life))),
                          width=3)
        elif kind == "snow":
            for x, y, s, ph in self.p[:110]:
                yy = ((y + t * (0.08 + 0.1 * s)) % 1.05) * H
                xx = x * W + math.sin(t * 1.2 + ph * 6) * 30
                r = 4 + 6 * s
                d.ellipse([xx - r, yy - r, xx + r, yy + r], fill=(255, 255, 255, a(210)))
        elif kind == "bubbles":
            for x, y, s, ph in self.p[:40]:
                yy = (1.05 - (y + t * (0.06 + 0.08 * s)) % 1.1) * H
                xx = x * W + math.sin(t * 1.5 + ph * 6) * 25
                r = 10 + 26 * s
                d.ellipse([xx - r, yy - r, xx + r, yy + r], outline=(255, 255, 255, a(170)), width=4)
                d.ellipse([xx - r * 0.5, yy - r * 0.6, xx - r * 0.15, yy - r * 0.25], fill=(255, 255, 255, a(190)))
        elif kind == "petals":
            colours = [(255, 170, 200), (255, 210, 120), (255, 255, 255), (250, 140, 170)]
            for k, (x, y, s, ph) in enumerate(self.p[:34]):
                yy = ((y + t * (0.05 + 0.05 * s)) % 1.1 - 0.05) * H
                xx = x * W + math.sin(t * 0.9 + ph * 6) * 70
                ang = t * 2 + ph * 6
                w, h = 34 + 20 * s, 18 + 10 * s
                pts = [(xx + math.cos(ang + q) * w * (0.5 if q % 3 else 1) * (1 if q < 3 else 0.6),
                        yy + math.sin(ang + q) * h) for q in (0, 1.5, 3.1, 4.7)]
                d.polygon(pts, fill=colours[k % 4] + (a(200),))
        elif kind in ("sparkles", "stars"):
            n = 36 if kind == "stars" else 22
            for x, y, s, ph in self.p[:n]:
                glow = max(0.0, math.sin(t * (1.5 + 2 * s) + ph * 6.28))
                if glow < 0.05:
                    continue
                xx = x * W
                yy = (y * 0.5 if kind == "stars" else y * 0.75) * H
                r = (10 + 18 * s) * glow
                c = (255, 250, 210, a(230 * glow))
                d.polygon([(xx, yy - r), (xx + r * 0.22, yy - r * 0.22), (xx + r, yy), (xx + r * 0.22, yy + r * 0.22),
                           (xx, yy + r), (xx - r * 0.22, yy + r * 0.22), (xx - r, yy), (xx - r * 0.22, yy - r * 0.22)],
                          fill=c)
        elif kind == "fireflies":
            for x, y, s, ph in self.p[:34]:
                glow = 0.5 + 0.5 * math.sin(t * (2 + 2 * s) + ph * 6.28)
                xx = (x + 0.04 * math.sin(t * 0.5 + ph * 9)) * W
                yy = (0.25 + 0.6 * y + 0.03 * math.sin(t * 0.7 + ph * 5)) * H
                r = 5 + 4 * s
                d.ellipse([xx - r * 3, yy - r * 3, xx + r * 3, yy + r * 3], fill=(255, 245, 140, a(45 * glow)))
                d.ellipse([xx - r, yy - r, xx + r, yy + r], fill=(255, 255, 190, a(230 * glow)))
        elif kind == "confetti":
            colours = [(255, 90, 90), (255, 200, 60), (90, 200, 255), (130, 230, 120), (220, 120, 255)]
            for k, (x, y, s, ph) in enumerate(self.p[:60]):
                yy = ((y + t * (0.12 + 0.12 * s)) % 1.1 - 0.05) * H
                xx = x * W + math.sin(t * 2 + ph * 6) * 40
                ang = t * (3 + 3 * s) + ph * 6
                w, h = 18 * abs(math.cos(ang)) + 3, 10
                d.polygon([(xx - w, yy - h), (xx + w, yy - h * 0.6), (xx + w, yy + h), (xx - w, yy + h * 0.6)],
                          fill=colours[k % 5] + (a(220),))
        elif kind == "hearts":
            for k, (x, y, s, ph) in enumerate(self.p[:14]):
                life = (t * (0.08 + 0.06 * s) + ph) % 1
                xx = x * W + math.sin(t * 1.4 + ph * 6) * 30
                yy = H * (1.0 - 0.9 * life)
                r = 14 + 14 * s
                c = (255, 110 + int(60 * s), 160, a(200 * math.sin(math.pi * life)))
                d.ellipse([xx - r, yy - r, xx, yy], fill=c)
                d.ellipse([xx, yy - r, xx + r, yy], fill=c)
                d.polygon([(xx - r, yy - r / 2), (xx + r, yy - r / 2), (xx, yy + r)], fill=c)
        img.alpha_composite(layer)
        return img

    def burst(self, img, age, cx=W / 2, cy=H * 0.5):
        """A pop of little stars when a line starts."""
        if not 0 <= age < 0.8:
            return img
        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        e = age / 0.8
        for k in range(12):
            ang = k * math.pi / 6 + 0.3
            r = 120 + 360 * (1 - (1 - e) ** 2)
            x, y = cx + math.cos(ang) * r, cy + math.sin(ang) * r * 0.7
            s = 16 * (1 - e) + 4
            c = (255, 240, 120, int(230 * (1 - e)))
            d.polygon([(x, y - s), (x + s * 0.3, y - s * 0.3), (x + s, y), (x + s * 0.3, y + s * 0.3), (x, y + s),
                       (x - s * 0.3, y + s * 0.3), (x - s, y), (x - s * 0.3, y - s * 0.3)], fill=c)
        img.alpha_composite(layer)
        return img


class PictureTrack:
    def __init__(self, folder, script, plan, fps, clips=True):
        self.folder, self.fps = folder, fps
        self.beat = 60.0 / float(plan.get("tempo", 100))
        path = os.path.join(folder, "pictures.json")
        slots = json.load(open(path, encoding="utf-8"))["pictures"] if os.path.exists(path) else []
        starts = {(x["scene"], x["beat"]): x["start"] for x in plan["lines"]}
        firsts = {}
        for x in plan["lines"]:
            firsts.setdefault(x["scene"], x["start"])
        sections = {s.get("scene"): s["start"] for s in plan["sections"] if "scene" in s}
        outro = next(s["start"] for s in plan["sections"] if s["kind"] == "outro")
        self.slots = []
        for s in slots:
            if s["role"] == "title":
                t0 = 0.0
            elif s["role"] == "end":
                t0 = outro
            else:
                key = tuple(s["lines"][0]) if s["lines"] else None
                if key not in starts:
                    continue   # the lyrics changed since pictures.json: run rhyme.py pictures again
                t0 = sections.get(s["scene"], starts[key]) if starts[key] == firsts.get(s["scene"]) else starts[key] - 0.3
            own = pictures.find_file(folder, s["id"])
            src = s
            if not own and s.get("same_as"):
                src = next((x for x in slots if x["id"] == s["same_as"]), s)
                own = pictures.find_file(folder, s["same_as"])
            ai = bool(own and os.path.basename(own) == src.get("ai_file"))
            layers = ai and bool(src.get("ai_layers"))
            from critters import KINDS
            sky = [k for k in cast_kinds(s) if k in KINDS and KINDS[k][4]] if ai and not layers else []
            clip = os.path.join(folder, "images", "clips", f"{s['id']}.mp4")      # its own clip (a chorus repeat
            if not os.path.exists(clip):                                            # has one), else the first one's
                clip = os.path.join(folder, "images", "clips", f"{src['id']}.mp4")
            if (clips and own and not own.lower().endswith((".mp4", ".webm", ".mov")) and os.path.exists(clip)
                    and os.path.getmtime(clip) >= os.path.getmtime(own)):
                # an AI clip made from this picture (rhyme/clips.py): the characters are in it and really move
                own, layers, sky = clip, False, []
            self.slots.append(dict(s, t0=t0, file=own, layers=layers, sky=sky))
        self.slots.sort(key=lambda s: s["t0"])
        for k, s in enumerate(self.slots):
            s["t1"] = self.slots[k + 1]["t0"] if k + 1 < len(self.slots) else plan["length"]
            s["move"] = MOVES[k % len(MOVES)]
            s["shot"] = (("orbit", "dolly_in", "truck_left")[k % 3] if s["role"] == "chorus"
                         else ("dolly_in", "truck_right", "crane_up", "truck_left", "dolly_out", "orbit")[k % 6])
            night = "night" in str(s.get("place", "")).lower()
            s["ambient"] = "confetti" if s["role"] == "chorus" else "fireflies" if night else "sparkles"
            first_of_part = k == 0 or self.slots[k - 1].get("scene") != s.get("scene")
            s["trans"] = "iris" if first_of_part else ("push", "zoom", "fade", "push_up")[k % 4]
            before = self.slots[k - 1] if k else None   # characters only pop in when the cast changes
            s["pop"] = not (before and before["layers"] and cast_kinds(before) == cast_kinds(s))
        self.line_starts = sorted(x["start"] for x in plan["lines"] if x.get("heard", True) or x["len"] >= 1.2)
        self.cache, self.clips, self.depth3d = {}, {}, {}
        self.cam = None
        try:
            import depth
            depth._model()
            self.depth_ok = True
        except Exception as e:  # noqa: BLE001
            print(f"  (no 3D camera: {e}; flat camera moves instead)")
            self.depth_ok = False
        self.effects = Effects()
        self.found = sum(1 for s in self.slots if s["file"])

    def __bool__(self):
        return self.found > 0

    def slot_at(self, t):
        k = 0
        for j, s in enumerate(self.slots):
            if s["t0"] <= t:
                k = j
        return k

    def still(self, s):
        if s["file"] not in self.cache:
            if len(self.cache) > 3:
                self.cache.pop(next(iter(self.cache)))
            img = Image.open(s["file"]).convert("RGB")
            self.cache[s["file"]] = cover(img, int(W * MARGIN), int(H * MARGIN))
        return self.cache[s["file"]]

    def parallax(self, s):
        """The picture with its depth map, for 3D camera moves (None: flat moves)."""
        if not self.depth_ok:
            return None
        if s["file"] not in self.depth3d:
            import depth
            if len(self.depth3d) > 3:
                self.depth3d.pop(next(iter(self.depth3d)))
            try:
                self.depth3d[s["file"]] = depth.Parallax(Image.open(s["file"]), depth.cached(s["file"]), (W, H))
            except Exception as e:  # noqa: BLE001
                print(f"  (no 3D camera for {os.path.basename(s['file'])}: {e})")
                self.depth3d[s["file"]] = None
        return self.depth3d[s["file"]]

    def view(self, s, t):
        """The picture of slot s at time t, with its camera move."""
        local = t - s["t0"]
        self.cam = None
        if s["file"].lower().endswith((".mp4", ".webm", ".mov")):
            if s["id"] not in self.clips:   # per slot: a reused clip starts again from its beginning
                ai = "/clips/" in s["file"].replace(os.sep, "/")
                # an AI clip plays once, forwards only (it looked repetitive going back and forth): a bit shorter
                # than its picture -> played up to 1.35x slower; still shorter -> a slow push-in on its last frame
                stretch = 1.0
                if ai:
                    need, have = s["t1"] - s["t0"] + FADE, clip_seconds(s["file"])
                    stretch = min(1.35, max(1.0, need / have)) if have else 1.0
                self.clips[s["id"]] = Clip(s["file"], self.fps, stretch=stretch)
            img, over = self.clips[s["id"]].at(local)
            if over > 0:   # the clip has ended: a slow push-in on its last frame until the next picture
                z = 1 + 0.02 * over
                cw, ch = W / z, H / z
                img = img.resize((W, H), Image.BILINEAR, box=((W - cw) / 2, (H - ch) / 2, (W + cw) / 2, (H + ch) / 2))
            return img.convert("RGBA")
        p = smooth(local / max(1.0, s["t1"] - s["t0"] + FADE))
        px = self.parallax(s)
        if px is not None:
            import depth
            sx, sy, push = depth.SHOTS[s.get("shot", "dolly_in")](p)
            sx += 0.06 * math.sin(t * 0.9)                # a little hand-held float
            sy += 0.05 * math.sin(t * 0.7 + 1)
            self.cam = px.shift_of(sx, sy, push, CHAR_DEPTH)
            return px.frame(sx, sy, push).convert("RGBA")
        big = self.still(s)
        bw, bh = big.size
        move = s["move"]
        zoom = {"in": 1 + 0.1 * p, "out": 1.1 - 0.1 * p, "in_up": 1 + 0.08 * p}.get(move, 1.04)
        cw, ch = W / zoom, H / zoom   # big is W*MARGIN x H*MARGIN: at zoom 1 the camera sees W x H of it
        free_x, free_y = bw - cw, bh - ch
        fx, fy = {"pan_right": (p, 0.5), "pan_left": (1 - p, 0.5), "pan_down": (0.5, p * 0.8),
                  "in_up": (0.5, 0.5 - 0.4 * p)}.get(move, (0.5, 0.5))
        x, y = free_x * fx, free_y * fy
        return big.resize((W, H), Image.BILINEAR, box=(x, y, x + cw, y + ch)).convert("RGBA")

    def compose(self, s, t):
        img = self.view(s, t)
        if s["layers"]:
            last = max((x for x in self.line_starts if x <= t + 0.05), default=None)
            place_cast(img, cast_kinds(s), t - s["t0"], (t / self.beat) % 1, lead_big=s["role"] == "title",
                       appear=None if s["pop"] else 99.0, cam=self.cam, accent=None if last is None else t - last,
                       dance=s["role"] == "chorus")
        elif s.get("sky"):   # a picture with the character drawn in it: the moon and stars still float above
            place_cast(img, s["sky"], t - s["t0"], (t / self.beat) % 1, cam=self.cam, corner=True)
        return img

    def frame(self, t):
        if not self.slots:
            return None
        k = self.slot_at(t)
        s = self.slots[k]
        if not s["file"]:
            return None
        img = self.compose(s, t)
        prev = self.slots[k - 1] if k > 0 else None
        into = t - s["t0"]
        if prev and prev["file"] and into < TRANS:
            img = self.transition(self.compose(prev, t), img, smooth(into / TRANS), s.get("trans", "fade"))
        strength = min(1.0, into / FADE) if k else 1.0
        img = self.effects.draw(img, s.get("ambient"), t, 0.7 * strength)
        img = self.effects.draw(img, s.get("effect"), t, strength)
        last = max((x for x in self.line_starts if x <= t + 0.05), default=None)
        if last is not None and s["role"] not in ("title", "end"):
            img = self.effects.burst(img, t - last)
        return img

    @staticmethod
    def transition(old, new, e, kind):
        """From the last picture to the new one: fade, iris (a growing circle), push (slides in), zoom."""
        if kind == "iris":
            r = e * math.hypot(W, H) / 2
            mask = Image.new("L", (W, H), 0)
            ImageDraw.Draw(mask).ellipse([W / 2 - r, H / 2 - r, W / 2 + r, H / 2 + r], fill=255)
            old = old.copy()
            old.paste(new, (0, 0), mask)
            return old
        if kind in ("push", "push_up"):
            out = Image.new("RGBA", (W, H))
            if kind == "push":
                out.paste(old, (int(-W * e), 0))
                out.paste(new, (int(W * (1 - e)), 0))
            else:
                out.paste(old, (0, int(-H * e)))
                out.paste(new, (0, int(H * (1 - e))))
            return out
        if kind == "zoom":
            z = 1 + 0.6 * e
            cw, ch = W / z, H / z
            old = old.resize((W, H), Image.BILINEAR, box=((W - cw) / 2, (H - ch) / 2, (W + cw) / 2, (H + ch) / 2))
        return Image.blend(old, new, e)

    def close(self):
        for c in self.clips.values():
            if c.proc:
                c.proc.kill()
