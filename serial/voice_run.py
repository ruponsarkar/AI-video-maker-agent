"""
Voices for serial episodes. Runs in venv-voice (Chatterbox), one episode folder or several:

    venv-voice/bin/python serial/voice_run.py series/ramayan/episodes/ep001 [ep002 ...] [--redo] [--no-check]

Each character speaks with its own voice. For a character the script looks for, in order:
    series/<slug>/voices/<character id>.wav      a recording made for this character (best)
    series/<slug>/voices/<voice type>.wav        one recording per type: male_young, female_adult, child, ...
    voices/serial/<voice type>.wav               the same, shared by all serials
    voices/narrator.wav                          your narrator voice, with its pitch moved to suit the type
A 10-20 second clean recording per voice type makes the biggest difference.

Writes audio/s<scene>_b<beat>.wav for every line and audio/lines.json with their lengths.
"""
import inspect
import json
import os
import re
import subprocess
import sys
import tempfile

import numpy as np
import soundfile as sf

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
from hindi_text import spoken_hi  # noqa: E402

MAX_CHARS = 150
SENTENCE_PAUSE = {"?": 0.32, "!": 0.30, "।": 0.26, ".": 0.26, ",": 0.10}
# semitones to move the narrator voice when a type has no recording of its own
PITCH = {"narrator": 0, "male_young": 1, "male_adult": 0, "male_old": -1, "male_deep": -3, "female_young": 5,
         "female_adult": 4, "female_old": 3, "child": 7, "demon": -4, "bird": 3}
# emotion -> (exaggeration, cfg weight): more exaggeration = more dramatic delivery
EMOTION = {"calm": (0.55, 0.5), "happy": (0.8, 0.45), "sad": (0.7, 0.4), "angry": (1.05, 0.35),
           "surprised": (0.95, 0.4), "fear": (0.9, 0.4), "narrator": (0.6, 0.5)}
TAKES = 2
GOOD_SCORE = 0.78


def split_sentences(text):
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
    if len(audio) == 0:
        return audio
    loud = np.where(np.abs(audio) > threshold * (np.abs(audio).max() + 1e-9))[0]
    if len(loud) == 0:
        return audio
    return audio[max(0, loud[0] - int(keep * sr)):min(len(audio), loud[-1] + int(keep * sr * 2))]


def normalize(audio, peak=0.89):
    m = np.abs(audio).max()
    return audio * (peak / m) if m > 0 else audio


def unload_ollama():
    try:
        import ollama
        import time
        for m in ollama.ps().models:
            ollama.generate(model=m.model, prompt="", keep_alive=0)
        for _ in range(30):
            if not ollama.ps().models:
                return
            time.sleep(1)
    except Exception:
        pass


def voice_for(series_dir, char_id, vtype):
    """(reference wav or None, semitones to shift)."""
    for path in (os.path.join(series_dir, "voices", f"{char_id}.wav"), os.path.join(series_dir, "voices", f"{vtype}.wav"),
                 os.path.join(ROOT, "voices", "serial", f"{vtype}.wav")):
        if os.path.exists(path):
            return path, 0
    narrator = os.path.join(series_dir, "voices", "narrator.wav")
    if not os.path.exists(narrator):
        narrator = os.path.join(ROOT, "voices", "narrator.wav")
    return (narrator if os.path.exists(narrator) else None), PITCH.get(vtype, 0)


def score(clips):
    python = os.path.join(ROOT, "venv", "bin", "python")
    if not os.path.exists(python):
        return None
    with tempfile.TemporaryDirectory() as tmp:
        ask, answer = os.path.join(tmp, "c.json"), os.path.join(tmp, "s.json")
        json.dump(clips, open(ask, "w", encoding="utf-8"), ensure_ascii=False)
        done = subprocess.run([python, os.path.join(ROOT, "voice_check.py"), ask, answer], capture_output=True,
                              text=True, env={**os.environ, "CUDA_VISIBLE_DEVICES": ""})
        return json.load(open(answer, encoding="utf-8")) if done.returncode == 0 else None


