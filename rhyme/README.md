# Rhymes

Original Hindi nursery rhymes (bal geet) as bright cartoon music videos, for a kids' YouTube channel. Separate from
Snack Code and from the story serial. Everything is local: the music, the cartoons and the backgrounds are made in
code (no licences), the voice is Chatterbox, the words come from you (a local model can draft them).

## Commands

Run from `~/snackcode-ai` with `source venv/bin/activate`.

```bash
python rhyme.py ideas                       # ideas for new rhymes -> rhyme/ideas.txt (12 are there already)
python rhyme.py ideas "good habits"         # more ideas around a theme

python rhyme.py new --pick 1                # a draft of idea 1: rhymes/songs/<slug>/lyrics.txt + review.md
python rhyme.py new "Titli Ke Rang" --about "a butterfly visits flowers of every colour" --tempo 96
python rhyme.py new "My Rhyme" --lyrics my_words.txt      # your own words (stanzas split by blank lines)

python rhyme.py story <slug>                # what the rhyme means, line by line -> story.md (--redo: ask again)

# read story.md (what it means), fix lyrics.txt (see review.md), then:
python rhyme.py make <slug>                 # pictures + voice + video + YouTube kit
python rhyme.py make <slug> --preview       # voice + only the first 30 s of video

python rhyme.py upload <slug> --channel @YourKidsChannel                      # private
python rhyme.py upload a-slug b-slug --start "2026-11-20 17:00" --every 2     # scheduled, one every 2 days

python rhyme.py list                        # every rhyme and how far it has got
python rhyme.py cast                        # rhymes/cast.png: all the cartoon characters
python rhyme.py sync|voice|render|kit|guide <slug>     # one step on its own
python rhyme.py render <slug> --drawn       # ignore the pictures, drawn cartoons only
python rhyme.py render <slug> --chant       # the spoken chant instead of the AI singing
python rhyme.py clips <slug>                # real 3D cartoon motion: every picture -> an AI clip (see below)
```

## First: what the rhyme means (story.md, automatic)

Before any picture is planned, three local agents read the song (`rhyme/story.py`):

1. **Explainer** (qwen3:8b): the rhyme in plain English (what happens, the lesson), who is who (a name the song
   uses, like "लियो/Leo", is mapped to the animal: the title's animal is the main character), and for every line:
   what it means, who is in it, where it happens, and what we SEE happen.
2. **Checker** (qwen3:8b): reads the Hindi again next to the explanation and corrects it.
3. **Hindi checker** (gemma3:4b, better Hindi): marks lines that make no sense; words not for small children too.

Then code rules: a character named in a line is always in its picture, only characters we can draw, max 3.
`story.md` is for you (read it first: if the meaning is wrong, the video will be too); `story.json` is what the
pictures and clips are made from. Edit `meaning` / `who` / `doing` there to correct a line (kept until the lyrics
change). A line whose meaning or cast changes gets a new picture plan and a new AI picture (your own files stay).
`new` runs it straight after writing: lines that make no sense are written again once, the rest go to review.md.
Why: Lion Ki Ladoo was drawn with Golu and Chinki and no lion: the song calls the lion "लियो", and the old word
matching only knew शेर. Titles in English ("Lion", "Cat", "Train") are now understood too.

## Pictures: the 3D cartoon look (automatic)

- **One picture per line**, in a "3D animated film" style. For each line qwen writes a `setting` in pictures.json
  (what the line is about: a bedroom for sleeping, a swing for swinging...), never containing the song's own
  characters; night songs stay at night. Edit a `setting`, then `python rhyme.py pictures <slug> --no-model
  --redo-picture p05,p09` (several at once) redraws just those.
- **Pictures that act out the line:** the planner also writes an `action`. When the line's description has an
  action a standing cut-out can't show (sleeping, swinging, washing, eating... `ACTIONS` in pictures.py), the
  picture is drawn WITH the children doing it (action phrase first in the prompt, `ACTION_PHRASES`); the moon and
  stars are still added small in a top corner. A line about children brings Golu (and Chinki) into its picture.
  Golu and Chinki are always described with the same short phrase (`KID` in draw_ai.py), in their cast art too,
  so they look like the same children everywhere.
- **Animation:** transitions change every picture (iris at a new part, push, zoom, fade), the camera always moves,
  characters dance in the chorus (side steps, bigger hops), jump at every line, turn round, lean; the moon and
  stars glow, twinkle and rock; fireflies at night, confetti in the chorus, a burst of little stars when a line
  starts. Karaoke words light up exactly when sung, the word being sung jumps and grows.
- **Quick start, no dead air** (align.py, automatic): the AI song's long music-only intro is cut to 3 s (the title
  drops in letter by letter with a burst of stars, then the first line is sung), breaks between lines longer than
  4 s are cut to ~2.5 s and the ending to the 5 s end card, all with crossfades -> audio/song_edit.wav (song.wav is
  never changed). Chanda Ki Lori: singing started at 28 s, now at 3 s; 170 s -> 127 s.
