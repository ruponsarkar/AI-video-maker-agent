"""
Cut a character out of its plain background (ISNet, Apache-2.0, run with onnxruntime on the CPU, in venv).

    python rhyme/cutout.py in.png out.png

Model file: ~/.cache/snackcode/isnet-general-use.onnx (from the rembg project's releases).
"""
import os
import sys

import numpy as np
from PIL import Image, ImageFilter

MODEL = os.path.expanduser("~/.cache/snackcode/isnet-general-use.onnx")
URL = "https://github.com/danielgatis/rembg/releases/download/v0.0.0/isnet-general-use.onnx"
_session = None


def _model():
    global _session
    if _session is None:
        if not os.path.exists(MODEL):
            raise SystemExit(f"Background-removal model missing: download {URL} to {MODEL}")
        import onnxruntime as ort
        _session = ort.InferenceSession(MODEL, providers=["CPUExecutionProvider"])
    return _session


def cut(img):
    """RGBA image with the background made transparent, trimmed to the character."""
    img = img.convert("RGB")
    s = _model()
    x = np.asarray(img.resize((1024, 1024), Image.BILINEAR), np.float32) / 255.0
    x = (x - 0.5) / 1.0                      # ISNet: mean 0.5, std 1
    x = x.transpose(2, 0, 1)[None]
    out = s.run(None, {s.get_inputs()[0].name: x})[0][0, 0]
    out = (out - out.min()) / (out.max() - out.min() + 1e-6)
    mask = Image.fromarray((out * 255).astype(np.uint8)).resize(img.size, Image.BILINEAR)
    # firm up the edge a little: fully keep the inside, softly fade only the outline
    a = np.asarray(mask, np.float32) / 255.0
    a = np.clip((a - 0.15) / 0.7, 0, 1)
    mask = Image.fromarray((a * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.8))
    rgba = img.convert("RGBA")
    rgba.putalpha(mask)
    box = mask.point(lambda v: 255 if v > 20 else 0).getbbox()
    return rgba.crop(box) if box else rgba


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    cut(Image.open(sys.argv[1])).save(sys.argv[2])
