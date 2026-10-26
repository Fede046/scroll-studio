"""world_track: follow a patch of a film through the shot it is in, as a similarity or a homography.

Planar tracking. Features are found inside a mask on the anchor frame (the wall a sign is painted on, or the pixels at the
depth a headline sits at), followed with pyramidal Lucas-Kanade, and a robust (RANSAC) model is fitted every frame:
a homography for a surface seen in perspective, a similarity (shift, turn, zoom) for a layer of the scene.
Drift is held down by tracking from a *keyframe* instead of from the frame before: every frame is matched against the last
keyframe (guessed from the previous frame's motion), and only when too few of the keyframe's features survive, a new keyframe
is taken at the previous frame, with fresh features, and the chain goes on from there.

`track` returns H[t] mapping the anchor frame's pixels to frame t's (NaN outside the shot or once the patch is lost), and a
confidence 0-1 per frame (features that held / features asked for). Everything is at the working size (960x540).
"""
from __future__ import annotations

from typing import Callable, Optional

import cv2
import numpy as np

MIN_FEATURES = 14
LK = dict(winSize=(31, 31), maxLevel=4, criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 30, 0.01))


def features(gray: np.ndarray, mask: Optional[np.ndarray], n: int = 500) -> np.ndarray:
    """Corners inside the mask (0-255 uint8, or None), as Nx1x2 float32. A smooth wall has few: the quality bar drops until
    there are enough."""
    for q in (0.01, 0.004, 0.0015):
        p = cv2.goodFeaturesToTrack(gray, maxCorners=n, qualityLevel=q, minDistance=5, blockSize=7, mask=mask)
        if p is not None and len(p) >= 3 * MIN_FEATURES:
            return p
    return p if p is not None else np.zeros((0, 1, 2), np.float32)


def fit(model: str, a: np.ndarray, b: np.ndarray) -> tuple[Optional[np.ndarray], np.ndarray]:
    """Robust transform a -> b (Nx2 each): (3x3 or None, inlier mask)."""
    if len(a) < 4:
        return None, np.zeros(len(a), bool)
    if model == "homography":
        h, m = cv2.findHomography(a, b, cv2.RANSAC, 2.5, maxIters=2000, confidence=0.995)
        if h is None:
            return None, np.zeros(len(a), bool)
        return h, m.ravel().astype(bool)
    m2, m = cv2.estimateAffinePartial2D(a, b, method=cv2.RANSAC, ransacReprojThreshold=2.0, maxIters=2000, confidence=0.995)
    if m2 is None:
        return None, np.zeros(len(a), bool)
    h = np.vstack([m2, [0, 0, 1]])
    return h, m.ravel().astype(bool)


def track(gray: np.ndarray, anchor: int, a: int, b: int, mask_at: Callable[[int], Optional[np.ndarray]], model: str = "similarity",
          log=None) -> tuple[np.ndarray, np.ndarray]:
    """gray: (n, h, w) uint8 working frames. The patch is `mask_at(frame)` (uint8, 255 inside) on every keyframe the tracker
    takes (the anchor first); the shot is frames a..b inclusive. Returns (H (n,3,3), confidence (n,))."""
    n = len(gray)
    H = np.full((n, 3, 3), np.nan)
    conf = np.zeros(n)
    H[anchor] = np.eye(3)
    conf[anchor] = 1.0
    for step in (1, -1):
        key, Hk = anchor, np.eye(3)                 # keyframe index, anchor -> keyframe
        pts = features(gray[key], mask_at(key))
        n0 = max(len(pts), 1)
        pts_a = cv2.perspectiveTransform(pts, np.linalg.inv(Hk)) if len(pts) else pts      # the same points in anchor coords
        prev, Hprev = anchor, np.eye(3)
        lost = 0
        t = anchor + step
        while a <= t <= b:
            if len(pts) < MIN_FEATURES:
                lost += 1
                H[t], conf[t] = Hprev, 0.0           # hold the last pose; the player fades the type out on confidence
                if lost > 3 and t - step != anchor:
                    # try to find fresh features at the held pose
                    key, Hk = prev, Hprev
                    pts = features(gray[key], _warped_mask(mask_at(anchor), Hprev, gray.shape[1:]))
                    n0 = max(len(pts), 1)
                    pts_a = cv2.perspectiveTransform(pts, np.linalg.inv(Hk)) if len(pts) else pts
                    lost = 0
                prev = t
                t += step
                continue
            guess = cv2.perspectiveTransform(pts_a, Hprev)           # where the previous frame's motion says they are
            nxt, st, _ = cv2.calcOpticalFlowPyrLK(gray[key], gray[t], pts, guess.copy(), flags=cv2.OPTFLOW_USE_INITIAL_FLOW, **LK)
            ok = st.ravel() == 1
            # forward-backward check: a feature that does not come back to where it started was not followed
            if ok.sum() >= 4:
                back, st2, _ = cv2.calcOpticalFlowPyrLK(gray[t], gray[key], nxt, None, **LK)
                ok &= (st2.ravel() == 1) & (np.linalg.norm(back - pts, axis=2).ravel() < 1.2)
            if ok.sum() < MIN_FEATURES:
                Hnew, inl = None, np.zeros(len(pts), bool)
            else:
                Hkt, inl_ok = fit(model, pts[ok].reshape(-1, 2), nxt[ok].reshape(-1, 2))
                inl = np.zeros(len(pts), bool)
                inl[np.where(ok)[0][inl_ok]] = True
                Hnew = None if Hkt is None else Hkt @ Hk
            if Hnew is not None and inl.sum() >= MIN_FEATURES and abs(np.linalg.det(Hnew[:2, :2])) > 1e-4:
                H[t] = Hnew
                conf[t] = float(min(1.0, inl.sum() / max(0.4 * n0, 1)))
                pts, pts_a = pts[inl], pts_a[inl]
                Hprev, prev = Hnew, t
                lost = 0
                # too few of the keyframe's features left, or it is old: re-key on this frame
                if len(pts) < 0.55 * n0 or abs(t - key) > 40:
                    key, Hk = t, Hnew
                    fresh = features(gray[key], _warped_mask(mask_at(anchor), Hnew, gray.shape[1:]) if mask_at(t) is None else mask_at(t))
                    if len(fresh) >= MIN_FEATURES:
                        pts = fresh
                        n0 = len(pts)
                        pts_a = cv2.perspectiveTransform(pts, np.linalg.inv(Hk))
            else:
                # lost this frame: re-key on the previous frame and try once more from there
                lost += 1
                H[t], conf[t] = Hprev, 0.0
                key, Hk = prev, Hprev
                fresh = features(gray[key], mask_at(key) if mask_at(key) is not None else _warped_mask(mask_at(anchor), Hprev, gray.shape[1:]))
                pts = fresh
                n0 = max(len(pts), 1)
                pts_a = cv2.perspectiveTransform(pts, np.linalg.inv(Hk)) if len(pts) else pts
                prev = t
            t += step
    return H, conf


