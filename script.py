"""
Snack Code - Step 4: write the video script as fast "beats"
Reads research/notes.md and writes scripts/script.json.

Each scene is split into 2-4 beats of 1-2 sentences (about 4-6 seconds each).
Every beat gets its own visual, so the picture changes every few seconds.

Usage:
    python script.py
"""
import json
import os

import ollama

MODEL = "qwen3:8b"

STYLE = """Tum Snack Code YouTube channel ke script writer ho.
Channel: tech aur online safety, simple Hindi mein, adults (25-34) ke liye.
Host: "Byte", ek chhota robot jo viewer se seedha baat karta hai.

Rules:
- Bhasha: simple Hinglish (Hindi Roman script mein, tech words English mein).
- Pehle 3 second: problem ya shocking fact. Koi 'hello friends' ya channel intro nahi.
- Total 1200-1500 words (8-10 minute video), 12-18 scenes.
- Chhote, punchy sentences. Sirf notes wale facts. Kuch bhi apne se mat banao.
- Scam video ho to end mein cybercrime helpline 1930 zaroor batao.
- End mein: comment karne ko bolo aur agla video suggest karo.

BEATS (sabse zaroori):
- Har scene ko 2-4 "beats" mein todo. Har beat = 1-2 sentences (4-6 second).
- Har beat ka apna "visual". Ek scene mein same type do baar mat lo.
- Pure video mein alag-alag types use karo. Har 3-4 beats mein ek baar "host".
- "pop": sirf sabse important 1-2 words (jaise "OTP", "1930", "FAKE"). Har scene mein max 1 pop. Zaroori na ho to pop mat do.
- "mood" (Byte ka chehra): happy, shock, think, warn, explain.

Visual types (inme se hi chuno; texts chhote rakho, max 8 words per item):
{"type": "title"}                               -> sirf pehle scene ki pehli beat
{"type": "host", "text": "Byte kya bolta hai (max 12 words)"}
{"type": "kinetic", "text": "screen par bade words (max 8)", "highlight": "ek word"}
{"type": "icon", "icon": "shield", "text": "chhota message"}
{"type": "phone_call", "caller": "Delivery Boy", "number": "+91 98XXX XXXXX"}
{"type": "phone_sms", "sender": "VM-ALERT", "message": "SMS text, fake link ke saath"}
{"type": "chat", "name": "Unknown Number", "messages": [{"from": "them", "text": "..."}, {"from": "me", "text": "..."}]}
{"type": "steps", "items": ["step 1", "step 2", "step 3"]}
{"type": "compare", "left_title": "Asli", "left": ["...", "..."], "right_title": "Fake", "right": ["...", "..."]}
{"type": "stat", "value": "16%", "label": "number ka matlab"}
{"type": "warning", "text": "kya kabhi nahi karna"}
{"type": "flow", "nodes": [{"icon": "hacker", "label": "Scammer"}, {"icon": "phone", "label": "Aapka phone"}, {"icon": "bank", "label": "Bank"}]}

Kab kaunsa: call -> phone_call; SMS/link -> phone_sms; baat-cheet -> chat;
process -> flow; tips -> steps; asli vs nakli -> compare; number/percent/price -> stat;
khatra -> warning; Byte ka sawaal ya reaction -> host; important line -> kinetic; baaki -> icon.

Icons (sirf ye): phone, shield, lock, bank, money, warning, user, hacker, globe, laptop,
wifi, chip, ram, bug, ai, key, sim, mail, check, cross

Output SIRF is JSON format mein:
{
  "title": "Hinglish title, 60 characters se kam",
  "scenes": [
    {
      "on_screen": "scene ki heading, 3-6 words",
      "narration_hi": "is scene ki saari beats ka text Devanagari mein (voiceover ke liye)",
      "beats": [
        {"say": "Hinglish sentence(s)", "visual": {"type": "..."}, "mood": "explain", "pop": "OTP"}
      ]
    }
  ]
}
"""

notes_path = "research/notes.md"
if not os.path.exists(notes_path):
    print("research/notes.md not found. Run research.py first.")
    raise SystemExit(1)

notes = open(notes_path, encoding="utf-8").read()
os.makedirs("scripts", exist_ok=True)

print(f"Writing script with {MODEL} (this can take 5-10 minutes) ...")
out = ollama.chat(
    model=MODEL,
    format="json",
    think=False,
    options={"num_ctx": 12288},
    messages=[
        {"role": "system", "content": STYLE},
        {"role": "user", "content": notes},
    ],
)

try:
    script = json.loads(out["message"]["content"])
except json.JSONDecodeError:
    raw = "scripts/script_raw.txt"
    open(raw, "w", encoding="utf-8").write(out["message"]["content"])
    print(f"The model did not return valid JSON. Raw output saved to {raw}. Run again.")
    raise SystemExit(1)

path = "scripts/script.json"
with open(path, "w", encoding="utf-8") as f:
    json.dump(script, f, ensure_ascii=False, indent=2)

scenes = script.get("scenes", [])
beats = [b for s in scenes for b in (s.get("beats") or [])]
print(f"Title: {script.get('title')}")
print(f"Scenes: {len(scenes)}, beats: {len(beats)}")
print("Visuals: " + ", ".join(str((b.get('visual') or {}).get('type', '-')) for b in beats))
missing = [i for i, s in enumerate(scenes) if not s.get("narration_hi")]
if missing:
    print(f"Note: scenes {missing} have no Devanagari text; voice.py will read the Hinglish instead.")
print(f"Saved {path}. Edit it by hand: fix facts, change visuals, add your own opinion.")