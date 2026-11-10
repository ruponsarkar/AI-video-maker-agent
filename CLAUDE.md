# Snack Code: local AI YouTube video pipeline

Offline pipeline that turns a video title into a researched Hinglish script, a realistic
Hindi voiceover and a graphical animated 1080p video for the YouTube channel
**Snack Code** (@SnackCode108). No paid APIs: Ollama + SearXNG + Chatterbox + FFmpeg.
This file was written from the planning chat on claude.ai; it is the project's memory.

## Channel context (why the videos look and sound this way)
- Niche: tech knowledge + online safety, explained simply. Main language Hindi/Hinglish
  (Roman script on screen), some English. Audience from Studio analytics: adults 25-34,
  ~74% male, 80% India, ~96% mobile, almost no subtitles used.
- Channel was tiny (~63 subs, ~16 views/28 days, 73% of lifetime views were paid ads).
  Goal: organic reach and YPP monetization (1,000 subs + 4,000 watch hours).
- Weak points found: CTR 0.5-3.5%, viewers leave in the first 30 s. So every video needs a
  hook in the first 3 s and a visual change every ~5 s.
- No fixed upload day or count (some weeks 0-3 videos). Studio defaults already set: Hindi, Science & Technology.
- Scam videos always end with helpline **1930** and cybercrime.gov.in.
- General news explainers are also made now (`type=news`, category News & Politics). Neutral: every claim
  attributed, both sides from the notes, no invented quotes or public opinion, human checks each one.
- YouTube "inauthentic content" policy: fully automatic, unedited AI videos risk losing
  monetization. Keep a human in the loop: edit every script, prefer the owner's own voice,
  mark realistic AI audio with YouTube's "altered or synthetic content" label.

## Machine
Dell G15 5530, Ubuntu, 16 GB RAM, NVIDIA RTX 3050 Laptop **6 GB VRAM**, driver 570 / CUDA 12.8.
Never run Ollama and the voice model at the same time (VRAM). Disk space is limited.

## Layout (~/snackcode-ai)
- `auto_video.py`  title -> research -> outline -> scenes -> metadata (-> render with --render)
- `topics.txt`     one video per line: `Title | direction for the AI | minutes=N`
- `voice.py`       voiceover, one clip per beat, writes exact timing JSON
- `hindi_text.py`  numbers, short forms and web addresses -> spoken Hindi, run on each beat by voice.py
- `animate.py`     renders the video from script.json + audio (Pillow frames piped to FFmpeg)
- `youtube_kit.py`  run in a video's folder after rendering: youtube/ with thumbnails, upload.md,
  description.txt; edit youtube/details.json. SCENE_GAP must match GAP in animate.py. Doesn't upload.
- `upload.py`  run in a video's folder after youtube_kit.py: official YouTube API, OAuth files
  client_secret.json + youtube_token.json (git-ignored, never read or print them). Private by default;
  youtube/uploaded.json prevents double uploads. Online and separate from the offline video pipeline.
  venv needs google-api-python-client + google-auth-oauthlib with `protobuf==4.25.9`
  (descript-audiotools needs protobuf <5; a plain install upgrades it).
- `script_review.py`  the script editor, a second local agent run on every new script before audio/video: remakes
  captions from say_hi, edits lines, reads the whole script, removes repeats. Edits only pass if numbers, short forms
  and (for news) attribution survive. Report: scripts/review_report.md. It can't check facts.
- `glossary.py`  hand-checked term explanations, inserted after a term's first mention (don't let
  the model write these). `india_places.py`  map coordinates. `photos.py`  Wikimedia Commons photos,
  CC0/PD/CC BY only (no SA/NC/ND), online but optional; review images/photos/review.jpg.
  `assets/`  Kalam font and India outline (Natural Earth, India point of view).
- Captions: Hindi words always use the rule spelling (to_roman); a model's English word is used only if english_matches()
  finds the same consonant sounds (oxygen=ऑक्सीजन passes, beryllium for बेरियम fails) and it's a dictionary word.
  caption_words.json `_checked_with` version: bump it to re-ask old guesses once.
  english_pass() (run by script_review and `hinglish.py --sync`) re-checks every sound-spelled caption word
  (mashin -> machine); unsure ones go to review_report.md. Test pairs before changing _skeletons_en/english_matches.
