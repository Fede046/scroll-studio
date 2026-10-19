"""world: headlines that live inside the film instead of floating over it.

A step with `place: {kind: behind | surface | sky}` has its title set in the scene. The page draws the film in WebGL and
composites the type itself (runtime/src/players/world.ts); this module makes what the shader needs, once per film, as
cached stages:

  world_depth        every frame of the shots that hold `behind` / `sky` type gets a depth map (Depth Anything V2), made to
                     hold still and snapped to the picture's edges (engine/world_depth.py), 960x540 uint8, 0 far .. 255 near
  world_text_<i>     for one step: where the type is laid out (the anchor frame), what it follows and how: the thing it sits
                     behind (a prompt, found by Florence-2 + SAM 2.1, read off the depth map), the surface it is painted on
                     (a prompt; SAM 2.1 tracks its mask through the shot, the same stages `reveal` uses) and the per-frame
                     matrix that carries the type with the camera (engine/world_track.py: planar tracking, homography on a
                     surface, similarity on a layer), smoothed
  world_pack         the depth maps and the surfaces' masks packed into one grayscale atlas video with the film's own frame
                     rate, frame count and GOP (a mask frame scrubs with its film frame, as for `reveal`), plus a half-size copy
                     for phones

The film itself is encoded as always (a film with no in-world type keeps its cache: nothing here runs for it).
Everything is in the 960x540 working frame (see engine/world_math.py for the coordinates).
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Optional

import cv2
import numpy as np

from . import reveal, world_depth as wd, world_math as wm
from .project import BuildContext, BuildError, file_key, probe
from .spec import FilmScene, RevealAt, RevealRegion, Step, WorldPlace

VERSION = 5
TILE = reveal.TILE
WORK = reveal.WORK
SOFT = {"behind": 0.04, "sky": 0.09}            # the width of the occlusion's soft edge, depth units (the runtime reads it)
DEFAULTS = {                                      # per kind: x, y, size, tracking (em), haze
    "behind": dict(x=0.5, y=0.5, size=0.5, track=0.0, haze=0.12),
    "sky": dict(x=0.5, y=0.3, size=0.72, track=0.1, haze=0.35),
    "surface": dict(x=0.5, y=0.5, size=0.8, track=0.05, haze=0.0),
}
MARGIN = 8                                        # frames tracked beyond the step's window, so the type is already in place


# ---------------------------------------------------------------- which steps

def world_steps(sec) -> list[tuple[int, Step, WorldPlace]]:
    return [(i, st, st.world) for i, st in enumerate(getattr(sec, "steps", [])) if st.world is not None]


def active(sec) -> bool:
    return bool(world_steps(sec))


def plain(title: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", title)).strip()


def validate(sec) -> None:
    """Fail before anything renders when a step's placement can't work."""
    if sec.type == "film" and sec.layout != "overlay":
        raise BuildError(f"section '{sec.id}': in-world type (`place: {{kind: ...}}`) needs `layout: overlay` on a film "
                         f"(the title is set in the picture; the other layouts put the copy in cards beside it)")
    for i, st, w in world_steps(sec):
        what = f"section '{sec.id}', step '{plain(st.title)[:40]}'"
        if sec.type == "film" and st.at is None:
            raise BuildError(f"{what}: in-world type needs `at: [from, to]` (scroll progress, 0-1) or `state: {{beat: <id>}}`")
        if w.kind == "surface" and not w.at and not w.quad:
            raise BuildError(f"{what}: a surface needs `at` (a prompt naming it, e.g. \"the wooden deck\") or a `quad`")
        if w.kind == "surface" and w.at is not None and not isinstance(w.at, str):
            raise BuildError(f"{what}: for a surface `at` is a prompt, not a number")
        if w.kind == "sky" and isinstance(w.at, str):
            raise BuildError(f"{what}: for sky `at` is a depth (0 far to 1 near), not a prompt")
        if w.quad and w.kind != "surface":
            raise BuildError(f"{what}: `quad` is for a surface")
    n_surf = sum(1 for _, _, w in world_steps(sec) if w.kind == "surface")
    n_depth = 1 if any(w.kind != "surface" for _, _, w in world_steps(sec)) else 0
    if n_surf + n_depth > 4:
        raise BuildError(f"section '{sec.id}': at most 4 in-world layers per scene (each surface, and all the behind/sky type "
                         f"together, takes one tile of the mask video); this one has {n_surf} surfaces")


def resolved(w: WorldPlace) -> dict:
    """The placement with its defaults filled in (what the runtime and the cache key see)."""
    d = DEFAULTS[w.kind]
    return {"kind": w.kind, "x": d["x"] if w.x is None else w.x, "y": d["y"] if w.y is None else w.y,
            "size": d["size"] if w.size is None else w.size, "track": d["track"] if w.track is None else w.track,
            "haze": d["haze"] if w.haze is None else w.haze}


# ---------------------------------------------------------------- frames

def read_frames(clip: Path, nframes: int, gray: bool = False, only: Optional[set[int]] = None):
    """The working clip's frames in order, as BGR (or gray) uint8 arrays (all of them, or only the indices in `only`)."""
    from .config import settings
    pix = "gray" if gray else "bgr24"
    cmd = [settings()["ffmpeg"], "-hide_banner", "-loglevel", "error", "-i", str(clip), "-f", "rawvideo", "-pix_fmt", pix, "-"]
    size = wm.W * wm.H * (1 if gray else 3)
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    try:
        i = 0
        while True:
            buf = p.stdout.read(size)
            if len(buf) < size:
                break
            if only is None or i in only:
                yield i, np.frombuffer(buf, np.uint8).reshape((wm.H, wm.W) if gray else (wm.H, wm.W, 3))
            i += 1
    finally:
        p.stdout.close()
        p.wait()


