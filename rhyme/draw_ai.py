"""
Make a rhyme's pictures on this laptop with a free image model (SSD-1B, Apache-2.0: fine for monetised videos).
Run with venv-voice (its torch sees the graphics card):

    venv-voice/bin/python rhyme/draw_ai.py rhymes/songs/<slug>              # every picture that's missing
    venv-voice/bin/python rhyme/draw_ai.py rhymes/songs/<slug> --redo p03   # a new try for p03 (new seed)
    venv-voice/bin/python rhyme/draw_ai.py rhymes/songs/<slug> --redo all   # every AI picture again

    ... --redo-character elephant                                         # a new look for one character (all songs!)

(rhyme.py pictures/make run this for you.) Pictures you saved yourself are never replaced.

Characters: each one is drawn ONCE for the whole channel (rhymes/cast_art/<kind>.png, cut out by cutout.py) and put
into every scene by motion.py, so it looks the same in every song. Scenes with characters get a background only
(images/pNN.png, "ai_layers" in pictures.json); motion.py puts the characters in and makes them bounce.
The local vision model (gemma3) checks every picture; a bad one is drawn again with a new seed (3 tries).
Never runs together with Ollama or the voice model: there is only 6 GB of graphics memory.
"""
import json
import os
import random
import sys
import time

os.environ.setdefault("HF_HUB_OFFLINE", "1")
HERE = os.path.dirname(os.path.abspath(__file__))
# Chatterbox needs diffusers 0.29 in venv-voice; the picture model needs a newer one, kept in its own folder:
#   uv pip install --python venv-voice/bin/python --target venv-voice/image-libs --no-deps diffusers==0.43.0
EXTRA = os.path.join(os.path.dirname(HERE), "venv-voice", "image-libs")
if os.path.isdir(EXTRA):
    sys.path.insert(0, EXTRA)
sys.path.insert(0, HERE)
import pictures  # noqa: E402
from critters import KINDS  # noqa: E402

CAST_ART = os.path.join(os.path.dirname(HERE), "rhymes", "cast_art")
PEOPLE = ("boy", "girl", "child", "kid", "person", "human", "man", "woman", "baby")

MODEL = "segmind/SSD-1B"
VAE = "madebyollin/sdxl-vae-fp16-fix"
LCM = "latent-consistency/lcm-lora-ssd-1b"
SIZE = (1344, 768)            # 16:9-ish, what SDXL-type models are trained for
STEPS, GUIDANCE = 8, 1.5      # LCM: few steps, low guidance
STYLE = ("3D animated feature film still, high quality CGI render, cute characters with big expressive eyes, soft "
         "global illumination, cinematic lighting, vibrant colours, shallow depth of field, detailed textures")
NEGATIVE = ("text, letters, words, watermark, logo, signature, photo, realistic, scary, ugly, deformed, extra limbs, "
            "extra fingers, missing eyes, blurry, low quality, dark, horror, weapon")


def unload_ollama():
    """Free the graphics card: ask Ollama to drop any model it has loaded."""
    try:
        import requests
        for m in requests.get("http://localhost:11434/api/ps", timeout=5).json().get("models", []):
            requests.post("http://localhost:11434/api/generate", json={"model": m["name"], "keep_alive": 0}, timeout=20)
    except Exception:  # noqa: BLE001
        pass


def short_look(look):
    """'a friendly baby elephant, soft grey, big flappy ears ...' -> 'a friendly baby elephant, soft grey'"""
    return ", ".join(look.split(", ")[:2])


def layered(slot):
    """Scenes with characters are drawn as a background; the characters are put in by motion.py."""
    if slot.get("layers") is False:
        return False
    return bool(slot["cast"]) and not pictures.acting(slot)


def cast_kinds(slot):
    return slot["cast"][:1] if slot["role"] == "title" else slot["cast"][:3]


POSE = {"people": "full body, standing, facing the viewer",
        "four_legs": "full body, standing on all four legs, three-quarter view, looking at the viewer",
        "train": "side view of the whole train, engine with a smiling face in front",
        "bird": "full body, standing, three-quarter view, whole tail visible",
        "float": "whole body, facing the viewer, simple shape, not a human, no hair"}
POSE_OF = {"boy": "people", "girl": "people", "cat": "four_legs", "dog": "four_legs", "rabbit": "four_legs",
           "elephant": "four_legs", "lion": "four_legs", "cow": "four_legs", "monkey": "people", "frog": "people",
           "duck": "bird", "peacock": "bird", "parrot": "bird", "train": "train"}


KID = pictures.KID   # Golu and Chinki in a few words (pictures.py: shared with the clip prompts in clips.py)


