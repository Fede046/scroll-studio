"""Framing: where each output frame looks inside its source, so 9:16 is a reframe, never a letterbox.

For a take with a product, the product's screen position per frame comes from the take's own camera
(`take.py --pass track`, the same camera maths as the product pass). Other footage uses a saliency-guided crop
(OpenCV spectral residual plus faces) sampled across the shot and smoothed into a slow, steady pan.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Optional

import numpy as np

from ..config import settings


def cover(sw: int, sh: int, W: int, H: int) -> tuple[float, float]:
    """Largest W:H rectangle inside a sw x sh source."""
    aspect = W / H
    cw = min(sw, sh * aspect)
    return cw, cw / aspect


def warp(img: np.ndarray, W: int, H: int, fx: float, fy: float, zoom: float) -> np.ndarray:
    """Crop the W:H window at zoom `zoom` centred (as far as the frame allows) on (fx, fy) in 0-1 source
    coordinates, scaled to W x H with sub-pixel placement so slow pans and pushes never step."""
    import cv2
    sh, sw = img.shape[:2]
    cw0, ch0 = cover(sw, sh, W, H)
    cw, ch = cw0 / zoom, ch0 / zoom
    x0 = min(max(fx * sw - cw / 2, 0.0), sw - cw)
    y0 = min(max(fy * sh - ch / 2, 0.0), sh - ch)
    s = W / cw
    M = np.float32([[s, 0, -x0 * s], [0, s, -y0 * s]])
    return cv2.warpAffine(img, M, (W, H), flags=cv2.INTER_CUBIC if s > 1 else cv2.INTER_AREA,
                          borderMode=cv2.BORDER_REPLICATE)


def frames(src: Path, t0: float, n: int, fps: int, speed: float = 1.0, hold: bool = False, width: Optional[int] = None):
    """Yield n BGR frames of src from t0 at `fps` (played at `speed`), decoded by FFmpeg; a short source repeats
    its last frame. hold: the frame at t0, n times."""
    info = _size(src)
    sw, sh = info
    if width:
        sh, sw = round(sh * width / sw / 2) * 2, width
    vf = [f"setpts=PTS/{speed}" if speed != 1 else None, f"fps={fps}", f"scale={sw}:{sh}" if width else None]
    vf = ",".join(v for v in vf if v)
    count = 1 if hold else n
    cmd = [settings()["ffmpeg"], "-hide_banner", "-loglevel", "error", "-ss", f"{max(t0, 0):.4f}", "-i", str(src),
           "-vf", vf, "-frames:v", str(count), "-f", "rawvideo", "-pix_fmt", "bgr24", "-"]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    size = sw * sh * 3
    last = None
    got = 0
    try:
        while got < count:
            buf = p.stdout.read(size)
            if len(buf) < size:
                break
            last = np.frombuffer(buf, np.uint8).reshape(sh, sw, 3)
            got += 1
            if not hold:
                yield last
    finally:
        p.stdout.close()
        p.wait()
    if last is None:   # asked for the very end of the file: take its last frame
        tail = subprocess.run([settings()["ffmpeg"], "-hide_banner", "-loglevel", "error", "-ss", f"{max(t0 - 1.5, 0):.4f}",
                               "-i", str(src), "-vf", vf, "-f", "rawvideo", "-pix_fmt", "bgr24", "-"],
                              capture_output=True).stdout
        if len(tail) < size:
            raise RuntimeError(f"could not decode {src} at {t0:.2f}s")
        last = np.frombuffer(tail[(len(tail) // size - 1) * size:][:size], np.uint8).reshape(sh, sw, 3)
    for _ in range(n - (0 if hold else got)):
        yield last


_SIZES: dict = {}


def _size(src: Path) -> tuple[int, int]:
    key = str(src)
    if key not in _SIZES:
        from ..project import probe
        i = probe(src)
        _SIZES[key] = (int(i["width"]), int(i["height"]))
    return _SIZES[key]


def still(src: Path, t: float, width: int = 480) -> np.ndarray:
    return next(frames(src, t, 1, 24, hold=True, width=width))


# ---------------------------------------------------------------- saliency

def _saliency(img: np.ndarray) -> np.ndarray:
    """Saliency map 0-1 (spectral residual) with faces lifted, from a small BGR frame."""
    import cv2
    h, w = img.shape[:2]
    # spectral residual (Hou & Zhang 2007) on a 96 px wide grey copy: what stands out from the image's own statistics
    sw = 96
    small = cv2.resize(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), (sw, max(8, round(h * sw / w))), interpolation=cv2.INTER_AREA)
    F = np.fft.fft2(small.astype(np.float32) / 255)
    logA = np.log(np.abs(F) + 1e-8)
    resid = logA - cv2.blur(logA, (3, 3))
    sal = np.abs(np.fft.ifft2(np.exp(resid + 1j * np.angle(F)))) ** 2
    sal = cv2.GaussianBlur(sal.astype(np.float32), (0, 0), 2.5)
    m = cv2.resize(sal, (w, h), interpolation=cv2.INTER_LINEAR)
    m /= max(float(m.max()), 1e-6)
    try:
        casc = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        for (x, y, w, h) in casc.detectMultiScale(gray, 1.15, 5, minSize=(img.shape[1] // 24,) * 2):
            m[y:y + h, x:x + w] += 1.5
    except Exception:
        pass
    return m


def salient_point(img: np.ndarray, W: int, H: int) -> tuple[float, float]:
    """Centre (0-1) of the W:H crop window that holds the most saliency, with a gentle pull to the middle."""
    m = _saliency(img)
    h, w = m.shape
    cw, ch = cover(w, h, W, H)
    xs = np.linspace(0, 1, w)
    ys = np.linspace(0, 1, h)
    col = m.sum(axis=0) * (1 - 0.35 * np.abs(xs - 0.5) * 2)
    row = m.sum(axis=1) * (1 - 0.35 * np.abs(ys - 0.5) * 2)

    def best(profile, win, n):
        win = max(1, int(round(win)))
        if win >= n:
            return 0.5
        c = np.convolve(profile, np.ones(win), "valid")
        return (int(np.argmax(c)) + win / 2) / n
    return best(col, cw, w), best(row, ch * 0.8, h)


def smooth(a: np.ndarray, sigma: float) -> np.ndarray:
    """Gaussian smoothing along time (edges held), sigma in frames."""
    if sigma <= 0 or len(a) < 3:
        return a
    r = int(3 * sigma)
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / sigma) ** 2)
    k /= k.sum()
    pad = np.pad(a, ((r, r),) + ((0, 0),) * (a.ndim - 1), mode="edge")
    if a.ndim == 1:
        return np.convolve(pad, k, "valid")
    return np.stack([np.convolve(pad[:, j], k, "valid") for j in range(a.shape[1])], axis=1)


def focus_path(src: Path, t0: float, n: int, fps: int, speed: float, hold: bool, W: int, H: int,
               track: Optional[dict] = None, fixed: Optional[tuple[float, float]] = None) -> np.ndarray:
    """Per output frame (fx, fy) in 0-1 source coordinates.

    fixed: the spec's `focus`. track: a take's product track; the crop follows the product once it is big enough
    to be the subject (blending in from the saliency crop while it is a speck), then everything is smoothed."""
    if fixed is not None:
        return np.tile(np.array(fixed, np.float64), (n, 1))
    times = np.array([t0 + (0 if hold else i * speed / fps) for i in range(n)])
    sal = None
    # saliency, sampled across the shot (about every 0.6 s of output, at least two samples)
    if not track:
        k = 1 if hold else max(2, min(8, int(n / fps / 0.6) + 1))
        st = np.linspace(times[0], times[-1], k)
        pts = np.array([salient_point(still(src, float(t)), W, H) for t in st])
        if k > 1:
            pts = smooth(pts, 0.8)
            sal = np.stack([np.interp(times, st, pts[:, j]) for j in range(2)], axis=1)
        else:
            sal = np.tile(pts[0], (n, 1))
    out = sal
    if track:
        # a take: away from the product the camera's own aim (the frame centre) frames the shot
        sal = np.tile(np.array([0.5, 0.5]), (n, 1))
        tf = track["fps"]
        fr = track["frames"]
        prod = np.zeros((n, 2))
        w = np.zeros(n)
        for i, t in enumerate(times):
            e = fr[min(len(fr) - 1, max(0, int(round(t * tf))))]
            if not e:
                continue
            x0, y0, x1, y1 = e["box"]
            inside = -0.05 < e["c"][0] < 1.05 and -0.05 < e["c"][1] < 1.05
            prod[i] = e["c"]
            w[i] = float(np.clip((y1 - y0 - 0.006) / 0.03, 0, 1)) if inside else 0.0
        w = smooth(w, fps * 0.4)
        out = sal * (1 - w[:, None]) + prod * w[:, None]
    return smooth(out, fps * 0.35)


# How far a crop may be scaled up before it reads soft: a 9:16 phone frame is seen small, so it tolerates more.
MAX_UPSCALE = {"16x9": 1.3, "9x16": 2.0}
MAX_PUSH = 1.3
TARGET = {"16x9": 0.36, "9x16": 0.32}     # the product's share of the frame height a push aims for


def max_zoom(src: Path, W: int, H: int, fmt: str) -> float:
    """The deepest push-in the source's resolution allows without going soft (never past MAX_PUSH)."""
    sw, sh = _size(src)
    cw0, _ = cover(sw, sh, W, H)
    return max(1.0, min(MAX_PUSH, MAX_UPSCALE[fmt] * cw0 / W))


