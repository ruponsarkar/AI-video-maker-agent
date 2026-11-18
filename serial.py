"""
Story serial: a separate pipeline for a separate YouTube channel. Long traditional stories (Ramayan, Mahabharat,
Panchatantra ...) told as a cartoon serial, episode by episode, each under 5 minutes, each remembering
everything before it.

    python serial.py find ["mythology"]            # search for good stories -> serial/stories.txt
    python serial.py new "Ramayan" [--episodes 150] [--channel @YourStoryChannel] [--kids] [--about "..."]
    python serial.py new --pick 2                   # the 2nd story in serial/stories.txt
    python serial.py list                           # all series and how far each has got
    python serial.py status ramayan                 # plan, progress, memory
    python serial.py make ramayan                   # the next 7 episodes: write, voice, render, kit
    python serial.py make ramayan 2                 # only the next 2 (any number 1-7; same as --count 2)
    python serial.py make ramayan --write-only      # only scripts: read and edit them before voicing
    python serial.py voice  ramayan 3 4             # one step for some episodes (also: render, kit, remember)
    python serial.py render ramayan 3 --preview
    python serial.py remember ramayan 3             # after you edit episode 3's script: update the memory
    python serial.py upload ramayan --start "2026-11-12 18:00" [--every 1] [--from 1 --to 7] [--channel @...]
        (--channel is needed once: saved in series/settings.json; series.json "channel" overrides it per serial)

Folders: series/<slug>/ series.json (settings), bible.json (cast and places, fixed forever), plan.json (arcs
and episodes), memory/ (what has happened), research/, episodes/epNNN/ (script.json, review.md, audio/, output/,
youtube/). Voices for characters: series/<slug>/voices/<character id or voice type>.wav. Your own music:
series/<slug>/music/<mood>.mp3 (calm happy sad tense battle mystery divine).
"""
import datetime
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
SERIAL = os.path.join(ROOT, "serial")
SETTINGS = os.path.join(ROOT, "series", "settings.json")   # {"channel": "@StoryChannel"}: default for every serial
sys.path.insert(0, SERIAL)
MAX_BATCH = 7


def flag(name, default=None):
    if name in sys.argv:
        k = sys.argv.index(name)
        if k + 1 < len(sys.argv) and not sys.argv[k + 1].startswith("--"):
            return sys.argv[k + 1]
        return True
    return default


def plain_args():
    out, skip = [], False
    values = {"--episodes", "--channel", "--about", "--pick", "--count", "--start", "--every", "--from", "--to", "--thumbnail",
              "--title"}
    for a in sys.argv[2:]:
        if skip:
            skip = False
            continue
        if a in values:
            skip = True
            continue
        if not a.startswith("--"):
            out.append(a)
    return out


def episodes_arg(rest, sdir):
    import story
    if rest:
        return [int(x) for x in rest if x.isdigit()]
    plan = story.jload(os.path.join(sdir, "plan.json"))
    return [e["n"] for e in plan["episodes"] if e["status"] != "planned"]


def run(cmd, label):
    print(f"\n== {label}", flush=True)
    done = subprocess.run(cmd, cwd=ROOT)
    if done.returncode != 0:
        raise SystemExit(f"{label} failed (exit {done.returncode}).")


def set_status(sdir, numbers, status):
    import story
    plan = story.jload(os.path.join(sdir, "plan.json"))
    for e in plan["episodes"]:
        if e["n"] in numbers:
            e["status"] = status
    story.jsave(os.path.join(sdir, "plan.json"), plan)


def voice(sdir, numbers):
    import story
    folders = [story.ep_dir(sdir, n) for n in numbers if os.path.exists(os.path.join(story.ep_dir(sdir, n), "script.json"))]
    python = os.path.join(ROOT, "venv-voice", "bin", "python")
    if not os.path.exists(python):
        raise SystemExit("venv-voice is missing: see readme.md (Two Python environments).")
    extra = [a for a in ("--redo", "--no-check", "--cpu") if a in sys.argv]
    run([python, os.path.join(SERIAL, "voice_run.py"), *folders, *extra], f"Voices for episode(s) {numbers}")
    set_status(sdir, numbers, "voiced")


