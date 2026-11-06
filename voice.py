"""
Snack Code - Step 5: realistic voiceover, one clip per BEAT (exact sync with the animation)

Engines:
    chatterbox (default)  Chatterbox Multilingual by Resemble AI (MIT license), realistic Hindi
                          and English, emotion control, can narrate in YOUR voice.
    kokoro                the old fast voice, as a fallback

Your narrator voice (recommended):
    Record 10-20 seconds of yourself speaking Hindi naturally (quiet room, phone is fine)
    and save it as voices/narrator.wav in ~/snackcode-ai. Every video is then narrated
    in your voice. Only use a voice you have the right to use (your own).

Reads:   scripts/script.json
Writes:  audio/scene_XX.wav (the scene), audio/scene_XX_bYY.wav (each beat),
         audio/scene_XX.json (exact beat timing, used by animate.py)
Adds:    "say_hi" (Devanagari) to every beat in script.json, so you can correct the Hindi

Usage:
    python voice.py                      # Hindi, Chatterbox, your voice if voices/narrator.wav exists
    python voice.py --lang en            # English narration (uses the "say" text directly)
    python voice.py --voice my_clip.wav  # use a different reference voice
    python voice.py --engine kokoro      # old voice
    python voice.py --redo               # regenerate all scenes
    python voice.py --scene 3            # regenerate only scene 3 (after you edit it)
    python voice.py --no-check           # skip the Whisper check (faster, but bad takes stay)

Emotion: each sentence gets its own delivery from its words and punctuation. For much stronger emotion,
record 8-15 s of yourself in that mood as voices/narrator_shock.wav, _warn, _happy, _think or _explain.
Each mood then copies your own delivery. Without them, voices/narrator.wav is used for every mood.

Accuracy: Whisper listens to every line after generating. Lines it can't match are generated again, up to
TAKES times, and the best take is kept. Anything still weak is listed in audio/voice_check.md.
"""
import inspect
import json
import os
import re
import subprocess
import sys
import tempfile
import time

import numpy as np
import soundfile as sf

from hindi_text import leftovers, spoken_hi

SCRIPT ="scripts/script.json"
PAUSE = 0.18          # silence between beats (seconds)
MAX_CHARS = 150       # Chatterbox sounds best on short pieces
SENTENCE_PAUSE = {"?": 0.34, "!": 0.30, "।": 0.24, ".": 0.24, ",": 0.10}
TAKES = 3             # tries per line when Whisper can't match it
GOOD_SCORE = 0.80     # a take scoring this or more is accepted


def arg(name, default=None):
    if name in sys.argv and sys.argv.index(name) + 1 < len(sys.argv):
        return sys.argv[sys.argv.index(name) + 1]
    return default


ENGINE = arg("--engine", "chatterbox")
LANG = arg("--lang", "hi")
REDO = "--redo" in sys.argv
ONLY = arg("--scene")
ONLY = int(ONLY) if ONLY is not None else None
here = os.path.dirname(os.path.abspath(__file__))
VOICE = arg("--voice") or next((p for p in ("voices/narrator.wav", os.path.join(here, "voices", "narrator.wav"))
                                if os.path.exists(p)), None)

# mood -> (exaggeration, cfg_weight): more drama for shock/warn, calmer for think
MOOD_STYLE = {"shock": (1.05, 0.40), "warn": (0.90, 0.45), "happy": (0.80, 0.45),
              "think": (0.55, 0.50), "explain": (0.60, 0.50)}
WARN_WORDS = re.compile(r"सावधान|खतरा|खतरनाक|नकली|ठग|धोखा|मत\s|कभी नहीं|बिल्कुल नहीं|हरगिज़")
SHOCK_WORDS = re.compile(r"!|चौंक|हैरान|असली खेल|गायब|अचानक|सब कुछ")
HAPPY_WORDS = re.compile(r"मज़े की|अच्छी बात|बधाई|कमाल|आसान")
THINK_WORDS = re.compile(r"\?|सोचो|लेकिन|क्यों")


def sentence_mood(text, beat_mood):
    """Delivery for one sentence: its words first, then the mood the script gave the beat."""
    if WARN_WORDS.search(text):
        return "warn"
    if SHOCK_WORDS.search(text):
        return "shock"
    if HAPPY_WORDS.search(text):
        return "happy"
    if THINK_WORDS.search(text):
        return "think"
    return beat_mood if beat_mood in MOOD_STYLE else "explain"


