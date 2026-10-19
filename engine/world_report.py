"""world_report: check the type of a built film before anyone has to look at the page (`studio world`, MCP `world_check`).

For every in-world title of a built film section the report draws where the type's box is on the film's own frames, from
the first to the last frame it is shown (a yellow outline carried by the per-frame matrices the player will read), with the
depth map beside the frames for `behind` and `sky` type, and measures what can be measured: how steady the track is (the
second difference of the box's centre, in pixels of the 960-wide working frame: a track that jitters shows as shimmer), how
much of the time the surface was followed, how much of the window the box is on screen, how steeply a surface slants.
Each finding that can be acted on comes with what to change. Writes `.build/<section>/world/report.json` and `sheet.jpg`.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Optional

import cv2
import numpy as np

from . import world as W, world_math as wm
from .project import BuildError, Project


def _tiles(frames: np.ndarray, depth: Optional[np.ndarray], box_px: list[np.ndarray], labels: list[str], tw: int = 480) -> np.ndarray:
    th = tw * wm.H // wm.W
    cols = []
    for k, fr in enumerate(frames):
        im = fr.copy()
        if box_px[k] is not None:
            cv2.polylines(im, [box_px[k].astype(np.int32)], True, (0, 255, 255), 3, cv2.LINE_AA)
        cv2.putText(im, labels[k], (10, 36), cv2.FONT_HERSHEY_SIMPLEX, 1.1, (255, 255, 255), 2, cv2.LINE_AA)
        col = [cv2.resize(im, (tw, th))]
        if depth is not None:
            d = cv2.applyColorMap(depth[k], cv2.COLORMAP_TURBO)
            col.append(cv2.resize(d, (tw, th)))
        cols.append(np.vstack(col))
    return np.hstack(cols)


def _jitter(cs: np.ndarray, window: int = 11) -> float:
    """The shimmer of a path: how far the box centre is, at the 95th percentile, from a local cubic fit over `window` frames
    (pixels of the 960-wide working frame). A camera that speeds up and slows down is smooth and scores low, whatever it
    does; a track that wobbles from frame to frame scores high."""
    from scipy.signal import savgol_filter
    n = len(cs)
    if n < 9:
        return 0.0
    w = min(window, n if n % 2 else n - 1)
    sm = savgol_filter(cs, w, 3, axis=0, mode="interp")
    return float(np.percentile(np.linalg.norm(cs - sm, axis=1), 95))


def _box_corners(t: dict, f: int, lay_h: float) -> Optional[np.ndarray]:
    M = np.asarray(t["m"][min(len(t["m"]) - 1, max(0, f - t["f0"]))], dtype=np.float64).reshape(3, 3)
    try:
        Mi = np.linalg.inv(M)
    except np.linalg.LinAlgError:
        return None
    bx, by, bw = t["box"]
    out = []
    for px, py in ((bx - bw / 2, by - lay_h / 2), (bx + bw / 2, by - lay_h / 2), (bx + bw / 2, by + lay_h / 2), (bx - bw / 2, by + lay_h / 2)):
        v = Mi @ np.array([px, py, 1.0])
        if abs(v[2]) < 1e-9:
            return None
        out.append([v[0] / v[2] * wm.W, v[1] / v[2] * wm.H])
    return np.array(out)


def check_film(project: Project, section: str, n: int = 6, log: Callable[[str], None] = print) -> dict:
    cfg_path = project.build / section / "config.json"
    if not cfg_path.exists():
        raise BuildError(f"section '{section}' has not been built: run `studio build --only {section}` first")
    cfg = json.loads(cfg_path.read_text())
    world = cfg.get("world")
    if not world or not world.get("texts"):
        raise BuildError(f"section '{section}' has no in-world type (no step has `place: {{kind: ...}}`)")
    work = project.build / section / "reveal" / "work.mp4"
    depth_file = project.build / section / "world" / "depth.npz"
    if not work.exists():
        raise BuildError("the working copy of the film is missing: build the section again")
    nframes = world["frames"]
    depth = np.load(depth_file)["depth"] if depth_file.exists() else None
    out_rows, texts = [], []
    for t in world["texts"]:
        f0, f1 = t["f0"], t["f1"]
        title_chars = len(t.get("title", "x"))
        plane_h = t["plane"][1]
        lines, bh = wm.estimate_lines(title_chars, t["style"].get("lines"), plane_h, t["box"][2], 0.6 if t.get("quad") else 0.3)
        picks = sorted({int(round(v)) for v in np.linspace(f0, f1, n)})
        frames = {i: f.copy() for i, f in W.read_frames(work, nframes, only=set(picks))}
        centres, inside = [], []
        for f in range(f0, f1 + 1):
            c = _box_corners(t, f, bh)
            if c is None:
                inside.append(False)
                continue
            m = c.mean(axis=0)
            centres.append(m)
            inside.append(bool(0 < m[0] < wm.W and 0 < m[1] < wm.H))
        cs = np.array(centres) if centres else np.zeros((0, 2))
        jitter = _jitter(cs)
        conf = np.asarray(t["c"], dtype=float)
        lost = int((conf < 0.3).sum()) if t["kind"] == "surface" else 0
        share_in = float(np.mean(inside)) if inside else 0.0
        info = {"step": t["i"], "kind": t["kind"], "title": t.get("title"), "frames": [f0, f1], "anchor": t["anchor"],
                "jitter_px_p95": round(jitter, 2), "on_screen": round(share_in, 2), "lost_frames": lost, "advice": []}
        for k in ("depth", "thing_depth", "tilt", "follow", "blur", "band", "tone"):
            if k in t:
                info[k] = t[k]
        adv = info["advice"]
        if jitter > 0.8:
            adv.append("the track jitters (the box centre strays more than 0.8 px from its own smoothed path): lower `follow`, move `anchor` to a frame with more to track, or choose another `at`")
        if lost > 0.2 * (f1 - f0 + 1):
            adv.append(f"the surface was lost for {lost} of {f1 - f0 + 1} frames: reword the prompt, move `anchor`, or give `quad`")
        if share_in < 0.5:
            adv.append("the type is on screen for less than half of its window: move `anchor`, or shorten/shift the step's `at`")
        if t["kind"] == "surface" and t.get("tilt", 0) > 80:
            adv.append(f"the surface is seen almost edge-on ({t['tilt']} degrees): the letters are slivers; put the type lower in the frame (`y`), or paint a more frontal surface")
        if t["kind"] == "behind" and t.get("band", 0) >= 0.3:
            adv.append("little to follow at the type's depth: it follows the nearest layer instead, so it may slide; set `follow` by hand")
        texts.append(info)
        log(f"  step {t['i']} ({t['kind']}): jitter {jitter:.2f} px, on screen {share_in:.0%}" + (f", lost {lost}" if lost else "")
            + "".join(f"\n    - {a}" for a in adv))
        idx = [i for i in picks if i in frames]
        row = _tiles(np.stack([frames[i] for i in idx]), depth[idx] if (depth is not None and t["kind"] != "surface") else None,
                     [_box_corners(t, i, bh) for i in idx], [str(i) for i in idx])
        out_rows.append(row)
    wdt = max(r.shape[1] for r in out_rows)
    rows = [np.pad(r, ((0, 0), (0, wdt - r.shape[1]), (0, 0))) for r in out_rows]
    sheet = project.build / section / "world" / "sheet.jpg"
    sheet.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(sheet), np.vstack(rows), [cv2.IMWRITE_JPEG_QUALITY, 88])
    rep = {"section": section, "sheet": str(sheet), "texts": texts}
    (sheet.parent / "report.json").write_text(json.dumps(rep, indent=1))
    rep["json"] = str(sheet.parent / "report.json")
    return rep


def check(project: Project, section: Optional[str] = None, n: int = 6, log: Callable[[str], None] = print) -> list[dict]:
    """The report for one film section, or every film section that has in-world type."""
    site = project.load()
    from . import world as _w
    ids = [s.id for s in site.sections if getattr(s, "type", None) == "film" and _w.active(s)] if section is None else [section]
    if not ids:
        raise BuildError("no film section has in-world type")
    out = []
    for sid in ids:
        log(f"{sid}:")
        out.append(check_film(project, sid, n, log))
    return out