- **Word stickers:** when a character's name is sung (चंदा, तारा, बच्चे... `lyrics.WHO`, using its cast art) or a
  love word (प्यार -> heart) or a sleep word (सो, नींद, लोरी -> Z z z), a sticker pops in at the side, wiggles and
  shrinks away, with a pop sound (`STICKER_WORDS` in video.py). One a line at most.
- **The picture bounces to the music:** on every beat in the chorus, every bar in the verses.
- **Like a real cartoon, no repeats:** every clip plays once, forwards. A line longer than ~6 s gets a SECOND clip
  that carries on from the last frame of the first (so the dance goes on, never backwards); a little shorter -> up
  to 1.35x slower. Every chorus repeat gets its OWN clip (same picture, new seed, new camera), and every shot has a
  different camera (push in, circle, track, crane, pull back, pan: `CAMERAS` in clips.py). The motion is the line's
  meaning from story.json ("the lion cub eats a red sweet"), not a generic wave.
- **Sound:** the AI song stays in stereo and the mix is set to -14 LUFS (YouTube's loudness), so it isn't quieter
  than other kids' videos.
- **3D camera** (`rhyme/depth.py`): Depth Anything V2 Small (Apache-2.0, ~/.cache/snackcode/depth-anything-v2-small.onnx,
  CPU) guesses what is near and far in every picture; the camera dollies, trucks, cranes and orbits with parallax
  (near things move more), and the cut-out characters move with it. Characters also jump when a line starts,
  lean, and now and then turn round. Depth maps are cached in images/.depth/. Needs opencv-python-headless (venv).
- **Real 3D cartoon motion (AI clips)**: see the next section. With clips, the characters really move (swing,
  sleep, wash, dance) instead of cut-outs hopping on a still picture.
- The channel's name (`channel_name` in rhymes/settings.json: Golu Cartoon) is shown in the corner and on the end
  card; the description gets a subscribe link to `channel` (@GoluCartoon14).

## Real 3D cartoon motion: AI clips (rhyme/clips.py)

Every picture becomes a short moving clip (image-to-video), made on this laptop by **Wan 2.2 TI2V 5B** (Apache-2.0:
fine for a monetised channel) with the **FastWan** 3-step speed-up, run through **WanGP** (`wan2gp/`, low-VRAM
runner; its licence lets you sell what you make and asks for a credit, which the description gets automatically).

- The clip starts from **exactly the frame the video shows** (`images/clips/pNN_start.png`: background + Golu and
  friends in place), so the characters keep their settled look; the model only adds the movement. The motion
  prompt comes from the line's `show` and `action` (`MOVES` in clips.py: sleep -> breathing under the blanket,
  swing -> swinging back and forth, dance -> swaying and hopping...).
- Clips are up to 5 s (121 frames, 1280x704, 24 fps); a longer picture holds the last frame with a slow push-in.
  Each chorus repeat gets its own clip (repeats under 2 s reuse the first). Karaoke, transitions, sparkles, title and end card stay on top.
- `make` does it after the song (about 6-7 minutes a 5 s clip on the RTX 3050, so 1-1.5 hours for a song); a rerun skips finished clips, so you can stop any
  time. Changed a picture? Its clip is remade (the start frame is compared).

