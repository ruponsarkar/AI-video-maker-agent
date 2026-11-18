# Story serial

A separate pipeline, for a separate YouTube channel, from Snack Code. It tells long traditional stories (Ramayan,
Mahabharat, Panchatantra ...) as an animated cartoon serial in Hindi, episode by episode, each under 5 minutes.
Every new episode remembers everything that happened before it, so a 150-episode story stays in one flow.

Everything runs on this laptop: Ollama (qwen3:8b plans and checks, gemma3:4b writes the Hindi, nomic-embed-text
remembers), SearXNG for research, Chatterbox for voices, Pillow and FFmpeg for the animation. Characters,
backgrounds, music and sound effects are all drawn and made in code, so nothing needs a licence.

## Commands

Run from `~/snackcode-ai` with `source venv/bin/activate` and `docker start searxng`.

```bash
# 1. Choose a story
python serial.py find                      # searches, adds good stories to serial/stories.txt
python serial.py find "folk tales"         # search around a theme
                                           # or add your own line to serial/stories.txt:
                                           # Title | about | episodes | source

# 2. Start a series (research, plan of the whole story, the cast)
python serial.py new "Ramayan" --episodes 150 --channel @YourStoryChannel
python serial.py new --pick 4              # the 4th story in serial/stories.txt
python serial.py new "Panchatantra" --kids # if the channel is made for kids (YouTube's legal audience setting)

# 3. Make episodes: 7 by default, or any number from 1 to 7. Each run carries on from the
#    last episode made, so 2 now and 5 later gives episodes 1-2, then 3-7.
python serial.py make ramayan              # the next 7: write, voice, render, YouTube kit
python serial.py make ramayan 2            # only the next 2 (a quick test); same as --count 2
python serial.py make ramayan 3 --write-only   # scripts only; read and edit them, then:
python serial.py voice ramayan 8 9 10
python serial.py render ramayan 8 9 10     # (--preview: first 45 seconds)
python serial.py kit ramayan 8 9 10

# 4. Edited a script after it was written? Update the story's memory, so later episodes know
python serial.py remember ramayan 8

# 5. Upload and schedule (private until the scheduled time)
python serial.py upload ramayan --start "2026-11-12 18:00" --every 1            # one a day
python serial.py upload ramayan --from 8 --to 14 --start "2026-11-20 18:00" --every 2
python serial.py upload ramayan 8 --dry-run --channel @YourStoryChannel

python serial.py list                      # every series, how far it has got
python serial.py status ramayan            # arcs, episodes, memory, the story so far
```

## Starting a series: `new` in detail

`python serial.py new "Title" [options]` does three things, once per series, and takes 10-20 minutes:

1. **Research.** Searches the web (SearXNG) for the whole story and saves the facts to
   `series/<slug>/research/overview.md`.
2. **Plan.** Splits the whole story, start to end, into arcs (big chapters such as "Sita Swayamvar"), each with
   a number of episodes. Saved in `plan.json`. The episodes of an arc are planned later, when its turn comes.
3. **Cast.** Designs the main characters (look, colours, crown, weapon, voice type) and places. Saved in
   `bible.json`; from episode 1 on, these never change, so everyone always looks the same.

| Option | What it does | Example |
|---|---|---|
| `"Title"` | The story to tell. The folder name (slug) is made from it: "Ramayan" -> `ramayan`. | `new "Mahabharat"` |
| `--pick N` | Use story number N from `serial/stories.txt` (as `find` lists them) instead of typing a title. | `new --pick 4` |
| `--about "..."` | A line on what to cover or focus on; guides research and planning. | `--about "Krishna ka bachpan se Dwarka tak"` |
| `--episodes N` | Roughly how many episodes the whole story should take. The arcs are scaled to it. Leave it out to let the planner decide. | `--episodes 150` |
| `--channel @handle` | The YouTube channel for this series, saved in `series.json`; `upload` uses it. You can also give it at upload time. | `--channel @MyKahaniChannel` |
| `--kids` | Marks every upload "made for kids". This is YouTube's legal audience setting (COPPA): it turns off comments, the notification bell and personalised ads. Use it only if the channel is meant for children. | `--kids` |

If `new` stops part-way, run the same command again: it keeps the research and the arc plan and carries on. When
it's done, read `plan.json` (the arcs) and `bible.json` (the cast) before making episodes, and fix anything wrong:
small local models can get facts of a long epic wrong.

## Making episodes: `make` in detail

`python serial.py make <slug> [N] [options]`

- `N` (or `--count N`): how many episodes, 1 to 7. Default 7. Use 1 or 2 to test.
- It always continues: it takes the next episodes not yet written, in order. When an arc runs out, the next arc
  is researched and planned automatically.
- Episodes are written one after another, so each remembers the one before. Then all of them are voiced, rendered
  and get their YouTube kit.
- `--write-only`: stop after the scripts, so you can read and edit them first (recommended).
- `--cpu`: voice without the GPU (much slower). `--no-check`: skip the Whisper voice check.

## How an episode is made

