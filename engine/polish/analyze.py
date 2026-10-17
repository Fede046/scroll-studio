"""Scoring one finished film: second by second and beat by beat.

`scan_film` reads a film once and measures it; `score` turns the measurements into severities (0 fine, 1 clearly
visible) for the five things a viewer notices without being able to say why: pops, softness, halos, style drift and
morphs. Thresholds are constants at the top of each scorer, with the clean and the broken values they were set between
(measured on the Presence landing page and on examples/feel; see docs/ENGINE.md, "Polish report").

Time is in seconds of the joined film. Everything here is CPU, numpy and OpenCV.
"""
from __future__ import annotations

import math
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

import cv2
import numpy as np

from . import metrics as M
from .metrics import ramp

SAMPLES_PER_S = 4            # edge / halo / style samples per second of film
MIN_SEV = 0.40               # an issue is a stretch whose severity reaches this
MERGE_GAP = 0.6              # samples closer than this (seconds) are one stretch
STILL_PX = 8.0               # the picture counts as still while it has moved less than this (px at 384 wide) since the beat began


@dataclass
class BeatSpan:
    id: str
    start: float                       # seconds of the joined film where the beat's own clip starts
    end: float
    clip: Optional[Path] = None
    kind: str = "generated"            # generated | freeze | film
    zoom: Optional[float] = None       # freeze: the tightest framing, as a share of the frame's width
    upscale: float = 1.0

    @property
    def dur(self) -> float:
        return self.end - self.start


@dataclass
class Scan:
    path: Path
    fps: float
    n: int
    size: tuple[int, int]                              # width, height of the film
    small: list = field(default_factory=list)          # FLOW_W gray uint8 per frame
    luma: np.ndarray = None
    samples: dict = field(default_factory=dict)        # frame index -> {"edge":, "style":}
    step: int = 6                                      # frames between samples


# ---------------------------------------------------------------- reading

def open_film(path: Path):
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise RuntimeError(f"cannot read the film {path} (OpenCV could not open it)")
    return cap


