"""world_depth: a steady, edge-true depth video for a film (Depth Anything V2 per frame, then made to hold still).

Depth Anything V2 gives one relative depth map per image. Run on every frame of a film it is sharp but it does not hold
still: each frame is normalised on its own, so the whole map breathes, and edges shimmer. Type that sits *behind* things
needs a map the eye cannot catch out, so after the per-frame estimate (`depth.estimate_raw`):

  align     each frame's map is fitted (scale and shift, robust least squares) to the previous steady map carried over by
            optical flow, so the scale cannot jump from frame to frame; the chain restarts at every cut,
  blend     where the flow is trustworthy (the frame it came from matches this one) the carried map is blended in, which
            averages out the per-frame noise without smearing moving edges (the carried map moves with the flow),
  snap      a guided filter with the frame itself as the guide pulls every depth edge onto the picture's own edge,
  range     the whole shot is then mapped to 0 (far) .. 1 (near) by percentiles smoothed over time.

`steady_depth` is the whole pipeline over an array of frames; `encode_depth` and the mask packing live in engine/world.py.
CPU twins of everything the browser does with the result are in engine/world_math.py.
"""
from __future__ import annotations

from typing import Callable, Iterable, Optional

import cv2
import numpy as np

VERSION = 2
CUT_CONFIDENCE = 0.12        # the flow explains less than this share of a frame: it is a new shot


def flow_back(cur_gray: np.ndarray, prev_gray: np.ndarray) -> np.ndarray:
    """Dense flow from the current frame to the previous one (so the previous map can be sampled at p + flow(p))."""
    dis = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)
    return dis.calc(cur_gray, prev_gray, None)


def warp(img: np.ndarray, flow: np.ndarray, border=cv2.BORDER_REPLICATE) -> np.ndarray:
    h, w = flow.shape[:2]
    gx, gy = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))
    return cv2.remap(img, gx + flow[..., 0], gy + flow[..., 1], cv2.INTER_LINEAR, borderMode=border)


def fit_affine(src: np.ndarray, dst: np.ndarray, w: np.ndarray, iters: int = 3) -> tuple[float, float]:
    """Robust a, b minimising sum w (a*src + b - dst)^2 (iteratively reweighted: outliers, such as things that moved, count less)."""
    s, d, w = src.ravel(), dst.ravel(), w.ravel().astype(np.float64)
    keep = w > 1e-3
    s, d, w = s[keep], d[keep], w[keep]
    if len(s) < 64:
        return 1.0, 0.0
    if len(s) > 60000:                      # a sample is plenty for two numbers
        idx = np.random.default_rng(1).choice(len(s), 60000, replace=False)
        s, d, w = s[idx], d[idx], w[idx]
    a, b = 1.0, 0.0
    cw = w.copy()
    for _ in range(iters):
        sw = cw.sum()
        ms, md = (cw * s).sum() / sw, (cw * d).sum() / sw
        var = (cw * (s - ms) ** 2).sum()
        a = (cw * (s - ms) * (d - md)).sum() / max(var, 1e-9)
        a = float(np.clip(a, 0.2, 5.0))
        b = float(md - a * ms)
        r = np.abs(a * s + b - d)
        cw = w / (1 + (r / (0.05 + 1e-9)) ** 2)
    return a, b