1. **Plan.** At `new`, the whole story is researched and split into arcs, each with the number of episodes it
   needs. When the next arc's turn comes, it gets its own research and is split into episodes: one clear piece of
   the story each, 3-5 story beats, ending on a hook.
2. **Remember.** Before writing, the memory gives the writer: the story so far, how the last episode ended, where
   every character is and whether they're alive, the story threads still open, and the earlier facts that matter
   most to this episode (found by meaning with the vector index, `memory/vectors.npy`).
3. **Write.** Scenes are planned (place, time of day, weather, music, who stands where). qwen writes each scene as
   an English script, a director agent adds emotions, actions (enter, point, attack, fall, fly, bless ...) and
   sound effects, then gemma turns every line into spoken Hindi and a check makes sure the Hindi says the same
   thing, with every name spelled the same way each time.
4. **Check.** A continuity agent compares the episode with the memory and the plan, and fixes contradictions
   (someone who died speaking, a wrong relationship, something not in the traditional story). What it changed or
   couldn't fix is in `episodes/epNNN/review.md`.
5. **Recap and teaser.** "Pichhle episode mein..." at the start, "Agle episode mein..." at the end.
6. **Memory.** The episode's facts, character states and threads are saved for every later episode.
7. **Voice, render, kit.** Each character speaks in their own voice; the renderer animates the cast with lip-sync,
   blinking, walking, poses, camera close-ups, weather and effects, and mixes music, ambience and effects under
   the voices. The kit makes two thumbnails, two titles, the description and an upload checklist.

## What to check by hand (every time)

The local models on this laptop are small. They are good enough to draft, not to publish unchecked:

- **The plan.** After `new`, read `plan.json` (arcs). The model's own plan of a long epic can have wrong facts
  (wrong person, wrong order, missing parts). The Ramayan plan in `series/ramayan/` was written by hand from Valmiki
  and is a good model for others. Each arc's episodes are checked against the research (an arc-boundary agent drops
  events from other arcs), but read `episodes` in `plan.json` too.
- **The cast.** `bible.json`: looks and voices. Code fixes impossible looks (tails only on monkeys ...), not taste.
- **Every episode.** `episodes/epNNN/review.md` shows each line in English (the story) and Hindi (the voice), and
  lists what the continuity and translation checks changed or couldn't fix ("CHECK the Hindi of ..."). Edit
  `say_hi` (and `say_en`) in `script.json`, then `python serial.py remember <slug> N`.
- The weak spot is the Hindi (gemma3:4b). For better Hindi, set a bigger model in `series.json`:
  `"hindi_model": "gemma3:12b"` (`ollama pull gemma3:12b`, about 8 GB; it shares RAM with the GPU, so writing takes
  2-3 times longer). `"story_model"` does the same for planning and the English script (default qwen3:8b).

## If voicing stops with "The GPU isn't available"

After the laptop sleeps, PyTorch often loses the GPU. Run `sudo rmmod nvidia_uvm && sudo modprobe nvidia_uvm` (or
restart), then `python serial.py voice <slug> N`. `--cpu` works without the GPU but is many times slower.

## Making it better

- **Voices.** Record 10-20 clean seconds per voice type and put them in `series/<slug>/voices/` named
  `male_young.wav`, `male_adult.wav`, `male_old.wav`, `male_deep.wav`, `female_young.wav`, `female_adult.wav`,
  `female_old.wav`, `child.wav`, `demon.wav`, or one per character (`ram.wav`, `sita.wav`). Without them, every
  character uses your narrator voice with its pitch moved, which works but sounds less natural for women and
  children. Use only voices you have permission to use.
- **Music.** The score is generated (tanpura drone, flute in a raga, tabla or war drums by mood). Your own tracks
  win: `series/<slug>/music/calm.mp3` (also happy, sad, tense, battle, mystery, divine).
- **The cast.** `series/<slug>/bible.json` holds how every character looks (skin, outfit, colours, crown, prop ...)
  and their voice type. Change a look there before episode 1; after that, keep it, so people recognise them.
- **Read every script.** Small local models make mistakes in Hindi and in the story. YouTube also expects a person
  in the loop for AI-made videos. Read `script.json` and `review.md`, edit, then `remember`.

## Folders

```
serial.py                 the command
serial/                   the code: story.py (planning, writing, agents), memory.py, cartoon.py, scenery.py,
                          sound.py, render.py, voice_run.py (venv-voice), kit.py, stories.txt
series/<slug>/
  series.json             title, channel, made-for-kids, language
  bible.json              the cast and places: fixed looks and voices
  plan.json               arcs and episodes, with each episode's status
  research/               notes for the whole story and for each arc
  memory/                 facts.jsonl, vectors.npy, state.json (story so far, characters, threads)
  voices/  music/         your recordings and music (optional)
  episodes/ep001/         script.json, review.md, audio/, output/episode.mp4 + .srt, youtube/
```

Each 5-minute episode is about 40-60 MB. 100 episodes is about 5 GB, so move finished `output/` folders off this
disk after uploading.