def character_prompts(kind, cast):
    look = cast["characters"][kind]["look"]
    pose = POSE[POSE_OF.get(kind, "float")]
    if POSE_OF.get(kind, "float") == "float":
        # sun, moon, star...: an object with a face. The film style's "cute characters" turns them into babies.
        return (f"{look}, centered, isolated on a plain white background",
                f"{look.split(',')[0]}, cute smiling face, glossy 3D render, soft studio light, plain white background")
    if kind in KID:
        return (f"{KID[kind]}, {pose}, centered, isolated on a plain white background",
                f"{KID[kind]}, {pose}, plain white background, {STYLE}")
    return (f"{look}, {pose}, centered, isolated on a plain white background",
            f"one {kind}, {pose}, plain white background, {STYLE}")


OBJECT_NEGATIVE = ", person, human, child, baby, boy, girl, body, arms, legs, hair, clothes"


def background_prompts(slot, cast):
    place = cast["places"].get(slot["place"], slot["place"])
    title = ", bright open sky in the top half" if slot["role"] == "title" else ""
    setting = (slot.get("setting") or "").rstrip(". ")
    if setting and "night" in (slot["place"] + place).lower() and "night" not in setting.lower():
        setting += ", at night, dark blue night sky, warm lamp light"   # a lullaby stays at night
    if setting and slot["role"] not in ("title", "end"):
        # what this line is about (pictures.py asks qwen): a different background for every line
        return (f"empty {setting}, nobody there, open floor in the middle",
                f"{setting}, background art for an animated film, no characters, {STYLE}")
    return (f"empty {place}, wide view, nobody there, open ground in the middle{title}",
            f"{place.split(',')[0]}, background art for a cartoon, no characters, {STYLE}")


def sd_prompts(slot, script, cast):
    """A whole picture with its characters in it (scenes without layers). Two prompts of at most 77 word-pieces
    each (the model can't read more): the characters come FIRST in both, or the model paints only the place."""
    chars = cast["characters"]
    names = [k for k in slot["cast"] if k in chars][:3]
    if pictures.acting(slot):   # the sky characters (moon, star) are put in afterwards: only who does the action
        from critters import KINDS
        names = [k for k in names if not KINDS[k][4]][:2]
    looks = [short_look(chars[k]["look"]) for k in names]
    spots = {2: ["on the left", "on the right"], 3: ["on the left", "in the middle", "on the right"]}.get(len(looks))
    who = (", ".join(f"{lk} {sp}" for lk, sp in zip(looks, spots)) if spots else "".join(looks)) or "a cute animal"
    if slot["role"] == "title":
        names = names[:1]
        who = short_look(chars[names[0]]["look"]) if names else who
        action = "smiling and waving at the viewer, close-up, clear sky above"
    elif slot["role"] == "end":
        action = "together, happy, waving goodbye at the viewer"
    else:
        action = slot.get("show") or "playing happily"
        for k in names:   # the model doesn't know our names: say what they are
            action = action.replace(f"{chars[k]['name']} the {k}", f"the {k}").replace(chars[k]["name"], f"the {k}")
        action = action.rstrip(". ")
    place = cast["places"].get(slot["place"], slot["place"]).split(",")[0]
    if pictures.acting(slot):   # the action first and short, or the model only draws the characters standing
        kid = KID
        subj = [kid.get(k, f"a cute {k}") for k in names] or ["a cute child"]
        subj = subj[0] if len(subj) == 1 else f"{subj[0]} and {subj[1]}"
        where = (slot.get("setting") or place).rstrip(". ")
        night = ", at night, warm lamp light" if "night" in (slot["place"] + where).lower() else ""
        doing = pictures.action_phrase(slot)
        return (f"{subj} {doing}, {where}{night}, 3d cartoon, cute",
                f"{subj} {doing}, {STYLE}")
    first = f"{who}, {action}, {place}, 3d cartoon, cute"
    if spots:
        who += f", {len(looks)} separate characters"
    second = f"{who} in {place}, {STYLE}"
    return first, second


