# Snack Code: local AI video pipeline

Give it a video title and it makes a researched Hinglish script, a Hindi voiceover and a
1080p animated video for the Snack Code YouTube channel. Everything runs on this laptop,
with no paid APIs.

```
title -> research -> script -> voiceover -> animated video
         (SearXNG)   (Ollama)  (Chatterbox)  (Pillow + FFmpeg)
```

## Quick start

Open a terminal and start the tools. Ollama must also be running, with the `qwen3:8b` and `gemma3:4b` models.
(`qwen3:8b` does the research and planning. `gemma3:4b` writes the script, because its Hindi is much better.)

```bash
cd ~/snackcode-ai
source venv/bin/activate
docker start searxng
```

Then choose one:

```bash
# One new video: script only
python auto_video.py "Agar internet 24 ghante ke liye band ho jaye to?"

# Every video in topics.txt: scripts only
python auto_video.py --file topics.txt

# Every video in topics.txt: scripts, voice and final video (good to run overnight)
python auto_video.py --file topics.txt --render
```

## Making one video, step by step

Scripts contain mistakes, so review each one before you make the voice and video.

**1. Write the script.**

```bash
python auto_video.py "Your title"
```

**2. Go to the video's folder.** The commands below must be run from inside it.

```bash
cd projects/<video-folder>
```

**3. Check and edit.** A second AI agent, the script editor, has already fixed grammar, wrong words, repeats
and hard lines. `scripts/review_report.md` shows every change it made. After your own edits you can run it again
with `python ../../script_review.py`. It can't check facts, so that part is still yours:

- Compare `research/notes.md` with its source links, because the AI can get facts wrong.
- Read `scripts/review.md` if it exists. It lists problems the automatic checks couldn't fix.
- Edit `scripts/script.json`. Read it aloud: the AI writes a first draft, and it can still repeat
  itself or get a word wrong. **Edit the Hindi in `say_hi`**, because that's what the voice reads, then
  run `python ../../hinglish.py --sync` to remake the captions from it.

**4. Make the voiceover.** This uses its own Python environment, `venv-voice`.

```bash
../../venv-voice/bin/python ../../voice.py
```

**5. Preview the first 3 scenes.**

```bash
python ../../animate.py --preview
xdg-open output/preview.mp4
```

**6. Render the full video.** A 10-minute video takes about 10 minutes.

```bash
python ../../animate.py
```

**7. Upload.**

```bash
python ../../youtube_kit.py
```

