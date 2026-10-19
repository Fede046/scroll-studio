"""cinemagraph: a still where only one thing moves, and everything else is held perfectly still.

`image: { ..., cinemagraph: { moves: "the steam above the cup" } }` on any image input. The still stays the picture the
page shows; this builds a small video of the part that moves, and a soft mask, and the page lays one over the other
(runtime/src/lib/cinemagraph.ts), so outside the mask the pixels are the still's and can never change. In stages, each
cached by its own key (an unchanged spec rebuilds nothing; a changed `seconds` or `loop` redoes only what follows it):

  region   `moves` -> the thing on the still (Florence-2 grounding + SAM 2.1, engine/region.py, the same cached stage an
           `edit.region` uses), grown and feathered; the crop around it (plus its surroundings) that the video model sees.
  clip     the crop brought to life by a local video model (LTX-2.3 or Wan 2.2 image-to-video, engine/animate.py), asked
           for low, local motion and a locked camera. `loop: seamless` generates first = last frame (the clip's end frame
           is the still, so it comes back to where it started); `pingpong` generates one way and plays it both ways.
           Kept lossless (FFV1) so every later stage can be redone without the GPU.
  track    SAM 2.1 follows the moving thing through the clip (seeded on the still's mask), so the mask keeps the whole
           path it sweeps (a flame that leans, a curtain that billows out of its first outline).
  mask     the region, the tracked path and where the clip really moves (temporal motion energy), grown and feathered:
           the mask's edge falls where nothing moves, so no seam is cut through the motion.
  encode   frames stabilised against the still (a video model drifts the whole frame a little), tone-matched to the
           still around the mask, the loop closed (a flow-aligned crossfade where the generated loop does not meet
           itself; pingpong has no seam), motion damped or exaggerated by `strength`, then encoded as H.264 and the
           mask as WebP, plus a report that measures the result: the loop's seam (the step from last frame to first,
           against a typical step), how much moves, how much of the picture, bytes.

The video holds only the crop around the moving part; its pixels outside the mask are the still's own, and the mask is the
page's compositing weight, so `still x (1 - mask) + video x mask` has the still's exact pixels wherever the mask is 0.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import time
from pathlib import Path
from typing import Callable, Optional

import numpy as np

from .project import BuildContext, BuildError, ffmpeg, file_key, probe
from .spec import Cinemagraph, EditRegion, ImageInput

VERSION = 1
FPS = 24
CONTEXT = 0.5            # how much of the surroundings the video model sees: a share of the region's size on every side
LTX_MP = 0.5             # megapixels LTX-2.3 renders the crop at (aspect kept)
MAX_VIDEO_W = 1280       # the encoded video's widest side
MIN_SIDE = 320           # the crop is at least this big (as far as the still goes)
SEAM_OK = 1.5            # a loop whose closing step is at most this many typical steps is seamless
NEGATIVE = ("camera movement, camera shake, zoom, pan, tilt, cuts, flicker, morphing, warping, new objects appearing, "
            "people, text, watermark, blur, motion in the background, changing light")


# ---------------------------------------------------------------- the spec side

def collect(site) -> list[tuple[str, ImageInput]]:
    """Every image input in a site's spec that carries a `cinemagraph`, with where it is: [("sections[0].image", input)]."""
    from pydantic import BaseModel
    found: list[tuple[str, ImageInput]] = []

    def walk(v, path: str):
        if isinstance(v, ImageInput):
            if v.cinemagraph is not None:
                found.append((path, v))
            for name in ("edit", "beat_frame"):      # the source of an edited image is another input
                walk(getattr(v, name, None), f"{path}.{name}")
        elif isinstance(v, BaseModel):
            for name in v.model_fields:
                walk(getattr(v, name, None), f"{path}.{name}" if path else name)
        elif isinstance(v, (list, tuple)):
            for i, x in enumerate(v):
                walk(x, f"{path}[{i}]")
        elif isinstance(v, dict):
            for k, x in v.items():
                walk(x, f"{path}.{k}")
    walk(site, "")
    return found


def region_of(cg: Cinemagraph) -> EditRegion:
    """The image editor's region (engine/region.py) that names what moves, so the two share one cached search."""
    return EditRegion(prompt=cg.moves if not cg.box else None, box=cg.box, points=list(cg.points),
                      negative_points=list(cg.negative_points), pick=cg.pick, grow=0, feather=0)