def scan_film(path: Path, progress: Callable[[float, str], None] = lambda f, m="": None,
              workers: Optional[int] = None) -> Scan:
    """One pass over the film: a small gray copy of every frame (for flow), and edge + style statistics of every
    `step`-th frame at full size."""
    import os
    cap = open_film(path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
    n_est = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
    W, H = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    step = max(1, round(fps / SAMPLES_PER_S))
    sc = Scan(path=path, fps=fps, n=0, size=(W, H), step=step)
    workers = workers or max(2, min(8, (os.cpu_count() or 4) - 1))
    sem = threading.BoundedSemaphore(workers * 3)
    pending: dict = {}

    def job(i, frame):
        try:
            g = M.gray_f32(frame)
            return {"edge": M.edge_stats(g, want_points=True), "style": M.style_stats(frame)}
        finally:
            sem.release()

    with ThreadPoolExecutor(workers) as ex:
        i = 0
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            sc.small.append(cv2.cvtColor(M.resize_w(frame, M.FLOW_W), cv2.COLOR_BGR2GRAY))
            if i % step == 0:
                sem.acquire()
                pending[i] = ex.submit(job, i, frame)
            i += 1
            if i % 48 == 0:
                progress(0.5 * min(1.0, i / n_est), f"reading frames ({i}/{n_est})")
        for k, fut in pending.items():
            sc.samples[k] = fut.result()
    cap.release()
    sc.n = i
    sc.luma = np.array([float(g.mean()) for g in sc.small], np.float32)
    return sc


def read_frames(path: Path, idxs: list[int], width: Optional[int] = None) -> dict[int, np.ndarray]:
    """BGR frames of a clip at the given frame indices (sequential read: seeking is not frame-exact in every file)."""
    want = sorted({max(0, int(i)) for i in idxs})
    out: dict[int, np.ndarray] = {}
    if not want:
        return out
    cap = open_film(path)
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    last = None
    i = 0
    wi = 0
    while wi < len(want):
        ok, f = cap.read()
        if not ok:
            break
        last = f
        while wi < len(want) and want[wi] == i:
            out[want[wi]] = M.resize_w(f, width) if width else f
            wi += 1
        i += 1
    if last is not None:              # indices past the end get the last frame
        for k in want[wi:]:
            out[k] = M.resize_w(last, width) if width else last
    cap.release()
    return out


# ---------------------------------------------------------------- motion: steps between new frames

def steps_of(sc: Scan, workers: Optional[int] = None,
             progress: Callable[[float, str], None] = lambda f, m="": None) -> dict:
    """Find the frames that are new (video made at 12 fps and written at 24 repeats every frame; a held shot repeats
    its frame), then measure every step from one new frame to the next."""
    import os
    G = sc.small
    n = len(G)
    plain = np.array([float(np.abs(G[i + 1].astype(np.int16) - G[i].astype(np.int16)).mean()) for i in range(n - 1)])
    # frame i+1 is a repeat when it hardly differs from i, compared with what moves nearby
    new = [0]
    for i in range(n - 1):
        lo, hi = max(0, i - 12), min(n - 1, i + 13)
        p90 = float(np.percentile(plain[lo:hi], 90))
        if plain[i] >= max(0.15, 0.2 * p90):
            new.append(i + 1)
    a_idx, b_idx = new[:-1], new[1:]
    workers = workers or max(2, min(8, (os.cpu_count() or 4) - 1))
    res: list = [None] * len(a_idx)
    done = [0]

    def one(k):
        r = M.step_stats(G[a_idx[k]], G[b_idx[k]])
        done[0] += 1
        return r
    with ThreadPoolExecutor(workers) as ex:
        for k, r in enumerate(ex.map(one, range(len(a_idx)))):
            res[k] = r
            if k % 40 == 0:
                progress(0.5 + 0.35 * k / max(1, len(a_idx)), f"measuring motion ({k}/{len(a_idx)})")
    gap = np.array([b - a for a, b in zip(a_idx, b_idx)], np.float32)
    return {"a": np.array(a_idx), "b": np.array(b_idx), "gap": gap, "t": np.array(b_idx) / sc.fps,
            "plain": np.array([r["plain"] for r in res]), "resid": np.array([r["resid"] for r in res]),
            "local": np.array([r["local"] for r in res]), "mot": np.array([r["mot"] for r in res]),
            "dl": np.array([abs(float(sc.luma[b]) - float(sc.luma[a])) for a, b in zip(a_idx, b_idx)]),
            "new_frames": len(new), "frames": n}


# ---------------------------------------------------------------- scorers: each returns series of (t, severity, info)

def _roll_median(x: np.ndarray, i: int, w: int) -> float:
    lo, hi = max(0, i - w), min(len(x), i + w + 1)
    v = np.concatenate([x[lo:i], x[i + 1:hi]])
    return float(np.median(v)) if len(v) else float(x[i])


def score_pops(st: dict) -> list[dict]:
    """Pops inside the film (not at joins: see score_joins).

    jump     the change between two frames that motion cannot explain (flow residual) is many times what its neighbours
             show: a pop, a glitch, a cut. Clean: 0.5-3x. Set between 2.5x (fine) and 5x (clearly a pop), and only when
             the residual is itself visible (1.5 levels and up).
    flash    the whole picture's brightness steps by more than the steps around it do: a flicker.
    stutter  while things move, the picture updates fewer than 12 times a second and by a visible amount: judder.
    """
    out = []
    if len(st["t"]) < 3:
        return out
    s = st["resid"] / st["gap"]
    dl = st["dl"] / st["gap"]
    for i in range(len(s)):
        base = max(_roll_median(s, i, 8), 0.6)
        ratio = s[i] / base
        sev = ramp(ratio, 2.5, 5.0) * ramp(s[i], 1.5, 3.0)
        if sev > 0:
            out.append({"t": float(st["t"][i]), "sev": sev, "kind": "jump", "ratio": float(ratio), "resid": float(s[i]),
                        "a": int(st["a"][i]), "b": int(st["b"][i])})
        bl = max(_roll_median(dl, i, 8), 0.3)
        fl = ramp(dl[i], 3.0, 8.0) * ramp(dl[i] / bl, 3.0, 6.0)
        if fl > 0:
            out.append({"t": float(st["t"][i]), "sev": fl, "kind": "flash", "step": float(dl[i]),
                        "a": int(st["a"][i]), "b": int(st["b"][i])})
    # stutter: windows of a second
    fps = st["frames"] / max(1e-3, st["t"][-1]) if len(st["t"]) else 24
    t_all = st["t"]
    for t0 in np.arange(0.0, float(t_all[-1]) - 0.5, 0.5):
        m = (t_all >= t0) & (t_all < t0 + 1.0)
        if m.sum() < 3:
            continue
        rate = float(m.sum())                                   # new frames in a second
        move = float(np.median(st["plain"][m]))
        sev = ramp(rate, 12.0, 6.0) * ramp(move, 1.0, 4.0)
        if sev > 0:
            out.append({"t": float(t0 + 0.5), "sev": sev, "kind": "stutter", "rate": rate, "move": move,
                        "a": int(st["a"][m][0]), "b": int(st["b"][m][-1])})
    return out


def score_morphs(st: dict, skip: tuple = ()) -> list[dict]:
    """Things that appear, dissolve or rearrange rather than move.

    Over every half second, `unexplained` is the share of the picture's change that optical flow cannot account for
    (flow residual / plain difference) and `level` how big that residual is. A walking crowd or a camera push is 0.2-0.5;
    a crowd that dissolves into rows is 0.8-1. Set between 0.55 (fine) and 0.85, and only when the residual is at least
    0.8 levels (quiet, grainy frames always read as unexplained)."""
    out = []
    t = st["t"]
    if len(t) < 4:
        return out
    for t0 in np.arange(0.0, float(t[-1]), 0.25):
        m = (t >= t0) & (t < t0 + 0.5)
        if m.sum() < 2 or any(a - 0.1 <= t0 + 0.25 <= b + 0.1 for a, b in skip):
            continue
        sp, sr = float(st["plain"][m].sum()), float(st["resid"][m].sum())
        q = sr / max(sp, 1e-3)
        level = sr / m.sum()
        sev = ramp(q, 0.55, 0.85) * ramp(level, 1.2, 2.2)
        if sev > 0:
            out.append({"t": float(t0 + 0.25), "sev": sev, "unexplained": float(q), "level": float(level),
                        "a": int(st["a"][m][0]), "b": int(st["b"][m][-1])})
    return out


def width_reference(samples: dict) -> Optional[float]:
    """The section's own sharpest: the 10th percentile of its frames' median edge widths."""
    w = [s["edge"]["width"] for s in samples.values() if s["edge"]["width"] is not None and s["edge"]["n_edges"] >= 300]
    return float(np.percentile(w, 10)) if len(w) >= 3 else None


def score_softness(sc: Scan) -> list[dict]:
    """Effective detail: the median width of the sharp edges, at 1920 px across. Clean ink-and-wash or photo: 1.7-2.2;
    a frame stretched from fewer pixels: 3.3-3.8 and up (Presence: the 7x crop of the hands 3.3, the boots 3.8). Severity
    from 2.4 (fine) to 3.8 (clearly upscaled). Needs 300 clean edges to judge (a blank frame is not soft)."""
    out = []
    ref = width_reference(sc.samples)
    for i, s in sorted(sc.samples.items()):
        e = s["edge"]
        if e["width"] is None or e["n_edges"] < 300:
            continue
        out.append({"t": i / sc.fps, "sev": ramp(e["width"], 2.4, 3.8), "width": e["width"], "ref": ref,
                    "aniso": e["aniso"], "frame": i})
    return out


def score_halos(sc: Scan) -> list[dict]:
    """Bright rims and seams beside clean edges: the share of flat-sided strong edges with one. Clean frames of linework or
    photo: 1-5%; the Presence hands close-up: 20% (halo seams down the coat and fingers). Severity from 7% to 17%. Needs
    300 such edges."""
    out = []
    for i, s in sorted(sc.samples.items()):
        e = s["edge"]
        if e["rim"] is None or e["n_rim"] < 300:
            continue
        out.append({"t": i / sc.fps, "sev": ramp(e["rim"], 0.07, 0.17), "rim": e["rim"], "n": e["n_rim"], "frame": i})
    return out


def score_drift(sc: Scan, st: dict, spans: list[BeatSpan], fade: float, embed: Optional[dict] = None) -> list[dict]:
    """How far the look moves from the section's base plate (its first second), and within a beat from where the beat
    started. Measured on:

    hatch    share of the picture's structure that is weak texture (hatching, pencil, grain) rather than strong lines.
             Presence: clean ink and wash 0.36, the pencil look the turn beat drifts to 0.64. One JND = 0.15.
    grain    noise in flat areas, only while the frame is not magnified (a zoom loses grain by itself). One JND = x1.65.
    tone, line, sat   histogram, line density, saturation against the beat's own first second, only while the camera
             has barely moved (a push changes the content, not the look). JND 0.10 / x1.4 / 0.06.
    embed    (with --embed) 1 - cosine of a CLIP image embedding to the base plate, while the camera is nearly still.

    Severity from 1 JND (fine) to 2 JND (clearly a different look); the worst component is the one reported."""
    out = []
    keys = sorted(sc.samples)
    if not keys:
        return out
    fps = sc.fps
    plate = [k for k in keys if k / fps < 1.0] or keys[:2]

    def med(ks, f):
        v = [sc.samples[k]["style"][f] for k in ks if sc.samples[k]["style"][f] == sc.samples[k]["style"][f]]
        return float(np.median(v)) if v else float("nan")
    p_hatch, p_fine, p_grain = med(plate, "hatch"), med(plate, "fine"), med(plate, "grain")
    p_w = [sc.samples[k]["edge"]["width"] for k in plate if sc.samples[k]["edge"]["width"] is not None]
    p_w = float(np.median(p_w)) if p_w else None
    # how far the picture has moved so far: cumulative mean flow length at every frame (px at FLOW_W)
    cam = np.zeros(sc.n + 1)
    for b, mo in zip(st["b"], st["mot"]):
        cam[b:] += mo
    for sp in spans:
        own = [k for k in keys if sp.start <= k / fps < sp.end]
        if not own:
            continue
        i0 = int(round(sp.start * fps))
        ref = [k for k in own if k / fps < sp.start + max(1.0, fade + 0.5)][:4] or own[:2]
        r_tone = np.mean([sc.samples[k]["style"]["tone"] for k in ref], 0)
        r_sat, r_line = med(ref, "sat"), med(ref, "line")
        r_emb = embed.get("beat_ref", {}).get(sp.id) if embed else None
        for k in own:
            sy = sc.samples[k]["style"]
            comps = {}
            if sy["fine"] >= 0.06 and p_fine >= 0.06 and sy["hatch"] == sy["hatch"] and p_hatch == p_hatch:
                comps["hatch"] = (abs(sy["hatch"] - p_hatch) / 0.15, sy["hatch"], p_hatch)
            w = sc.samples[k]["edge"]["width"]
            if (sy["grain"] == sy["grain"] and p_grain == p_grain and p_grain > 0.3 and sy["grain"] > 0.1
                    and w is not None and p_w and w / p_w <= 1.5):
                comps["grain"] = (abs(math.log(sy["grain"] / p_grain)) / math.log(1.65), sy["grain"], p_grain)
            still = abs(cam[k] - cam[min(sc.n, max(i0, ref[0]))]) < STILL_PX
            if still and k not in ref:
                comps["tone"] = (float(np.abs(sy["tone"] - r_tone).sum() / 2) / 0.10, None, None)
                if r_line > 0.01 and sy["line"] > 0.005:
                    comps["line"] = (abs(math.log(sy["line"] / r_line)) / math.log(1.4), sy["line"], r_line)
                comps["sat"] = (abs(sy["sat"] - r_sat) / 0.06, sy["sat"], r_sat)
            if embed and still and k in embed.get("frame", {}) and embed.get("plate") is not None:
                d = 1.0 - float(np.dot(embed["frame"][k], embed["plate"]))
                comps["embed"] = (d / embed.get("jnd", 0.12), d, None)
            if not comps:
                continue
            # the most telling component that is a clear change; else the biggest
            clear = [c for c in ("embed", "hatch", "grain", "line", "tone", "sat") if c in comps and comps[c][0] >= 1.0]
            name = clear[0] if clear else max(comps, key=lambda c: comps[c][0])
            z, v, r = comps[name]
            z = max(z, max(c[0] for c in comps.values()) if clear else z)
            out.append({"t": k / fps, "sev": ramp(z, 1.0, 2.0), "z": float(z), "what": name, "value": v, "ref": r,
                        "beat": sp.id, "frame": k, "all": {a: float(b[0]) for a, b in comps.items()}})
    return out


# ---------------------------------------------------------------- joins

def score_joins(spans: list[BeatSpan], fade: float, log: Callable[[str], None] = lambda s: None) -> list[dict]:
    """The dissolve between two shots. At the middle of the crossfade the viewer sees both pictures at half strength:
    `edges` is the share of edge energy that is not in both. Same drawing = 0 (the new shot starts where the old one
    ended and nothing moves), two shots that do not line up = 0.6-0.9. Severity from 0.45 (fine) to 0.85. A colour
    change (`chroma`, Lab levels) counts from 1.5 to 4.5, and a hard cut (no fade) is judged on the two frames it
    joins."""
    out = []
    for prev, cur in zip(spans[:-1], spans[1:]):
        if prev.clip is None or cur.clip is None or not prev.clip.exists() or not cur.clip.exists():
            continue
        cap = open_film(prev.clip)
        fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
        na = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)); cap.release()
        cap = open_film(cur.clip)
        nb = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)); cap.release()
        nf = max(1, int(round(fade * fps)))
        ia = {s: (na - nf + int(round(s * nf)) - (1 if s == 1.0 else 0)) for s in (0.0, 0.5, 1.0)}
        ib = {s: min(nb - 1, int(round(s * nf))) for s in (0.0, 0.5, 1.0)}
        fa = read_frames(prev.clip, list(ia.values()), 480)
        fb = read_frames(cur.clip, list(ib.values()), 480)
        mm = {s: M.mismatch(fa[ia[s]], fb[ib[s]]) for s in (0.0, 0.5, 1.0)}
        if fade < 0.15:
            m0 = M.mismatch(fa[na - 1] if na - 1 in fa else fa[ia[1.0]], fb[0])
            sev = ramp(m0["edges"], 0.25, 0.6)
            kind = "cut"
        else:
            m0 = mm[0.5]
            sev = max(ramp(m0["edges"], 0.45, 0.85), 0.8 * ramp(m0["chroma"], 1.5, 4.5))
            kind = "dissolve"
        out.append({"t": cur.start + fade / 2, "t0": cur.start, "t1": cur.start + fade, "sev": sev, "kind": kind,
                    "from": prev.id, "to": cur.id, "edges": m0["edges"], "luma": m0["luma"], "chroma": m0["chroma"],
                    "phases": {f"{s:.1f}": mm[s]["edges"] for s in mm},
                    "frames": {"a": ia[0.5], "b": ib[0.5], "prev": prev.id, "cur": cur.id}})
    return out