This makes a `youtube/` folder with thumbnails and an `upload.md` guide: title, description with
chapters, tags, pinned comment, Studio settings and a checklist. The first run creates
`youtube/details.json` from `metadata.md`. Edit that file to change any of these, including the
thumbnail text, then run the command again. Run it again after every re-render too, so the chapter
times stay correct. It doesn't upload anything: either follow `upload.md` in YouTube Studio, or use
`upload.py` (see [Uploading by script](#uploading-by-script)).

## What each video gets

Each title gets its own folder in `projects/`, so videos don't overwrite each other.

| File | What's inside |
| --- | --- |
| `research/notes.md` | Facts from up to 8 articles, each under its source link |
| `research/sources.json` | The list of sources used |
| `scripts/outline.json` | The story plan: its shape, sections and ending, which differ from video to video |
| `scripts/review_report.md` | What the script editor changed and flagged |
| `scripts/review.md` | Only if needed: problems the automatic checks couldn't fix |
| `scripts/script.json` | The final script: beats, visuals, Byte's moods, stickers, Hindi voice text |
| `metadata.md` | 3 title options, thumbnail text, description with sources, tags |
| `audio/` | Voice clips and their timing, one per scene and one per beat |
| `images/` | Optional: your screenshots, named `scene_XX.png` or `.jpg` |
| `output/animated.mp4` | The finished video |
| `output/animated.srt` | Subtitles for YouTube Studio |
| `youtube/` | Thumbnails and the upload guide, made by `youtube_kit.py` |

## What's on screen

The writer picks visuals by itself. You can also set them by hand in `scripts/script.json`.

| Visual | What it shows | How to set it |
| --- | --- | --- |
| `term` | A hard word in a notebook: the word, its meaning and an everyday example, written by a pen | `{"type": "term", "term": "VPN", "meaning": "...", "example": "...", "icon": "lock"}` |
| `symbols` | 2-3 realistic 3D icons on bright cards | `{"type": "symbols", "items": [{"icon": "ship", "label": "Jahaz"}, {"icon": "cable", "label": "Cable"}]}` |
| `pen` | A pen draws boxes and arrows. `broken` crosses out one arrow, counting from 0 | `{"type": "pen", "title": "UPI", "items": [{"label": "Phone", "icon": "phone"}, {"label": "Bank", "icon": "bank"}], "note": "..."}` |
| `map` | India with a pin on each place named | `{"type": "map", "places": ["Delhi", "Assam"], "label": "..."}` |
| `photo` | A real photo across the whole screen | `{"type": "photo", "query": "mobile tower", "caption": "Mobile tower"}` |

- **Hard terms:** the first time a video says a term from `glossary.py`, the next beat explains it. These
  explanations are written by hand, not by the local model. If a term isn't in the list, it doesn't
  get a card, so add an entry for any new term you want explained.
- **Maps:** a beat that names a place in `india_places.py` shows the map automatically. The outline is
  Natural Earth's India view, simplified. Check it yourself before publishing a video that
  focuses on a border area.
- **Photos:** `auto_video.py` fetches them from Wikimedia Commons, using only CC0, public-domain and
  CC BY licences. The local AI looks at each one first and rejects photos of people, slides and big text. **Look at `images/photos/review.jpg` before voicing**, because the search can pick
  the wrong picture. Photos say "Sanketik photo" on screen, and `youtube_kit.py` adds the credits to
  the description. To use your own photo, add `"file": "images/my_photo.jpg"` to the beat's visual.
  To choose again, run `python ../../photos.py --redo`.
- **Icons:** realistic 3D icons are in `assets/icons/` (Microsoft Fluent Emoji, MIT licence). Any file you
  add there can be used by its file name.
- **Mix:** `auto_video.py` limits repeated cards like `compare` and `steps`, and swaps some for photos and symbols.
- **Colours:** each scene gets its own colours. To keep one colour, run `animate.py --one-colour`.

## Making the voice more emotional

Each sentence already gets its own delivery from its words and punctuation. The biggest improvement
comes from your own recordings, because the voice copies how the reference clip sounds.

Record 8-15 seconds of yourself, in Hindi, in each mood, and save them in `voices/`:

| File | How to sound |
| --- | --- |
| `narrator_shock.wav` | Surprised, like you've just heard big news |
| `narrator_warn.wav` | Serious, warning a friend |
| `narrator_happy.wav` | Excited and smiling |
| `narrator_think.wav` | Curious, asking a question |
| `narrator_explain.wav` | Calm, explaining over chai |

You can add some or all of them. `voices/narrator.wav` is used for any mood without its own file.

## Adding videos to `topics.txt`

Put one video on each line. Only the title is required, and the length defaults to 8 minutes.

```
Title | direction for the AI | minutes=8 | type=news
```

`type` can be `news`, `scam` or `explainer`. Leave it out and the script guesses from the words used.

**News videos** search the last month of news and follow one path: what happened, why, who says what,
and what it means for you. They're told to name who said each thing, give every side and add no
opinion, but **the local model still gets this wrong, including stating claims as fact**. So `--render`
and `upload.py --publish` or `--schedule` refuse a news video until you've checked every name, date and
claim against the sources (`scripts/review.md` has the checklist) and added `"reviewed": true` to
`scripts/script.json`.

Use one specific story per video, like `Sansad mein naya Bill: kya badlega?`, because a broad title
like `Current political news` gives scattered research. People's opinions only appear when a source
reports them: the script won't make up quotes or polls.

Lines starting with `#` are skipped. Remove the `#` from a line to include that video.

## Fixing and redoing things

Run the `voice.py` and `animate.py` commands from inside the video's folder. Scene numbers
start at 0, matching the audio file names (`scene_00.wav` is `--scene 0`).

| I want to... | Command |
| --- | --- |
| Redo one scene's voice after editing it | `../../venv-voice/bin/python ../../voice.py --scene 8` |
| Redo all the voice clips | `../../venv-voice/bin/python ../../voice.py --redo` |
| Rebuild the video after a voice change | `python ../../animate.py` |
| Redo a video from scratch | `python auto_video.py "Title" --force` (from `~/snackcode-ai`) |

- **After `--force`:** with `--render` the voice is redone too. Without `--render`, run
  `voice.py --redo` yourself, because the old audio is kept.
- **After an interrupted run:** run the same command again. It picks up where it stopped.
- **Existing scripts:** titles that already have a `script.json` aren't rewritten unless you
  use `--force`. With `--render`, their video is still rendered again.
- **Cut-off words:** Chatterbox sometimes cuts the last word of a beat. Listen to the
  `scene_XX_bYY.wav` files and redo that scene with `--scene`.
- **A word spelled wrong:** voice spellings are in `hindi_words.json`. Screen spellings are in
  `caption_words.json`, where each Hindi word is matched to how it shows on screen, like
  `"ऑटोमेशन": "automation"`. English terms appear in real English. Fix a word in either file and it stays
  fixed in every video. Then run `python ../../hinglish.py --sync` and `python ../../animate.py`; the voice
  doesn't need redoing. Test a line with `python ../../hinglish.py "..."`.
- **Voice not matching a line:** `voice.py` listens to every line with Whisper and redoes weak ones, up
  to 3 takes. Anything still weak is listed in `audio/voice_check.md`. Whisper can be wrong, so listen first.
- **Wrong number or short form:** test the text with `python hindi_text.py "UPI 1930"`, which
  shows what the voice will read. Fix a word by adding it to the lists in `hindi_text.py`, or
  by writing it in Hindi in `say_hi`. `voice.py` also prints any English words it couldn't convert.

## Uploading by script

`upload.py` sends the video, title, description, chapters, tags, thumbnail, subtitles and settings
to YouTube, including the AI label. It's free, uses YouTube's official API, and can only upload to
@SnackCode108.

**One-time setup**

1. In [Google Cloud Console](https://console.cloud.google.com/), create a project and enable
   **YouTube Data API v3**.
2. Set up the OAuth login screen as **External**, and add your own email as a test user.
3. Create a **Desktop app** client and save its JSON file as `~/snackcode-ai/client_secret.json`.
4. Verify the channel at [youtube.com/verify](https://www.youtube.com/verify), which custom thumbnails need.
5. If the libraries are missing from `venv`, install them. `protobuf` must stay below version 5:
   ```bash
   uv pip install --python venv/bin/python google-api-python-client google-auth-oauthlib "protobuf==4.25.9"
   ```

**Uploading a video.** Run these from the video's folder, after `youtube_kit.py`:

```bash
# See what would be sent, without uploading anything
python ../../upload.py --thumbnail b --dry-run

# Upload as private (the default)
python ../../upload.py --thumbnail b

# Upload now, and go public at this India time
python ../../upload.py --thumbnail b --schedule "2026-11-08 18:00"

# Go public straight away (asks you to type PUBLISH first)
python ../../upload.py --thumbnail b --publish
```

On the first run a browser opens: choose the Snack Code channel and click Allow. While the app is in
test mode, Google may ask you to log in again about every 7 days.

- **Running it again is safe:** `youtube/uploaded.json` records the upload, so the video is never
  sent twice. A new run only retries failed steps and posts the comment once the video is public.
- **Changing visibility later:** once a video is uploaded, change it in YouTube Studio. `--publish`
  and `--schedule` only apply to the first upload.
- **Uploading a new version:** YouTube can't replace a video's file. Delete the old video in Studio,
  delete `youtube/uploaded.json`, then upload again.
- **Still done in Studio:** pinning the comment, the end screen and Test & Compare for thumbnails.
- **Keep these private:** `client_secret.json` and `youtube_token.json` give access to the channel.
  They're in `.gitignore`, so git won't add them. To remove access, go to your
  [Google account permissions](https://myaccount.google.com/permissions).

## All run commands

Every command assumes you've started the tools first:

```bash
cd ~/snackcode-ai
source venv/bin/activate
docker start searxng
```

**Run these from `~/snackcode-ai`:**

```bash
# Script only: one video, with an optional direction for the AI
python auto_video.py "Title"
python auto_video.py "Title" "Direction for the AI"

# Script, voice and video for one video (news videos stop until "reviewed": true is set)
python auto_video.py "Title" --render

# Every video in topics.txt
python auto_video.py --file topics.txt
python auto_video.py --file topics.txt --render

# Redo a video from scratch. This replaces its research and script
python auto_video.py "Title" --force
python auto_video.py "Title" --force --render

# See how the voice will read numbers and short forms
python hindi_text.py "UPI 1930"

# See a line's spelling: Roman gives Devanagari, Devanagari gives the on-screen caption
python hinglish.py "Data ka chhota tukda"
python hinglish.py "डेटा का छोटा टुकड़ा"
```

**Run these from the video's folder.** Go there first with `cd projects/<video-folder>`:

```bash
# Script checks
python ../../script_review.py                   # recheck the script with the script editor
python ../../hinglish.py --sync                 # remake captions after editing say_hi

# Photos
python ../../photos.py                          # fetch photos that are missing
python ../../photos.py --redo                   # choose all the photos again

# Voice (uses venv-voice)
../../venv-voice/bin/python ../../voice.py                        # voice any scenes that aren't done
../../venv-voice/bin/python ../../voice.py --redo                 # redo every scene
../../venv-voice/bin/python ../../voice.py --scene 8              # redo one scene
../../venv-voice/bin/python ../../voice.py --redo --voice my.wav  # use a different reference voice
../../venv-voice/bin/python ../../voice.py --redo --no-check      # faster: skip the Whisper check
../../venv-voice/bin/python ../../voice.py --redo --lang en       # English narration
python ../../voice.py --redo --engine kokoro                      # Kokoro male voice (uses venv)
python ../../voice.py --redo --engine kokoro --female             # Kokoro female voice (uses venv)

# Video
python ../../animate.py --preview               # first 3 scenes
python ../../animate.py                         # the full video
python ../../animate.py --theme ocean           # emerald, violet, ocean, sunset or crimson
python ../../animate.py --one-colour            # one colour for the whole video
python ../../animate.py --no-mascot             # without Byte
python ../../animate.py --no-sfx                # without sound effects

# YouTube
python ../../youtube_kit.py                     # thumbnails, chapters and the upload guide
python ../../upload.py --thumbnail b --dry-run  # see what would be sent; nothing is uploaded
python ../../upload.py --thumbnail b            # upload as private
python ../../upload.py --thumbnail b --schedule "2026-11-08 18:00"   # goes public at this India time
python ../../upload.py --thumbnail b --publish  # public straight away; asks you to type PUBLISH
python ../../upload.py                          # after an upload: retry failed steps, post the comment
```

`voice.py` runs `voice_check.py` for you, so you don't need to run it yourself. The `--force` commands, `voice.py --redo`
and `photos.py --redo` replace existing files for that video.

**Older single-step scripts.** These use `./research` and `./scripts` in the current folder:

```bash
python research.py "call forwarding scam India"
python script.py
```

## All options

**`animate.py`**

| Option | What it does |
| --- | --- |
| `--preview` | Renders the first 3 scenes to `output/preview.mp4` |
| `--theme NAME` | Sets the colours: `emerald`, `violet`, `ocean`, `sunset` or `crimson` |
| `--no-mascot` | Hides Byte, the robot host |
| `--no-sfx` | Turns off sound effects |
| `--one-colour` | Keeps one colour for the whole video |

**`voice.py`**

| Option | What it does |
| --- | --- |
| `--redo` | Regenerates all scenes |
| `--scene N` | Regenerates one scene |
| `--lang hi` or `en` | Sets the narration language (default `hi`) |
| `--voice file.wav` | Uses a different reference voice |
| `--engine chatterbox` or `kokoro` | Sets the voice engine (default `chatterbox`) |
| `--no-check` | Skips the Whisper check: faster, but bad takes stay |
| `--female` | Uses a female Hindi voice, with `--engine kokoro` only |

Kokoro is installed in `venv`, not `venv-voice`, so with `venv` active run it like this:

```bash
python ../../voice.py --engine kokoro --female
```

## Project files

| Path | Purpose |
| --- | --- |
| `auto_video.py` | Main script: title to research, outline, scenes and metadata |
| `voice.py` | Makes the voiceover |
| `hindi_text.py` | Turns numbers, short forms and web addresses into spoken Hindi before voicing |
| `animate.py` | Renders the video from the script and audio |
| `youtube_kit.py` | Makes thumbnails and the upload guide for a finished video |
| `upload.py` | Uploads a finished video to YouTube with all its details |
| `.gitignore` | Keeps login files, the voice sample, environments and heavy media out of git |
| `glossary.py` | Hand-written explanations of hard tech, government, court and money terms |
| `hinglish.py`, `hindi_words.json`, `caption_words.json` | Keep captions and voice on the same words; the voice and screen spelling lists |
| `script_review.py` | The script editor: a second AI agent that rechecks every script before audio and video |
| `voice_check.py` | Listens to voice clips with Whisper and scores them |
| `india_places.py` | Places the map can mark |
| `photos.py` | Fetches safely licensed real photos |
| `assets/` | Handwriting font (Kalam, OFL licence) and the India outline |
| `topics.txt` | The list of videos to make |
| `voices/narrator.wav` | 10-20 second sample of the owner's own voice, copied by Chatterbox |
| `searxng/settings.yml` | Search settings (`formats` must include `json`) |
| `research.py`, `script.py` | Older single-step versions that use `./research` and `./scripts` |

Optional extras:

- **`fonts/*.ttf` and `music.mp3`:** put these in `~/snackcode-ai`. `--render` links them into
  each video's folder. If you run `animate.py` by hand, it only looks in the current folder.
- **Other music formats:** `music.wav` and `music.m4a` also work.

## Good to know

- **Two Python environments:** use `venv` for research, scripts and animation, and
  `venv-voice` for Chatterbox. `--render` picks the right one by itself.
- **Graphics memory:** the 6 GB GPU can't run Ollama and the voice model together.
  `voice.py` unloads Ollama before it starts generating voice.
- **Scam videos:** always end with helpline **1930** and **cybercrime.gov.in**.
- **Script format:** see `CLAUDE.md` for the `script.json` format and visual types.