def motion_text(cg: Cinemagraph) -> str:
    """What the video model is told: the motion, and that nothing else moves."""
    how = cg.motion or f"gentle, slow, natural motion of {cg.moves}"
    return (f"{how}. Only {cg.moves} moves; everything else in the picture stays perfectly still. "
            "Locked static camera, no camera movement. A calm, subtle cinemagraph loop")


def video_model_for(cg: Cinemagraph, site_model: Optional[str] = None) -> str:
    from .animate import video_model
    return video_model(cg.model, site_model)


# ---------------------------------------------------------------- the pure parts (numpy / OpenCV, no models)

def luma(a: np.ndarray) -> np.ndarray:
    return a[..., 0] * 0.299 + a[..., 1] * 0.587 + a[..., 2] * 0.114


def seam_report(frames: np.ndarray, mask: Optional[np.ndarray] = None) -> dict:
    """How well a loop closes. `step` is the mean absolute difference (0-255 levels, over the mask) between neighbouring
    frames; `seam` is the same between the last frame and the first, the step the loop makes when it wraps. The ratio is
    seam / typical step: about 1 for a loop that is continuous (the wrap is a step like any other), well above it for
    a loop that jumps."""
    f = frames.astype(np.float32)
    w = None if mask is None else (mask.astype(np.float32) / 255.0)

    def mad(a, b):
        d = np.abs(a - b).mean(axis=-1)
        return float((d * w).sum() / max(w.sum(), 1e-6)) if w is not None else float(d.mean())

    steps = [mad(f[i], f[i + 1]) for i in range(len(f) - 1)]
    typical = float(np.median(steps)) if steps else 0.0
    seam = mad(f[-1], f[0])
    return {"typical_step": round(typical, 3), "max_step": round(max(steps), 3) if steps else 0.0,
            "seam": round(seam, 3), "ratio": round(seam / max(typical, 1e-3), 2), "frames": int(len(f))}


def stabilise(frames: np.ndarray, ref: np.ndarray, keep: np.ndarray, log=print) -> tuple[np.ndarray, float]:
    """Undo the drift of the whole frame. A video model moves the picture a little as it renders (a slow push, a sway of
    a pixel or two), which would show as the moving part sliding against the still around it. Each frame is registered
    to the still (ECC, affine) on the pixels that are held (`keep`, 0-255: where the mask is zero) and warped back.
    Returns the frames and the largest drift found in pixels; frames that drift under a third of a pixel are not touched
    (resampling would only soften them)."""
    import cv2
    T, H, W, _ = frames.shape
    s = min(1.0, 480 / max(H, W))
    gray = lambda a: cv2.GaussianBlur(cv2.cvtColor(a, cv2.COLOR_RGB2GRAY), (0, 0), 1.2)
    rg = gray(ref)
    msk = (keep > 200).astype(np.uint8) * 255
    if s < 1:
        rs = cv2.resize(rg, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
        ms = cv2.resize(msk, (rs.shape[1], rs.shape[0]), interpolation=cv2.INTER_NEAREST)
    else:
        rs, ms = rg, msk
    if (ms > 0).mean() < 0.05:           # nothing held to register on (the mask covers the crop)
        return frames, 0.0
    out = frames.copy()
    worst = 0.0
    crit = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 60, 1e-5)
    for t in range(T):
        g = gray(frames[t])
        gs = cv2.resize(g, (rs.shape[1], rs.shape[0]), interpolation=cv2.INTER_AREA) if s < 1 else g
        warp = np.eye(2, 3, dtype=np.float32)
        try:
            _, warp = cv2.findTransformECC(rs, gs, warp, cv2.MOTION_AFFINE, crit, ms, 5)
        except cv2.error:
            continue
        warp[:, 2] /= s                  # translation back to full size
        # how far the frame moved, at the corners and the centre
        pts = np.array([[0, 0, 1], [W, 0, 1], [0, H, 1], [W, H, 1], [W / 2, H / 2, 1]], dtype=np.float32)
        drift = float(np.abs(pts @ warp.T - pts[:, :2]).max())
        if drift > 0.05 * max(H, W) or abs(np.linalg.det(warp[:, :2]) - 1) > 0.10:    # a registration gone wrong, not a drift
            continue
        worst = max(worst, drift)
        if drift < 0.33:
            continue
        out[t] = cv2.warpAffine(frames[t], warp, (W, H), flags=cv2.INTER_CUBIC | cv2.WARP_INVERSE_MAP,
                                borderMode=cv2.BORDER_REPLICATE)
    return out, worst