class Frames:
    """The working clip in memory (gray), read on first use (a dry-run plan never touches the files)."""
    def __init__(self, clip: Path, nframes: int):
        self.clip, self.n, self._gray = clip, nframes, None

    @property
    def gray(self) -> np.ndarray:
        if self._gray is None:
            g = np.zeros((self.n, wm.H, wm.W), np.uint8)
            for i, f in read_frames(self.clip, self.n, gray=True):
                if i < self.n:
                    g[i] = f
            self._gray = g
        return self._gray


def fkey(path: Path) -> dict:
    """file_key, or a placeholder for a file a dry-run plan has not made yet."""
    return file_key(path) if path.exists() else {"path": path.name, "pending": True}


def frame_of(progress: float, nframes: int) -> int:
    return max(0, min(nframes - 1, int(round(progress * (nframes - 1)))))


def window_frames(st: Step, nframes: int) -> tuple[int, int]:
    a, b = st.at
    return frame_of(a, nframes), frame_of(b, nframes)


def shot_of(shots: list[tuple[int, int]], frame: int) -> tuple[int, int]:
    return next(s for s in shots if s[0] <= frame <= s[1])


# ---------------------------------------------------------------- depth

def depth_stage(sec: FilmScene, ctx: BuildContext, clip: Path, nframes: int, need: list[tuple[int, int]]) -> Path:
    """Stage world_depth: steady depth maps (uint8, frames x 540 x 960; zeros outside the shots in `need`)."""
    out = ctx.work / "world" / "depth.npz"
    out.parent.mkdir(parents=True, exist_ok=True)
    model = sec.depth_model or "small"
    key = {"clip": fkey(clip), "model": model, "shots": need, "v": wd.VERSION}

    def run():
        from .backends import depth as depthmod
        from . import world_depth as wd
        from PIL import Image
        res = np.zeros((nframes, wm.H, wm.W), np.uint8)
        for (a, b) in need:
            ctx.log(f"  world depth: frames {a}-{b} ({model})")
            frames = [f.copy() for i, f in read_frames(clip, nframes, only=set(range(a, b + 1)))]
            est = lambda f: depthmod.estimate_raw(Image.fromarray(cv2.cvtColor(f, cv2.COLOR_BGR2RGB)), model)
            res[a:b + 1] = wd.steady_depth(frames, est, log=ctx.log)
            del frames
        np.savez_compressed(out, depth=res)
    ctx.stage("world_depth", key, [out], run)
    return out