def check(path, kinds, model="gemma3:4b", empty=False, single=False):
    """The local vision model looks at a picture: are the wanted characters there, separate and whole, as a
    cartoon? empty: a background, so no animals or people at all. single: exactly one character.
    Returns (ok, reason). Fails open (ok) if Ollama isn't there."""
    import base64
    import requests
    want = kinds[:2]
    ask = ("You check pictures for a children's cartoon video. Look carefully at this picture and answer JSON: "
           '{"animals_and_people": [every animal, person or vehicle you see, one or two words each], '
           '"blended": true/false (two different creatures or things melted together into one body, like an animal '
           'that is half train), "broken": true/false (a creature with extra or missing heads, legs or eyes, or a '
           'messed-up face), "cartoon": true/false (a cute 3D cartoon, not a realistic photo)}')
    try:
        img = base64.b64encode(open(path, "rb").read()).decode()
        r = requests.post("http://localhost:11434/api/chat", timeout=180, json={
            "model": model, "stream": False, "format": "json", "options": {"temperature": 0},
            "messages": [{"role": "user", "content": ask, "images": [img]}]})
        seen = json.loads(r.json()["message"]["content"])
    except Exception as e:  # noqa: BLE001
        return True, f"not checked ({e})"
    names = " ".join(str(x).lower() for x in seen.get("animals_and_people", []))
    words = {"boy": ("boy", "child", "kid", "person", "human"), "girl": ("girl", "child", "kid", "person", "human"),
             "cat": ("cat", "kitten"), "dog": ("dog", "puppy"), "rabbit": ("rabbit", "bunny"), "train": ("train",
             "engine", "locomotive"), "fish": ("fish",), "duck": ("duck",), "cow": ("cow", "calf"),
             "lion": ("lion",), "sun": ("sun",), "moon": ("moon",), "star": ("star",)}
    missing = [k for k in want if not any(w in names for w in words.get(k, (k,)))]
    problems = []
    if empty:   # a background: no people and none of this scene's characters (they're added later; fish are fine)
        bad = PEOPLE + tuple(w for k in kinds for w in words.get(k, (k,)))
        found = [str(x) for x in seen.get("animals_and_people", []) if any(w in str(x).lower() for w in bad)]
        return not found, (f"has {', '.join(found)[:60]}" if found else "ok (empty scene)")
    if single and len(seen.get("animals_and_people", [])) > 1:
        problems.append("more than one character")
    if missing:
        problems.append("no " + ", ".join(missing))
    if seen.get("blended") is True:
        problems.append("characters melted together")
    if seen.get("broken") is True:
        problems.append("broken body or face")
    if seen.get("cartoon") is False:
        problems.append("not cartoon")
    return not problems, "; ".join(problems) or f"ok ({names[:60]})"