def snap(depth: np.ndarray, frame_bgr: np.ndarray, radius: int, eps: float) -> np.ndarray:
    """Guided filter of a float depth map with the frame as the guide (depth edges move onto the picture's edges)."""
    g = frame_bgr
    try:
        return cv2.ximgproc.guidedFilter(g, depth.astype(np.float32), radius, eps * 255 * 255)
    except AttributeError:                  # opencv without contrib: a single-channel box-filter guided filter
        return _guided_gray(cv2.cvtColor(g, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255, depth.astype(np.float32), radius, eps)


def _guided_gray(I: np.ndarray, p: np.ndarray, r: int, eps: float) -> np.ndarray:
    k = (2 * r + 1, 2 * r + 1)
    mI, mp = cv2.boxFilter(I, -1, k), cv2.boxFilter(p, -1, k)
    cov = cv2.boxFilter(I * p, -1, k) - mI * mp
    var = cv2.boxFilter(I * I, -1, k) - mI * mI
    a = cov / (var + eps)
    b = mp - a * mI
    return cv2.boxFilter(a, -1, k) * I + cv2.boxFilter(b, -1, k)


def steady_depth(frames: Iterable[np.ndarray], estimate: Callable[[np.ndarray], np.ndarray], cuts: Optional[set[int]] = None,
                 blend: float = 0.5, radius: int = 6, eps: float = 2e-4, log=None) -> np.ndarray:
    """BGR uint8 frames -> uint8 depth (n, h, w): 0 far .. 255 near, steady in time and snapped to the picture's edges.

    estimate: BGR frame -> float map, any scale (larger = nearer; Depth Anything's relative inverse depth).
    cuts: frame indices where a new shot starts (the chain restarts there)."""
    cuts = cuts or set()
    out: list[np.ndarray] = []
    prev_g = prev_s = None
    lo_hi: list[tuple[float, float]] = []
    shot_start = 0
    shot_bounds: list[tuple[int, int]] = []
    for i, fr in enumerate(frames):
        raw = estimate(fr).astype(np.float32)
        g = cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY)
        if i in cuts and i > 0:
            shot_bounds.append((shot_start, i))
            shot_start = i
            prev_g = prev_s = None
        conf_mean = 0.0
        if prev_s is not None:
            fl = flow_back(g, prev_g)
            carried = warp(prev_s, fl)
            back = warp(prev_g, fl)
            err = np.abs(back.astype(np.float32) - g.astype(np.float32)) / 255
            # confidence: the frame it came from looks like this one here, and the flow is smooth (no tearing)
            fmag = cv2.GaussianBlur(np.linalg.norm(fl - cv2.GaussianBlur(fl, (0, 0), 3), axis=2), (0, 0), 2)
            conf = np.exp(-(err / 0.06) ** 2) * np.exp(-(fmag / 1.5) ** 2)
            conf_mean = float(conf.mean())
            if conf_mean < CUT_CONFIDENCE:           # nothing of the last frame is in this one: a cut nobody listed
                shot_bounds.append((shot_start, i))
                shot_start = i
                prev_s = None
        if prev_s is None:
            a, b = np.percentile(raw, [2, 99.5])
            s = (raw - a) / max(b - a, 1e-6)
        else:
            a, b = fit_affine(raw, carried, conf)
            aligned = a * raw + b
            s = aligned * (1 - blend * conf) + carried * (blend * conf)
        s = snap(s, fr, radius, eps)
        prev_g, prev_s = g, s
        out.append(s)
        lo_hi.append((float(np.percentile(s, 1)), float(np.percentile(s, 99.5))))
        if log and i % 60 == 0:
            log(f"    depth {i}  (flow confidence {conf_mean:.2f})")
    shot_bounds.append((shot_start, len(out)))
    # one range for every frame of a shot, smoothed over time: depth 0..1 means the same thing from frame to frame
    res = np.empty((len(out), *out[0].shape), dtype=np.uint8)
    for a0, b0 in shot_bounds:
        seg = np.array(lo_hi[a0:b0], dtype=np.float64)
        k = max(1, min(len(seg) // 2, 24))
        pad = np.pad(seg, ((k, k), (0, 0)), mode="edge")
        sm = np.stack([np.convolve(pad[:, c], np.ones(2 * k + 1) / (2 * k + 1), mode="valid") for c in range(2)], axis=1)
        for j in range(a0, b0):
            lo, hi = sm[j - a0]
            res[j] = np.clip((out[j] - lo) / max(hi - lo, 1e-6) * 255 + 0.5, 0, 255).astype(np.uint8)
    return res
