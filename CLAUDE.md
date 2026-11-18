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

## Story serial (separate pipeline, separate channel)
- `serial.py` + `serial/` (docs: serial/README.md). Traditional/public-domain stories as a Hindi cartoon serial,
  episodes <= 5 min, max 7 per `make` run, upload with `--channel @handle` (own token file per channel).
- Memory: series/<slug>/memory/ facts.jsonl + vectors.npy (nomic-embed-text, falls back to word match) + state.json
  (story so far, character states, open threads). Every episode is written from it; `remember` after edits.
- Agents: scene planner, gemma writer (Hindi lines `Name: line`), director (emotion/action/sfx JSON), continuity
  checker, recap/teaser, summariser. bible.json character looks never change once episodes exist.
- Art is drawn in code (cartoon.py characters, scenery.py places), sound in code (sound.py), so no licences.
- upload.py now takes --channel/--video/--subtitles/--category/--kids/--playlist; defaults are unchanged for Snack Code.
- Three channels, one Google Cloud project (one client_secret.json, shared daily quota), one token file per channel:
  projects/ -> Snack Code @snackcode108 (youtube_token.json); rhymes/ -> Golu Cartoon @GoluCartoon14 (rhymes/settings.json);
  series/ -> story channel (series/settings.json, set by the first `serial.py upload --channel`; series.json overrides).
  `python upload.py --check --channel @handle` logs in and verifies a channel without uploading. serial.py refuses
  the Snack Code / rhymes handles.