def main():
    folders = [a for a in sys.argv[1:] if not a.startswith("--")]
    redo, check = "--redo" in sys.argv, "--no-check" not in sys.argv
    if not folders:
        raise SystemExit(__doc__)
    unload_ollama()
    import torch
    import librosa
    from chatterbox.mtl_tts import ChatterboxMultilingualTTS

    device = "cuda" if torch.cuda.is_available() else "cpu"
    if device == "cpu" and "--cpu" not in sys.argv:
        raise SystemExit("The GPU isn't available to PyTorch (this often happens after the laptop sleeps).\n"
                         "Fix: sudo rmmod nvidia_uvm && sudo modprobe nvidia_uvm   (or restart the laptop)\n"
                         "Or voice on the CPU, many times slower: add --cpu")
    print(f"Loading Chatterbox on {device} ...", flush=True)
    tts = ChatterboxMultilingualTTS.from_pretrained(device=device)
    sr = tts.sr
    accepted = set(inspect.signature(tts.generate).parameters)

    def speak(text, ref, shift, emotion, seed):
        exag, cfg = EMOTION.get(emotion, EMOTION["calm"])
        pieces = []
        parts = split_sentences(text)
        for k, part in enumerate(parts):
            params = {"language_id": "hi", "audio_prompt_path": ref, "exaggeration": exag, "cfg_weight": cfg,
                      "temperature": 0.7}
            params = {a: b for a, b in params.items() if a in accepted and b is not None}
            torch.manual_seed(seed + k * 7)
            wav = tts.generate(part, **params)
            wav = wav.squeeze().detach().cpu().numpy() if hasattr(wav, "detach") else np.asarray(wav).squeeze()
            pieces.append(trim(wav.astype(np.float32), sr))
            if k < len(parts) - 1:
                pieces.append(np.zeros(int(SENTENCE_PAUSE.get(part[-1], 0.15) * sr), np.float32))
        audio = np.concatenate(pieces)
        if shift:
            audio = librosa.effects.pitch_shift(audio, sr=sr, n_steps=shift).astype(np.float32)
        return audio

    for folder in folders:
        script_path = os.path.join(folder, "script.json")
        script = json.load(open(script_path, encoding="utf-8"))
        series_dir = os.path.dirname(os.path.dirname(os.path.abspath(folder)))
        bible = json.load(open(os.path.join(series_dir, "bible.json"), encoding="utf-8"))
        os.makedirs(os.path.join(folder, "audio"), exist_ok=True)
        listing = os.path.join(folder, "audio", "lines.json")
        old = {(x["scene"], x["beat"]): x for x in json.load(open(listing))["lines"]} if os.path.exists(listing) and not redo else {}
        out, todo = [], []
        print(f"\n{folder}: voicing", flush=True)
        for i, scene in enumerate(script["scenes"]):
            for j, beat in enumerate(scene["beats"]):
                text = str(beat.get("say_hi") or "").strip()
                if not text:
                    continue
                path = os.path.join(folder, "audio", f"s{i:02d}_b{j:02d}.wav")
                known = old.get((i, j))
                if known and known.get("text") == text and os.path.exists(path):
                    out.append(known)
                    continue
                who = beat.get("speaker", "narrator")
                vtype = "narrator" if who == "narrator" else (bible["characters"].get(who, {}).get("voice") or "male_adult")
                ref, shift = voice_for(series_dir, who if who != "narrator" else "narrator", vtype)
                emotion = "narrator" if who == "narrator" else beat.get("emotion", "calm")
                spoken = spoken_hi(text)
                audio = speak(spoken, ref, shift, emotion, seed=script.get("n", 1) * 1000 + i * 50 + j)
                sf.write(path, normalize(audio), sr)
                item = {"scene": i, "beat": j, "file": os.path.relpath(path, folder), "text": text, "spoken": spoken,
                        "speaker": who, "dur": round(len(audio) / sr, 3), "ref": ref, "shift": shift, "emotion": emotion}
                out.append(item)
                todo.append(item)
            print(f"  scene {i}: done", flush=True)
        # listen back with Whisper and give weak lines one more take
        if check and todo:
            scores = score([{"file": os.path.join(folder, x["file"]), "text": x["spoken"]} for x in todo])
            if scores:
                weak = [(x, s) for x, s in zip(todo, scores) if s["score"] < GOOD_SCORE]
                print(f"  voice check: {len(weak)} of {len(todo)} lines get another take", flush=True)
                for take in range(1, TAKES):
                    if not weak:
                        break
                    tries = []
                    for x, s in weak:
                        audio = speak(x["spoken"], x["ref"], x["shift"], x["emotion"], seed=take * 7777 + hash(x["file"]) % 999)
                        tmp = os.path.join(folder, x["file"] + ".try.wav")
                        sf.write(tmp, normalize(audio), sr)
                        tries.append((x, s, tmp, audio))
                    again = score([{"file": t[2], "text": t[0]["spoken"]} for t in tries]) or []
                    for (x, s, tmp, audio), s2 in zip(tries, again):
                        if s2["score"] > s["score"]:
                            os.replace(tmp, os.path.join(folder, x["file"]))
                            x["dur"] = round(len(audio) / sr, 3)
                            s = s2
                        if os.path.exists(tmp):
                            os.remove(tmp)
                        x["score"] = s["score"]
                    weak = [(x, {"score": x.get("score", 0)}) for x, _ in weak if x.get("score", 0) < GOOD_SCORE]
                for x, s in zip(todo, scores):
                    x.setdefault("score", s["score"])
        json.dump({"sr": sr, "lines": sorted(out, key=lambda x: (x["scene"], x["beat"]))},
                  open(listing, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        low = [x for x in out if x.get("score") is not None and x["score"] < GOOD_SCORE]
        if low:
            with open(os.path.join(folder, "audio", "voice_check.md"), "w", encoding="utf-8") as f:
                f.write("# Lines to listen to\n\n")
                for x in low:
                    f.write(f"- {x['file']} ({x['score']}): {x['text']}\n")
        print(f"  {len(out)} lines, {sum(x['dur'] for x in out):.0f} s of voice", flush=True)


if __name__ == "__main__":
    main()