# ---------------------------------------------------------------- one text

def _anchor(sec, st: Step, w: WorldPlace, nframes: int, fps: float, spans) -> int:
    if w.anchor is not None:
        return reveal.film_frame(sec, w.anchor, nframes, fps, spans)
    a, b = window_frames(st, nframes)
    return (a + b) // 2


def _frame_png(ctx: BuildContext, clip: Path, frame: int) -> Path:
    png = ctx.work / "world" / f"frame_{frame}.png"
    if not png.exists():                    # written once: a stable file keeps the prompt searches below cached
        png.parent.mkdir(parents=True, exist_ok=True)
        reveal._frame_png(clip, frame, png)
    return png


def _thing_mask(ctx: BuildContext, clip: Path, frame: int, prompt: str, log) -> np.ndarray:
    """The soft mask (0-255, working size) of the thing a prompt names on one frame (Florence-2 + SAM 2.1; cached)."""
    from . import region
    from .spec import EditRegion
    from PIL import Image
    png = _frame_png(ctx, clip, frame)
    raw = region.find(ctx.project, png, EditRegion(prompt=prompt), log)
    return np.asarray(Image.open(raw).convert("L"))


def _band_mask(depth: np.ndarray, dt: float, band: float) -> np.ndarray:
    m = (np.abs(depth.astype(np.float32) / 255 - dt) < band).astype(np.uint8) * 255
    m[:12] = 0
    m[-12:] = 0
    m[:, :12] = 0
    m[:, -12:] = 0
    return cv2.erode(m, np.ones((5, 5), np.uint8))


def _sharpness(gray: np.ndarray, sel: np.ndarray) -> float:
    g = cv2.GaussianBlur(gray, (0, 0), 0.8).astype(np.float32)
    gx, gy = cv2.Sobel(g, cv2.CV_32F, 1, 0), cv2.Sobel(g, cv2.CV_32F, 0, 1)
    mag = np.sqrt(gx * gx + gy * gy)
    v = mag[sel > 0]
    return float(np.percentile(v, 75)) if len(v) > 50 else 0.0