def tone_match(frames: np.ndarray, ref: np.ndarray, mask: np.ndarray, ring: int) -> np.ndarray:
    """Make every frame's tone agree with the still around the moving part. A video model returns a picture a shade off
    the one it was given (the encode, a little contrast, a warmer white), and inside the mask that shade would show as a
    patch. Per frame and channel, a gain and offset fitted on the pixels just outside the mask (the ring, where the still
    and the frame should be the same thing), then a smooth residual spread inward from the ring."""
    import cv2
    T, H, W, _ = frames.shape
    m = (mask > 0).astype(np.uint8)
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * ring + 1, 2 * ring + 1))
    near = cv2.dilate(m, k, iterations=2)
    band = (near > 0) & (m == 0)
    if band.sum() < 200:               # the mask reaches the crop's edge all round: fit on everything held
        band = m == 0
    if band.sum() < 200:
        return frames
    refb = ref[band].astype(np.float32)                       # (n, 3)
    out = np.empty_like(frames)
    sig = max(6.0, min(H, W) / 8)
    wmap = band.astype(np.float32)
    wblur = cv2.GaussianBlur(wmap, (0, 0), sig) + 1e-4
    for t in range(T):
        f = frames[t].astype(np.float32)
        fb = f[band]
        g = np.empty(3, np.float32)
        o = np.empty(3, np.float32)
        for c in range(3):
            x, y = fb[:, c], refb[:, c]
            vx = x.var()
            g[c] = np.clip(np.cov(x, y)[0, 1] / vx, 0.85, 1.15) if vx > 1e-3 else 1.0
            o[c] = y.mean() - g[c] * x.mean()
        f = f * g + o
        # what is left, smooth, from the ring inward
        resid = (ref.astype(np.float32) - f) * wmap[..., None]
        resid = np.stack([cv2.GaussianBlur(resid[..., c], (0, 0), sig) for c in range(3)], axis=-1) / wblur[..., None]
        f = f + resid * (m[..., None] > 0)
        out[t] = np.clip(f + 0.5, 0, 255).astype(np.uint8)
    return out


def motion_energy(frames: np.ndarray) -> np.ndarray:
    """Where the clip moves, as a 0-255-level map: per pixel, a high percentile over time of how far a (slightly blurred)
    frame is from the clip's own mean. Blurred first so grain and codec noise do not count as motion."""
    import cv2
    T, H, W, _ = frames.shape
    s = min(1.0, 640 / max(H, W))
    small = np.stack([cv2.GaussianBlur(cv2.resize(f, None, fx=s, fy=s, interpolation=cv2.INTER_AREA) if s < 1 else f,
                                       (0, 0), 1.5) for f in frames]).astype(np.float32)
    dev = np.abs(small - small.mean(axis=0, keepdims=True)).mean(axis=-1)       # (T, h, w)
    e = np.percentile(dev, 92, axis=0).astype(np.float32)
    if s < 1:
        e = cv2.resize(e, (W, H), interpolation=cv2.INTER_LINEAR)
    return e


def final_mask(seed: np.ndarray, energy: np.ndarray, grow: float, feather: float, tracked: Optional[np.ndarray] = None
               ) -> tuple[np.ndarray, dict]:
    """The mask the page composites through (uint8, 0 = the still, 255 = the video), from the region found on the still
    (`seed`, 0-255), the path the tracker saw it sweep (`tracked`, the union over the clip, or None), and the clip's
    motion energy. The video is kept where the thing is or where it is seen to move, near it; where nothing moves at all
    the still is kept (a patch of the video there would only be softer than the still), and the mask's soft edge falls on
    pixels that do not move, so no seam is cut through the motion."""
    import cv2
    from .region import despeckle, shape
    H, W = seed.shape
    base = seed > 127
    if tracked is not None:
        base = base | (tracked > 127)
    peak = float(np.percentile(energy, 99.5))
    tau = max(4.0, 0.30 * peak)
    moving = energy > tau
    side = min(H, W)
    ell = lambda r: cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))
    reach = max(6, int(0.07 * side))
    near = cv2.dilate(base.astype(np.uint8), ell(reach)) > 0
    where = base | (moving & near)
    # keep it only where something moves within a feather's width (a still part of the region is kept as the still)
    live = cv2.dilate(moving.astype(np.uint8), ell(max(3, int(feather)))) > 0
    where = where & live
    info = {"tau": round(tau, 2), "peak": round(peak, 2), "moving_px": int(moving.sum())}
    if where.sum() < max(64, 0.0005 * H * W):
        raise BuildError("the clip does not move where the picture says: nothing in the region moves. Raise `strength`, describe "
                         "the motion in `motion`, or point at the thing with `box` / `points`")
    where = cv2.morphologyEx(where.astype(np.uint8) * 255, cv2.MORPH_CLOSE, ell(max(2, int(grow))))
    where = despeckle(where, 0.02)
    return shape(where, int(round(grow)), int(round(feather))), info


