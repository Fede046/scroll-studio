"""Register an edited image back onto its source (`edit.align`): undo Qwen-Image-Edit's own re-framing.

The editor often returns a picture a few percent zoomed, shifted or turned. For one frame edited into several poses (the
same person at one mirror) that makes every key frame a different camera. Here the edit is matched to its source on what
should not have changed (everything outside `align.subject`, the person who moves): SIFT features on both pictures, matched
with a ratio test, a robust similarity (scale, rotation, shift) fitted with RANSAC, and the edit warped by it onto the
source's frame. Dense flow (engine/light.py) is not used: it is capped at a few tens of pixels and a re-framed edit moves
the place by more than that. With `lock` the source's own pixels are kept outside the subject box (feathered), so the place
is pixel-identical across edits and only the subject differs.
"""
from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

VERSION = 1          # bump when an aligned edit would come out differently for the same inputs
MATCH_W = 1280       # width at which features are found and matched


def _gray(rgb: np.ndarray, w: int) -> tuple[np.ndarray, float]:
    k = w / rgb.shape[1]
    small = cv2.resize(rgb, (w, round(rgb.shape[0] * k)), interpolation=cv2.INTER_AREA)
    return cv2.cvtColor(small, cv2.COLOR_RGB2GRAY), k


def _outside(shape, box, grow: float) -> np.ndarray:
    """A 0/255 mask of everything outside `box` (0-1), the box grown by `grow` of the frame on every side."""
    h, w = shape[:2]
    m = np.full((h, w), 255, np.uint8)
    if box is not None:
        x0, y0, x1, y1 = box
        m[max(0, int((y0 - grow) * h)):min(h, int((y1 + grow) * h)), max(0, int((x0 - grow) * w)):min(w, int((x1 + grow) * w))] = 0
    return m


def register(src: np.ndarray, edit: np.ndarray, subject=None) -> tuple[np.ndarray, dict]:
    """The similarity that maps `edit` (already at the source's size) onto `src`, measured outside `subject`.
    Returns the 2x3 matrix at full size and a report (scale, rotation, shift, matches, inliers, residual px)."""
    gs, k = _gray(src, MATCH_W)
    ge, _ = _gray(edit, MATCH_W)
    sift = cv2.SIFT_create(nfeatures=6000)
    ks, ds = sift.detectAndCompute(gs, _outside(gs.shape, subject, 0.02))
    # the edit's subject may have moved a little: leave a wider margin round it there
    ke, de = sift.detectAndCompute(ge, _outside(ge.shape, subject, 0.05))
    if ds is None or de is None or len(ks) < 12 or len(ke) < 12:
        return np.eye(2, 3, dtype=np.float32), {"ok": False, "why": "too few features outside the subject"}
    pairs = cv2.BFMatcher(cv2.NORM_L2).knnMatch(de, ds, k=2)
    good = [m for m, n in (p for p in pairs if len(p) == 2) if m.distance < 0.75 * n.distance]
    if len(good) < 12:
        return np.eye(2, 3, dtype=np.float32), {"ok": False, "why": f"only {len(good)} matches outside the subject"}
    pe = np.float32([ke[m.queryIdx].pt for m in good])
    ps = np.float32([ks[m.trainIdx].pt for m in good])
    M, inl = cv2.estimateAffinePartial2D(pe, ps, method=cv2.RANSAC, ransacReprojThreshold=3.0, maxIters=5000,
                                         confidence=0.999)
    if M is None or inl is None or int(inl.sum()) < 10:
        return np.eye(2, 3, dtype=np.float32), {"ok": False, "why": "no consistent move found"}
    inl = inl.ravel().astype(bool)
    res = np.linalg.norm((pe[inl] @ M[:, :2].T + M[:, 2]) - ps[inl], axis=1)
    scale = float(np.hypot(M[0, 0], M[1, 0]))
    Mf = M.astype(np.float32).copy()
    Mf[:, 2] /= k                       # the shift was measured at MATCH_W
    return Mf, {"ok": True, "scale": round(scale, 4), "rotation_deg": round(float(np.degrees(np.arctan2(M[1, 0], M[0, 0]))), 3),
                "shift_px": [round(float(Mf[0, 2]), 1), round(float(Mf[1, 2]), 1)], "matches": len(good),
                "inliers": int(inl.sum()), "residual_px": round(float(np.median(res)) / k, 2)}


def align_edit(src_path: Path, edit_path: Path, spec, out: Path, log=print) -> dict:
    """Write `out`: the edit at `edit_path` registered onto the source at `src_path` (and locked outside the subject)."""
    src = np.asarray(Image.open(src_path).convert("RGB"))
    h, w = src.shape[:2]
    edit = np.asarray(Image.open(edit_path).convert("RGB").resize((w, h), Image.LANCZOS))
    M, rep = register(src, edit, spec.subject)
    if rep["ok"]:
        moved = cv2.warpAffine(edit, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
        log(f"  aligned the edit to its source: scale {rep['scale']}, turn {rep['rotation_deg']} deg, shift "
            f"{rep['shift_px']} px ({rep['inliers']}/{rep['matches']} matches, residual {rep['residual_px']} px)")
    else:
        moved = edit
        log(f"  could not align the edit to its source ({rep['why']}); it is kept as the editor made it")
    if spec.lock and spec.subject is not None:
        # the whole subject box comes from the edit; the soft edge falls outside it, on the place, where the aligned
        # edit and the source agree, so no part of the subject is ever mixed with the source's old pose
        x0, y0, x1, y1 = (int(spec.subject[0] * w), int(spec.subject[1] * h), int(spec.subject[2] * w), int(spec.subject[3] * h))
        f = spec.feather
        a = np.zeros((h, w), np.float32)
        a[max(0, y0 - f):min(h, y1 + f), max(0, x0 - f):min(w, x1 + f)] = 1.0
        if f:
            a = cv2.GaussianBlur(a, (0, 0), f / 2)
        a[y0:y1, x0:x1] = 1.0
        moved = (moved.astype(np.float32) * a[..., None] + src.astype(np.float32) * (1 - a[..., None])).round()
        moved = np.clip(moved, 0, 255).astype(np.uint8)
    Image.fromarray(moved).save(out)
    out.with_suffix(".align.json").write_text(json.dumps(rep, indent=1))
    return rep