```bash
python rhyme.py clips <slug>                      # make the missing clips, then: python rhyme.py render <slug>
python rhyme.py clips <slug> --redo-clip p05,p09  # new tries for clips you didn't like
python rhyme.py clips <slug> --only-clip p09      # just one
python rhyme.py clips <slug> --fast               # 832x480: about 3x quicker, softer
python rhyme.py make <slug> --no-clips            # skip clips this time; render --no-clips ignores existing ones
```

- **Every picture gets a clip**, also sky-only ones (moon, stars, sun): those get a scenery prompt (the moon glows,
  clouds drift, leaves sway) that says "nobody in it" in the prompt AND the negative prompt, because a plain prompt
  made the model invent children. Check them on review.jpg too; `SKY_CLIPS = False` in clips.py turns them off.
- **`make` never quietly falls back to the flat look.** It checks the GPU first (before the song and pictures).
  If clips fail, it tries the missing ones again in low-RAM mode (WanGP profile 5, slower), and if some are still
  missing it STOPS before the video and tells you. Close big programs and run the same `make` again: finished clips
  are kept. Reasons per clip: `images/clips/make.log`. `--allow-2d` renders anyway. Under 8.5 GB free RAM it starts
  in low-RAM mode by itself.
- **The laptop can't freeze any more** (it did once, for 35 minutes: the clip maker needs ~10 GB and had locked 9 GB
  that could never be swapped). Now it locks at most 38% of RAM, runs inside a memory box (`systemd-run`, 3.5 GB
  always left for the desktop), and stops itself cleanly when Linux reports the system is starting to hang.
  Best: close the browser and keep only the terminal open while clips are made (an overnight job).
- The clip prompt says only what is in the start frame: how many characters, each described with the same phrase
  as the pictures (`KID` in pictures.py), the place, the movement, "no other children or people". The line's own
  description is left out on purpose: "love for everyone" made the model add new children.
- **Check `images/clips/review.jpg`** (made after every clips run: start, middle and end frame of each clip). Look
  for a child who wasn't there, a see-through ghost, two heads, a melted hand, clothes changing colour.
- Look at every clip before uploading (images/clips/pNN.mp4): AI video can melt a face or a hand in a fast move.
  Remake a bad one with `--redo-clip pNN` (new seed), or delete it (the picture then gets the 3D camera move).
- Turn clips off for good: `"ai_clips": false` in rhymes/settings.json.
- Setup (done once): `git clone https://github.com/deepbeepmeep/Wan2GP wan2gp`; `uv venv --python 3.11 venv-video`;
  torch 2.7.1 + cu128 (driver 570 can't run the cu130 build WanGP's README asks for), then wan2gp/requirements.txt
  with overrides torchcodec==0.5, onnxruntime-gpu==1.22.0, plus WGPKernels 1.4.3+cu128. Models download to
  wan2gp/ckpts on first use (~14 GB; if a download stalls, set HF_HUB_DISABLE_XET=1). Runs with `--profile 4 --attention sdpa`. Ollama must be off (rhyme.py
  unloads it).

`make` now makes the pictures itself, on this laptop, then animates them: a slow camera move across each picture,
soft crossfades, a moving effect on top (rain, bubbles, sparkles, petals, stars, snow), the karaoke words, the title
and an end card with a Subscribe button.

How:
1. qwen3 reads the Hindi lines and plans about one picture per two lines (`pictures.json`, readable as
   `pictures.md`). A repeated chorus reuses its picture, so a song needs about 10.
2. **Characters are drawn once for the whole channel** (`rhymes/cast_art/<kind>.png`) by the free image model
   SSD-1B (Apache-2.0 licence, fine on a monetised channel), then cut out (`cutout.py`, ISNet). Every song reuses
   them, so Chinki, Golu, the elephant ... look exactly the same in every video. Their looks come from
   `rhymes/cast.json` the first time they're needed.
3. For scenes with characters the model draws **only the background** (it can't draw two characters together
   reliably: it melts them into one). The video puts the characters in front, standing on the ground, and they
   pop in, hop and sway to the beat while the camera slowly moves over the background.
4. The local vision model (gemma3) looks at every picture; a bad one (missing or melted characters, a person in
   a background) is drawn again with a new seed, up to 3 tries. `images/review.jpg` shows them all.

About 10 s a picture, 2-4 minutes a song. Ollama, the image model and the voice model never run at the same time.