def close_loop(frames: np.ndarray, overlap: int, flow: bool = True) -> np.ndarray:
    """Close a clip into a loop by crossfading its tail into its head. Frames 0..T-1 become T-overlap frames, in which
    the first `overlap` frames are the clip's last `overlap` frames dissolving into its first ones: so the wrap
    (last frame -> first) is a step like any other. With `flow`, each blend is made between frames moved halfway toward
    each other (optical flow), so a flame or a fold of cloth slides across the dissolve instead of ghosting; blends
    that flow made worse (it can: soft, translucent subjects) fall back to the plain dissolve."""
    import cv2
    T = len(frames)
    n = int(max(1, min(overlap, T // 2 - 1)))
    L = T - n
    out = [f for f in frames[:L]]
    f32 = frames.astype(np.float32)
    dis = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM) if flow else None
    gray = lambda a: cv2.cvtColor(np.clip(a, 0, 255).astype(np.uint8), cv2.COLOR_RGB2GRAY)
    H, W = frames.shape[1:3]
    gx, gy = np.meshgrid(np.arange(W, dtype=np.float32), np.arange(H, dtype=np.float32))
    for i in range(n):
        a, b = f32[L + i], f32[i]             # a: the tail's i-th frame (fading out), b: the head's (fading in)
        w = (i + 1) / (n + 1)
        plain = a * (1 - w) + b * w
        if dis is not None:
            fab = dis.calc(gray(a), gray(b), None)      # a -> b
            fba = dis.calc(gray(b), gray(a), None)      # b -> a
            wa = cv2.remap(a, gx + fab[..., 0] * w, gy + fab[..., 1] * w, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
            wb = cv2.remap(b, gx + fba[..., 0] * (1 - w), gy + fba[..., 1] * (1 - w), cv2.INTER_LINEAR,
                           borderMode=cv2.BORDER_REPLICATE)
            morph = wa * (1 - w) + wb * w
            # the better blend is the one that is closer to both neighbours' appearance in the middle of the dissolve
            ref = (a + b) * 0.5
            pick = morph if np.abs(morph - ref).mean() <= np.abs(plain - ref).mean() * 1.6 else plain
        else:
            pick = plain
        out[i] = np.clip(pick + 0.5, 0, 255).astype(np.uint8)
    return np.stack(out)


def pingpong(frames: np.ndarray) -> np.ndarray:
    """Forward, then back without repeating the turning frames: the loop's wrap is a step between neighbours."""
    if len(frames) < 3:
        return frames
    return np.concatenate([frames, frames[-2:0:-1]])


def damp(frames: np.ndarray, k: float) -> np.ndarray:
    """Scale the motion about its resting look (the mean of the loop): k < 1 calms it, k > 1 exaggerates it."""
    if abs(k - 1.0) < 1e-3:
        return frames
    f = frames.astype(np.float32)
    mean = f.mean(axis=0, keepdims=True)
    return np.clip(mean + (f - mean) * k + 0.5, 0, 255).astype(np.uint8)


def composite_video(frames: np.ndarray, still: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """The frames the video holds: the clip where the mask is above zero, the still itself everywhere else (so that the
    encoder has nothing to spend bits on outside the moving part, and the part it does encode is the whole story)."""
    live = (mask > 0)[None, ..., None]
    return np.where(live, frames, still[None])


def page_composite(poster: np.ndarray, frame: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """What the browser shows for one video frame: poster x (1 - mask) + frame x mask (integer arithmetic, the twin of
    region.composite): where the mask is 0 the pixel is the poster's, exactly."""
    from .region import composite
    return composite(poster, frame, mask)


# ---------------------------------------------------------------- video in and out

def read_video(path: Path) -> np.ndarray:
    """Every frame of a clip as uint8 RGB (T, H, W, 3), through FFmpeg."""
    from .config import settings
    info = probe(path)
    W, H = int(info["width"]), int(info["height"])
    p = subprocess.run([settings()["ffmpeg"], "-hide_banner", "-loglevel", "error", "-i", str(path), "-f", "rawvideo",
                        "-pix_fmt", "rgb24", "-"], capture_output=True)
    if p.returncode != 0:
        raise BuildError(f"could not read {path.name}: {p.stderr.decode(errors='replace')[-400:]}")
    a = np.frombuffer(p.stdout, np.uint8)
    return a.reshape(-1, H, W, 3)


def write_lossless(frames: np.ndarray, path: Path, fps: int = FPS) -> None:
    """FFV1 in Matroska: the generated clip kept exactly, at a third of the PNGs' size."""
    from .config import settings
    T, H, W, _ = frames.shape
    tmp = path.with_name(path.stem + ".tmp.mkv")
    p = subprocess.Popen([settings()["ffmpeg"], "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
                          "-s", f"{W}x{H}", "-r", str(fps), "-i", "-", "-c:v", "ffv1", "-level", "3", "-pix_fmt", "bgr0",
                          str(tmp)], stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    _, err = p.communicate(np.ascontiguousarray(frames).tobytes())
    if p.returncode != 0:
        raise BuildError(f"FFV1 encode failed: {err.decode(errors='replace')[-400:]}")
    tmp.replace(path)


def encode_h264(frames: np.ndarray, path: Path, fps: int = FPS, crf: int = 23) -> None:
    """The cinemagraph's video: H.264 (plays everywhere), yuv420p tagged BT.709 so a browser shows its colours the way it
    shows the poster's, faststart, no audio."""
    from .config import settings
    T, H, W, _ = frames.shape
    tmp = path.with_name(path.stem + ".tmp.mp4")
    vf = "scale=out_color_matrix=bt709:out_range=tv,format=yuv420p"
    p = subprocess.Popen([settings()["ffmpeg"], "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
                          "-s", f"{W}x{H}", "-r", str(fps), "-i", "-", "-vf", vf, "-an", "-c:v", "libx264", "-profile:v", "main",
                          "-preset", "slow", "-crf", str(crf), "-g", str(fps * 2), "-colorspace", "bt709", "-color_primaries",
                          "bt709", "-color_trc", "bt709", "-color_range", "tv", "-movflags", "+faststart", str(tmp)],
                         stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    _, err = p.communicate(np.ascontiguousarray(frames).tobytes())
    if p.returncode != 0:
        raise BuildError(f"H.264 encode failed: {err.decode(errors='replace')[-400:]}")
    tmp.replace(path)


def save_mask(mask: np.ndarray, path: Path) -> None:
    """The mask as a WebP the page uses as a CSS mask: white, with the mask as its alpha (lossless: the 8-bit weights are
    exactly what the engine measured)."""
    from PIL import Image
    H, W = mask.shape
    rgba = np.full((H, W, 4), 255, np.uint8)
    rgba[..., 3] = mask
    Image.fromarray(rgba, "RGBA").save(path, "WEBP", lossless=True, method=6, exact=True)


# ---------------------------------------------------------------- stages

def _digest(obj) -> str:
    return hashlib.sha1(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()[:12]


def region_key(cg: Cinemagraph) -> dict:
    return {"moves": cg.moves, "box": cg.box, "points": [list(p) for p in cg.points],
            "negative_points": [list(p) for p in cg.negative_points], "pick": cg.pick}


def crop_around(mask: np.ndarray, still_size: tuple[int, int], context: float = CONTEXT) -> tuple[int, int, int, int]:
    """The crop of the still the video model is shown: the region plus its surroundings, at least MIN_SIDE across, edges on
    multiples of 8 (so every size derived from it is a whole number of macroblocks)."""
    from .region import crop_box
    W, H = still_size
    x0, y0, x1, y1 = crop_box(mask, context)
    def snap(lo, hi, limit):
        lo, hi = max(0, lo // 8 * 8), min(limit, -(-hi // 8) * 8)
        if hi - lo < min(MIN_SIDE, limit):                     # still a little small: widen about the middle
            mid = (lo + hi) // 2
            lo, hi = max(0, mid - MIN_SIDE // 2), min(limit, mid + MIN_SIDE // 2)
        return lo, hi
    (a, c), (b, d) = snap(x0, x1, W), snap(y0, y1, H)
    return a, b, c, d


def gen_size(cw: int, ch: int, model: str, wan: Optional[dict]) -> tuple[int, int]:
    """What the video model renders the crop at (aspect kept): LTX about LTX_MP megapixels, Wan its own (animate.wan_size)."""
    from .animate import ltx_size, wan_size
    if model == "wan":
        return wan_size(cw, ch, (wan or {}).get("res"))
    return ltx_size(cw, ch, LTX_MP)


def work_size(cw: int, ch: int) -> tuple[int, int]:
    """The size of everything after the clip (and of the encoded video): the crop's own pixels, down to MAX_VIDEO_W, even."""
    s = min(1.0, MAX_VIDEO_W / max(cw, ch))
    return max(2, round(cw * s / 2) * 2), max(2, round(ch * s / 2) * 2)


class Built(dict):
    """What a cinemagraph build gives the page: video, mask (files), box (fractions of the still), sizes, report."""


def build(project, ref: ImageInput, log: Callable[[str], None] = print, force: bool = False,
          options: Optional[dict] = None, site_video_model: Optional[str] = None, site_wan: Optional[dict] = None,
          only_cached: bool = False) -> Optional[Built]:
    """Build (or find in the cache) the cinemagraph of an image input. Returns None when only_cached and nothing is built,
    or when planning. Files are in .build/_cinemagraph/<id>/: cine.mp4, cine.mask.webp, report.json."""
    from . import inputs
    from .fidelity import is_planning
    cg = ref.cinemagraph
    if cg is None:
        return None
    still_path = inputs.resolve_image(project, ref, log)
    from PIL import Image, ImageOps
    sim = ImageOps.exif_transpose(Image.open(still_path)).convert("RGB")
    W, H = sim.size
    model = video_model_for(cg, site_video_model)
    wan = dict(site_wan or {})
    sid = _digest([file_key(still_path), region_key(cg), VERSION])
    ctx = BuildContext(project, f"_cinemagraph/{sid}", log=log, force=force, options=dict(options or {}))
    work = ctx.work
    plan = ctx.options.get("plan")

    # ---- region: the mask on the still, and the crop the model sees
    from . import region as region_mod
    reg = region_of(cg)
    if only_cached or is_planning():
        digest = _digest([file_key(still_path), region_mod.find_spec(reg), "large", region_mod.VERSION])
        if not (project.build / "_generated" / f"region_{digest}.png").exists():
            return None
    raw_path = region_mod.find(project, still_path, reg, log)
    raw = np.asarray(Image.open(raw_path).convert("L"))
    if raw.shape != (H, W):
        raw = np.asarray(Image.fromarray(raw).resize((W, H), Image.BILINEAR))
    seed_full = region_mod.shape(raw, 0, 0)               # the region as found (binary, despeckled), at the still's size
    box = crop_around(seed_full, (W, H))
    x0, y0, x1, y1 = box
    cw, ch = x1 - x0, y1 - y0
    ww, wh = work_size(cw, ch)
    gw, gh = gen_size(cw, ch, model, wan)
    seconds = float(cg.seconds)
    flf = cg.loop == "seamless"
    crop_png = work / "crop.png"
    sim.crop(box).save(crop_png)

    # ---- clip: the video model brings the crop to life
    clip = work / "clip.mkv"
    ckey = {"v": VERSION, "crop": [file_key(still_path), box], "motion": motion_text(cg), "seconds": seconds, "seed": cg.seed,
            "model": model, "wan": wan if model == "wan" else None, "flf": flf, "size": [gw, gh]}
    if only_cached and ctx.status("clip", ckey, [clip]) not in ("fresh", "migrated", "locked"):
        return None

    def make_clip():
        from . import animate
        from .fidelity import would_render
        would_render("cinemagraph", cg.moves)
        frames = animate.animate(crop_png, "", motion_text(cg), seconds, cg.seed, work, size=(gw, gh), log=log,
                                 negative=NEGATIVE, strength=1.0, end_image=crop_png if flf else None, model=model, wan=wan)
        import cv2
        arr = np.stack([cv2.resize(np.asarray(Image.open(p).convert("RGB")), (ww, wh), interpolation=cv2.INTER_AREA
                                   if (ww, wh) < Image.open(p).size else cv2.INTER_CUBIC) for p in frames])
        write_lossless(arr, clip)
        shutil.rmtree(work / "frames", ignore_errors=True)
    ctx.stage("clip", ckey, [clip], make_clip)
    if plan is not None and not clip.exists():
        return None

    frames_raw = read_video(clip)
    T = len(frames_raw)
    import cv2
    still_c = cv2.resize(np.asarray(sim.crop(box)), (ww, wh), interpolation=cv2.INTER_AREA if (ww, wh) < (cw, ch) else cv2.INTER_CUBIC)
    seed_c = cv2.resize(seed_full[y0:y1, x0:x1], (ww, wh), interpolation=cv2.INTER_LINEAR)
    sc = ww / cw                                           # work pixels per still pixel

    # ---- track: SAM 2.1 follows the moving thing through the clip
    tracked = None
    if cg.track:
        tr = work / "track.npz"
        tkey = {"v": VERSION, "clip": ckey, "seed": hashlib.sha1(seed_c.tobytes()).hexdigest()[:12]}

        def run_track():
            _track(ctx, frames_raw, seed_c, tr, log)
        try:
            ctx.stage("track", tkey, [tr], run_track)
            if tr.exists():
                tracked = np.load(tr)["union"]
        except BuildError as e:
            log(f"  note: tracking did not run ({e}); the mask follows the region and the clip's motion instead")

    # ---- mask: where the clip moves, the region and the path it sweeps, grown and feathered
    frames_st, drift = stabilise(frames_raw, still_c, np.where(seed_c > 0, 0, 255).astype(np.uint8), log)
    energy = motion_energy(frames_st)
    mask, minfo = final_mask(seed_c, energy, cg.grow * sc, cg.feather * sc, tracked)

    # ---- encode: stabilise, tone-match, close the loop, damp, composite, encode, measure
    out_id = _digest([ckey, region_key(cg), cg.grow, cg.feather, cg.track, cg.loop, cg.strength, VERSION])
    mp4, wp, rep = work / f"cine_{out_id}.mp4", work / f"cine_{out_id}.mask.webp", work / f"cine_{out_id}.json"
    ekey = {"v": VERSION, "out": out_id}

    def run_encode():
        ring = max(8, int(round(cg.feather * sc)))
        fr = tone_match(frames_st, still_c, mask, ring)
        before = seam_report(fr, mask)
        if cg.loop == "pingpong":
            seq, how = pingpong(fr), "pingpong"
            closed = seam_report(seq, mask)
        else:
            if before["ratio"] <= SEAM_OK:
                seq, how, closed = fr, "as generated", before
            else:
                n = int(min(max(8, T // 6), T // 2 - 1))
                seq, how = close_loop(fr, n, flow=True), f"crossfade ({n} frames, flow-aligned)"
                closed = seam_report(seq, mask)
                plain = close_loop(fr, n, flow=False)
                alt = seam_report(plain, mask)
                if alt["ratio"] < closed["ratio"]:
                    seq, how, closed = plain, f"crossfade ({n} frames)", alt
        seq = damp(seq, cg.strength)
        vid = composite_video(seq, still_c, mask)
        encode_h264(vid, mp4)
        save_mask(mask, wp)
        dec = read_video(mp4)                                   # measure what the page will play, not what we meant
        outside = _outside_change(dec, mask)
        decoded = seam_report(dec, mask)
        motion = float(np.mean(np.std(seq.astype(np.float32), axis=0).mean(axis=-1)[mask > 127])) if (mask > 127).any() else 0.0
        report = {
            "moves": cg.moves, "model": model, "seconds": round(len(seq) / FPS, 2), "fps": FPS, "frames": int(len(seq)),
            "loop": {"mode": cg.loop, "closed_by": how, "generated": before, "closed": closed, "encoded": decoded,
                     "seamless": decoded["ratio"] <= SEAM_OK},
            "still": [W, H], "box": [x0, y0, x1, y1], "video": [ww, wh], "bytes": mp4.stat().st_size + wp.stat().st_size,
            "mask": {"share_of_still": round(float((mask > 127).sum()) / sc / sc / (W * H), 4), **minfo,
                     "tracked": tracked is not None},
            "motion": {"temporal_std": round(motion, 2), "drift_px": round(drift, 2)},
            "held": {"max_change_outside_mask": outside["max"], "share_changed": outside["share"]},
        }
        rep.write_text(json.dumps(report, indent=1))
    ctx.stage("encode", ekey, [mp4, wp, rep], run_encode)
    report = json.loads(rep.read_text())
    return Built(video=mp4, mask=wp, report=rep, data=report, box=[x0 / W, y0 / H, x1 / W, y1 / H], still=[W, H],
                 size=[ww, wh], poster_crop=crop_png, id=out_id)


def _outside_change(dec: np.ndarray, mask: np.ndarray) -> dict:
    """Over the decoded video, composited through the mask over its own first frame's pixels outside it: the largest change
    of any pixel where the mask is zero. The page never shows the video there (the mask is zero), so this is a property of
    the file too: the video holds the same still outside the mask, to within the codec."""
    z = mask == 0
    if not z.any():
        return {"max": 0, "share": 0.0}
    d = np.abs(dec[:, z].astype(np.int16) - dec[0:1, z].astype(np.int16))
    return {"max": int(d.max()), "share": round(float((d.max(axis=(0, 2)) > 0).mean()), 4)}


def _track(ctx: BuildContext, frames: np.ndarray, seed: np.ndarray, out: Path, log) -> None:
    """SAM 2.1 through the clip, seeded on frame 0 with a box (and a point inside) per piece of the region; the union of
    the masks over time is what is saved (`union`, uint8, the clip's size)."""
    import cv2
    from . import reveal
    from .backends import comfy
    from PIL import Image
    T, H, W, _ = frames.shape
    s = min(1.0, 640 / max(H, W))
    tw, th = max(32, round(W * s / 2) * 2), max(32, round(H * s / 2) * 2)
    small = np.stack([cv2.resize(f, (tw, th), interpolation=cv2.INTER_AREA) for f in frames])
    clip = ctx.work / "track_in.mp4"
    encode_h264(small, clip, crf=12)
    sm = cv2.resize(seed, (tw, th), interpolation=cv2.INTER_LINEAR) > 127
    n, lab, stats, cent = cv2.connectedComponentsWithStats(sm.astype(np.uint8), connectivity=8)
    prompts = []
    for i in range(1, n):
        if stats[i, cv2.CC_STAT_AREA] < max(24, 0.02 * stats[1:, cv2.CC_STAT_AREA].max()):
            continue
        x, y, w, h = (int(stats[i, k]) for k in (cv2.CC_STAT_LEFT, cv2.CC_STAT_TOP, cv2.CC_STAT_WIDTH, cv2.CC_STAT_HEIGHT))
        dist = cv2.distanceTransform((lab == i).astype(np.uint8), cv2.DIST_L2, 3)
        py, px = np.unravel_index(int(dist.argmax()), dist.shape)
        prompts.append({"box": [x / tw, y / th, (x + w) / tw, (y + h) / th], "points": [[px / tw, py / th]], "labels": [1]})
    if not prompts:
        raise BuildError("no region to track")
    reveal._need_nodes(log)
    log(f"  tracking the moving part through the clip (SAM 2.1, {len(prompts)} object(s), {T} frames)")
    name = comfy.upload(str(clip))
    images = comfy.run(reveal.track_graph(name, 0, prompts, "large", f"studio/cine_{ctx.section_id.split('/')[-1]}", 0, T - 1), poll=2)
    got = Path(comfy.fetch(images, str(ctx.work / "track_png")))
    try:
        files = sorted(got.glob("*.png"))
        if len(files) != T:
            raise BuildError(f"the tracker returned {len(files)} masks for {T} frames")
        m = np.stack([np.asarray(Image.open(p).convert("L")) for p in files])
    finally:
        shutil.rmtree(got, ignore_errors=True)
    union = m.max(axis=0)
    area0, areaU = float((m[0] > 127).mean()), float((union > 127).mean())
    if area0 < 1e-4 or areaU > 0.9:               # the tracker lost it, or took the picture: keep nothing of it
        raise BuildError(f"the tracker's masks are not usable (first frame {area0:.2%}, union {areaU:.2%})")
    union = cv2.resize(union, (W, H), interpolation=cv2.INTER_LINEAR)
    np.savez_compressed(out, union=union)


# ---------------------------------------------------------------- the page's side

def page_entry(built: Built, media_url: Callable[[Path], str]) -> dict:
    """What the page needs to play it, for the `data-cine` attribute: the files, and where the video sits on the still."""
    x0, y0, x1, y1 = built["box"]
    return {"v": media_url(built["video"]), "m": media_url(built["mask"]),
            "b": [round(x0, 5), round(y0, 5), round(x1 - x0, 5), round(y1 - y0, 5)],
            "r": round(built["still"][0] / built["still"][1], 5), "fps": FPS}


def summary(rep: dict) -> str:
    """One readable line per cinemagraph, for the CLI and the build log."""
    lp = rep["loop"]
    return (f"{rep['moves']}: {rep['seconds']}s {rep['model']} loop ({lp['mode']}, {lp['closed_by']}), seam x{lp['encoded']['ratio']} "
            f"{'ok' if lp['seamless'] else 'VISIBLE'}, {rep['mask']['share_of_still']:.1%} of the picture moves, "
            f"outside the mask max change {rep['held']['max_change_outside_mask']}, {rep['bytes'] / 1024:.0f} KB")
