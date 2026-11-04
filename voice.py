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
"""
import inspect
import json
import os
import re
import sys
import time

import numpy as np
import soundfile as sf

from hindi_text import leftovers, spoken_hi

SCRIPT ="scripts/script.json"
LLM_MODEL = "qwen3:8b"
PAUSE = 0.18          # silence between beats (seconds)
MAX_CHARS = 260       # Chatterbox sounds best on short pieces


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
MOOD_STYLE = {"shock": (0.75, 0.35), "warn": (0.65, 0.40), "happy": (0.60, 0.45),
              "think": (0.45, 0.50), "explain": (0.50, 0.50)}


def has_devanagari(text):
    return bool(re.search(r"[ऀ-ॿ]", str(text)))


def split_long(text, limit=MAX_CHARS):
    parts, cur = [], ""
    for piece in re.split(r"(?<=[.?!।,])\s+", text.strip()):
        if cur and len(cur) + len(piece) + 1 > limit:
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
        print(f"Converting {len(missing)} beats to Devanagari with {LLM_MODEL} ...")
        import ollama
        for i, b in missing:
            out = ollama.chat(model=LLM_MODEL, think=False, options={"temperature": 0.2, "num_predict": 600},
                              messages=[{"role": "system", "content":
                                         "Neeche diya Hinglish (Roman) text Devanagari Hindi script mein likho. "
                                         "Same words, same order. English tech words bhi Devanagari mein likho. "
                                         "Lekin short forms CAPITAL Roman mein hi rakho (OTP, UPI, I4C), web addresses "
                                         "aur numbers bhi waise hi rakho (1930, ₹500, 25%). Sirf converted text do."},
                                        {"role": "user", "content": b["say"]}])
            b["say_hi"] = out["message"]["content"].strip()
            print(f"  {b['say'][:40]}...  ->  {b['say_hi'][:40]}...")
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
    if VOICE:
        print(f"Narrator voice: {VOICE}")
    else:
        print("No voices/narrator.wav found: using the built-in voice. "
              "Record 10-20 s of your own voice for a much more natural result.")

    def speak(text, mood, seed):
        exag, cfg = MOOD_STYLE.get(mood, MOOD_STYLE["explain"])
        params = {"language_id": LANG, "audio_prompt_path": VOICE, "exaggeration": exag,
                  "cfg_weight": cfg, "cfg": cfg, "temperature": 0.8}
        params = {k: v for k, v in params.items() if k in accepted and v is not None}
        pieces = []
        for k, part in enumerate(split_long(text)):
            torch.manual_seed(seed * 10 + k)
            wav = tts.generate(part, **params)
            wav = wav.squeeze().detach().cpu().numpy() if hasattr(wav, "detach") else np.asarray(wav).squeeze()
            pieces.append(trim(wav.astype(np.float32), SR))
            pieces.append(np.zeros(int(0.08 * SR), np.float32))
        return np.concatenate(pieces[:-1]) if pieces else np.zeros(1, np.float32)

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
for i in todo:
    beats, real = scene_beats(scenes[i])
    clips, timing, cursor = [], [], 0.0
    for j, b in enumerate(beats):
        text = (b.get("say_hi") if LANG == "hi" and has_devanagari(b.get("say_hi", "")) else b.get("say", "")).strip()
        if not text:
            continue
        if LANG == "hi":
            text = spoken_hi(text)
            if leftovers(text):
                print(f"  scene {i:02d} beat {j:02d}: model will guess these English words: "
                      f"{', '.join(leftovers(text))} (write them in Hindi in say_hi to fix)")
        audio = speak(text, b.get("mood", "explain"), seed=i * 100 + j)
        sf.write(f"audio/scene_{i:02d}_b{j:02d}.wav", normalize(audio), SR)
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
    if real:
        json.dump({"beats": timing, "total": round(len(scene_audio) / SR, 3), "engine": ENGINE},
                  open(f"audio/scene_{i:02d}.json", "w"), indent=2)
    else:
        json.dump({"beats": [], "total": round(len(scene_audio) / SR, 3), "engine": ENGINE},
                  open(f"audio/scene_{i:02d}.json", "w"), indent=2)
    print(f"  scene {i:02d}: {len(timing)} beats, {len(scene_audio) / SR:.1f}s")

print("Done. Listen to a few files in the audio folder, then run animate.py.")