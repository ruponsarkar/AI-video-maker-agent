"""
Listens to voice clips with Whisper and scores how closely each one says its text (0 to 1).

voice.py runs this for you, on the normal venv, because Whisper isn't installed in venv-voice.
Usage:  python voice_check.py clips.json scores.json
clips.json holds [{"file": "...", "text": "..."}]. The score compares consonant sounds, so it isn't thrown off by
Whisper writing a word in English ("domain") or mixing up similar letters (डेटा / देटा).
"""
import difflib
import json
import re
import subprocess
import sys

import numpy as np
from faster_whisper import WhisperModel

from hinglish import _skeleton_en, _skeleton_hi


def sounds(text):
    out = []
    for w in re.findall(r"[ऀ-ॿ]+|[A-Za-z0-9]+", text):
        out.append(_skeleton_hi(w) if re.match(r"[ऀ-ॿ]", w) else _skeleton_en(w))
    return "".join(out)


def score(expected, heard):
    a, b = sounds(expected), sounds(heard)
    return round(difflib.SequenceMatcher(None, a, b, autojunk=False).ratio(), 3) if a and b else 0.0


def main():
    clips = json.load(open(sys.argv[1], encoding="utf-8"))
    model = WhisperModel("medium", device="cpu", compute_type="int8")
    for c in clips:
        # FFmpeg decode: faster-whisper's own decoder doesn't work with the installed av version
        pcm = subprocess.run(["ffmpeg", "-v", "error", "-i", c["file"], "-ar", "16000", "-ac", "1", "-f", "f32le", "-"],
                             capture_output=True, check=True).stdout
        segments, _ = model.transcribe(np.frombuffer(pcm, np.float32), language="hi", beam_size=3)
        c["heard"] = " ".join(s.text.strip() for s in segments)
        c["score"] = score(c["text"], c["heard"])
    json.dump(clips, open(sys.argv[2], "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
