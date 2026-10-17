"""Layered depth for frozen moments (`freeze.layers`): planes instead of one warped sheet.

A frozen frame warped by one depth map smears at every depth jump: the foreground's edge drags the background with it
(a halo), the background is sometimes sampled from the person (a double edge), and nothing can show what is behind a
person because the picture does not contain it. Here the frame is cut into planes, back to front:

  background plate   the frame with the subjects painted out (Qwen-Image-Edit through the subjects' mask, pixel-exact
                     outside the hole), its depth with the holes filled from the surroundings
  subject planes     one per person or group of people at a similar depth: a soft alpha (SAM 2.1 inside the box Florence-2
                     found, refined to the picture's own edge with the guided filter), a smooth depth of its own (no jump
                     inside a plane, so no internal stretch), and the picture's pixels with the plate's contribution
                     removed at the edge (foreground colour estimation, so no fringe of the old background)
  render             the planes are marched and sampled one after the other, each with its own depth, and composited over
                     each other: at rest the result is the frame itself; when the camera moves, a plane slides over the
                     plate instead of smearing, and the plate shows through where the person was.

The planes are cut from the same picture at render time (not separate images), so with deep zoom (`freeze.detail`) every
tile carries its own alpha, refined at the tile's resolution, and the plate continues down the pyramid: a layered deep
zoom costs one extra tile attribute per plane instead of one pyramid per plane, and every level agrees by construction.
See docs/ENGINE.md, "Layered depth".
"""
from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

import numpy as np

from .project import BuildError

VERSION = 1

PLATE_INSTRUCTION = ("Remove every person from this picture. Fill the space where they stood with the empty street, "
                     "ground, fog and buildings continuing naturally behind them, in exactly the same drawing style, "
                     "line weight and tones. Do not add anything new and do not change anything else.")


# ---------------------------------------------------------------- pure maths (cv2 / numpy)

def push_pull(img: np.ndarray, valid: np.ndarray) -> np.ndarray:
    """Fill the invalid part of `img` (float H x W or H x W x C) from the valid part, smoothly at every scale (push-pull):
    where `valid` (0-1) is 1 the image is unchanged, elsewhere it is the surroundings continued."""
    import cv2
    a = img.astype(np.float32)
    v = valid.astype(np.float32)
    if a.ndim == 2:
        a = a[..., None]
    levels = [(a * v[..., None], v)]
    while min(levels[-1][1].shape) > 6:
        n, d = levels[-1]
        n2 = cv2.pyrDown(n)
        d2 = cv2.pyrDown(d)
        levels.append((n2.reshape(n2.shape[0], n2.shape[1], -1), d2))
    n, d = levels[-1]
    cur = n / np.maximum(d, 1e-6)[..., None]
    if float(d.max()) < 1e-6:
        return img.astype(np.float32)               # nothing to fill from
    for n, d in reversed(levels[:-1]):
        h, w = d.shape
        up = cv2.resize(cur, (w, h), interpolation=cv2.INTER_LINEAR).reshape(h, w, -1)
        known = n / np.maximum(d, 1e-6)[..., None]
        wgt = np.clip(d * 1.5, 0, 1)[..., None]
        cur = known * wgt + up * (1 - wgt)
    out = cur.reshape(a.shape)
    out = a * v[..., None] + out * (1 - v[..., None])
    return out[..., 0] if img.ndim == 2 else out


def soft_alpha(mask: np.ndarray, feather: float) -> np.ndarray:
    """A float 0-1 alpha from a mask (any 0-1 or 0-255 map): thresholded, then softened over about `feather` pixels."""
    import cv2
    m = np.asarray(mask, dtype=np.float32)
    if m.max() > 1.5:
        m = m / 255.0
    m = (m > 0.5).astype(np.float32)
    if feather > 0.2:
        m = cv2.GaussianBlur(m, (0, 0), feather / 2)
    return m


def grow_mask(m: np.ndarray, px: int) -> np.ndarray:
    import cv2
    if px <= 0:
        return m.astype(np.float32)
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * px + 1, 2 * px + 1))
    return cv2.dilate((m > 0.5).astype(np.uint8) * 255, k).astype(np.float32) / 255.0


