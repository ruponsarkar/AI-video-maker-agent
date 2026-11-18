"""
A real sung song (voice + music together) from the lyrics, made by ACE-Step 1.5 (MIT licence, outputs may be used
commercially), run locally on the GPU. Runs in venv-voice; called by `python rhyme.py song <slug>` and `make`.

    venv-voice/bin/python rhyme/song_ai.py <song folder> [--seed N] [--style "..."] [--roman]

Makes --takes N (default 3) different takes: audio/takes/take1.wav ... + takes.json (seeds). rhyme.py then keeps
the take whose singing follows the lyrics best (Whisper: rhyme/align.py) as audio/song.wav + song.json.
Install: ace-step/ (git clone of github.com/ace-step/ACE-Step-1.5), models in ace-step/checkpoints
(vae, Qwen3-Embedding-0.6B, acestep-v15-turbo: 6.3 GB), small extra packages in venv-voice/ace-libs.
The singer's voice is the model's own (not rhymes/voices/singer.wav).
"""
import json
import os
import random
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ACE = os.path.join(ROOT, "ace-step")

STYLE = ("cheerful Indian children's nursery rhyme, Hindi kids song, sweet bright female singer, clear vocals, "
         "catchy simple melody, ukulele, glockenspiel, xylophone, hand claps, light drums, bass, playful, happy")
LOVE = "gentle Hindi lullaby for kids, soft sweet female singer, clear vocals, music box, soft piano, warm strings, slow, calm"


def lyrics_text(script, roman=False):
    parts = []
    for scene in script["scenes"]:
        tag = {"chorus": "[Chorus]", "verse": "[Verse]", "bridge": "[Bridge]"}.get(scene.get("kind"), "[Verse]")
        lines = [(b.get("say") if roman else b["say_hi"]) or b["say_hi"] for b in scene["beats"]]
        parts.append(tag + "\n" + "\n".join(lines))
    return "\n\n".join(parts)


def length_for(script):
    """Seconds: 2 bars a line plus room (a song squeezed for time drops lines), 2 bars between parts, intro, outro."""
    bar = 240.0 / float(script.get("tempo", 100))
    n = sum(len(s["beats"]) for s in script["scenes"])
    return round(min(300, max(40, bar * (2.2 * n + 2 * len(script["scenes"]) + 6))))


def unload_ollama():
    try:
        import requests
        for m in requests.get("http://localhost:11434/api/ps", timeout=3).json().get("models", []):
            requests.post("http://localhost:11434/api/generate", json={"model": m["name"], "keep_alive": 0}, timeout=10)
    except Exception:
        pass


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        raise SystemExit(__doc__)
    folder = os.path.abspath(args[0])

    def opt(name, default=None):
        return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default

    if not os.path.isdir(os.path.join(ACE, "checkpoints", "acestep-v15-turbo")):
        raise SystemExit("ACE-Step isn't installed (ace-step/checkpoints): see rhyme/README.md, 'Real singing'.")
    script = json.load(open(os.path.join(folder, "script.json"), encoding="utf-8"))
    roman = "--roman" in sys.argv
    lyrics = lyrics_text(script, roman)
    title = script["title"].lower()
    style = opt("--style") or script.get("song_style") or (LOVE if any(w in title for w in ("lori", "lullaby", "neend")) else STYLE)
    seed = int(opt("--seed", random.randint(1, 10 ** 6)))
    seconds = length_for(script)
    key = script.get("key", "C")
    unload_ollama()
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    # ACE-Step's own versions (transformers 4.57, diffusers 0.37) live beside venv-voice, not in it: Chatterbox
    # needs different ones
    sys.path[:0] = [ACE, os.path.join(ROOT, "venv-voice", "ace-libs")]
    from acestep import model_downloader
    # no language model (it needs more memory than a 6 GB card has): don't let the start-up check ask for it
    model_downloader.MAIN_MODEL_COMPONENTS[:] = [c for c in model_downloader.MAIN_MODEL_COMPONENTS if "-lm-" not in c]
    from acestep.handler import AceStepHandler
    from acestep.inference import GenerationConfig, GenerationParams, generate_music
    h = AceStepHandler()
    t = time.time()
    status = h.initialize_service(project_root=ACE, config_path="acestep-v15-turbo", device="cuda",
                                  offload_to_cpu=True, offload_dit_to_cpu=True)
    if isinstance(status, tuple) and status and status[1] is False:
        raise SystemExit(f"ACE-Step didn't start: {status[0]}")
    p = GenerationParams(caption=style, lyrics=lyrics, bpm=int(float(script.get("tempo", 100))),
                         keyscale=f"{key} major", timesignature="4", vocal_language="en" if roman else "hi",
                         duration=float(seconds), seed=seed, inference_steps=8, shift=3.0, thinking=False)
    c = GenerationConfig(batch_size=1, use_random_seed=False, audio_format="wav")
    takes_dir = os.path.join(folder, "audio", "takes")
    os.makedirs(takes_dir, exist_ok=True)
    for f in os.listdir(takes_dir):
        os.remove(os.path.join(takes_dir, f))
    n = int(opt("--takes", 3))
    made = []
    for k in range(n):
        p.seed = seed + k * 7919
        out_dir = os.path.join(folder, "audio", "ace")
        os.makedirs(out_dir, exist_ok=True)
        r = generate_music(h, None, p, c, save_dir=out_dir)
        if not r.success or not r.audios:
            print(f"  take {k + 1} failed: {getattr(r, 'error', None) or getattr(r, 'status_message', '')}")
        else:
            dst = os.path.join(takes_dir, f"take{k + 1}.wav")
            os.replace(r.audios[0]["path"], dst)
            made.append({"file": os.path.basename(dst), "seed": p.seed})
        for f in os.listdir(out_dir):   # the model's extra files (json, previews)
            os.remove(os.path.join(out_dir, f))
        os.rmdir(out_dir)
    if not made:
        raise SystemExit("ACE-Step made no take.")
    json.dump({"model": "ACE-Step 1.5 turbo", "style": style, "seconds": seconds, "roman": roman, "lyrics": lyrics,
               "made": time.strftime("%Y-%m-%d %H:%M"), "takes": made},
              open(os.path.join(takes_dir, "takes.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"  {len(made)} take(s) of {seconds} s in {time.time() - t:.0f} s")


if __name__ == "__main__":
    main()
