"""
Rhymes: original Hindi nursery rhymes as bright cartoon music videos, for a kids' YouTube channel. Separate from
Snack Code and from the story serial.

    python rhyme.py ideas ["animals"]          # rhyme ideas -> rhyme/ideas.txt
    python rhyme.py new "Medhak Ki Chhalang"   # a new original rhyme: lyrics.txt + review.md  (--about "...",
                                               # --pick N from ideas.txt, --lyrics my.txt for your own words, --tempo 100)
    python rhyme.py story <slug>               # what the rhyme means, line by line -> story.md (two agents:
                                               # explainer + checker; make/new/pictures run it; --redo asks again)
    python rhyme.py pictures <slug>            # plan the pictures (pictures.md) and draw them with the local image
                                               # model -> images/p01.png ... (--redo-picture p03 / all, --no-draw,
                                               # --redo-character elephant: a new look for the whole channel)
    python rhyme.py make <slug>                # pictures + voice + video + YouTube kit (after editing lyrics.txt;
                                               # --drawn: no pictures, code-drawn cartoons)
    python rhyme.py make <slug> --preview      # only the first 30 seconds of video
    python rhyme.py song <slug>                # a new take of the AI-sung song (ACE-Step: real singing + music),
                                               # --seed N to remake one you liked, --style "soft piano lullaby ..."
    python rhyme.py clips <slug>               # real 3D cartoon motion: every picture -> an AI clip (Wan 2.2 5B,
                                               # ~6-12 min each; --redo-clip p05,p09, --only-clip p05, --fast)
                                               # make does this too (--no-clips: skip; render --no-clips: ignore them);
                                               # make stops before the video if clips are missing (--allow-2d: render anyway)
    python rhyme.py sync|voice|guide|render|kit <slug>      # one step (render --preview / --drawn / --chant, voice --redo / --cpu)
    python rhyme.py upload <slug> [<slug> ...] --channel @YourKidsChannel [--start "2026-11-20 17:00" --every 2]
    python rhyme.py list                       # every rhyme and how far it has got
    python rhyme.py cast                       # rhymes/cast.png: every cartoon character

Folders: rhyme/ (the code), rhymes/settings.json (channel, singer voice), rhymes/voices/ (singer.wav),
rhymes/cast.json (the recurring characters' looks for picture prompts),
rhymes/songs/<slug>/ lyrics.txt (the words, edit here), script.json, review.md, pictures.md, images/, audio/,
output/rhyme.mp4, youtube/.
"""
import datetime
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
CODE = os.path.join(ROOT, "rhyme")
DATA = os.path.join(ROOT, "rhymes")
SONGS = os.path.join(DATA, "songs")
IDEAS = os.path.join(CODE, "ideas.txt")
SETTINGS = os.path.join(DATA, "settings.json")
sys.path.insert(0, CODE)
sys.path.insert(0, ROOT)
VALUE_FLAGS = {"--seed", "--style", "--takes", "--about", "--pick", "--lyrics", "--tempo", "--channel", "--start", "--every", "--thumbnail", "--title",
               "--redo-picture", "--redo-character", "--redo-clip", "--only-clip"}


def flag(name, default=None):
    if name in sys.argv:
        k = sys.argv.index(name)
        if k + 1 < len(sys.argv) and not sys.argv[k + 1].startswith("--"):
            return sys.argv[k + 1]
        return True
    return default


def plain_args():
    out, skip = [], False
    for a in sys.argv[2:]:
        if skip:
            skip = False
        elif a in VALUE_FLAGS:
            skip = True
        elif not a.startswith("--"):
            out.append(a)
    return out


def settings():
    data = {"channel": "", "singer_voice": "female_young", "playlist": "Hindi Rhymes", "original": True,
            "lyrics_model": "gemma3:4b", "ai_pictures": True,
            "singing": "ai_song",   # ai_song: see below
            "ai_clips": True}       # every picture -> an AI-animated clip (rhyme/clips.py), when wan2gp is set up
    # ai_song: ACE-Step sings with its own music; "voice": Chatterbox + sing.py
    if os.path.exists(SETTINGS):
        data.update(json.load(open(SETTINGS, encoding="utf-8")))
    return data