- Serial writing flow: qwen writes each scene as an ENGLISH script (say_en) -> continuity check (plan events are the
  truth, later episodes' events are 'not yet') -> director -> gemma translates to Hindi (say_hi) with a fixed name
  spelling list (series glossary.json) -> qwen meaning check + name check -> retranslate. gemma writing the story
  directly misread events ('no children' -> 'children missing'). Arcs: events listed, arc-boundary agent drops
  other arcs' events, code splits ~3.5 events per episode. Cast lock: scenes only use the episode's characters.
- Local models still make factual and Hindi mistakes: plans for big epics should be hand-checked (Ramayan's is
  hand-written), and every episode needs a human read of review.md. series.json hindi_model/story_model.
- After suspend, torch loses CUDA: sudo rmmod nvidia_uvm && sudo modprobe nvidia_uvm. voice_run stops unless --cpu.

## Rhymes (separate pipeline, kids' channel)
- `rhyme.py` + `rhyme/` (docs: rhyme/README.md), data in `rhymes/` (settings.json, voices/, songs/<slug>/).
  Original Hindi bal geet as cartoon music videos (~1.5-2 min). `rhymes/songs/<slug>/lyrics.txt` is the only source of the words;
  every step re-syncs script.json + review.md from it. `[verse place=.. cast=..]` overrides the picture.
- Singing (default): rhyme/song_ai.py runs ACE-Step 1.5 turbo (MIT, ace-step/, 6.3 GB, no LM; venv-voice + ace-libs with
  transformers 4.57/diffusers 0.37) -> audio/song.wav (song + music, ~30 s); align.py (Whisper medium word times, DP
  match on consonant skeletons) -> audio/song_timing.json, used by video.py instead of tune.py + sing.py. `rhyme.py song`.
  3 takes per song, the one Whisper hears every line in is kept (chanda: 17/24 -> 24/24); karaoke uses word times.
- Pictures: one per line, 3D-film STYLE, qwen writes setting (no cast in it) + action; acting lines (sleep/swing/wash..)
  are whole pictures with the action phrase FIRST (77-token limit); KID phrase keeps Golu/Chinki identical.
  motion.py: depth.py parallax camera, transitions, dances, glows, particles. Channel: Golu Cartoon @GoluCartoon14.
- AI clips (rhyme/clips.py, `rhyme.py clips`, part of `make`): every picture -> 5 s image-to-video clip by Wan 2.2 TI2V 5B
  (Apache-2.0) + FastWan LoRA (3 steps) via WanGP (wan2gp/, venv-video: py3.11, torch 2.7.1 cu128 because driver 570
  can't run cu130; wgpkernels cu128; --profile 4 --attention sdpa). Start frame = motion.compose_still (characters
  in place) so looks stay; images/clips/pNN.mp4 used by motion.PictureTrack when newer than the picture. HF xet
  downloads stall here: use HF_HUB_DISABLE_XET=1. Credit 'WanGP (Wan 2.2)' goes in the description (licence).
  Sky-only pictures get scenery clips ('nobody in it' in prompt + negative; plain prompts invented children). make STOPS before rendering if clips are missing (retry once with --low-ram = WanGP profile 5; <8.5 GB free RAM starts there; reasons in images/clips/make.log; --allow-2d overrides). haathi-ka-hatha came out 2D because align.py set CUDA_VISIBLE_DEVICES='' (Whisper on CPU) inside make and the clip maker inherited it: now align restores it (cpu_only) and clips() strips it from the child env. Clip prompt = only what's in
  the start frame (count + KID phrase + setting), never the line's `show` ("love for everyone" added new kids).
  ~6.7 min a 5 s clip, ~10 GB RAM (model 5 GB + umt5 text encoder 6.4 GB): never run Whisper/other big jobs alongside.
  18 Nov: WanGP pinned 60% of RAM (default) -> swap filled, laptop frozen 35 min. Now: --perc-reserved-mem-max 0.38,
  ram_watchdog (stops at 'full' memory pressure >30% or <0.5 GB, exit 3), rhyme.py runs it in systemd-run --user
  --scope MemoryMax=total-3.5G MemorySwapMax=1G, and make checks the GPU (gpu_check) before any long step.
- story.py (before pictures, in make/new/pictures; `rhyme.py story`): explainer + checker (qwen) + Hindi checker (gemma)
  -> story.json (per line meaning/who/where/doing) + story.md. lyrics.plan/pictures.slots take cast per LINE from it
  (names like लियो map to lion; kinds_in_title knows English titles). Changed story_key -> re-plan + redraw that AI
  picture. new: unclear lines rewritten once (mend_unclear). Clips: prompt motion = story doing, CAMERAS per shot,
  own clip per chorus repeat (>=2 s), lines >~6 s get a continuation clip from the last frame; no forwards-backwards
  loop (Clip stretch <=1.35x, then push-in on the last frame). Lion Ki Ladoo had no lion before this.
- align.py also edits the AI song (song_edit.wav): intro 3 s, breaks <= ~2.5 s, short ending, crossfades; Whisper
  words cached in audio/song_words.json, EDIT_VERSION bump re-edits old songs. video.py: stereo, -14 LUFS loudnorm,
  word stickers (lyrics.WHO + STICKER_WORDS), beat bounce in chorus, AI clips loop forwards-backwards.
- Music (tune.py) is on one tempo grid; video.py puts every line on a bar and time-stretches the chant (pitch kept).
  Chatterbox can't sing: sing.py (pyworld/WORLD) re-pitches the chant per syllable onto a melody that fits tune.py's
  chords (2 bars a line, same tune per verse; --chant = old chant). Whisper clarity: chant 0.95, sung ~0.65. Owner singing to output/guide.wav as audio/vocals.wav replaces it
  (timing frozen in audio/timing.json). Voice uses serial/voice_run.py with rhymes/bible.json (speaker "singer").
- gemma3:4b lyric drafts rhyme (RHYME_PAIRS help) but make nonsense ("frog says meow"): always human-rewritten.
  No film/TV songs (copyrighted). Uploads always made-for-kids, category education.
- Pictures: `make` plans them (pictures.py, qwen); draw_ai.py (venv-voice, SSD-1B + LCM-LoRA, diffusers 0.43 in
  venv-voice/image-libs because Chatterbox pins 0.29; venv torch has no CUDA on driver 570) draws each character ONCE
  (rhymes/cast_art, cut out by cutout.py/ISNet in venv) and backgrounds only for character scenes (SSD-1B melts two
  characters together); motion.py composites + animates them. gemma3 vision checks each, 3 tries. Load the SD pipe
  once per run (twice = out of memory, 16 GB). Owner files (pNN.jpg/mp4) beat AI pNN.png. Free tiers only: Suno
  free is non-commercial, so music stays tune.py.

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
- RTX 3050 6 GB: SSD-1B (fp16, LCM, cpu offload) makes 1344x768 images in ~9 s; video generation is still too big.

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
