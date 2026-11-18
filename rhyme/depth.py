"""
3D camera moves on a flat picture: a small depth model (Depth Anything V2 Small, Apache-2.0, ONNX on the CPU, in venv)
guesses how near each part of the picture is; then every frame near things move more than far things as the camera
glides, pushes in or orbits (parallax), so a still picture looks like a 3D shot.

    python rhyme/depth.py picture.png depth.png       # see the depth map (white = near)

Model file: ~/.cache/snackcode/depth-anything-v2-small.onnx
(https://huggingface.co/onnx-community/depth-anything-v2-small, onnx/model.onnx). Depth maps are cached next to the
picture as images/.depth/<name>.png.
"""
import math
import os
import sys

import numpy as np
from PIL import Image, ImageFilter

MODEL = os.path.expanduser("~/.cache/snackcode/depth-anything-v2-small.onnx")
URL = "https://huggingface.co/onnx-community/depth-anything-v2-small/resolve/main/onnx/model.onnx"
_session = None


def _model():
    global _session
    if _session is None:
        if not os.path.exists(MODEL):
            raise FileNotFoundError(f"depth model missing: download {URL} to {MODEL}")
        import onnxruntime as ort
        _session = ort.InferenceSession(MODEL, providers=["CPUExecutionProvider"])
    return _session


def estimate(img):
    """Depth of an RGB picture: float32 array, same size, 0 = far, 1 = near."""
    img = img.convert("RGB")
    w, h = img.size
    th = 518
    tw = max(14, int(round(th * w / h / 14)) * 14)
    x = np.asarray(img.resize((tw, th), Image.BICUBIC), np.float32) / 255.0
    x = (x - np.array([0.485, 0.456, 0.406], np.float32)) / np.array([0.229, 0.224, 0.225], np.float32)
    s = _model()
    d = s.run(None, {s.get_inputs()[0].name: x.transpose(2, 0, 1)[None]})[0][0]
    lo, hi = np.percentile(d, 2), np.percentile(d, 98)
    d = np.clip((d - lo) / (hi - lo + 1e-6), 0, 1)
    out = Image.fromarray((d * 255).astype(np.uint8)).resize((w, h), Image.BILINEAR)
    # soften edges a little: a hard step in depth tears the picture when it moves
    out = out.filter(ImageFilter.MaxFilter(5)).filter(ImageFilter.GaussianBlur(4))
    return np.asarray(out, np.float32) / 255.0


def cached(path):
    """Depth map for a picture file, made once and kept in images/.depth/."""
    folder = os.path.join(os.path.dirname(path), ".depth")
    out = os.path.join(folder, os.path.splitext(os.path.basename(path))[0] + ".png")
    if not os.path.exists(out) or os.path.getmtime(out) < os.path.getmtime(path):
        os.makedirs(folder, exist_ok=True)
        d = estimate(Image.open(path))
        Image.fromarray((d * 255).astype(np.uint8)).save(out)
    return np.asarray(Image.open(out).convert("L"), np.float32) / 255.0


# camera moves: each gives (sideways shift, up/down shift, push-in) at progress p (0..1) through the picture's time
SHOTS = {
    "dolly_in":   lambda p: (0.0, 0.0, 0.10 * p),
    "dolly_out":  lambda p: (0.0, 0.0, 0.10 * (1 - p)),
    "truck_right": lambda p: (-0.5 + p, 0.0, 0.04),
    "truck_left": lambda p: (0.5 - p, 0.0, 0.04),
    "crane_up":   lambda p: (0.0, 0.5 - p, 0.05 + 0.03 * p),
    "orbit":      lambda p: (0.55 * math.sin(math.pi * (p - 0.5)), 0.12 * math.cos(math.pi * p), 0.06),
}
ORDER = ("dolly_in", "truck_right", "orbit", "crane_up", "truck_left", "dolly_out")


class Parallax:
    """One picture and its depth, ready to be filmed from slightly different camera positions."""

    def __init__(self, img, depth, size, strength=1.0):
        import cv2
        self.cv2 = cv2
        self.w, self.h = size
        margin = 1.12                      # the picture is a bit bigger than the frame: room for the moves
        bw, bh = int(self.w * margin), int(self.h * margin)
        s = max(bw / img.width, bh / img.height)
        img = img.convert("RGB").resize((max(bw, round(img.width * s)), max(bh, round(img.height * s))), Image.LANCZOS)
        dm = Image.fromarray((depth * 255).astype(np.uint8)).resize(img.size, Image.BILINEAR)
        x0, y0 = (img.width - bw) // 2, (img.height - bh) // 2
        self.src = np.ascontiguousarray(np.asarray(img.crop((x0, y0, x0 + bw, y0 + bh))))
        self.depth = np.asarray(dm.crop((x0, y0, x0 + bw, y0 + bh)), np.float32) / 255.0
        self.bw, self.bh = bw, bh
        self.strength = strength
        # where each output pixel sits on the bigger picture, before any move
        gx, gy = np.meshgrid(np.arange(self.w, dtype=np.float32), np.arange(self.h, dtype=np.float32))
        self.gx = gx + (bw - self.w) / 2
        self.gy = gy + (bh - self.h) / 2
        self.cx, self.cy = bw / 2, bh / 2
        # depth seen from the frame's own pixels (good enough for small moves: no holes to fill)
        self.d = cv2.resize(self.depth, (bw, bh))[int((bh - self.h) / 2):int((bh - self.h) / 2) + self.h,
                                                   int((bw - self.w) / 2):int((bw - self.w) / 2) + self.w]

    def frame(self, sx, sy, push):
        """sx, sy: camera shift (-1..1, about 5% of the width for the nearest things), push: dolly in (0..0.15)."""
        k = self.strength
        near = self.d
        # near things move more and grow more; far things barely move (the sky stays put)
        amp_x = 0.045 * self.w * k
        amp_y = 0.03 * self.h * k
        scale = 1 + push * (0.35 + 0.65 * near)
        mx = self.cx + (self.gx - self.cx) / scale - sx * amp_x * (near - 0.3)
        my = self.cy + (self.gy - self.cy) / scale - sy * amp_y * (near - 0.3)
        out = self.cv2.remap(self.src, mx, my, self.cv2.INTER_LINEAR, borderMode=self.cv2.BORDER_REFLECT)
        return Image.fromarray(out)

    def shift_of(self, sx, sy, push, depth=0.85):
        """How far something standing at this depth moves (for the cut-out characters): (dx, dy, scale)."""
        k = self.strength
        return (sx * 0.045 * self.w * k * (depth - 0.3), sy * 0.03 * self.h * k * (depth - 0.3),
                1 + push * (0.35 + 0.65 * depth))


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    d = estimate(Image.open(sys.argv[1]))
    Image.fromarray((d * 255).astype(np.uint8)).save(sys.argv[2])