def load_pipe():
    import torch
    from diffusers import AutoencoderKL, LCMScheduler, StableDiffusionXLPipeline
    vae = AutoencoderKL.from_pretrained(VAE, torch_dtype=torch.float16)
    pipe = StableDiffusionXLPipeline.from_pretrained(MODEL, vae=vae, torch_dtype=torch.float16, variant="fp16",
                                                     use_safetensors=True)
    pipe.load_lora_weights(LCM, weight_name="pytorch_lora_weights.safetensors")
    pipe.fuse_lora()
    pipe.scheduler = LCMScheduler.from_config(pipe.scheduler.config)
    pipe.enable_model_cpu_offload()     # only the part that's working sits on the graphics card
    pipe.vae.enable_tiling()
    pipe.set_progress_bar_config(disable=True)
    return pipe


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    redo = sys.argv[sys.argv.index("--redo") + 1] if "--redo" in sys.argv else None
    if not args:
        raise SystemExit(__doc__)
    folder = args[0]
    path = os.path.join(folder, "pictures.json")
    if not os.path.exists(path):
        raise SystemExit("No pictures.json: run python rhyme.py pictures <slug> first.")
    data = json.load(open(path, encoding="utf-8"))
    slots = data["pictures"]
    script = json.load(open(os.path.join(folder, "script.json"), encoding="utf-8"))
    cast = pictures.load_cast()
    os.makedirs(os.path.join(folder, "images"), exist_ok=True)
    os.makedirs(CAST_ART, exist_ok=True)
    index_path = os.path.join(CAST_ART, "index.json")
    art = json.load(open(index_path, encoding="utf-8")) if os.path.exists(index_path) else {}
    base = sum(map(ord, script["title"]))
    jobs = []   # everything to draw: {name, file, prompts, size, seed, check, extra negative, after}
    for s in slots:
        if "same_as" in s:
            continue
        have = pictures.find_file(folder, s["id"])
        mine = have and os.path.basename(have) != s.get("ai_file")   # a file you saved: never touched
        wanted = redo and (s["id"] in redo.split(",") or (redo == "all" and not mine))
        if wanted and mine:
            print(f"  {s['id']}: that's your own picture ({os.path.basename(have)}); delete it to let the AI draw it")
        if mine or (have and not wanted):
            continue
        if have:
            os.remove(have)
            s["seed"] = random.randint(1, 10 ** 9)
        s.setdefault("seed", base + int(s["id"][1:]) * 7919)
        if layered(s):
            kinds = cast_kinds(s)
            jobs.append({"name": s["id"], "slot": s, "file": os.path.join(folder, "images", f"{s['id']}.png"),
                         "prompts": background_prompts(s, cast), "size": SIZE, "kinds": kinds, "empty": True,
                         "negative": ", animal, person, child, character, " + ", ".join(kinds)})
        else:
            jobs.append({"name": s["id"], "slot": s, "file": os.path.join(folder, "images", f"{s['id']}.png"),
                         "prompts": sd_prompts(s, script, cast), "size": SIZE, "negative": "",
                         "kinds": [k for k in cast_kinds(s) if not (pictures.acting(s) and KINDS[k][4])]})
    # characters this song needs that have no picture yet (drawn once for the whole channel)
    need = list(dict.fromkeys(k for s in slots if "same_as" not in s and layered(s) for k in cast_kinds(s)))
    again = sys.argv[sys.argv.index("--redo-character") + 1].split(",") if "--redo-character" in sys.argv else []
    for kind in need + [k for k in again if k not in need]:
        again_kind = kind if kind in again else None
        if kind not in cast["characters"]:
            continue
        raw = os.path.join(CAST_ART, f"{kind}.png")
        if os.path.exists(raw) and kind != again_kind:
            continue
        for old in (raw, os.path.join(CAST_ART, f"{kind}_cut.png")):
            if os.path.exists(old):
                os.remove(old)
        art[kind] = {"seed": random.randint(1, 10 ** 9) if kind == again_kind else 7 + sum(map(ord, kind)),
                     "look": cast["characters"][kind]["look"]}
        jobs.insert(0, {"name": f"character {kind}", "kind": kind, "file": raw, "prompts": character_prompts(kind, cast),
                        "size": (768, 1024), "kinds": [kind], "single": kind != "train",   # coaches count

                        "negative": ", background scenery, grass, ground, cropped, two characters"
                        + (OBJECT_NEGATIVE if POSE_OF.get(kind, "float") == "float" else "")})
    if not jobs:
        print("  every picture is there")
        return
    try:
        import diffusers  # noqa: F401
    except ImportError:
        raise SystemExit("diffusers isn't installed in venv-voice: uv pip install --python venv-voice/bin/python diffusers")
    import torch
    checked = "--no-check" not in sys.argv
    doubtful = {}
    unload_ollama()
    try:
        pipe = load_pipe()   # loaded once (about 7 GB of memory): loading it twice ran out of memory
    except OSError as e:
        raise SystemExit(f"The image model isn't downloaded ({e}). See rhyme/README.md, 'Pictures'.")

    def seed_of(job):
        return art[job["kind"]]["seed"] if "kind" in job else job["slot"]["seed"]

    def new_seed(job):
        if "kind" in job:
            art[job["kind"]]["seed"] = random.randint(1, 10 ** 9)
        else:
            job["slot"]["seed"] = random.randint(1, 10 ** 9)

    def save_state():
        json.dump(data, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        json.dump(art, open(index_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    todo = jobs
    for attempt in range(3 if checked else 1):
        unload_ollama()
        print(f"  drawing {len(todo)} picture(s) with {MODEL}{' (another try)' if attempt else ''} ...", flush=True)
        for job in todo:
            first, second = job["prompts"]
            started = time.time()
            image = pipe(prompt=first, prompt_2=second, negative_prompt=NEGATIVE + job["negative"],
                         num_inference_steps=STEPS, guidance_scale=GUIDANCE, width=job["size"][0],
                         height=job["size"][1], generator=torch.Generator("cpu").manual_seed(seed_of(job))).images[0]
            image.save(job["file"])
            if "slot" in job:
                s = job["slot"]
                s["ai"], s["ai_file"], s["sd_prompt"] = MODEL, os.path.basename(job["file"]), [first, second]
                s["ai_layers"] = bool(job.get("empty"))
            save_state()
            print(f"  {job['name']} ({time.time() - started:.0f} s): {first[:80]}", flush=True)
        pipe.maybe_free_model_hooks()   # everything back to normal memory: the graphics card is free for the check
        torch.cuda.empty_cache()
        if not checked:
            break
        again = []   # the vision model looks at each one; the bad ones get a new seed and another try
        for job in todo:
            ok, why = check(job["file"], job["kinds"], empty=job.get("empty", False), single=job.get("single", False))
            print(f"    check {job['name']}: {why}", flush=True)
            target = job.get("slot") or art[job["kind"]]
            if ok:
                doubtful.pop(job["name"], None)
                target.pop("doubt", None)
            else:
                doubtful[job["name"]] = why
                target["doubt"] = why
                if attempt < 2:   # the last try keeps its seed (it's the picture that stays)
                    new_seed(job)
                again.append(job)
        unload_ollama()
        save_state()
        if not again or attempt == 2:
            break
        todo = again
    if doubtful:   # the last try is kept; you decide
        print("  still not right after 3 tries (look at these): " + "; ".join(f"{k}: {v}" for k, v in doubtful.items()))


if __name__ == "__main__":
    main()