def plane_depth(depth: np.ndarray, alpha: np.ndarray) -> np.ndarray:
    """A subject plane's depth: the scene depth smoothed inside the subject (no jump within a plane: the part of a person
    nearer the camera still leads, the outline does not tear) and continued smoothly outside it (so the march has
    something sensible past the edge; the alpha cuts the colour there)."""
    import cv2
    inside = (alpha > 0.5).astype(np.float32)
    if inside.sum() < 4:
        return depth.astype(np.float32)
    ys, xs = np.nonzero(inside)
    sigma = max(2.0, 0.03 * (ys.max() - ys.min() + 1))
    num = cv2.GaussianBlur(depth.astype(np.float32) * inside, (0, 0), sigma)
    den = cv2.GaussianBlur(inside, (0, 0), sigma)
    sm = np.where(inside > 0, num / np.maximum(den, 1e-6), 0).astype(np.float32)
    return push_pull(sm, inside)


def background_depth(depth: np.ndarray, hole: np.ndarray) -> np.ndarray:
    """The scene depth with the subjects' hole filled from the surroundings (what the depth behind them would be)."""
    return push_pull(depth.astype(np.float32), 1.0 - np.clip(hole, 0, 1))


def refine_alpha(parent_up: np.ndarray, rgb: np.ndarray, radius: int = 0, eps: float = 4e-4) -> np.ndarray:
    """A plane's alpha at a tile's resolution: the parent's alpha enlarged (float 0-1, `parent_up`), snapped to the edges
    of the tile's own picture with the guided filter, with a little gain so a half-covered edge pixel reads as an edge."""
    import cv2
    from .freeze import guided_filter
    H, W = rgb.shape[:2]
    g = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY).astype(np.float32) / 255
    r = radius or max(3, W // 400)
    a = guided_filter(g, np.clip(parent_up.astype(np.float32), 0, 1), r, eps)
    return np.clip((a - 0.5) * 1.25 + 0.5, 0, 1)


def estimate_foreground(rgb: np.ndarray, alpha: np.ndarray, plate: np.ndarray) -> np.ndarray:
    """The subject's own colour at its edge: the picture's pixel is alpha * foreground + (1 - alpha) * plate, so
    foreground = (pixel - (1 - alpha) * plate) / alpha where alpha is solid enough to divide by, the pixel itself elsewhere.
    Composited over the plate again it gives the picture back exactly; over anything else it has no fringe of the old
    background. (float arrays, 0-255)"""
    a = alpha[..., None]
    fg = (rgb - (1 - a) * plate) / np.maximum(a, 0.08)
    fg = np.clip(fg, 0, 255)
    w = np.clip((alpha - 0.04) / 0.2, 0, 1)[..., None]
    return rgb * (1 - w) + fg * w


def group_planes(items: list[tuple[str, float]], max_planes: int) -> list[list[int]]:
    """Group subjects (id, depth) into at most `max_planes` planes of similar depth: sorted by depth, split at the
    largest gaps. Returns lists of indices into `items`, farthest plane first."""
    order = sorted(range(len(items)), key=lambda i: items[i][1])
    if len(order) <= max_planes:
        return [[i] for i in order]
    gaps = sorted(range(1, len(order)), key=lambda k: -(items[order[k]][1] - items[order[k - 1]][1]))[:max_planes - 1]
    cuts = sorted(gaps)
    out, start = [], 0
    for c in [*cuts, len(order)]:
        out.append(order[start:c])
        start = c
    return out


# ---------------------------------------------------------------- finding the subjects (Florence-2 + SAM 2.1)

@dataclass
class Subject:
    id: str
    mask: np.ndarray                    # float 0-1, the frame's size
    layer: int = -1                     # which `subjects` entry named it (-1: auto)


def _segment(png: Path, prompts: list[dict], work: Path, tag: str) -> np.ndarray:
    """SAM 2.1 on one image: the soft mask (float 0-1) of the objects `prompts` name (their union)."""
    from PIL import Image
    from .backends import comfy
    from .region import seg_graph
    name = comfy.upload(str(png))
    images = comfy.run(seg_graph(name, prompts, "large", f"studio/layers_{tag}"), poll=2)
    got = Path(comfy.fetch(images, str(work / f"_seg_{tag}")))
    try:
        files = sorted(got.glob("*.png"))
        if not files:
            raise BuildError("layers: the segmentation returned no mask")
        return np.asarray(Image.open(files[0]).convert("L"), dtype=np.float32) / 255.0
    finally:
        shutil.rmtree(got, ignore_errors=True)


def find_subjects(png: Path, layers, work: Path, log: Callable) -> list[Subject]:
    """The subjects of a frame, one mask each. `layers.subjects == "auto"`: every person Florence-2 finds; or the named
    subjects (a prompt can match several things: they share a plane, the plane's mask is their union)."""
    from .reveal import _need_nodes, find_boxes
    from .spec import FreezeLayer
    _need_nodes(log)
    specs = [FreezeLayer(prompt="a person")] if layers.subjects == "auto" else list(layers.subjects)
    out: list[Subject] = []
    for li, sp in enumerate(specs):
        boxes: list[list[float]] = []
        if sp.box:
            boxes = [list(sp.box)]
        elif sp.prompt:
            log(f"  layers: finding {sp.prompt!r} (Florence-2)")
            boxes, _all, _o = find_boxes(png, sp.prompt, "all", None, log)
            if layers.subjects == "auto":
                boxes = [b for b in boxes if (b[2] - b[0]) * (b[3] - b[1]) < 0.4 and (b[3] - b[1]) > (b[2] - b[0])]
        items: list[dict] = [{"box": b} for b in boxes]
        for p in sp.points:
            items.append({"points": [list(p)], "labels": [1]})
        if not items:
            raise BuildError(f"layers: nothing found for {sp.prompt or sp.box or sp.points}: reword it, or give a `box` / `points`")
        if layers.subjects == "auto":
            for k, it in enumerate(items):          # each person is cut out alone: planes group them by depth afterwards
                out.append(Subject(f"person{k + 1}", _segment(png, [it], work, f"p{k}"), li))
        else:
            out.append(Subject(sp.id or f"layer{li + 1}", _segment(png, items, work, f"l{li}"), li))
    out = [s for s in out if (s.mask > 0.5).mean() > 2e-5]
    if not out:
        raise BuildError("layers: no subject was found on the frame")
    return out


# ---------------------------------------------------------------- the background plate

def plate_of(frozen: np.ndarray, hole: np.ndarray, instruction: str, seed: int, work: Path, log: Callable) -> np.ndarray:
    """The frame with the hole painted out: Qwen-Image-Edit over the whole frame, kept only inside the hole (`region.composite`:
    outside it the pixel is the frame's, exactly), through a softened edge. Without ComfyUI the hole is filled smoothly from
    its surroundings (push-pull): a gradient, no detail, and a say so in the log."""
    from PIL import Image
    from . import region
    from .backends import comfy
    mask8 = np.clip(hole * 255, 0, 255).astype(np.uint8)
    if not comfy.alive():
        log("  layers: ComfyUI is not running: filling the background behind the subjects smoothly from its surroundings")
        fill = np.clip(push_pull(frozen.astype(np.float32), 1.0 - hole), 0, 255).astype(np.uint8)
        return region.composite(frozen, fill, mask8)
    log("  layers: painting the background behind the subjects (Qwen-Image-Edit)")
    src = work / "_plate_in.png"
    Image.fromarray(frozen).save(src)
    comfy.free()
    names = [comfy.upload(str(src))]
    images = comfy.run(comfy.build_qwen_edit_graph(names, instruction, seed, 20, prefix="studio/layers_plate"), poll=2)
    got = Path(comfy.fetch(images, str(work / "_plate_out")))
    try:
        edited = Image.open(next(got.glob("*.png"))).convert("RGB")
    finally:
        shutil.rmtree(got, ignore_errors=True)
        src.unlink(missing_ok=True)
        comfy.free()
    if edited.size != (frozen.shape[1], frozen.shape[0]):
        edited = edited.resize((frozen.shape[1], frozen.shape[0]), Image.LANCZOS)
    return region.composite(frozen, np.asarray(edited), mask8)


# ---------------------------------------------------------------- the planes of a frame

@dataclass
class LayerSet:
    """The planes of a frame at the beat's size. `alpha`: P soft maps (farthest plane first), `depth`: P plane depths,
    `hole`: where the subjects were (grown), `plate`: the frame with them painted out (uint8), `bg_depth`: the
    background plane's depth. `ids`: the subjects of each plane."""
    alpha: np.ndarray                     # (P, H, W) float32
    depth: np.ndarray                     # (P, H, W) float32
    hole: np.ndarray                      # (H, W) float32
    plate: np.ndarray                     # (H, W, 3) uint8
    bg_depth: np.ndarray                  # (H, W) float32
    ids: list[list[str]] = field(default_factory=list)
    key: str = ""


def build_planes(frozen: np.ndarray, depth_raw: np.ndarray, layers, seed: int, work: Path, log: Callable,
                 subjects: Optional[list[Subject]] = None, png: Optional[Path] = None) -> LayerSet:
    """Cut `frozen` (uint8, beat size) into planes: find the subjects, group them by depth, paint the plate."""
    H, W = frozen.shape[:2]
    if subjects is None:
        subjects = find_subjects(png, layers, work, log)
    med = []
    for s in subjects:
        m = s.mask > 0.5
        med.append((s.id, float(np.median(depth_raw[m])) if m.any() else 0.0))
    if layers.subjects == "auto":
        groups = group_planes(med, layers.planes)
    else:
        groups = [[i] for i in sorted(range(len(subjects)), key=lambda i: med[i][1])][: layers.planes]
    log(f"  layers: {len(subjects)} subjects in {len(groups)} planes")
    alphas, depths, ids = [], [], []
    for g in groups:
        union = np.max([subjects[i].mask for i in g], axis=0)
        a = soft_alpha(union, layers.feather)
        alphas.append(a)
        depths.append(plane_depth(depth_raw, a))
        ids.append([subjects[i].id for i in g])
    hole = np.clip(grow_mask(np.max([(a > 0.02).astype(np.float32) for a in alphas], axis=0), layers.grow), 0, 1)
    import cv2
    hole = cv2.GaussianBlur(hole, (0, 0), max(1.0, layers.feather)) if layers.feather > 0 else hole
    instruction = PLATE_INSTRUCTION + (" " + layers.plate.strip() if layers.plate.strip() else "")
    plate = plate_of(frozen, hole, instruction, seed, work, log)
    return LayerSet(np.stack(alphas).astype(np.float32), np.stack(depths).astype(np.float32), hole.astype(np.float32), plate,
                    background_depth(depth_raw, hole), ids)


# ---------------------------------------------------------------- tiles of a layered pyramid

def tile_layers(parent_alpha: np.ndarray, parent_hole: np.ndarray, parent_bg: np.ndarray, rgb: np.ndarray, box_parent, box_tile,
                resample: Callable) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """What a tile adds for the planes, from its parent's (all over the parent's box, `resample(img, src_box, dst_box)` puts
    them over the tile's): alphas refined at the tile's resolution, the hole, and the background picture: the tile's own
    pixels outside the hole, the parent's plate (enlarged) inside it. Returns (alpha (P,H,W) u8, hole (H,W) u8, bg (H,W,3) u8)."""
    P = parent_alpha.shape[0]
    alpha = np.stack([refine_alpha(resample(parent_alpha[p], box_parent, box_tile), rgb) for p in range(P)])
    hole = np.clip(resample(parent_hole, box_parent, box_tile), 0, 1)
    plate_up = resample(parent_bg.astype(np.float32), box_parent, box_tile)
    h = hole[..., None]
    bg = rgb.astype(np.float32) * (1 - h) + plate_up * h
    return (alpha * 255 + 0.5).astype(np.uint8), (hole * 255 + 0.5).astype(np.uint8), np.clip(bg + 0.5, 0, 255).astype(np.uint8)


def base_background(rgb: np.ndarray, ls: LayerSet) -> np.ndarray:
    """The background plane's picture at the base level's size (`rgb`: the upscaled frame, uint8): the frame's own pixels
    outside the hole, the plate (enlarged) inside it."""
    import cv2
    H, W = rgb.shape[:2]
    plate = cv2.resize(ls.plate, (W, H), interpolation=cv2.INTER_CUBIC).astype(np.float32)
    hole = cv2.resize(ls.hole, (W, H), interpolation=cv2.INTER_LINEAR)[..., None]
    return np.clip(rgb.astype(np.float32) * (1 - hole) + plate * hole + 0.5, 0, 255).astype(np.uint8)


def tile_plane_depths(depth_raw: np.ndarray, alpha_u8: np.ndarray, hole_u8: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(plane depths (P,H,W), background depth (H,W)) of a tile, float32, from its raw depth and its alphas."""
    P = alpha_u8.shape[0]
    pd = np.stack([plane_depth(depth_raw, alpha_u8[p].astype(np.float32) / 255) for p in range(P)])
    return pd.astype(np.float32), background_depth(depth_raw, hole_u8.astype(np.float32) / 255).astype(np.float32)


def build_cached(bdir: Path, frozen_png: Path, frozen: np.ndarray, depth_raw: np.ndarray, layers, seed: int, key: str,
                 log: Callable) -> LayerSet:
    """The frame's planes, made once and kept under bdir/layers/ (keyed by the frame, its depth and the layers settings)."""
    from PIL import Image
    ldir = bdir / "layers"
    ldir.mkdir(parents=True, exist_ok=True)
    stamp, npz, plate = ldir / "planes.key", ldir / "planes.npz", ldir / "plate.png"
    k = hashlib.sha1(json.dumps([VERSION, key, layers.model_dump(mode="json"), seed], sort_keys=True).encode()).hexdigest()[:16]
    if stamp.exists() and stamp.read_text() == k and npz.exists() and plate.exists():
        z = np.load(npz, allow_pickle=False)
        return LayerSet(z["alpha"].astype(np.float32) / 255, z["depth"].astype(np.float32), z["hole"].astype(np.float32) / 255,
                        np.asarray(Image.open(plate).convert("RGB")), z["bg_depth"].astype(np.float32),
                        json.loads(str(z["ids"])), k)
    ls = build_planes(frozen, depth_raw, layers, seed, ldir, log, png=frozen_png)
    review(ldir, frozen, ls)
    np.savez(ldir / "_tmp.npz", alpha=(ls.alpha * 255 + 0.5).astype(np.uint8), depth=ls.depth.astype(np.float16),
             hole=(ls.hole * 255 + 0.5).astype(np.uint8), bg_depth=ls.bg_depth.astype(np.float16), ids=json.dumps(ls.ids))
    (ldir / "_tmp.npz").replace(npz)
    Image.fromarray(ls.plate).save(plate)
    stamp.write_text(k)
    ls.key = k
    return ls


def review(ldir: Path, frozen: np.ndarray, ls: LayerSet) -> None:
    """planes.jpg beside the planes: the frame, the plate, and each plane's alpha tinted over the frame (what to look at
    when a subject was missed or a plate came out wrong)."""
    from PIL import Image
    tints = [(255, 60, 60), (60, 200, 90), (70, 120, 255), (255, 200, 40), (200, 80, 255), (40, 220, 220), (255, 130, 40), (160, 160, 160)]
    over = frozen.astype(np.float32).copy()
    for i, a in enumerate(ls.alpha):
        over = over * (1 - 0.55 * a[..., None]) + np.array(tints[i % len(tints)], np.float32) * 0.55 * a[..., None]
    h, w = frozen.shape[:2]
    sheet = np.concatenate([frozen, np.clip(over, 0, 255).astype(np.uint8), ls.plate], axis=1)
    im = Image.fromarray(sheet)
    im.thumbnail((2400, 700))
    im.save(ldir / "planes.jpg", quality=88)