- Photos: the title beat gets a hook photo (visual title + query); first ~10 beats get a photo every 2 beats;
  each photo beat has a `backup` query.
- Captions (`say`) and voice (`say_hi`) are separate texts. screen_text() has gemma write the caption with the whole
  sentence as context (English words in real English), then checks every word against the voice text with
  same_word() and the dictionary; a word that fails falls back to to_roman(). `say_from` records which say_hi a
  caption was made from, so --sync only rewrites captions whose voice changed. Music: animate.py --music FILE,
  --music-volume, --no-music; music.* in the video folder or ~/snackcode-ai.
- `hinglish.py` + `hindi_words.json`  to_roman() is the letter-by-letter fallback for captions;
  English terms show in real English on screen (automation, never otomeshan): learn_words() asks gemma once and saves
  to caption_words.json; fix_screen_text() corrects headings and card labels. to_hindi() spells Roman lines word by word. `voice_check.py`  Whisper score per clip (venv, CPU), run by voice.py.
- `research.py`, `script.py`  older single-step versions (still work on ./research, ./scripts)
- `voices/narrator.wav`  10-20 s reference voice for Chatterbox (owner's own voice only)
- `projects/<slug>/`  one folder per video: research/notes.md, research/sources.json,
  scripts/outline.json, scripts/script.json, metadata.md, audio/, images/, output/
- `fonts/*.ttf`, `music.mp3`  optional; animate.py uses them if present
- SearXNG runs in Docker (`docker start searxng`), config in `searxng/settings.yml`
  (`search.formats` must include `json`).

## Two Python environments (important)
- `venv`        research, scripts, animation: `source venv/bin/activate`
                (requests, trafilatura, ollama, soundfile, kokoro, faster-whisper, torch)
- `venv-voice`  Chatterbox only (uv venv, Python 3.11): run as `venv-voice/bin/python voice.py`
                Needed `uv pip install --python venv-voice/bin/python "setuptools<81" peft`
                because uv venvs have no setuptools and Chatterbox's watermark module needs it.
`auto_video.py --render` picks venv-voice for voice.py automatically.

## Commands
```bash
cd ~/snackcode-ai && source venv/bin/activate && docker start searxng
python auto_video.py --file topics.txt            # scripts for every title
python auto_video.py --file topics.txt --render   # + voice + video
python auto_video.py "Title" --force              # redo one video from scratch
cd projects/<slug>
../../venv-voice/bin/python ../../voice.py --redo     # all scenes
../../venv-voice/bin/python ../../voice.py --scene 8  # one scene after editing
python ../../animate.py --preview                     # first 3 scenes
python ../../animate.py                               # full: output/animated.mp4 + .srt
```
animate.py flags: `--theme emerald|violet|ocean|sunset|crimson`, `--no-mascot`, `--no-sfx`, `--one-colour`.
voice.py flags: `--lang hi|en`, `--voice file.wav`, `--engine chatterbox|kokoro`.

## script.json format
```json
{"title": "...", "topic": "...", "theme": "crimson",
 "scenes": [{"on_screen": "3-6 word heading", "narration_hi": "Devanagari",
   "beats": [{"say": "Hinglish 1-2 sentences", "say_hi": "same in Devanagari",
              "visual": {"type": "phone_call", "caller": "..."},
              "mood": "shock", "pop": "OTP"}]}]}
```
- Beat visual types: title (first beat only), chapter (`part`, `total`: the card between parts),
  host, kinetic, icon, phone_call, phone_sms,
  chat, steps, compare, stat, warning, flow, term, pen, map, photo; `image` is used automatically when
  `images/scene_XX.png` exists. Fields for the last four are in readme.md ("What's on screen").
- Icons: phone shield lock bank money warning user hacker globe laptop wifi chip ram bug
  ai key sim mail check cross.
- mood (drives the mascot face AND voice emotion): happy, shock, think, warn, explain.
- pop = 1-2 word sticker shown when that word is spoken (max 1 per scene).
- Old scripts with only `narration` / one `visual` per scene still work (auto-split into beats).

## How the pieces fit
- auto_video.py: Qwen3 writes search queries -> SearXNG -> trafilatura reads <=8 sources ->
  facts per source (unrelated -> NONE, skipped) -> story outline (opening + roadmap of questions
  -> parts -> ending) -> each part written as plain text, not JSON -> split into beats -> visuals
  picked per scene -> Devanagari one sentence at a time -> metadata.md. Part cards, the roadmap
  and the 1930 ending are added by code. Checks: numbers not in the notes, repeated sentences
  (removed), Devanagari on screen, English text, too short; what can't be fixed goes to
  scripts/review.md. Saves progress (outline.json, scenes_partial.json) so a rerun resumes.
  Skips videos that already have script.json unless --force.
- Every video gets its own shape (SHAPES_BY_KIND) and section count, picked from the title: never announce a fixed
  "3 sawaal" roadmap or reuse one set of questions. The intro is built from 4 checked sentences (hook, topic, why, tease).
- balance_visuals limits repeated cards (compare, steps...) and adds real photos and 3D symbols. photos.py asks the
  gemma vision model to reject faces, slides and text; queries must be things a camera can photograph.
- Don't give the writing model a worked example: qwen3:8b copied it into the video even when told
  not to (a Supreme Court video opened with an electricity-bill story).
- `llm()` retries on Ollama errors (e.g. "token repeat limit reached"), bad JSON and
  incomplete answers, raising temperature/repeat_penalty each try, with num_predict caps;
  last try runs without JSON mode and extracts the JSON from text.
- voice.py: fills missing `say_hi` with Ollama (then unloads it), Chatterbox per beat with
  mood -> (exaggeration, cfg_weight), trims silence, writes audio/scene_XX.wav,
  scene_XX_bYY.wav and scene_XX.json `{"beats":[{"start","dur"}],"total"}`.
- animate.py: uses scene_XX.json for exact beat timing (falls back to text-length split);
  captions are timed per beat. Render loop: background -> beat visual (slide transition
  between beats) -> heading -> camera (push-in, punch-in zooms, shake) -> mascot "Byte"
  (lip-sync from voice loudness) -> sticker -> captions -> wipe between scenes -> logo +
  progress bar. Sound effects (whoosh, pop, ding, ring, alarm, tick, riser) are generated
  in code and mixed with voice and optional music. Theme/background picked from the title hash.
- Render speed ~29 fps on this laptop (10-min video ~= 10 min render).

## Known issues / open items
- Script language: the writer is gemma3:4b writing Devanagari; `say` is generated from `say_hi`. qwen3:8b can't
  fix Hindi grammar (tested) and translates when converting scripts, so it only does research, outline, visuals.
- News: gemma still sometimes states an allegation as fact. Keep the `"reviewed": true` lock in place.
- Voice: settings barely change accuracy (tested 9 combinations); best takes via Whisper is what works. Whisper
  itself hears डेटा as देटा, so voice_check compares consonant sounds, not exact letters.
- Chatterbox logs "Detected 2x repetition" / "forcing EOS": normal safety stop, but it can
  cut the last word of a beat. Check scene_XX_bYY.wav files and re-run `--scene N`.
  Idea not built yet: auto-detect short clips (duration vs text length) and retry them.
- qwen3:8b Hindi is OK but makes factual mistakes; always check research/notes.md against
  the source links before publishing.
- RTX 3050 6 GB is too small for useful local image/video generation; use screen
  recordings (OBS) in images/ and Canva for thumbnails.

## Topic backlog (topics.txt)
Voice-clone scam ("Beta ki awaaz..."), UPI 100 Second Mein, investment scam
(Rs 19,813 crore lost in 2025 per I4C via McAfee report), "Agar internet 24 ghante band
ho jaye to?". More ideas: OTP 100 Second Mein, deepfake checks, call forwarding scam,
e-challan scam, phone hack check, link-less scam messages, RBI "donation" fee scam
(verify on rbi.org.in first).

## Working rules for Claude in this repo
- Keep scripts runnable offline; no paid APIs or API keys.
- Test changes with `animate.py --preview` before full renders; look at extracted frames.
- Hinglish (Roman) for anything on screen; Devanagari only for the voice text.
- Don't invent facts or numbers in scripts; every fact must come from research notes.
- Explain every hard term for a first-time listener; put new terms in glossary.py, written by hand.
