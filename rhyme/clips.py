"""
Real 3D cartoon motion: every picture of a song becomes a short moving clip (image-to-video), made on this laptop by
Wan 2.2 TI2V 5B (Apache-2.0) with the FastWan 3-step speed-up, run through WanGP (wan2gp/, its own venv-video).
The clip starts from exactly the frame the video would show (background + Golu and friends in place), so the
characters keep their settled look; the model only adds the movement. video.py uses images/clips/pNN.mp4 when it
is newer than the picture. Your own pNN.mp4 still wins.

    python rhyme.py clips <slug> [--redo p05,p09] [--only p05] [--fast]     # what you normally run

Steps (rhyme.py runs both):
    venv/bin/python rhyme/clips.py prepare <song folder>     # start frames + images/clips/jobs.json
    venv-video/bin/python rhyme/clips.py make <song folder>  # the clips (GPU; Ollama must be off)

About 6-12 minutes a clip on the RTX 3050 (6 GB): a song is an overnight job. Stop any time; a rerun skips
finished clips. --fast makes 832x480 clips (about 3x quicker, softer picture).
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
WAN = os.path.join(ROOT, "wan2gp")
MODEL = "ti2v_2_2_fastwan"
FPS = 24                       # Wan 2.2 5B makes 24 frames a second
MAX_FRAMES = 121               # 5 s: what the model was trained on; a longer picture holds the last frame
MIN_FRAMES = 49
SIZE = (1280, 704)             # the model's own size (16:9); --fast: 832x480
FAST = (832, 480)
NEGATIVE = ("extra person, new character appearing, other children, another child, crowd, group of kids, twins, "
            "ghost, transparent person, duplicate character, two heads, giant face close-up, "
            "blurry, distorted face, deformed hands, extra limbs, extra fingers, melting, morphing, flicker, text, "
            "letters, watermark, logo, frozen, still image, scary, dark, ugly, realistic photo")

# what the characters do in the clip, from the picture's action word (pictures.py writes "action" per line)
MOVES = {
    "sleep": "the child sleeps peacefully, breathing slowly, the blanket rising and falling gently",
    "lie": "the child lies down calmly, blinking slowly and smiling",
    "swing": "the swing moves back and forth smoothly, the children laugh and their hair flies in the breeze",
    "dance": "the children dance happily, swaying, clapping and hopping to the music",
    "wash": "the children wash their hands, water splashing softly, they rub their hands and smile",
    "bath": "the child splashes happily in the bath, bubbles floating up",
    "brush": "the child brushes the teeth up and down, smiling into the mirror",
    "eat": "the child eats happily, taking a bite and chewing with a big smile",
    "drink": "the child drinks from a glass and smiles",
    "sit": "the characters sit, look around and smile, swinging their feet",
    "read": "the child turns a page of the book and looks up surprised and happy",
    "ride": "the child rides along happily, the scenery moving past",
    "swim": "the character swims smoothly through the water, making little ripples",
    "climb": "the child climbs up step by step and waves at the top",
    "hug": "the characters hug each other warmly and smile",
    "cook": "the child stirs a little pot, steam rising gently",
    "paint": "the child paints with a brush, colours appearing on the paper",
    "kick": "the child kicks the ball, it rolls away and the child cheers",
    "throw": "the child throws the ball high and catches it",
    "fly a kite": "the kite flies high in the wind, the child pulls the string and laughs",
    "plant": "the child pats the soil around a small plant and smiles",
    "water": "the child waters the plant, water drops sparkling",
    "carry": "the character carries the load carefully, walking along",
    "arrive": "the moon rises slowly in the sky and glows brighter, the stars twinkle",
    "shine": "the moon glows softly and the stars twinkle and sparkle",
    "illuminate": "soft moonlight spreads across the scene, the stars twinkle",
    "sing": "the characters sing happily, mouths moving, swaying to the music",
    "play": "the children play happily, running and jumping",
    "run": "the character runs happily across the scene",
    "jump": "the character jumps up and down happily",
    "walk": "the characters walk along happily, looking around",
    "wave": "the characters wave at the viewer and smile",
    "fly": "the bird flies gracefully, flapping its wings",
    "laugh": "the characters laugh and bounce with joy",
}
DEFAULT_MOVE = "the characters smile, look around, wave and sway gently, hair and clothes moving in a soft breeze"
STYLE = ("3D animated cartoon for small children, high quality CGI animation, cute characters with big expressive "
         "eyes, smooth natural movement, soft cinematic lighting, vibrant colours")


def clip_dir(folder):
    return os.path.join(folder, "images", "clips")


def md5(path):
    return hashlib.md5(open(path, "rb").read()).hexdigest()


def move_for(slot):
    act = (slot.get("action") or "").lower().strip()
    for k, v in MOVES.items():
        if act == k or act.startswith(k):
            return v
    text = f"{slot.get('show', '')} {act}".lower()
    for k, v in MOVES.items():
        if k in text.split() or k + "s" in text.split() or k + "ing" in text.split():
            return v
    return DEFAULT_MOVE


# a different camera for every shot, like a real cartoon (the same chorus line gets a new one each time it comes back)
CAMERAS = ["Wide shot, the camera slowly moves in a little towards the characters",
           "The camera slowly circles around the characters",
           "Medium shot, the camera tracks sideways along with the action",
           "Low angle, the camera rises slowly to look down at the characters",
           "Medium shot that slowly pulls back to show the whole place",
           "The camera pans gently from left to right across the scene"]
LONG = MAX_FRAMES / FPS * 1.2   # a picture longer than this gets a second clip that carries on from the first


def story_move(slot, cast, ground):
    """What we see happen in this line (story.py: the meaning of the line, made visual), with our names swapped for
    what the video model knows ("Sheru" -> "the lion cub")."""
    doing = ((slot.get("story") or {}).get("doing") or "").strip().rstrip(".")
    if not doing:
        return ""
    chars = cast.get("characters", {})
    for k, c in chars.items():
        what = {"boy": "the boy", "girl": "the girl"}.get(k, f"the {k}")
        doing = re.sub(rf"\b{re.escape(c.get('name', k))}\b( the {k})?", what, doing)
    if not any(k in ("boy", "girl") for k in ground):    # nobody may walk in
        doing = re.sub(r"\b(children|kids?|people|friends|everyone|others|another \w+|crowd)\b", "", doing, flags=re.I)
    return re.sub(r"\s+", " ", doing).strip(" ,")


NUMBER = {1: "one", 2: "two", 3: "three", 4: "four"}
# MOVES are written for several characters; with one, the verbs take an s ("the child smiles")
VERB_ONE = {w: w + ("es" if w.endswith(("sh", "ch")) else "s") for w in (
    "smile", "look", "wave", "sway", "sing", "dance", "play", "laugh", "bounce", "sit", "walk", "hug", "wash", "rub",
    "clap", "hop", "jump", "run", "swing", "lie", "sleep", "eat", "drink")}
VERB_ONE["mouths"] = "mouth"


def describe(kind, cast):
    import pictures
    if kind in pictures.KID:
        return pictures.KID[kind]
    look = cast.get("characters", {}).get(kind, {}).get("look", kind)
    return ", ".join(look.split(", ")[:2])


def prompt_for(slot, shown, cast, shot=0):
    """The clip prompt says ONLY what is in the start frame: who (counted, described like the pictures) and where.
    The line's own description is left out: it often names people who aren't in the picture ("love for everyone",
    "the friends"), and the video model then adds them (tested: new children walked in)."""
    from critters import KINDS
    ground = [k for k in shown if not (k in KINDS and KINDS[k][4])]
    sky = [k for k in shown if k in KINDS and KINDS[k][4]]
    n = len(ground)
    kids = all(k in ("boy", "girl") for k in ground)
    where = (slot.get("setting") or "").strip().rstrip(".")
    if not where and "Scene:" in slot.get("prompt", ""):   # title and end pictures: where the picture prompt drew
        where = slot["prompt"].split("Place:", 1)[1].split(".")[0].strip() if "Place:" in slot["prompt"] else ""
    who = "; ".join(describe(k, cast) for k in ground)
    told = story_move(slot, cast, ground)
    move = told or move_for(slot)
    if n == 1 and not told:   # one character: say so everywhere, in the singular
        he = {"boy": ("he", "his"), "girl": ("she", "her")}.get(ground[0], ("it", "its"))
        for a, b in (("the children", "the child" if kids else "the character"), ("the characters", "the child"
                     if kids else "the character"), ("they ", he[0] + " "), ("their ", he[1] + " "),
                     ("each other", "the viewer")):
            move = move.replace(a, b)
        move = " ".join(VERB_ONE.get(w.rstrip(",."), w.rstrip(",.")) + w[len(w.rstrip(",.")):] for w in move.split(" "))
    count = NUMBER.get(n, str(n))
    alone = (f"Only {count} {'child' if kids else 'character'} in the whole video, alone, no other children or people"
             if n == 1 else f"Exactly {count} {'children' if kids else 'characters'} in the whole video, "
                            "no other children or people")
    camera = CAMERAS[shot % len(CAMERAS)]
    if told:   # the line's action, plus the small natural movement that makes a cartoon feel alive
        alive = ("hair and clothes moving naturally" if all(k in ("boy", "girl") for k in ground) else
                 "fur, ears and tail moving naturally" if not any(k in ("boy", "girl") for k in ground) else
                 "hair, clothes and fur moving naturally")
        move += (", " if move else "") + f"with lively, expressive cartoon acting, {alive}"
    names = {"moon": "crescent moon", "star": "little star", "sun": "sun"}
    sky_line = (" The smiling " + " and the ".join(names.get(k, k) for k in sky)
                + (" stay" if len(sky) > 1 else " stays") + " in the sky." if sky and slot.get("ai_layers") else "")
    # no light or time of day: the start picture decides it (some "night" lines are drawn in daylight)
    return (f"{STYLE}. {count.capitalize()} {'children' if kids and n > 1 else 'child' if kids else 'characters' if n > 1 else 'character'}: "
            f"{who}" + (f", in {where[:1].lower() + where[1:]}" if where else "") + f". {move.capitalize()}. {camera}."
            f"{sky_line} {alone}; the whole body always in view, never a big face close-up; same faces and clothes "
            "from start to end.")


# pictures with only the sky (moon, stars, sun): the world moves, nobody is added. A plain prompt made the model
# invent children (tested), so the prompt and the negative both say that nobody is there.
SKY_CLIPS = True
NO_PEOPLE = ("person, people, child, children, kid, boy, girl, baby, human, man, woman, face, hands, character "
             "walking in, animal, ")


def scenery_prompt(slot, sky):
    names = {"moon": "smiling crescent moon", "star": "little stars", "sun": "smiling sun", "cloud": "fluffy clouds"}
    things = " and the ".join(names.get(k, k) for k in sky) or "sky"
    one = len(sky) == 1 and sky[0] not in ("star", "cloud")
    where = (slot.get("setting") or "").strip().rstrip(".")
    return (f"{STYLE}. A peaceful scenery shot with nobody in it" + (f": {where[:1].lower() + where[1:]}" if where else "")
            + f". The {things} {'glows' if one else 'glow'} softly and {'twinkles' if one else 'twinkle'}, thin clouds "
            "drift slowly across the sky, leaves and grass sway gently in the breeze, tiny sparkles float in the air. "
            "The camera slowly pushes in. No people, no children, no animals in the whole video: only the sky and "
            "the scenery.")


def frames_for(seconds):
    n = int(round(seconds * FPS))
    n = max(MIN_FRAMES, min(MAX_FRAMES, n))
    return (n - 1) // 4 * 4 + 1          # the model needs 4k+1 frames


# ------------------------------------------------------------------ prepare (venv)
def prepare(folder, only=None, redo=()):
    sys.path.insert(0, HERE)
    import motion
    script = json.load(open(os.path.join(folder, "script.json"), encoding="utf-8"))
    timing = os.path.join(folder, "audio", "song_timing.json")
    if not os.path.exists(timing):
        timing = os.path.join(folder, "audio", "timing.json")
    if not os.path.exists(timing):
        raise SystemExit("  no song timing yet: run python rhyme.py song <slug> first (clips follow the song).")
    plan = json.load(open(timing, encoding="utf-8"))
    track = motion.PictureTrack(folder, script, plan, FPS, clips=False)
    out = clip_dir(folder)
    os.makedirs(out, exist_ok=True)
    old = {}
    path = os.path.join(out, "jobs.json")
    if os.path.exists(path):
        old = {j["id"]: j for j in json.load(open(path, encoding="utf-8"))["jobs"]}
    import pictures
    cast = pictures.load_cast()
    jobs, seen, skipped = [], set(), []
    for k, s in enumerate(track.slots):
        if not s["file"] or s["file"].lower().endswith((".mp4", ".webm", ".mov")) or s["id"] in seen:
            continue
        # a repeated chorus picture (same_as) starts from the same picture but gets its OWN clip: a new seed and a
        # new camera, so the chorus never plays the same animation twice
        if only and s["id"] not in only:
            continue
        seen.add(s["id"])
        still = motion.compose_still(folder, s, (1920, 1080))
        if still is None:
            continue
        start = os.path.join(out, f"{s['id']}_start.png")
        still.convert("RGB").save(start)
        seconds = s["t1"] - s["t0"] + motion.TRANS
        from critters import KINDS
        kinds = motion.cast_kinds(s)
        ground = [k for k in kinds if not (k in KINDS and KINDS[k][4])]   # not the moon, sun, stars (floats)
        if not ground and not SKY_CLIPS:
            skipped.append(s["id"])
            continue
        shown = kinds if s.get("ai_layers") else ground   # whole pictures: moon and stars are added later
        if s.get("same_as") and seconds < 2.0:   # a very short chorus repeat: it plays the first chorus's clip
            skipped.append(s["id"])
            continue
        before = old.get(s["id"], {})
        seed = before.get("seed", 1000 + k) + (7919 if s["id"] in redo else 0)   # a redo is a new try
        job = {"id": s["id"], "start": start, "start_md5": md5(start),
               "prompt": prompt_for(s, shown, cast, shot=k) if ground else scenery_prompt(s, kinds),
               "frames": frames_for(seconds), "seed": seed, "seconds": round(seconds, 2)}
        if seconds > LONG:   # a second clip carries on from the last frame of the first: no repeat, no reverse
            job["extend"] = frames_for(seconds - (job["frames"] - 1) / FPS)
        if not ground:
            job["negative"], job["scenery"] = NO_PEOPLE + NEGATIVE, True
        clip = os.path.join(out, f"{s['id']}.mp4")
        # a finished clip stays unless its picture changed or you asked for a redo (not when the prompt code changes)
        job["done"] = bool(os.path.exists(clip) and before.get("start_md5") == job["start_md5"]
                           and before.get("done") and s["id"] not in redo
                           and before.get("extend") == job.get("extend"))   # a long picture needs its second part
        if s["id"] in redo and os.path.exists(clip):
            os.remove(clip)
        jobs.append(job)
    keep = [j for i, j in old.items() if i not in seen and i not in skipped]   # --only: the other pictures' jobs stay as they were
    json.dump({"model": MODEL, "jobs": sorted(jobs + keep, key=lambda j: j["id"])},
              open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    todo = sum(not j["done"] for j in jobs)
    for pid in skipped:
        for f in (f"{pid}.mp4", f"{pid}_start.png"):
            if os.path.exists(os.path.join(out, f)):
                os.remove(os.path.join(out, f))
    print(f"  clips: {len(jobs)} pictures, {todo} to make"
          + (f" (short repeats, they reuse the first chorus clip: {', '.join(skipped)})" if skipped else ""))
    return todo


def review(folder):
    """images/clips/review.jpg: the first, middle and last frame of every clip, to spot a new face or a melted hand."""
    import subprocess
    from PIL import Image, ImageDraw
    out = clip_dir(folder)
    rows = []
    for name in sorted(f for f in os.listdir(out) if f.endswith(".mp4")):
        path = os.path.join(out, name)
        n = int(subprocess.run(["ffprobe", "-v", "error", "-count_packets", "-select_streams", "v", "-show_entries",
                                "stream=nb_read_packets", "-of", "csv=p=0", path], capture_output=True, text=True)
                .stdout.strip() or 0)
        if n < 3:
            continue
        tmp = os.path.join(out, "_sheet.jpg")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", path, "-vf",
                        f"select='eq(n\\,0)+eq(n\\,{n // 2})+eq(n\\,{n - 1})',scale=480:-1,tile=3x1",
                        "-frames:v", "1", tmp], check=False)
        if os.path.exists(tmp):
            row = Image.open(tmp).convert("RGB")
            ImageDraw.Draw(row).text((8, 6), name[:-4], fill=(255, 255, 0), font_size=28, stroke_width=3,
                                     stroke_fill=(0, 0, 0))
            rows.append(row)
            os.remove(tmp)
    if not rows:
        return None
    sheet = Image.new("RGB", (rows[0].width, sum(r.height for r in rows)))
    y = 0
    for r in rows:
        sheet.paste(r, (0, y))
        y += r.height
    path = os.path.join(out, "review.jpg")
    sheet.save(path, quality=85)
    return path


# ------------------------------------------------------------------ make (venv-video, GPU)
def free_ram_gb():
    for line in open("/proc/meminfo"):
        if line.startswith("MemAvailable:"):
            return int(line.split()[1]) / 1024 / 1024
    return 99.0


NEED_RAM = 8.5     # GB free for profile 4 (the model is pinned in RAM); less -> profile 5 (slower, less RAM)
# WanGP locks ("pins") 60% of RAM by default on Linux: ~9 GB that can't go to swap. With VS Code open that froze the
# laptop for 35 minutes (18 Nov). The transformer + LoRA need ~5.5 GB pinned; the rest streams from normal RAM.
PIN_SHARE = {"4": "0.38", "5": "0.2"}
LOW_RAM_STOP = 0.5  # GB available: below this the clip maker stops itself
THRASH_STOP = 30.0  # % of time everything waits for memory (Linux "full" memory pressure, avg10): the laptop hangs


def thrashing():
    try:
        for line in open("/proc/pressure/memory"):
            if line.startswith("full"):
                return float(line.split("avg10=")[1].split()[0])
    except OSError:
        pass
    return 0.0


def ram_watchdog(log_path):
    """Stops this process before the laptop runs out of memory and hangs (18 Nov: 35 minutes frozen, then a
    restart). It watches Linux's memory pressure: when programs spend a third of their time waiting for memory,
    or RAM is nearly gone, for 5 s, the clip maker stops cleanly. Finished clips are kept."""
    import threading

    def watch():
        bad = 0
        while True:
            time.sleep(1)
            ram, stall = free_ram_gb(), thrashing()
            bad = bad + 1 if (ram < LOW_RAM_STOP or stall > THRASH_STOP) else 0
            if bad >= 5:
                msg = (f"stopped to keep the laptop from hanging: {ram:.1f} GB RAM free, waiting for memory "
                       f"{stall:.0f}% of the time. Close the browser and other big programs, then run the same "
                       "command again; finished clips are kept.")
                print(f"\n  clips {msg}", flush=True)
                try:
                    open(log_path, "a", encoding="utf-8").write(msg + "\n")
                finally:
                    os._exit(3)
    threading.Thread(target=watch, daemon=True).start()


def make(folder, fast=False, only=None, low_ram=False):
    """Makes every clip still to do. Exit code 1 if any is still missing at the end, so `make` never quietly
    turns into a 2D video (rhyme.py then tries once more in a fresh process with --low-ram)."""
    out = clip_dir(folder)
    path = os.path.join(out, "jobs.json")
    data = json.load(open(path, encoding="utf-8"))

    def todo():
        return [j for j in data["jobs"] if not j["done"] and (not only or j["id"] in only)]
    if not todo():
        print("  clips: all made")
        return 0
    import torch
    if not torch.cuda.is_available():
        if "CUDA_VISIBLE_DEVICES" in os.environ:
            print(f"  clips: the GPU is hidden (CUDA_VISIBLE_DEVICES={os.environ['CUDA_VISIBLE_DEVICES']!r}): "
                  "run without it.")
            return 1
        print("  clips: the GPU is not reachable (CUDA). After a suspend run:\n"
              "    sudo rmmod nvidia_uvm && sudo modprobe nvidia_uvm\n  then run the same command again.")
        return 1
    ram = free_ram_gb()
    profile = "5" if low_ram or ram < NEED_RAM else "4"
    if profile == "5":
        print(f"  clips: {ram:.1f} GB RAM free: low-RAM mode (slower). Close the browser and other big programs "
              "for faster clips.", flush=True)
    os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
    ram_watchdog(os.path.join(out, "make.log"))
    sys.path.insert(0, WAN)
    cwd = os.getcwd()
    os.chdir(WAN)                        # WanGP finds its models, settings and ckpts from its own folder
    from pathlib import Path
    from shared.api import init
    tmp = os.path.join(out, "_wan")
    w, h = FAST if fast else SIZE
    log = open(os.path.join(out, "make.log"), "a", encoding="utf-8")
    log.write(f"\n=== {time.strftime('%Y-%m-%d %H:%M')} {len(todo())} to make, {ram:.1f} GB RAM free, "
              f"profile {profile}\n")
    session = None
    try:
        session = init(root=Path(WAN), output_dir=tmp, console_output=True,
                       cli_args=["--attention", "sdpa", "--profile", profile,
                                 "--perc-reserved-mem-max", PIN_SHARE[profile]])
        jobs = todo()
        def generate(prompt, start, frames, seed):
            """One clip from the model: (file, error)."""
            settings = {"model_type": MODEL, "prompt": prompt, "negative_prompt": job.get("negative", NEGATIVE),
                        "image_prompt_type": "S", "image_start": start, "resolution": f"{w}x{h}",
                        "video_length": frames, "seed": seed}
            shutil.rmtree(tmp, ignore_errors=True)
            try:
                res = session.submit_task(settings).result()
                files = [f for f in (res.generated_files or []) if str(f).lower().endswith(".mp4")]
                if res.success and files:
                    return str(files[0]), ""
                return None, "; ".join(str(e.message) for e in res.errors) if res.errors else "no video made"
            except Exception as e:          # one bad clip must not stop the others
                return None, f"{type(e).__name__}: {e}"

        for n, job in enumerate(jobs, 1):
            t0 = time.time()
            print(f"  clip {job['id']} ({n}/{len(jobs)}, {job['frames']} frames {w}x{h}"
                  + (f" + {job['extend']} more" if job.get("extend") else "") + ") ...", flush=True)
            first, msg = generate(job["prompt"], job["start"], job["frames"], job["seed"])
            if msg:
                print(f"    failed: {msg}", flush=True)
                log.write(f"{job['id']} failed ({free_ram_gb():.1f} GB RAM free): {msg}\n")
                log.flush()
                continue
            final = os.path.join(out, f"{job['id']}.mp4")
            part_a = os.path.join(out, f"{job['id']}_a.mp4")
            shutil.move(first, part_a)
            if job.get("extend"):   # the second part starts exactly where the first one ended
                last = os.path.join(out, f"{job['id']}_last.png")
                subprocess.run(["ffmpeg", "-v", "error", "-y", "-sseof", "-0.1", "-i", part_a, "-frames:v", "1",
                                "-update", "1", last], check=False)
                cont = job["prompt"]
                for cam in CAMERAS:   # the first part's camera kept pushing in: part 2 pulls back to a wide shot
                    cont = cont.replace(cam, "The camera slowly pulls back to a wide shot showing the whole body")
                second, msg2 = generate(cont + " The action carries on smoothly from this moment.", last,
                                        job["extend"], job["seed"] + 1) if os.path.exists(last) else (None, "no last frame")
                if second:
                    part_b = os.path.join(out, f"{job['id']}_b.mp4")
                    shutil.move(second, part_b)
                    joined = subprocess.run(
                        ["ffmpeg", "-v", "error", "-y", "-i", part_a, "-i", part_b, "-filter_complex",
                         "[1:v]trim=start_frame=1,setpts=PTS-STARTPTS[b];[0:v][b]concat=n=2:v=1[v]", "-map", "[v]",
                         "-an", "-c:v", "libx264", "-preset", "medium", "-crf", "16", "-pix_fmt", "yuv420p", final])
                    if joined.returncode == 0:
                        os.remove(part_a)
                        os.remove(part_b)
                else:
                    log.write(f"{job['id']} second part failed: {msg2} (the first part is used)\n")
                if os.path.exists(last):
                    os.remove(last)
            if os.path.exists(part_a):
                os.replace(part_a, final)
            job["done"], job["size"] = True, f"{w}x{h}"
            json.dump(data, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            log.write(f"{job['id']} done in {(time.time() - t0) / 60:.1f} min\n")
            log.flush()
            print(f"    done in {(time.time() - t0) / 60:.1f} min", flush=True)
    except Exception as e:
        log.write(f"the video model did not start: {type(e).__name__}: {e}\n")
        print(f"  clips: the video model did not start: {type(e).__name__}: {e}")
    finally:
        if session is not None:
            session.close()
        shutil.rmtree(tmp, ignore_errors=True)
        os.chdir(cwd)
        left = [j["id"] for j in todo()]
        log.write(f"missing: {', '.join(left) or 'none'}\n")
        log.close()
    if left:
        print(f"  clips still missing: {', '.join(left)} (reasons in images/clips/make.log)")
        return 1
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 3 or sys.argv[1] not in ("prepare", "make", "review"):
        raise SystemExit(__doc__)
    folder = os.path.abspath(sys.argv[2])
    args = sys.argv[3:]

    def listed(name):
        return set(args[args.index(name) + 1].split(",")) if name in args and args.index(name) + 1 < len(args) else set()
    if sys.argv[1] == "review":
        print(review(folder))
    elif sys.argv[1] == "prepare":
        prepare(folder, listed("--only"), listed("--redo"))
    else:
        sys.exit(make(folder, "--fast" in args, listed("--only"), "--low-ram" in args))