def has_devanagari(text):
    return bool(re.search(r"[ऀ-ॿ]", str(text)))


def split_sentences(text):
    """Sentences, with any too long for the voice model split again at a comma."""
    parts = []
    for sentence in re.split(r"(?<=[.?!।])\s+", text.strip()):
        cur = ""
        for piece in re.split(r"(?<=,)\s+", sentence):
            if cur and len(cur) + len(piece) + 1 > MAX_CHARS:
                parts.append(cur)
                cur = piece
            else:
                cur = f"{cur} {piece}".strip()
        if cur:
            parts.append(cur)
    return parts or [text]


def trim(audio, sr, threshold=0.015, keep=0.04):
    """Cut silence at the start and end of a clip, keep a little air."""
    if len(audio) == 0:
        return audio
    loud = np.where(np.abs(audio) > threshold * (np.abs(audio).max() + 1e-9))[0]
    if len(loud) == 0:
        return audio
    a = max(0, loud[0] - int(keep * sr))
    b = min(len(audio), loud[-1] + int(keep * sr * 2))
    return audio[a:b]


def normalize(audio, peak=0.89):
    m = np.abs(audio).max()
    return audio * (peak / m) if m > 0 else audio


# ---------------------------------------------------------------- load script and beats
script = json.load(open(SCRIPT, encoding="utf-8"))
scenes = script["scenes"]


def scene_beats(scene):
    beats = [b for b in (scene.get("beats") or []) if isinstance(b, dict) and str(b.get("say", "")).strip()]
    if beats:
        return beats, True
    # old-style scene: one beat with the whole narration
    return [{"say": scene.get("narration", ""), "say_hi": scene.get("narration_hi", ""), "mood": "explain"}], False


todo = []
for i, scene in enumerate(scenes):
    if ONLY is not None and i != ONLY:
        continue
    wav, tim = f"audio/scene_{i:02d}.wav", f"audio/scene_{i:02d}.json"
    if os.path.exists(wav) and not os.path.exists(tim) and not REDO and ONLY is None:
        print(f"  scene {i:02d}: keeping existing audio (your own recording?). Use --redo to regenerate.")
        continue
    if os.path.exists(wav) and os.path.exists(tim) and not REDO and ONLY is None:
        print(f"  scene {i:02d}: already done")
        continue
    todo.append(i)

if not todo:
    print("Nothing to do.")
    raise SystemExit(0)
os.makedirs("audio", exist_ok=True)