def _auto_blur(gray: np.ndarray, depth: np.ndarray, dt: float) -> float:
    """How soft the footage is at the type's depth, in pixels of a 1920-wide frame: the gradient energy of the pixels at that
    depth against the sharpest tenth of the picture. Generated films have their own depth of field, and type that is sharper
    than what is around it at the same distance reads as pasted on."""
    sel = (np.abs(depth.astype(np.float32) / 255 - dt) < 0.1).astype(np.uint8)
    here = _sharpness(gray, sel)
    g = cv2.GaussianBlur(gray, (0, 0), 0.8).astype(np.float32)
    mag = np.sqrt(cv2.Sobel(g, cv2.CV_32F, 1, 0) ** 2 + cv2.Sobel(g, cv2.CV_32F, 0, 1) ** 2)
    tiles = mag[: mag.shape[0] // 54 * 54, : mag.shape[1] // 96 * 96].reshape(10, 54, 10, 96).mean(axis=(1, 3))
    best = float(np.percentile(tiles, 92)) * 1.4
    if here <= 0 or best <= 0:
        return 0.0
    r = min(1.0, here / best)
    return float(np.clip((1 - r) * 5.0, 0.0, 5.0))


def _text_stage(sec: FilmScene, ctx: BuildContext, i: int, st: Step, w: WorldPlace, clip: Path, frames: "Frames", depth_file: Optional[Path],
                nframes: int, fps: float, spans, shots, key_base: dict) -> Path:
    out = ctx.work / "world" / f"text_{i}.json"
    fa = _anchor(sec, st, w, nframes, fps, spans)
    a0, b0 = window_frames(st, nframes)
    sa, sb = shot_of(shots, fa)
    f0, f1 = max(sa, a0 - MARGIN), min(sb, b0 + MARGIN)
    if f1 < f0:
        raise BuildError(f"section '{sec.id}', step '{plain(st.title)[:40]}': its `at` window lies outside the shot the anchor "
                         f"frame ({fa}) is in ({sa}-{sb}); move `anchor` or `at`")
    if a0 < sa or b0 > sb:
        ctx.log(f"  note: step {i} spans a cut: its type is shown only in the shot it is anchored in (frames {sa}-{sb})")
    r = resolved(w)
    spec = {**w.model_dump(mode="json"), "r": r, "anchor_frame": fa, "range": [f0, f1], "shot": [sa, sb]}
    key = {**key_base, "spec": spec, "title": len(plain(st.title)), "v": VERSION}
    mask_files: list[Path] = []
    if w.kind == "surface":
        # the surface's mask through the shot: reveal's own stages (Florence-2 on the anchor, SAM 2.1 forward and back)
        rg_id = f"world{i}"
        rg = RevealRegion(id=rg_id, prompt=w.at if isinstance(w.at, str) else None, box=None if w.at else _quad_box(w.quad),
                          at=RevealAt(frame=fa))
        rv = SimpleNamespace(tracker="large", cuts=[])
        ctx.log(f"  world {i}: surface {w.at or 'quad'}")
        mask_files = reveal.track_region(sec, ctx, rv, rg, ctx.work / "unused", clip, nframes, fps, spans, shots)
        key["masks"] = [fkey(f) for f in mask_files]
    if depth_file is not None and (w.kind != "surface" or not w.quad):
        key["depth"] = fkey(depth_file)

    def run():
        res = _plan_text(sec, ctx, i, st, w, r, clip, frames, depth_file, mask_files, nframes, fa, f0, f1, (sa, sb))
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(res))
    ctx.stage(f"world_text_{i}", key, [out], run)
    return out


def _quad_box(quad) -> Optional[tuple[float, float, float, float]]:
    if not quad:
        return None
    xs, ys = [p[0] for p in quad], [p[1] for p in quad]
    return (min(xs), min(ys), max(xs), max(ys))


def _far_mask(depth: np.ndarray, limit: float) -> np.ndarray:
    """The far layers (sky type follows them): everything below `limit` in depth, away from the frame's edge."""
    m = (depth.astype(np.float32) / 255 < limit).astype(np.uint8) * 255
    m[:12] = 0
    m[-12:] = 0
    m[:, :12] = 0
    m[:, -12:] = 0
    return cv2.erode(m, np.ones((5, 5), np.uint8))


