"""Pictures of the worst moments of a report: one JPEG per issue, made of the frames that show the problem.

  pop (jump, flash, stutter)   the frame before and the frame after
  dissolve / cut               the old shot, what the dissolve shows at mid-fade, the new shot
  softness                     the frame, and a 1:1 crop of its busiest part (look at the edges)
  halos                        the frame with the rim pixels marked, and a 1:1 crop of where they are densest
  drift                        the section's base plate beside the frame
  morph                        the start, middle and end of the window
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from . import analyze as A
from . import metrics as M

MAX_THUMBS = 36
W_SINGLE = 560


def _label(img: np.ndarray, text: str) -> np.ndarray:
    img = img.copy()
    (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
    cv2.rectangle(img, (0, 0), (tw + 10, th + 10), (24, 24, 24), -1)
    cv2.putText(img, text, (5, th + 4), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (240, 240, 240), 1, cv2.LINE_AA)
    return img


def _row(imgs: list[np.ndarray], h: int) -> np.ndarray:
    out = []
    for im in imgs:
        w = max(1, round(im.shape[1] * h / im.shape[0]))
        out.append(cv2.resize(im, (w, h), interpolation=cv2.INTER_AREA))
    gap = np.full((h, 4, 3), 30, np.uint8)
    parts = []
    for k, im in enumerate(out):
        if k:
            parts.append(gap)
        parts.append(im)
    return np.hstack(parts)


def _busiest(bgr: np.ndarray, cw: int = 480, ch: int = 270) -> tuple[int, int]:
    """Top-left of the cw x ch window with the most strong edges."""
    g = M.gray_f32(bgr)
    h, w = g.shape
    gx = cv2.Sobel(g, cv2.CV_32F, 1, 0, ksize=3); gy = cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=3)
    m = (np.hypot(gx, gy) > 60).astype(np.float32)
    k = 8
    small = cv2.resize(m, (w // k, h // k), interpolation=cv2.INTER_AREA)
    box = cv2.boxFilter(small, -1, (max(1, cw // k), max(1, ch // k)), normalize=True, borderType=cv2.BORDER_CONSTANT)
    y, x = np.unravel_index(int(np.argmax(box)), box.shape)
    x0 = int(min(max(0, x * k - cw // 2), max(0, w - cw)))
    y0 = int(min(max(0, y * k - ch // 2), max(0, h - ch)))
    return x0, y0


def _densest(points: np.ndarray, w: int, h: int, cw: int = 480, ch: int = 270) -> tuple[int, int]:
    """Top-left of the window holding most of the marked points (points are 0-1)."""
    px, py = points[:, 0] * w, points[:, 1] * h
    gx, gy = max(1, w // 40), max(1, h // 40)
    H, _, _ = np.histogram2d(px, py, bins=[np.arange(0, w + gx, gx), np.arange(0, h + gy, gy)])
    H = cv2.boxFilter(H.astype(np.float32), -1, (max(1, cw // gx), max(1, ch // gy)), normalize=False, borderType=cv2.BORDER_CONSTANT)
    ix, iy = np.unravel_index(int(np.argmax(H)), H.shape)
    x0 = int(min(max(0, ix * gx - cw // 2 + gx // 2), max(0, w - cw)))
    y0 = int(min(max(0, iy * gy - ch // 2 + gy // 2), max(0, h - ch)))
    return x0, y0


def _need(issue: dict, st: dict, sc: A.Scan) -> list[tuple[int, bool]]:
    """(film frame index, full resolution?) pairs the thumbnail needs."""
    p = issue["_peak"]
    m = issue["metric"]
    last = sc.n - 1
    clamp = lambda i: int(min(last, max(0, i)))
    if m == "pops" and p.get("kind") in ("dissolve", "cut"):
        return [(clamp(round(p["t"] * sc.fps)), False)]
    if m == "pops":
        return [(clamp(p["a"]), False), (clamp(p["b"]), False)]
    if m in ("softness", "halos"):
        return [(clamp(p["frame"]), True)]
    if m == "drift":
        return [(clamp(p["plate_frame"]), False), (clamp(p["frame"]), False)]
    if m == "morphs":
        a, b = p["a"], p["b"]
        return [(clamp(a), False), (clamp((a + b) // 2), False), (clamp(b), False)]
    return [(clamp(round(p["t"] * sc.fps)), False)]


def make_thumbs(report: dict, sc: A.Scan, st: dict, spans, joins: list[dict], path: Path, out_dir: Path, name: str, log) -> None:
    issues = report["issues"]
    pick = list(issues[:MAX_THUMBS])
    for b in report["beats"]:                                  # every beat's worst issue gets a picture
        w = next((x for x in issues if x["beat"] == b["id"]), None)
        if w is not None and not any(w is q for q in pick):
            pick.append(w)
    if not pick:
        return
    folder = out_dir / name
    folder.mkdir(parents=True, exist_ok=True)
    for old in folder.glob("*.jpg"):
        old.unlink()
    needs = {i: _need(x, st, sc) for i, x in enumerate(pick)}
    full = {k: any(f for (idx, f) in v if idx == k) for v in needs.values() for (k, _) in v}
    want = sorted(full)
    frames: dict[int, np.ndarray] = {}
    cap = A.open_film(path)
    i = 0
    wi = 0
    while wi < len(want):
        ok, f = cap.read()
        if not ok:
            break
        while wi < len(want) and want[wi] == i:
            frames[want[wi]] = f if full[want[wi]] else M.resize_w(f, 640)
            wi += 1
        i += 1
    cap.release()
    join_by = {(j["from"], j["to"]): j for j in joins}
    for n, x in enumerate(pick):
        p = x["_peak"]
        try:
            fr = [frames[idx] for idx, _ in needs[n] if idx in frames]
            m = x["metric"]
            if not fr:
                continue
            if m == "pops" and p.get("kind") in ("dissolve", "cut"):
                j = join_by.get((p["from"], p["to"]))
                a = b = None
                if j is not None:
                    pa = next(s for s in spans if s.id == p["from"]).clip
                    pb = next(s for s in spans if s.id == p["to"]).clip
                    fa = A.read_frames(pa, [j["frames"]["a"]], 480); fb = A.read_frames(pb, [j["frames"]["b"]], 480)
                    a, b = list(fa.values())[0], list(fb.values())[0]
                mid = M.resize_w(fr[0], 480)
                parts = [_label(im, t) for im, t in ((a, f"{p['from']} (outgoing)"), (mid, "what the dissolve shows"), (b, f"{p['to']} (incoming)")) if im is not None]
                img = _row(parts, 270)
            elif m == "pops":
                img = _row([_label(M.resize_w(fr[0], 480), "before"), _label(M.resize_w(fr[-1], 480), "after")], 270)
            elif m == "softness":
                f0 = fr[0]
                x0, y0 = _busiest(f0)
                crop = f0[y0:y0 + 270, x0:x0 + 480]
                crop = cv2.resize(crop, None, fx=1.5, fy=1.5, interpolation=cv2.INTER_NEAREST)
                small = M.resize_w(f0, W_SINGLE)
                img = _row([_label(small, f"{x['t']:.1f}s"), _label(crop, "1:1 crop, enlarged 1.5x")], 315)
            elif m == "halos":
                f0 = fr[0]
                h, w = f0.shape[:2]
                pts = sc.samples[p["frame"]]["edge"].get("points")
                marked = f0.copy()
                crops = []
                if pts is not None and len(pts):
                    for px, py in pts[:: max(1, len(pts) // 1500)]:
                        cv2.circle(marked, (int(px * w), int(py * h)), 3, (0, 0, 255), -1)
                    rest = pts
                    for _ in range(2):                         # the two places the rims are densest
                        if len(rest) < 8:
                            break
                        x0, y0 = _densest(rest, w, h)
                        crops.append((x0, y0))
                        inside = ((rest[:, 0] * w >= x0) & (rest[:, 0] * w < x0 + 480) & (rest[:, 1] * h >= y0) & (rest[:, 1] * h < y0 + 270))
                        rest = rest[~inside]
                if not crops:
                    crops = [_busiest(f0)]
                panes = [_label(M.resize_w(marked, W_SINGLE), f"{x['t']:.1f}s, rims marked red")]
                for n_, (x0, y0) in enumerate(crops):
                    cm = marked[y0:y0 + 270, x0:x0 + 480]
                    panes.append(_label(cv2.resize(cm, None, fx=1.5, fy=1.5, interpolation=cv2.INTER_NEAREST), f"1:1 crop {n_ + 1}"))
                img = _row(panes, 315)
            elif m == "drift":
                img = _row([_label(M.resize_w(fr[0], 480), "start of the scene"), _label(M.resize_w(fr[-1], 480), f"{x['t']:.1f}s")], 270)
            elif m == "morphs":
                img = _row([_label(M.resize_w(f, 400), t) for f, t in zip(fr, ("start", "middle", "end"))], 225)
            else:
                img = M.resize_w(fr[0], W_SINGLE)
            file = f"{m}_{x['t']:06.2f}.jpg"
            cv2.imwrite(str(folder / file), img, [cv2.IMWRITE_JPEG_QUALITY, 84])
            x["thumb"] = f"{name}/{file}"
        except Exception as e:                                  # a picture must never sink the report
            log(f"  no picture for {x['metric']} at {x['t']}s: {e}")