def _warped_mask(mask: Optional[np.ndarray], Hm: np.ndarray, shape) -> Optional[np.ndarray]:
    if mask is None:
        return None
    return cv2.warpPerspective(mask, Hm, (shape[1], shape[0]), flags=cv2.INTER_NEAREST)


# ---------------------------------------------------------------- shaping the track

def smooth_poses(H: np.ndarray, conf: np.ndarray, corners: np.ndarray, window: int = 11) -> np.ndarray:
    """Smooth a track without blurring it: the motion of four points (`corners`, 4x2 in anchor pixels: the box the type
    occupies) is fitted with a local cubic over `window` frames (Savitzky-Golay: noise goes, a camera speeding up and slowing
    down stays exactly as it is) and the homography is rebuilt from them. Frames that are NaN stay NaN."""
    from scipy.signal import savgol_filter
    n = len(H)
    ok = ~np.isnan(H[:, 0, 0])
    idx = np.where(ok)[0]
    if len(idx) < 5:
        return H
    pts = np.full((n, 4, 2), np.nan)
    c = corners.reshape(-1, 1, 2).astype(np.float32)
    for t in idx:
        pts[t] = cv2.perspectiveTransform(c, H[t]).reshape(4, 2)
    out = pts.copy()
    w = min(window, len(idx) if len(idx) % 2 else len(idx) - 1)
    if w >= 5:
        out[idx] = savgol_filter(pts[idx].reshape(len(idx), 8), w, 3, axis=0, mode="interp").reshape(len(idx), 4, 2)
    res = H.copy()
    for t in idx:
        res[t] = cv2.getPerspectiveTransform(corners.astype(np.float32), out[t].astype(np.float32))
    return res


def damp_similarity(H: np.ndarray, k: float, pivot: tuple[float, float]) -> np.ndarray:
    """Follow a similarity only part of the way (k 0..1: 0 stays on the screen, 1 follows the camera fully): shift, turn and
    zoom about the pivot are all scaled by k. This is how a layer that is farther away than the thing it was measured on
    moves less than it does."""
    if k >= 0.999 or np.isnan(H[0, 0]):
        return H
    A = H[:2, :2]
    s = float(np.sqrt(abs(np.linalg.det(A))))
    th = float(np.arctan2(A[1, 0], A[0, 0]))
    c = np.array(pivot)
    d = (H @ np.array([c[0], c[1], 1.0]))[:2] / (H @ np.array([c[0], c[1], 1.0]))[2] - c
    s_k, th_k, d_k = s ** k, th * k, d * k
    R = np.array([[np.cos(th_k), -np.sin(th_k)], [np.sin(th_k), np.cos(th_k)]]) * s_k
    out = np.eye(3)
    out[:2, :2] = R
    out[:2, 2] = c + d_k - R @ c
    return out