def render(sdir, numbers):
    import story
    for n in numbers:
        folder = story.ep_dir(sdir, n)
        run([sys.executable, os.path.join(SERIAL, "render.py"), folder, *[a for a in ("--preview", "--no-music") if a in sys.argv]],
            f"Render episode {n}")
        if "--preview" not in sys.argv:
            length = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                           os.path.join(folder, "output", "episode.mp4")], capture_output=True,
                                          text=True).stdout.strip() or 0)
            if length > 300:
                print(f"  Warning: episode {n} is {length / 60:.1f} minutes (over 5). Shorten script.json and run again.")
            set_status(sdir, [n], "rendered")


def kit(sdir, numbers):
    import kit as kitmod
    import story
    for n in numbers:
        kitmod.build(story.ep_dir(sdir, n), redo="--redo" in sys.argv)


def upload(sdir, numbers):
    import story
    series = story.jload(os.path.join(sdir, "series.json"))
    shared = story.jload(SETTINGS) if os.path.exists(SETTINGS) else {}
    given = flag("--channel") if isinstance(flag("--channel"), str) else ""
    channel = given or series.get("channel") or shared.get("channel")
    if not channel:
        raise SystemExit("Which channel? Add --channel @YourStoryChannel once: it's remembered in series/settings.json.")
    channel = channel if channel.startswith("@") else "@" + channel
    # the three pipelines go to three channels: never send a story to Snack Code or Golu Cartoon by mistake
    rhymes = os.path.join(ROOT, "rhymes", "settings.json")
    others = {"@snackcode108"} | ({json.load(open(rhymes)).get("channel", "").lower()} if os.path.exists(rhymes) else set())
    if channel.lower() in others:
        raise SystemExit(f"{channel} is the Snack Code / rhymes channel, not the story channel. Nothing was uploaded.")
    if given and not shared.get("channel"):
        shared["channel"] = channel
        json.dump(shared, open(SETTINGS, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print(f"Story channel {channel} saved in series/settings.json (used by every serial without its own).")
    start = flag("--start")
    every = float(flag("--every", 1))
    when = datetime.datetime.strptime(start, "%Y-%m-%d %H:%M") if isinstance(start, str) else None
    playlist = series.get("title_screen") or series["title"]
    for k, n in enumerate(numbers):
        folder = story.ep_dir(sdir, n)
        cmd = [sys.executable, os.path.join(ROOT, "upload.py"), "--channel", channel, "--video", "output/episode.mp4",
               "--subtitles", "output/episode.srt", "--category", "story", "--playlist", playlist]
        if series.get("made_for_kids"):
            cmd.append("--kids")
        if when:
            cmd += ["--schedule", (when + datetime.timedelta(days=every * k)).strftime("%Y-%m-%d %H:%M")]
        for name in ("--thumbnail", "--title"):
            if flag(name):
                cmd += [name, flag(name)]
        if "--dry-run" in sys.argv:
            cmd.append("--dry-run")
        if "--publish" in sys.argv:
            cmd.append("--publish")
        print(f"\n== Upload episode {n}" + (f" (goes public {cmd[cmd.index('--schedule') + 1]})" if "--schedule" in cmd else ""))
        done = subprocess.run(cmd, cwd=folder)
        if done.returncode != 0:
            raise SystemExit(f"Upload of episode {n} stopped. Fix the problem above and run the same command again: "
                             "finished episodes are skipped.")
        if "--dry-run" not in sys.argv:
            set_status(sdir, [n], "uploaded")


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help", "help"):
        print(__doc__)
        return
    cmd = sys.argv[1]
    import story
    rest = plain_args()

    if cmd == "find":
        rows = story.find_stories(" ".join(rest))
        print(f"\n{len(rows)} new stories added to {story.STORIES_FILE}:")
        for k, r in enumerate(story.read_stories(), 1):
            print(f"  {k:2d}. {r[0]}  -  {r[1][:70]}  ({r[2]} episodes)")
        print('\nStart one with: python serial.py new "Title"   or   python serial.py new --pick N')
        return
    if cmd == "new":
        title, about = (rest[0] if rest else None), flag("--about", "")
        if flag("--pick"):
            rows = story.read_stories()
            k = int(flag("--pick")) - 1
            if not 0 <= k < len(rows):
                raise SystemExit("No such number in serial/stories.txt. Run: python serial.py find")
            title, about = rows[k][0], about or rows[k][1]
        if not title:
            raise SystemExit('Give a title: python serial.py new "Ramayan"')
        eps = flag("--episodes")
        slug = story.new_series(title, about if isinstance(about, str) else "", int(eps) if isinstance(eps, str) else None,
                                flag("--channel", "") if isinstance(flag("--channel", ""), str) else "", bool(flag("--kids")))
        print(f"\nNext: check series/{slug}/bible.json (the cast) and plan.json, then: python serial.py make {slug}")
        return
    if cmd == "list":
        root = story.SERIES_ROOT
        for slug in sorted(os.listdir(root)) if os.path.exists(root) else []:
            p = os.path.join(root, slug, "plan.json")
            if os.path.exists(p):
                plan = story.jload(p)
                eps = plan["episodes"]
                done = {s: sum(e["status"] == s for e in eps) for s in ("written", "voiced", "rendered", "uploaded")}
                total = sum(a["episodes"] for a in plan["arcs"])
                print(f"{slug}: {len(eps)} of ~{total} episodes planned; " + ", ".join(f"{v} {k}" for k, v in done.items()))
        return

    if not rest:
        raise SystemExit(f"Which series? python serial.py {cmd} <slug>   (see: python serial.py list)")
    sdir = story.series_dir(rest[0])
    numbers = rest[1:]

    if cmd == "status":
        plan = story.jload(os.path.join(sdir, "plan.json"))
        from memory import Memory
        mem = Memory(sdir)
        for a in plan["arcs"]:
            eps = [e for e in plan["episodes"] if e["arc"] == a["n"]]
            print(f"Arc {a['n']:2d} {a['title'][:40]:40s} {a['episodes']:3d} ep  "
                  + (", ".join(f"{e['n']}:{e['status'][0]}" for e in eps) if eps else "(not planned yet)"))
        print(f"\nMemory: {len(mem.facts)} facts, {len(mem.state.get('open_threads', []))} open threads, "
              f"vectors {'on' if mem.vectors is not None else 'off (ollama pull nomic-embed-text)'}")
        if mem.state.get("story_so_far"):
            print("\nStory so far:\n" + mem.state["story_so_far"])
        return
    if cmd == "make":
        asked = numbers[0] if numbers and numbers[0].isdigit() else flag("--count", MAX_BATCH)
        try:
            count = int(asked)
        except (TypeError, ValueError):
            raise SystemExit("How many episodes? A number from 1 to 7, e.g.: python serial.py make ramayan 3")
        if count < 1:
            raise SystemExit("Make at least 1 episode.")
        if count > MAX_BATCH:
            print(f"At most {MAX_BATCH} episodes per run (the GPU and your review time): making {MAX_BATCH}.")
            count = MAX_BATCH
        todo = story.next_episode_numbers(sdir, count)
        if not todo:
            print("Every episode in the plan is written.")
            return
        print(f"Writing episodes {todo} (one after another, each remembers the last)")
        for n in todo:
            story.write_episode(sdir, n)
        if "--write-only" in sys.argv:
            print(f"\nScripts written. Read episodes/epNNN/script.json and review.md, then: "
                  f"python serial.py voice {rest[0]} {' '.join(map(str, todo))}")
            return
        voice(sdir, todo)
        render(sdir, todo)
        kit(sdir, todo)
        print(f"\nDone: episodes {todo}. Watch them, then: python serial.py upload {rest[0]} --start \"YYYY-MM-DD HH:MM\"")
        return
    if cmd == "write":
        for n in map(int, numbers):
            story.write_episode(sdir, n)
        return
    if cmd == "remember":
        for n in map(int, numbers):
            story.remember(sdir, n)
        return
    targets = episodes_arg(numbers, sdir)
    if cmd == "voice":
        voice(sdir, targets)
    elif cmd == "render":
        render(sdir, targets)
    elif cmd == "kit":
        kit(sdir, targets)
    elif cmd == "upload":
        if numbers:
            targets = [int(x) for x in numbers]
        else:
            plan = story.jload(os.path.join(sdir, "plan.json"))
            lo, hi = int(flag("--from", 1)), int(flag("--to", 10 ** 6))
            targets = [e["n"] for e in plan["episodes"] if lo <= e["n"] <= hi and e["status"] in ("rendered", "uploaded")]
        upload(sdir, targets)
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