```bash
python rhyme.py pictures <slug>                          # plan + draw only; look at images/review.jpg
python rhyme.py pictures <slug> --redo-picture p03       # a new try for one picture (new seed)
python rhyme.py pictures <slug> --redo-picture all       # every AI picture again
python rhyme.py pictures <slug> --redo-character elephant      # a new look for a character (every song!)
python rhyme.py make <slug> --drawn                      # no pictures: the code-drawn cartoons
```

- Pick each character's look before you publish many songs: `--redo-character elephant` until you like it, then
  keep it. Delete nothing in `rhymes/cast_art/` afterwards: it's your channel's cast (back it up).
- A scene that should be one whole picture (e.g. a character doing something special): set `"layers": false` for
  it in pictures.json and `--redo-picture pNN`; the model then draws the character in the scene itself.
- Your own picture always wins: save `images/p03.jpg` (from any tool, or a short clip `p03.mp4`) and it is used
  as it is, never overwritten. `pictures.md` has a ready prompt for each picture.
- Turn AI pictures off for good with `"ai_pictures": false` in rhymes/settings.json.
- Model files (~4.7 GB): ~/.cache/huggingface (segmind/SSD-1B fp16, madebyollin/sdxl-vae-fp16-fix,
  latent-consistency/lcm-lora-ssd-1b) and ~/.cache/snackcode/isnet-general-use.onnx. Chatterbox needs
  diffusers 0.29, so the newer diffusers for pictures lives in `venv-voice/image-libs/`.