def save_settings(data):
    os.makedirs(DATA, exist_ok=True)
    json.dump(data, open(SETTINGS, "w", encoding="utf-8"), ensure_ascii=False, indent=2)


def slugify(title):
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:50] or "rhyme"


def folder_of(slug):
    path = os.path.join(SONGS, slug)
    if not os.path.exists(os.path.join(path, "lyrics.txt")):
        raise SystemExit(f"No rhyme '{slug}'. See: python rhyme.py list")
    return path


def run(cmd, label, cwd=ROOT):
    print(f"\n== {label}", flush=True)
    if subprocess.run(cmd, cwd=cwd).returncode != 0:
        raise SystemExit(f"{label} failed.")


# ------------------------------------------------------------------ steps
def sync(folder, quiet=False):
    """lyrics.txt -> script.json (pictures planned, Roman captions) and review.md."""
    import lyrics
    from hinglish import to_roman
    import story as storymod
    raw = lyrics.read(os.path.join(folder, "lyrics.txt"))
    song = lyrics.plan(raw, storymod.load(folder, raw))   # who/where per line from story.json (if it's up to date)
    if not song["sections"]:
        raise SystemExit("lyrics.txt has no lines.")
    path = os.path.join(folder, "script.json")
    known = {}
    if os.path.exists(path):
        for s in json.load(open(path, encoding="utf-8"))["scenes"]:
            for b in s["beats"]:
                known[b["say_hi"]] = b["say"]
    script = lyrics.to_script(song, lambda hi: known.get(hi) or to_roman(hi))
    json.dump(script, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    problems, _ = lyrics.check(song["sections"])
    rows = [f"# Review: {song['title']}", "",
            "Read the words out loud. Edit lyrics.txt, then run the next step again (it re-reads lyrics.txt).", ""]
    st = storymod.load(folder, raw)
    if st:
        problems = problems + [f"line {x['n']} doesn't make sense ({x['problem'] or 'story checker'}): {x['hi']}"
                               for x in storymod.unclear(st)]
    if problems:
        rows += ["## Look at these", *[f"- [ ] {p}" for p in problems], ""]
    if st:
        rows += ["## What the rhyme means (story.md has every line)", "", st["summary"], ""]
    rows += ["## Pictures (change with [verse place=... cast=...] in lyrics.txt)"]
    for k, s in enumerate(song["sections"], 1):
        rows.append(f"- {k}. {s['kind']}: {s['place']}, {', '.join(s['cast'])}")
    rows += ["", "## Words on screen (Roman)", ""]
    for k, s in enumerate(script["scenes"], 1):
        rows += [f"**{k}. {s['kind']}**", *[f"- {b['say_hi']}  ->  {b['say']}" for b in s["beats"]], ""]
    rows += ["## Before voicing", "- [ ] Every line is simple, kind and right for children aged 2-6",
             "- [ ] The words are new (not copied from a film song or another published rhyme)",
             "- [ ] Roman spelling on screen is right (fix with ' | Roman' after a line in lyrics.txt)",
             "", "Tick the boxes ([x]) when done: kit's upload.md reminds you of any left."]
    open(os.path.join(folder, "review.md"), "w", encoding="utf-8").write("\n".join(rows) + "\n")
    if not quiet:
        print(f"  {sum(len(s['beats']) for s in script['scenes'])} lines in {len(script['scenes'])} parts; "
              f"{len(problems)} thing(s) to look at in review.md")
    return problems


def voice(folder):
    if os.path.exists(os.path.join(folder, "audio", "vocals.wav")):
        print("  audio/vocals.wav (your singing) is there: no AI voice needed.")
        return
    cfg = settings()
    json.dump({"characters": {"singer": {"name": "Singer", "voice": cfg.get("singer_voice", "female_young")}}, "places": {}},
              open(os.path.join(DATA, "bible.json"), "w", encoding="utf-8"), indent=1)
    python = os.path.join(ROOT, "venv-voice", "bin", "python")
    extra = [a for a in ("--redo", "--no-check", "--cpu") if a in sys.argv]
    run([python, os.path.join(ROOT, "serial", "voice_run.py"), folder, *extra], "Voice")


def ai_song_ready():
    return os.path.isdir(os.path.join(ROOT, "ace-step", "checkpoints", "acestep-v15-turbo"))


def pick_take(folder):
    """Keep the take whose singing follows the lyrics best (every line sung, words clear) as audio/song.wav."""
    import align
    import shutil
    takes_dir = os.path.join(folder, "audio", "takes")
    info = json.load(open(os.path.join(takes_dir, "takes.json"), encoding="utf-8"))
    print(f"  listening to {len(info['takes'])} take(s) to keep the one that sings every line (Whisper)...", flush=True)
    best = None
    for tk in info["takes"]:
        heard, quality, total = align.score(folder, os.path.join(takes_dir, tk["file"]))
        tk.update(heard=heard, quality=round(quality, 3))
        print(f"    {tk['file']}: {heard} of {total} lines heard, words {quality:.0%} clear")
        if best is None or (heard, quality) > (best["heard"], best["quality"]):
            best = tk
    shutil.copy(os.path.join(takes_dir, best["file"]), os.path.join(folder, "audio", "song.wav"))
    keep = {k: v for k, v in info.items() if k != "takes"}
    json.dump(dict(keep, seed=best["seed"], take=best["file"], takes=info["takes"]),
              open(os.path.join(folder, "audio", "song.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"  kept {best['file']} (seed {best['seed']}); the others stay in audio/takes/")


def song(folder, new_take=False):
    """The AI-sung song (rhyme/song_ai.py in venv-voice) and when each line is sung in it (rhyme/align.py)."""
    import align
    sys.path.insert(0, CODE)
    from song_ai import lyrics_text
    wav, info = os.path.join(folder, "audio", "song.wav"), os.path.join(folder, "audio", "song.json")
    script = json.load(open(os.path.join(folder, "script.json"), encoding="utf-8"))
    old = json.load(open(info, encoding="utf-8")) if os.path.exists(info) else {}
    stale = old and old.get("lyrics") != lyrics_text(script, old.get("roman", False))
    if os.path.exists(wav) and not new_take and not stale:
        print("\n== Song\n  audio/song.wav is there (python rhyme.py song <slug> makes a new take)")
    else:
        if stale:
            print("\n  the lyrics changed since the song was made: singing it again")
        if os.path.exists(wav):
            os.replace(wav, os.path.join(folder, "audio", "song_previous.wav"))
        cmd = [os.path.join(ROOT, "venv-voice", "bin", "python"), os.path.join(CODE, "song_ai.py"), folder]
        for name in ("--seed", "--style", "--takes"):
            if isinstance(flag(name), str):
                cmd += [name, flag(name)]
        if "--roman" in sys.argv:
            cmd.append("--roman")
        run(cmd, "Song")
        pick_take(folder)
    if not align.fresh(folder):
        print("  finding when each line is sung (Whisper, about 1.5 min the first time)...", flush=True)
        align.run(folder)


def story(folder, show=True):
    """What the rhyme means, line by line (rhyme/story.py: explainer + checker agents) -> story.md / story.json.
    Then script.json is synced again, so every picture gets the right characters."""
    import lyrics
    import story as storymod
    song_ = lyrics.read(os.path.join(folder, "lyrics.txt"))
    fresh = storymod.load(folder, song_) is None
    if fresh:
        print("\n== Story (what the rhyme means, line by line)", flush=True)
    st = storymod.understand(folder, song_)
    if fresh or show:
        storymod.print_summary(st)
        print(f"  read it: {os.path.relpath(folder, ROOT)}/story.md")
    sync(folder, quiet=True)
    return st


def pictures(folder, ask_model=True):
    import pictures as pics
    pics.build(folder, ask_model=ask_model)


def draw(folder):
    """The missing pictures, made by the local image model (rhyme/draw_ai.py, venv-voice)."""
    if not settings().get("ai_pictures", True) or "--no-draw" in sys.argv:
        return
    python = os.path.join(ROOT, "venv-voice", "bin", "python")
    cmd = [python, os.path.join(CODE, "draw_ai.py"), folder]
    if isinstance(flag("--redo-picture"), str):
        cmd += ["--redo", flag("--redo-picture")]
    if isinstance(flag("--redo-character"), str):
        cmd += ["--redo-character", flag("--redo-character")]
    print("\n== Pictures", flush=True)
    if subprocess.run(cmd, cwd=ROOT).returncode != 0:
        print("  (pictures not made: the video uses the drawn cartoons where they're missing)")
    import motion
    sheet = motion.review_sheet(folder)   # also cuts out new characters (rhymes/cast_art/<kind>_cut.png)
    if sheet:
        print(f"  all pictures on one sheet: {os.path.relpath(sheet, ROOT)}")


def refresh_pictures(folder):
    """Lyrics may have changed since `pictures`: re-plan (no model) so the right picture goes with each line."""
    if os.path.exists(os.path.join(folder, "pictures.json")):
        pictures(folder, ask_model=False)


def clips_ready():
    return (os.path.exists(os.path.join(ROOT, "venv-video", "bin", "python"))
            and os.path.exists(os.path.join(ROOT, "wan2gp", "wgp.py")))


def gpu_check():
    """The clip maker needs the GPU: checked at the START of make, not after an hour of song and pictures."""
    env = {k: v for k, v in os.environ.items() if k != "CUDA_VISIBLE_DEVICES"}
    r = subprocess.run([os.path.join(ROOT, "venv-video", "bin", "python"), "-c",
                        "import torch; torch.zeros(1).cuda(); print('ok')"], capture_output=True, text=True, env=env)
    if "ok" not in r.stdout:
        raise SystemExit("The GPU is not reachable (CUDA), so no 3D clips can be made. After a suspend run:\n"
                         "  sudo rmmod nvidia_uvm && sudo modprobe nvidia_uvm\n(or restart the laptop), then run make again.")


def memory_capped(cmd):
    """Runs the clip maker in a memory box: if it needs more than the laptop can spare, Linux stops only the clip
    maker instead of freezing the whole desktop (it froze for 35 minutes once, 18 Nov). Swap is kept small too:
    swapping is what makes everything hang."""
    import shutil
    if not shutil.which("systemd-run"):
        return cmd
    total = int(next(l for l in open("/proc/meminfo") if l.startswith("MemTotal:")).split()[1]) // 1024   # MB
    cap = max(6000, total - 3500)          # 16 GB laptop: ~12 GB for clips, 3.5 GB for the desktop
    probe = subprocess.run(["systemd-run", "--user", "--scope", "--quiet", "-p", "MemoryMax=100M", "true"],
                           capture_output=True)
    if probe.returncode != 0:
        return cmd
    return ["systemd-run", "--user", "--scope", "--quiet", "-p", f"MemoryMax={cap}M", "-p", "MemorySwapMax=1G", *cmd]


def clips(folder):
    """Real 3D cartoon motion: every picture -> a short AI clip (rhyme/clips.py, Wan 2.2 5B in venv-video).
    Returns True when every clip is there. A failed run is tried once more in low-RAM mode."""
    if not clips_ready():
        print("  (no AI clips: wan2gp/ or venv-video/ is missing, see rhyme/README.md)")
        return False
    extra = []
    for name, to in (("--redo-clip", "--redo"), ("--only-clip", "--only")):
        if isinstance(flag(name), str):
            extra += [to, flag(name)]
    run([sys.executable, os.path.join(CODE, "clips.py"), "prepare", folder, *extra], "Clips: start frames")
    import song_ai
    song_ai.unload_ollama()               # the video model needs all of the GPU
    cmd = [os.path.join(ROOT, "venv-video", "bin", "python"), os.path.join(CODE, "clips.py"), "make", folder]
    cmd += ["--fast"] if "--fast" in sys.argv else []
    cmd += ["--only", flag("--only-clip")] if isinstance(flag("--only-clip"), str) else []
    print("\n== Clips (AI animation: about 7 minutes each, a rerun skips finished clips)", flush=True)
    env = {k: v for k, v in os.environ.items() if k != "CUDA_VISIBLE_DEVICES"}   # the clip maker needs the GPU
    def go(c):
        rc = subprocess.run(memory_capped(c), cwd=ROOT, env=env).returncode
        if rc in (137, -9):
            print("  clips: the clip maker needed more memory than the laptop could spare and was stopped "
                  "(the laptop itself stays usable)", flush=True)
        elif rc == 3:
            print("  clips: stopped early because memory ran low (see above)", flush=True)
        return rc == 0
    ok = go(cmd)
    if not ok:
        print("\n== Clips: second try for the missing ones (low-RAM mode)", flush=True)
        song_ai.unload_ollama()
        ok = go(cmd + ["--low-ram"])
    import clips as clipmod
    sheet = clipmod.review(folder)
    if sheet:
        print(f"  check every clip: {os.path.relpath(sheet, ROOT)} (start, middle, end); a bad one: "
              f"python rhyme.py clips {os.path.basename(folder)} --redo-clip pNN")
    return ok


def render(folder, guide=False):
    extra = [a for a in ("--preview", "--no-music", "--drawn", "--chant", "--no-clips") if a in sys.argv] + (["--guide"] if guide else [])
    run([sys.executable, os.path.join(CODE, "video.py"), folder, *extra], "Guide track" if guide else "Video")


def kit(folder):
    import rkit
    rkit.build(folder, settings(), redo="--redo" in sys.argv)


def upload(folders):
    cfg = settings()
    channel = flag("--channel") if isinstance(flag("--channel"), str) else cfg.get("channel")
    if not channel:
        raise SystemExit("Which channel? Add --channel @YourKidsChannel (it's remembered in rhymes/settings.json).")
    if channel != cfg.get("channel"):
        cfg["channel"] = channel
        save_settings(cfg)
    start = flag("--start")
    when = datetime.datetime.strptime(start, "%Y-%m-%d %H:%M") if isinstance(start, str) else None
    every = float(flag("--every", 1))
    for k, folder in enumerate(folders):
        cmd = [sys.executable, os.path.join(ROOT, "upload.py"), "--channel", channel, "--video", "output/rhyme.mp4",
               "--subtitles", "output/rhyme.srt", "--category", "education", "--kids", "--playlist", cfg["playlist"]]
        if when:
            cmd += ["--schedule", (when + datetime.timedelta(days=every * k)).strftime("%Y-%m-%d %H:%M")]
        for name in ("--thumbnail", "--title"):
            if isinstance(flag(name), str):
                cmd += [name, flag(name)]
        cmd += [a for a in ("--dry-run", "--publish") if a in sys.argv]
        run(cmd, f"Upload {os.path.basename(folder)}", cwd=folder)


# ------------------------------------------------------------------ ideas and new rhymes
def read_ideas():
    if not os.path.exists(IDEAS):
        return []
    rows = []
    for line in open(IDEAS, encoding="utf-8"):
        if line.strip() and not line.startswith("#"):
            parts = [p.strip() for p in line.split("|")]
            rows.append((parts[0], parts[1] if len(parts) > 1 else ""))
    return rows


def ideas(theme):
    from auto_video import MODEL, llm
    have = {t.lower() for t, _ in read_ideas()}
    answer = llm("Suggest ideas for NEW, original Hindi nursery rhymes for children aged 2-6 (not existing rhymes or film "
                 "songs). Each: a short catchy title in Roman Hindi (like 'Medhak Ki Chhalang') and one line in English "
                 "on what it is about (an animal, counting, colours, a good habit, nature, a vehicle). Use these animals "
                 "and things where you can: fish, elephant, cat, dog, rabbit, frog, duck, cow, lion, monkey, butterfly, "
                 "sun, moon, stars, peacock, parrot, train, boy, girl. "
                 'JSON: {"ideas": [{"title": "...", "about": "..."}]} with 10 ideas.',
                 f"Theme: {theme or 'anything children love'}\nAlready have: {', '.join(sorted(have))[:1500]}",
                 model=MODEL, max_tokens=1500, temperature=0.8)
    new = []
    for x in (answer or {}).get("ideas", []):
        if not isinstance(x, dict):
            continue
        title, about = str(x.get("title", "")).strip(), str(x.get("about", "")).strip()
        if title and title.lower() not in have and not re.search(r"[ऀ-ॿ]", title):
            have.add(title.lower())
            new.append(f"{title} | {about}")
    if new:
        with open(IDEAS, "a", encoding="utf-8") as f:
            f.write("\n".join(new) + "\n")
    return new


def new(title, about):
    import lyrics
    slug = slugify(title)
    folder = os.path.join(SONGS, slug)
    if os.path.exists(os.path.join(folder, "lyrics.txt")) and "--force" not in sys.argv:
        raise SystemExit(f"rhymes/songs/{slug}/lyrics.txt already exists. Edit it, or add --force to write it again.")
    os.makedirs(folder, exist_ok=True)
    own = flag("--lyrics")
    if isinstance(own, str):
        sections, note = lyrics.from_text(own), f"Words from {os.path.basename(own)}: make sure you may use them."
    else:
        print(f"Writing a new rhyme: {title}")
        model = settings().get("lyrics_model") or "gemma3:4b"
        sections, note = lyrics.write_new(title, about, model=model), f"Written by {model}: read and improve it."
        subprocess.run(["ollama", "stop", model], capture_output=True)
    tempo = int(flag("--tempo")) if isinstance(flag("--tempo"), str) and flag("--tempo").isdigit() else 100
    path = os.path.join(folder, "lyrics.txt")
    lyrics.write_file(path, {"title": title, "about": about, "tempo": tempo, "key": "C", "sections": sections}, note)
    sync(folder, quiet=True)
    import story as storymod
    st = story(folder, show=False)
    if not isinstance(own, str) and storymod.unclear(st):   # the model's own draft: fix lines that make no sense once
        print(f"  {len(storymod.unclear(st))} line(s) make no sense: writing them again ...", flush=True)
        song_ = lyrics.read(path)
        if lyrics.mend_unclear(song_, st, model=settings().get("lyrics_model") or "gemma3:4b"):
            subprocess.run(["ollama", "stop", settings().get("lyrics_model") or "gemma3:4b"], capture_output=True)
            lyrics.write_file(path, song_, note)
            st = story(folder, show=False)
    storymod.print_summary(st)
    sync(folder)
    print(f"\nNext: read rhymes/songs/{slug}/story.md (what it means), lyrics.txt and review.md, edit, then: "
          f"python rhyme.py make {slug}")
    return slug


# ------------------------------------------------------------------ main
def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help", "help"):
        print(__doc__)
        return
    cmd, rest = sys.argv[1], plain_args()
    os.makedirs(SONGS, exist_ok=True)
    if cmd == "ideas":
        added = ideas(" ".join(rest))
        print(f"{len(added)} new idea(s) added to rhyme/ideas.txt:")
        for k, (t, a) in enumerate(read_ideas(), 1):
            print(f"  {k:2d}. {t}  -  {a[:70]}")
        print('\nStart one: python rhyme.py new --pick N   or   python rhyme.py new "Title" --about "..."')
        return
    if cmd == "new":
        title, about = (rest[0] if rest else None), flag("--about", "")
        if isinstance(flag("--pick"), str):
            rows = read_ideas()
            k = int(flag("--pick")) - 1
            if not 0 <= k < len(rows):
                raise SystemExit("No such number in rhyme/ideas.txt. See: python rhyme.py ideas")
            title, about = rows[k][0], about if isinstance(about, str) and about else rows[k][1]
        if not title:
            raise SystemExit('Give a title: python rhyme.py new "Medhak Ki Chhalang"')
        new(title, about if isinstance(about, str) else "")
        return
    if cmd == "list":
        for slug in sorted(os.listdir(SONGS)):
            f = os.path.join(SONGS, slug)
            state = ("uploaded" if os.path.exists(os.path.join(f, "youtube", "uploaded.json")) else
                     "kit ready" if os.path.exists(os.path.join(f, "youtube", "upload.md")) else
                     "rendered" if os.path.exists(os.path.join(f, "output", "rhyme.mp4")) else
                     "voiced" if os.path.exists(os.path.join(f, "audio", "lines.json")) else "lyrics")
            print(f"  {slug:40s} {state}")
        return
    if cmd == "cast":
        out = os.path.join(DATA, "cast.png")
        subprocess.run([sys.executable, os.path.join(CODE, "critters.py"), out], check=True)
        print(f"Every character: {out}")
        return
    if not rest:
        raise SystemExit(f"Which rhyme? python rhyme.py {cmd} <slug>   (see: python rhyme.py list)")
    folders = [folder_of(s) for s in rest]
    if cmd == "upload":
        upload(folders)
        return
    for folder in folders:
        if cmd == "sync":
            sync(folder)
        elif cmd == "voice":
            sync(folder, quiet=True)
            voice(folder)
        elif cmd == "guide":
            sync(folder, quiet=True)
            render(folder, guide=True)
        elif cmd == "pictures":
            sync(folder, quiet=True)
            if "--no-model" not in sys.argv:
                story(folder, show=False)
            pictures(folder, ask_model="--no-model" not in sys.argv)
            draw(folder)
            print(f"  Next: look at {os.path.relpath(folder, ROOT)}/images/review.jpg, then "
                  f"python rhyme.py render {os.path.basename(folder)} --preview")
        elif cmd == "render":
            sync(folder, quiet=True)
            if settings().get("singing") == "ai_song" and os.path.exists(os.path.join(folder, "audio", "song.wav")):
                import align
                if not align.fresh(folder):
                    print("  updating the song timing and edit ...", flush=True)
                    align.run(folder)
            refresh_pictures(folder)
            render(folder)
        elif cmd == "story":
            sync(folder, quiet=True)
            if "--redo" in sys.argv and os.path.exists(os.path.join(folder, "story.json")):
                os.remove(os.path.join(folder, "story.json"))
            story(folder)
        elif cmd == "kit":
            kit(folder)
        elif cmd == "clips":
            gpu_check()
            sync(folder, quiet=True)
            refresh_pictures(folder)
            clips(folder)
            print(f"  Next: python rhyme.py render {os.path.basename(folder)}")
        elif cmd == "song":
            sync(folder, quiet=True)
            song(folder, new_take=True)
            print(f"  Listen: {os.path.relpath(folder, ROOT)}/audio/song.wav (the last take is song_previous.wav), "
                  f"then python rhyme.py render {os.path.basename(folder)}")
        elif cmd == "make":
            wants_clips = (settings().get("ai_clips", True) and clips_ready() and "--drawn" not in sys.argv
                           and "--no-clips" not in sys.argv and "--preview" not in sys.argv)
            if wants_clips:
                gpu_check()
            sync(folder)
            if "--drawn" not in sys.argv:
                story(folder, show=False)   # what each line means and who is in it, BEFORE any picture
            if os.path.exists(os.path.join(folder, "pictures.json")):
                pictures(folder)    # re-plans only lines whose meaning/cast changed (your edits stay)
            elif settings().get("ai_pictures", True) and "--drawn" not in sys.argv:
                pictures(folder)    # a local model plans the pictures (then it's unloaded)
            if "--drawn" not in sys.argv:
                draw(folder)        # the image model fills in what's missing (then it's unloaded)
            if settings().get("singing") == "ai_song" and ai_song_ready() and "--chant" not in sys.argv:
                song(folder)        # real singing: the AI song (voice + music), then Whisper finds each line
            else:
                voice(folder)
            if (settings().get("ai_clips", True) and "--drawn" not in sys.argv and "--no-clips" not in sys.argv
                    and "--preview" not in sys.argv):
                # real cartoon motion for every picture (hours: an overnight job). Without them the video would be
                # the old flat look, so make stops here instead of quietly rendering that.
                if not clips(folder) and "--allow-2d" not in sys.argv:
                    slug = os.path.basename(folder)
                    raise SystemExit(
                        f"\nStopped before the video: some 3D clips are missing (see "
                        f"{os.path.relpath(folder, ROOT)}/images/clips/make.log).\n"
                        f"Close the browser and other big programs, then run\n"
                        f"  python rhyme.py make {slug}\nagain (finished clips are kept). "
                        f"To render anyway with the missing pictures as camera moves: add --allow-2d")
            render(folder)
            if "--preview" not in sys.argv:
                kit(folder)
                print(f"\nDone. Watch {os.path.relpath(folder, ROOT)}/output/rhyme.mp4, then: "
                      f"python rhyme.py upload {os.path.basename(folder)} --channel @YourKidsChannel")
        else:
            print(__doc__)
            return


if __name__ == "__main__":
    main()