def _plan_text(sec, ctx, i, st, w, r, clip, frames, depth_file, mask_files, nframes, fa, f0, f1, shot) -> dict:
    """Stage body of world_text_<i>: the placement of one title as plain numbers (see the module docstring)."""
    from . import world_track as wt
    log = ctx.log
    gray = frames.gray
    title_chars = len(plain(st.title))
    kind = w.kind
    cx, cy = r["x"] * wm.W, r["y"] * wm.H
    model = w.track_model or ("homography" if kind == "surface" else "similarity")
    info: dict = {"i": i, "kind": kind, "f0": f0, "f1": f1, "anchor": fa, "shot": list(shot), "title": plain(st.title)}

    if kind == "surface":
        masks = None
        for mf in mask_files:
            m = np.load(mf)["masks"]
            masks = m if masks is None else np.maximum(masks, m)
        sel = masks[fa] > 127
        tone = float(gray[fa][sel].mean() / 255) if sel.any() else float(gray[fa].mean() / 255)
        plane = [1.0, wm.H / wm.W]
        if w.quad:
            # the surface's corners were given: the type is laid out in that quadrilateral, x, y across and down it
            quad = wm.order_quad(np.array(w.quad, dtype=np.float64) * [wm.W, wm.H])
            aspect = wm.plane_aspect(quad)
            R = wm.rectify(quad, aspect)
            plane = [1.0, 1.0 / aspect]
            box_cx, box_cy = r["x"], r["y"] / aspect
            lines, bh = wm.estimate_lines(title_chars, w.lines, plane[1], r["size"], 0.6)
            corners = quad
            info.update(aspect=round(aspect, 4), ppp=round(float(0.5 * (np.linalg.norm(quad[1] - quad[0]) + np.linalg.norm(quad[2] - quad[3]))) / wm.W, 4),
                        quad=[[round(float(x) / wm.W, 4), round(float(y) / wm.H, 4)] for x, y in quad])
        else:
            # the surface's orientation from the depth map: a plane's disparity is linear in the image, so a fit over the
            # mask is its normal; the type is laid out on that plane at x, y of the frame (see world_math.plane_frame)
            depth = np.load(depth_file)["depth"]
            sol = wm.fit_disparity_plane(depth[fa].astype(np.float32) / 255, masks[fa])
            n = sol if sol is not None else np.array([0.0, 0.0, 1.0])
            P = wm.plane_frame(n, (cx, cy))
            R = np.linalg.inv(P)
            box_cx, box_cy = 0.0, 0.0
            lines, bh = wm.estimate_lines(title_chars, w.lines, plane[1], r["size"], 0.3)
            hw, hh = r["size"] / 2, bh / 2
            corners = cv2.perspectiveTransform(np.float32([[[-hw, -hh], [hw, -hh], [hw, hh], [-hw, hh]]]), P).reshape(4, 2)
            nn = n / max(np.linalg.norm(n), 1e-9)
            info.update(ppp=1.0, normal=[round(float(v), 4) for v in nn],
                        tilt=round(float(np.degrees(np.arccos(abs(nn[2])))), 1))
        grip = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))

        def mask_at(f):
            return cv2.erode((masks[f] > 127).astype(np.uint8) * 255, grip)
        Hs, conf = wt.track(gray, fa, f0, f1, mask_at, "homography", log)
        info.update(follow=1.0, slot_kind="mask", tone=round(tone, 3), lines=lines)
    else:
        depth = np.load(depth_file)["depth"]
        D = depth[fa].astype(np.float32) / 255
        R = wm.frame_plane()
        plane = [1.0, wm.H / wm.W]
        box_cx, box_cy = r["x"], r["y"] * wm.H / wm.W
        lines, bh = wm.estimate_lines(title_chars, w.lines, plane[1], r["size"])
        bw_px, bh_px = r["size"] * wm.W, bh * wm.W
        x0, x1 = int(max(0, cx - bw_px / 2)), int(min(wm.W, cx + bw_px / 2))
        y0, y1 = int(max(0, cy - bh_px / 2)), int(min(wm.H, cy + bh_px / 2))
        inbox = D[y0:y1, x0:x1] if (x1 > x0 and y1 > y0) else D
        # the depth the type sits at
        if kind == "behind" and isinstance(w.at, str):
            m = _thing_mask(ctx, clip, fa, w.at, log)
            sel = depth[fa][m > 127]
            if len(sel) < 20:
                raise BuildError(f"world: nothing matching \"{w.at}\" on frame {fa} (step {i}); reword the prompt, move "
                                 f"`anchor`, or give a depth")
            thing = float(np.median(sel)) / 255
            dt = max(0.0, thing - w.gap)
            info["thing_depth"] = round(thing, 3)
        elif w.at is not None:
            dt = float(w.at)
        elif kind == "behind":
            dt = float(np.percentile(inbox, 70)) if inbox.size else 0.4
        else:
            dt = 0.07
        dt = float(np.clip(dt, 0.0, 1.0))
        # what the type follows: the layer at its own depth (a wider band until there is something to track); sky follows
        # whatever is far
        if kind == "behind":
            steps = (0.06, 0.12, 0.2, 0.32)
            make = lambda f, v: _band_mask(depth[f], dt, v)
        else:
            steps = (0.18, 0.3, 0.45)
            make = lambda f, v: _far_mask(depth[f], v)
        used, tracked = None, None
        for v in steps:
            m0 = make(fa, v)
            if (m0 > 0).sum() > 400 and len(wt.features(gray[fa], m0)) >= 24:
                used, tracked = v, m0
                break
        if tracked is None:
            used, tracked = 1.0, np.full((wm.H, wm.W), 255, np.uint8)
            log(f"  note: step {i}: nothing to follow at depth {dt:.2f}; the type follows the whole picture")

        def mask_at(f):
            return make(f, used) if used < 1.0 else tracked
        Hs, conf = wt.track(gray, fa, f0, f1, mask_at, model, log)
        # the layer followed is not always at the type's depth: a farther type moves less than a nearer layer does
        med = float(np.median(D[tracked > 0])) if (tracked > 0).any() else dt
        if w.follow is not None:
            k = w.follow
        elif kind == "behind":
            k = float(np.clip((dt + 0.04) / (max(med, dt) + 0.04), 0.35, 1.0))
        else:
            k = 1.0
        for t in range(f0, f1 + 1):
            if not np.isnan(Hs[t, 0, 0]):
                Hs[t] = wt.damp_similarity(Hs[t], k, (cx, cy))
        corners = np.array([[cx - bw_px / 2, cy - bh_px / 2], [cx + bw_px / 2, cy - bh_px / 2],
                            [cx + bw_px / 2, cy + bh_px / 2], [cx - bw_px / 2, cy + bh_px / 2]])
        reg = gray[fa][y0:y1, x0:x1] if (x1 > x0 and y1 > y0) else gray[fa]
        # the footage the type is read against: what shows around it, the pixels farther than the type
        seen = reg[(D[y0:y1, x0:x1] < dt + SOFT[kind])] if (x1 > x0 and y1 > y0) else reg
        if seen.size > 0.05 * reg.size:
            reg = seen
        info.update(follow=round(k, 3), band=round(used, 2), depth=round(dt, 4), soft=SOFT[kind], slot_kind="depth", ppp=1.0,
                    tone=round(float(reg.mean() / 255), 3),
                    tracked_depth=round(med, 3), lines=lines,
                    blur=round(w.blur if w.blur is not None else _auto_blur(gray[fa], depth[fa], dt), 2))

    Hs = wt.smooth_poses(Hs, conf, corners, sigma=1.6)
    mats, confs, last = [], [], None
    for t in range(f0, f1 + 1):
        if np.isnan(Hs[t, 0, 0]):
            Hs[t] = last if last is not None else np.eye(3)
            c = 0.0
        else:
            c = float(conf[t])
            last = Hs[t]
        if kind != "surface":
            c = 1.0                       # a layer at infinity does not vanish when its features do
        M = wm.screen_matrix(R, Hs[t], (box_cx, box_cy, w.angle) if (kind == "surface" and w.angle) else None)
        mats.append(wm.pack_matrix(M, (box_cx, box_cy)))
        confs.append(round(min(1.0, c), 2))
    info.update(plane=[round(plane[0], 5), round(plane[1], 5)], box=[round(box_cx, 5), round(box_cy, 5), round(r["size"], 4)],
                style={"align": w.align, "caps": w.caps, "track": r["track"], "weight": w.weight, "color": w.color,
                       "haze": r["haze"], "fog": w.fog, "wear": w.wear, "relief": w.relief, "lines": w.lines},
                m=mats, c=confs)
    return info