- Free online tools: check their terms allow commercial use on your plan and never remove a watermark. Free song
  tools (for example Suno's free plan) are personal use only, so the music stays our own.

## lyrics.txt: the only place the words live

```
title: Medhak Ki Chhalang
tempo: 100            beats per minute (70-140): every line starts on a bar
key: C                C D E F G A Bb

[verse]                               the picture is chosen from the words (मेंढक -> frog, तालाब -> pond ...)
तालाब किनारे रहता मेंढक
...
[chorus]
...
[chorus]                              an empty [chorus] repeats the last one
[verse place=night cast=frog,moon]    choose the picture yourself
सूरज डूबा, हो गई शाम | Suraj dooba, ho gayi shaam     <- ' | Roman' sets the on-screen spelling
```

Places: garden jungle farm pond underwater sky night beach room rail.
Cast (up to 3 per part, the first one sings): boy girl cat dog rabbit elephant lion monkey cow frog duck fish
butterfly sun moon star peacock parrot train.

After editing lyrics.txt, run the step again; it re-reads the file. Only changed lines are voiced again.

## The words: write or rewrite them yourself

`new` drafts the words with the local model (gemma3:4b). It is checked for rhyme (lines 2 and 4, or 1-2 and 3-4),
line length, unsafe words and repeats, and it gets rhyming word pairs to choose from. **But a 4B model writes weak
Hindi verse**: in testing it rhymed but wrote things like "the frog says meow". Treat the draft as a starting point
and rewrite it; a 16-line rhyme is 10 minutes of your time and decides whether children like it. A bigger model
helps: `ollama pull gemma3:12b` and set `"lyrics_model": "gemma3:12b"` in `rhymes/settings.json`.

Use only words you may use: your own, or truly traditional folk rhymes. Most well-known Hindi children's songs from
films and TV (for example "Chanda Mama Door Ke", from a 1955 film) are under copyright.

## The voice: AI singing, or you singing

- **Every line sung, words on screen in time:** each `song` run makes 3 takes (`--takes N`); Whisper (small)
  counts how many lyric lines each take really sings and the best one becomes `audio/song.wav` (all takes stay in
  `audio/takes/`). Whisper's word times drive the karaoke; a line the song skipped shows no text.
- **Real AI singing (default, `"singing": "ai_song"` in rhymes/settings.json):** ACE-Step 1.5 (MIT licence; its
  model card allows commercial use of the songs) sings the lyrics with its own music, locally on the GPU, in about
  30 s. `make` does it automatically; `python rhyme.py song <slug>` makes a new take (each take is different: listen
  to `audio/song.wav`, the one before is `song_previous.wav`; `--seed N` remakes a take, `--style "..."` changes the
  music, lullabies get a soft style by the title). Then Whisper (`rhyme/align.py`, ~1.5 min on the CPU) finds when
  each line is sung, for the karaoke and the pictures. The model sometimes skips, repeats or squeezes a line: those
  are placed between their neighbours and get no karaoke; if a take mangles the words, make another one.
  The singer is the model's own voice (not singer.wav), and there's no tune.py music. Mark it as AI music/voice
  when uploading.
  Install (done): `git clone https://github.com/ace-step/ACE-Step-1.5 ace-step`; models (6.3 GB, without the
  optional 1.7B language model, which doesn't fit 6 GB) in `ace-step/checkpoints`; its own transformers 4.57 /
  diffusers 0.37 and small packages in `venv-voice/ace-libs` (`uv pip install --target ... --no-deps`), using
  venv-voice's torch 2.6.
- **Spoken-and-tuned (old, `"singing": "voice"` or `--chant` for the plain chant):** Chatterbox says each line in a happy voice; then `rhyme/sing.py` turns it into a tune: every
  syllable goes on the beat (about one per eighth note, two bars a line) and is moved to a note that fits the
  chords, with glides and a little vibrato. Every verse gets the same tune, every chorus its own, and the marimba
  plays the tune softly along with it. It sounds like a clean "auto-tuned" voice, not a real singer, and some words
  get less clear than spoken. `--chant` (render/make) goes back to the plain spoken chant on the beat.
  The voice is your `voices/narrator.wav` moved up in pitch, unless you add `rhymes/voices/singer.wav` (10-20 s of
  a clear, cheerful voice; only one you may use) or set `"singer_voice"` in `rhymes/settings.json`.
  Needs `pip install pyworld "setuptools<81"` in venv (done).
- **You singing (best, and YouTube prefers a real person):** `python rhyme.py guide <slug>` writes
  `output/guide.wav` (music + the AI tune to follow) and `output/guide.txt` (when each line starts). Sing along with
  headphones, save your recording from the very start as `audio/vocals.wav`, then `python rhyme.py render <slug>`.
  Your voice replaces the AI, the mouths move to it, and the kit drops the "AI voice" label. Don't change
  lyrics.txt after recording: the timing is fixed in `audio/timing.json`.

## The music

Made fresh for each rhyme: kick, clap and shaker; a bouncy bass; ukulele-like chords (different chords for verse and
chorus); a marimba tune that is louder between lines and softer under the voice; bells at each new part; sound
effects (pop when a character appears, splash by water, twinkle for stars, a clap after the chorus). Your own track
wins: put `music.mp3` in the rhyme's folder (it must match the tempo; the lines don't move to it).

## YouTube

Nursery rhymes must be marked **made for kids** (that's YouTube's rule for content aimed at children; it turns off
comments, the bell and personalised ads, so earnings per view are low). `upload` always does this, uses the Education
category, a "Hindi Rhymes" playlist (`"playlist"` in settings.json) and the channel you give once with `--channel`
(remembered). The first upload to a new channel opens a browser: choose that channel and Allow.

YouTube removes or demonetises kids' channels with low-effort mass-produced videos. What keeps this on the right
side: your own words, your own voice where you can, one rhyme at a time, and watching each video before publishing.

## Folders

```
rhyme.py                    the command
rhyme/                      the code: lyrics.py (writing, checks, pictures), tune.py (music), critters.py (cast),
                            stage.py (backgrounds), video.py (timing, animation, mix), rkit.py (YouTube kit), ideas.txt,
                            pictures.py (picture plan + prompts), draw_ai.py (SSD-1B pictures + checks), cutout.py, motion.py (camera moves, clips, effects),
                            sing.py (chant -> sung melody, cached in audio/sung/)
rhymes/settings.json        channel, singer_voice, playlist, lyrics_model
rhymes/cast.json            recurring characters' looks and the picture style (for picture prompts)
rhymes/cast_art/            each character drawn once (<kind>.png) + its cut-out (<kind>_cut.png)
rhymes/voices/singer.wav    the singing voice (optional)
rhymes/songs/<slug>/        lyrics.txt, review.md, script.json, pictures.md + pictures.json, images/ (p01.jpg ...),
                            audio/ (lines, timing.json, vocals.wav),
                            output/rhyme.mp4 + .srt + guide.wav, youtube/
```