def product_sizes(track: dict, times) -> np.ndarray:
    fr, tf = track["frames"], track["fps"]
    out = []
    for t in times:
        e = fr[min(len(fr) - 1, max(0, int(round(t * tf))))]
        ok = e and -0.05 < e["c"][0] < 1.05 and -0.05 < e["c"][1] < 1.05
        out.append(max(0.0, e["box"][3] - e["box"][1]) if ok else 0.0)
    return np.array(out)


def product_push(track: dict, times, fmt: str, zmax: float) -> Optional[float]:
    """The zoom that makes a take's product read large (TARGET of the frame height), within what the source allows;
    None when the product is not the subject of these frames (mostly off screen, or a speck)."""
    h = product_sizes(track, times)
    vis = h[h > 0]
    if len(vis) < 0.6 * len(h) or float(np.median(vis)) < 0.035 or zmax <= 1.001:
        return None
    return float(np.clip(TARGET[fmt] / float(np.median(vis)), 1.0, zmax))


def load_track(path: Optional[Path]) -> Optional[dict]:
    """A take's product track (take.py --pass track) as {fps, frames: [{c, box, dist} | None]}."""
    if not (path and path.exists()):
        return None
    t = json.loads(path.read_text(encoding="utf-8"))
    frames = []
    for e in t.get("frames", []):
        if e and "c" in e:
            frames.append(e)
        elif e and e.get("centre") and e.get("box"):
            frames.append({"c": e["centre"], "box": e["box"], "dist": e.get("distance")})
        else:
            frames.append(None)
    return {"fps": t["fps"], "res": t.get("size") or t.get("res"), "frames": frames}