# ---------------------------------------------------------------- packing

def _depth_tiles(depth: np.ndarray, tile: tuple[int, int]) -> np.ndarray:
    return np.stack([cv2.resize(d, tile, interpolation=cv2.INTER_AREA if tile[0] < wm.W else cv2.INTER_LINEAR) for d in depth])


def pack(ctx: BuildContext, names: list[str], load, key: dict, fps: float, gop: int) -> dict:
    """Stage world_pack: the layers (depth, then each surface's mask; up to four) as one atlas video + a phone copy. `load(name)`
    returns a layer's frames (read inside the stage, so a cached pack reads nothing)."""
    web = ctx.web
    outs = [web / "world.mp4", web / "world-mobile.mp4"]

    def run():
        arrays = [(n, load(n)) for n in names]
        for suffix, tile, crf in (("", TILE, 14), ("-mobile", (TILE[0] // 2, TILE[1] // 2), 20)):
            tiles = [_depth_tiles(a, tile) if n == "depth" else reveal.tile_masks(a, 0.0, 0, tile) for n, a in arrays]
            reveal.encode_atlas(tiles, fps, gop, web / f"world{suffix}.mp4", crf=crf, log=ctx.log)
            del tiles
    ctx.stage("world_pack", key, outs, run)
    cols, rows = reveal.atlas_layout(len(names))
    return {"video": ctx.url(outs[0]), "mobile": ctx.url(outs[1]), "cols": cols, "rows": rows, "tile": list(TILE),
            "slots": list(names)}


# ---------------------------------------------------------------- the section

def preflight(sec, ctx: Optional[BuildContext] = None) -> None:
    """Before a film renders: the placements must be possible, and ComfyUI must have the nodes a prompt needs."""
    validate(sec)
    if any(w.kind == "surface" or isinstance(w.at, str) for _, _, w in world_steps(sec)):
        reveal.preflight(ctx)


def build(sec: FilmScene, ctx: BuildContext, src: Path, cfg: dict) -> dict:
    """The `world` config of a film's page (depth, tracks and masks made and cached as needed), from the film's own source."""
    validate(sec)
    steps = world_steps(sec)
    ctx.log(f"  world: {len(steps)} in-world title(s)")
    info = probe(src, "stream=width,height,r_frame_rate,nb_read_frames")
    fps = reveal._fps(info.get("r_frame_rate"))
    nframes = reveal._count_frames(src)
    clip = reveal._work_clip(src, ctx)
    spans = reveal.spans_of(sec, ctx)
    shots = reveal.shots_of(sec, ctx, SimpleNamespace(cuts=[]), clip, nframes, fps, spans)
    frames = Frames(clip, nframes)

    # the shots that need a depth map: the ones holding behind / sky type
    need = sorted({shot_of(shots, _anchor(sec, st, w, nframes, fps, spans)) for _, st, w in steps if w.kind != "surface" or not w.quad})
    depth_file = depth_stage(sec, ctx, clip, nframes, [list(s) for s in need]) if need else None
    key_base = {"clip": fkey(clip), "fps": round(fps, 4), "model": sec.depth_model or "small", "shots": [list(s) for s in shots]}

    texts = []
    for i, st, w in steps:
        f = _text_stage(sec, ctx, i, st, w, clip, frames, depth_file, nframes, fps, spans, shots, key_base)
        texts.append(json.loads(f.read_text()) if f.exists() else {"i": i, "kind": w.kind})

    # the atlas: depth first, then a mask per surface
    names: list[str] = []
    pkey: dict = {"fps": round(fps, 4), "gop": sec.gop, "film": fkey(src), "v": VERSION}
    if depth_file is not None and any(t["kind"] != "surface" for t in texts):
        names.append("depth")
        pkey["depth"] = fkey(depth_file)
    surf = {}
    for t in texts:
        if t["kind"] == "surface":
            surf[f"s{t['i']}"] = sorted((ctx.work / "reveal" / f"world{t['i']}").glob("masks*.npz"))
            names.append(f"s{t['i']}")
            pkey[f"s{t['i']}"] = [fkey(f) for f in surf[f"s{t['i']}"]]

    def load(name: str) -> np.ndarray:
        if name == "depth":
            return np.load(depth_file)["depth"]
        m = None
        for f in surf[name]:
            a = np.load(f)["masks"]
            m = a if m is None else np.maximum(m, a)
        return m
    atlas = pack(ctx, names, load, pkey, fps, sec.gop) if names else None
    for t in texts:
        t["slot"] = "depth" if t["kind"] != "surface" else f"s{t['i']}"
    return {"fps": round(fps, 4), "frames": nframes, "atlas": atlas, "texts": texts}