# ---------------------------------------------------------------- Devanagari for every beat (Hindi)
if LANG == "hi":
    missing = [(i, b) for i in todo for b in scene_beats(scenes[i])[0] if not has_devanagari(b.get("say_hi", ""))]
    if missing:
        print(f"Spelling {len(missing)} lines in Devanagari ...")
        from hinglish import to_hindi
        for i, b in missing:
            b["say_hi"], left = to_hindi(b["say"])
            if left:
                print(f"  no spelling yet for: {', '.join(left)} (add to hindi_words.json)")
        for i in todo:  # keep old-style scenes in sync
            beats, real = scene_beats(scenes[i])
            if not real and has_devanagari(beats[0].get("say_hi", "")):
                scenes[i]["narration_hi"] = beats[0]["say_hi"]
        json.dump(script, open(SCRIPT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print("Saved the Hindi text into script.json (edit 'say_hi' there to fix any word).")


# ---------------------------------------------------------------- free the GPU
def unload_ollama(wait=30):
    """Ollama keeps models in GPU memory after use, and 6 GB can't hold them and the voice model."""
    try:
        import ollama
        loaded = [m.model for m in ollama.ps().models]
        for name in loaded:
            print(f"Unloading {name} from the GPU ...")
            ollama.generate(model=name, prompt="", keep_alive=0)
        for _ in range(wait):
            if not ollama.ps().models:
                return
            time.sleep(1)
        print("Warning: Ollama still has a model loaded; the voice model may run out of memory.")
    except Exception:  # Ollama not running: nothing to unload
        pass


unload_ollama()

# ---------------------------------------------------------------- voice engine
if ENGINE == "chatterbox":
    import torch
    import perth

    if getattr(perth, "PerthImplicitWatermarker", None) is None:
        # find out why the watermark module did not load, and say how to fix it
        try:
            from perth.perth_net.perth_net_implicit.perth_watermarker import PerthImplicitWatermarker  # noqa
            reason = "unknown"
        except Exception as e:
            reason = f"{type(e).__name__}: {e}"
        hint = ("uv pip install --python venv-voice/bin/python \"setuptools<81\""
                if "pkg_resources" in reason or "setuptools" in reason
                else "uv pip install --python venv-voice/bin/python <the missing package named above>")
        raise SystemExit(f"\nChatterbox's watermark module could not load: {reason}\n"
                         f"Fix it from ~/snackcode-ai with:\n    {hint}\nthen run voice.py again.")

    from chatterbox.mtl_tts import ChatterboxMultilingualTTS

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Loading Chatterbox Multilingual on {device} ...")
    tts = ChatterboxMultilingualTTS.from_pretrained(device=device)
    SR = tts.sr
    accepted = set(inspect.signature(tts.generate).parameters)
    VOICES = {m: p for m in MOOD_STYLE for p in [os.path.join(os.path.dirname(VOICE or "voices/x"), f"narrator_{m}.wav")]
              if os.path.exists(p)}
    if VOICES:
        print(f"Your mood recordings: {', '.join(VOICES)}")
    if VOICE:
        print(f"Narrator voice: {VOICE}")
    else:
        print("No voices/narrator.wav found: using the built-in voice. "
              "Record 10-20 s of your own voice for a much more natural result.")

    def speak(text, mood, seed):
        exag, cfg = MOOD_STYLE.get(mood, MOOD_STYLE["explain"])
        params = {"language_id": LANG, "audio_prompt_path": VOICE, "exaggeration": exag,
                  "cfg_weight": cfg, "cfg": cfg, "temperature": 0.7}
        params = {k: v for k, v in params.items() if k in accepted and v is not None}
        for voice in VOICES.get(mood), VOICE:
            if voice:
                params["audio_prompt_path"] = voice
                break
        torch.manual_seed(seed)
        wav = tts.generate(text, **params)
        wav = wav.squeeze().detach().cpu().numpy() if hasattr(wav, "detach") else np.asarray(wav).squeeze()
        return trim(wav.astype(np.float32), SR)

elif ENGINE == "kokoro":
    from kokoro import KPipeline

    SR = 24000
    kp = KPipeline(lang_code="h" if LANG == "hi" else "a")
    kvoice = ("hf_alpha" if "--female" in sys.argv else "hm_omega") if LANG == "hi" else "am_michael"

    def speak(text, mood, seed):
        parts = [a for _, _, a in kp(text, voice=kvoice, speed=1.0)]
        return trim(np.concatenate([np.asarray(p) for p in parts]).astype(np.float32), SR)
else:
    raise SystemExit("Unknown engine. Use --engine chatterbox or --engine kokoro")

# ---------------------------------------------------------------- generate
def speak_beat(text, mood, seed):
    """One beat, sentence by sentence: each with its own delivery, then a natural pause."""
    clips = []
    parts = split_sentences(text) if LANG == "hi" and ENGINE == "chatterbox" else [text]
    for k, part in enumerate(parts):
        clips.append(speak(part, sentence_mood(part, mood), seed + k * 7))
        if k < len(parts) - 1:
            clips.append(np.zeros(int(SENTENCE_PAUSE.get(part[-1], 0.15) * SR), np.float32))
    return np.concatenate(clips)


def score_clips(clips):
    """Ask Whisper how well each clip says its text. Needs the normal venv; if it's missing, skip the check."""
    python = os.path.join(here, "venv", "bin", "python")
    if not os.path.exists(python):
        return None
    with tempfile.TemporaryDirectory() as tmp:
        ask, answer = os.path.join(tmp, "clips.json"), os.path.join(tmp, "scores.json")
        json.dump(clips, open(ask, "w", encoding="utf-8"), ensure_ascii=False)
        done = subprocess.run([python, os.path.join(here, "voice_check.py"), ask, answer],
                              capture_output=True, text=True, env={**os.environ, "CUDA_VISIBLE_DEVICES": ""})
        if done.returncode != 0:
            print(f"Voice check skipped: {done.stderr.strip()[-200:]}")
            return None
        return json.load(open(answer, encoding="utf-8"))


lines = {}
for i in todo:
    beats, real = scene_beats(scenes[i])
    for j, b in enumerate(beats):
        text = (b.get("say_hi") if LANG == "hi" and has_devanagari(b.get("say_hi", "")) else b.get("say", "")).strip()
        if not text:
            continue
        if LANG == "hi":
            text = spoken_hi(text)
            if leftovers(text):
                print(f"  scene {i:02d} beat {j:02d}: model will guess these English words: "
                      f"{', '.join(leftovers(text))} (write them in Hindi in say_hi to fix)")
        path = f"audio/scene_{i:02d}_b{j:02d}.wav"
        audio = speak_beat(text, b.get("mood", "explain"), seed=i * 100 + j)
        sf.write(path, normalize(audio), SR)
        lines[(i, j)] = {"file": path, "text": text, "mood": b.get("mood", "explain"), "audio": audio, "score": None}
    print(f"  scene {i:02d}: voiced", flush=True)

# ----- listen back: generate weak lines again and keep the best take
if LANG == "hi" and "--no-check" not in sys.argv and lines:
    weak = list(lines)
    for take in range(TAKES):
        print(f"Checking {len(weak)} lines with Whisper ...", flush=True)
        scores = score_clips([{"file": lines[k]["file"] if take == 0 else f"{lines[k]['file']}.try.wav",
                               "text": lines[k]["text"]} for k in weak])
        if scores is None:
            break
        for k, s in zip(weak, scores):
            line = lines[k]
            if line["score"] is None or s["score"] > line["score"]:
                line["score"], line["heard"] = s["score"], s["heard"]
                if take:
                    line["audio"] = line.pop("candidate")
                    sf.write(line["file"], normalize(line["audio"]), SR)
            line.pop("candidate", None)
        weak = [k for k in weak if lines[k]["score"] < GOOD_SCORE]
        if not weak or take == TAKES - 1:
            break
        print(f"  {len(weak)} lines need another take", flush=True)
        for k in weak:
            line = lines[k]
            line["candidate"] = speak_beat(line["text"], line["mood"], seed=k[0] * 100 + k[1] + 1000 * (take + 1))
            sf.write(f"{line['file']}.try.wav", normalize(line["candidate"]), SR)
    for line in lines.values():
        if os.path.exists(f"{line['file']}.try.wav"):
            os.remove(f"{line['file']}.try.wav")
    scored = [v for v in lines.values() if v["score"] is not None]
    if scored:
        bad = sorted([v for v in scored if v["score"] < GOOD_SCORE], key=lambda v: v["score"])
        print(f"Voice check: average {sum(v['score'] for v in scored) / len(scored):.2f}, "
              f"{len(bad)} of {len(scored)} lines below {GOOD_SCORE}")
        with open("audio/voice_check.md", "w", encoding="utf-8") as f:
            f.write("# Lines to listen to\n\nWhisper couldn't match these well. It can be wrong, so listen first. "
                    "To fix one, edit say_hi and run voice.py --scene N.\n\n")
            for v in bad:
                f.write(f"- {v['file']} ({v['score']})\n  - script: {v['text']}\n  - heard: {v.get('heard', '')}\n")

# ----- join the final takes into scenes
for i in todo:
    beats, real = scene_beats(scenes[i])
    clips, timing, cursor = [], [], 0.0
    for j in range(len(beats)):
        if (i, j) not in lines:
            continue
        audio = lines[(i, j)]["audio"]
        clips.append(audio)
        dur = len(audio) / SR
        timing.append({"start": round(cursor, 3), "dur": round(dur, 3)})
        cursor += dur
        if j < len(beats) - 1:
            clips.append(np.zeros(int(PAUSE * SR), np.float32))
            cursor += PAUSE
    if not clips:
        continue
    scene_audio = normalize(np.concatenate(clips))
    sf.write(f"audio/scene_{i:02d}.wav", scene_audio, SR)
    json.dump({"beats": timing if real else [], "total": round(len(scene_audio) / SR, 3), "engine": ENGINE},
              open(f"audio/scene_{i:02d}.json", "w"), indent=2)
    print(f"  scene {i:02d}: {len(timing)} beats, {len(scene_audio) / SR:.1f}s")

print("Done. Listen to a few files in the audio folder, then run animate.py.")
