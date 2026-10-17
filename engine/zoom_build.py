"""Building the deep-zoom pyramid of a frozen beat (`freeze.detail`): one cached stage per tile.

For every tile of the plan (engine/zoom.py), parent first:

  parent_up   the parent's picture over the tile's box, resampled to the tile's size (exact geometry, bicubic)
  enlarge     a crop of the parent enlarged to the tile's size: SeedVR2 (or Lanczos when it is not installed)
  redraw      Z-Image Turbo img2img (or Qwen-Image-Edit) at low strength: fine detail in the picture's own style
  align       ECC registration of the redrawn tile to parent_up (a redraw may nudge shapes a pixel or two)
  lock        parent_up's low frequencies + the tile's fine detail: colours and shapes are exactly the parent's
  depth       the parent's depth over the tile, snapped to the tile's own edges (guided filter), the near side grown

Each tile is cached by what made it (its box, its parent's key, the detail settings), under .build/<section>/beats/<id>/
zoom/, so changing the deepest box redoes only the tiles that moved and never repeats the others.
"""
from __future__ import annotations

import hashlib
import json
import math
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import numpy as np

from . import zoom
from .freeze import FPS, CameraPath
from .project import BuildError
from .zoom import Tile, TileImage

GENERIC_PROMPT = ("the same style, lighting, line work and colours as the picture, extremely fine detail, crisp, sharp, "
                  "clean edges, nothing added that is not already there")


@dataclass
class Level0:
    """The base level the pyramid starts from: the (upscaled) frame, its raw depth (edge-snapped, not grown) at the
    beat's size, and a key naming what made them."""
    rgb: np.ndarray
    depth_raw: np.ndarray
    key: str

    box = (0.0, 0.0, 1.0, 1.0)


def digest(*parts) -> str:
    return hashlib.sha1(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()[:16]


def tile_pixels(size: tuple[int, int], tile: float) -> tuple[int, int]:
    """A tile's size: the beat's size times `tile`, a multiple of 16 (the diffusion model's grid) on both sides, with
    the beat's aspect to within a pixel."""
    w = int(round(size[0] * tile / 32)) * 32
    h = int(round(w * size[1] / size[0] / 16)) * 16
    return w, h


def make_plan(f, seconds: float, base_px: int, size: tuple[int, int]) -> tuple[list[Tile], list[float], float, tuple[int, int]]:
    """The tiles the camera of freeze `f` needs. (tiles, nominal sizes per level, ratio, tile pixels)"""
    d = f.detail
    path = CameraPath(f.camera, f.ease)
    views = zoom.views_of(path, max(48, int(round(seconds * FPS)) * 2))
    tw, th = tile_pixels(size, d.tile)
    levels = None if d.levels == "auto" else int(d.levels)
    tiles, sizes, ratio = zoom.plan_tiles(views, base_px=base_px, out_px=size[0], tile_px=tw, ratio=d.ratio, levels=levels)
    return tiles, sizes, ratio, (tw, th)


def prompt_of(d) -> str:
    return (d.prompt.strip().rstrip(".") + ". " if d.prompt.strip() else "") + GENERIC_PROMPT


def _read(p: Path) -> np.ndarray:
    from PIL import Image
    return np.asarray(Image.open(p).convert("RGB"))


def _write(a: np.ndarray, p: Path) -> None:
    from PIL import Image
    Image.fromarray(a).save(p)


def enlarge(parent_rgb: np.ndarray, parent_box, tile: Tile, tsize: tuple[int, int], method: str, seed: int,
            work: Path, log: Callable) -> np.ndarray:
    """A crop of the parent around the tile, enlarged to the tile's size (uint8): SeedVR2 or Lanczos. The crop is whole
    parent pixels (a little wider than the box); the result is re-sampled to the box's exact geometry afterwards."""
    from .backends import upscale as up
    ph, pw = parent_rgb.shape[:2]
    ps = parent_box[2] - parent_box[0]
    x0 = (tile.box[0] - parent_box[0]) / ps * pw
    x1 = (tile.box[2] - parent_box[0]) / ps * pw
    y0 = (tile.box[1] - parent_box[1]) / ps * ph
    y1 = (tile.box[3] - parent_box[1]) / ps * ph
    ix0, ix1 = max(0, int(math.floor(x0)) - 2), min(pw, int(math.ceil(x1)) + 2)
    iy0, iy1 = max(0, int(math.floor(y0)) - 2), min(ph, int(math.ceil(y1)) + 2)
    rect = (parent_box[0] + ix0 / pw * ps, parent_box[1] + iy0 / ph * ps, parent_box[0] + ix1 / pw * ps, parent_box[1] + iy1 / ph * ps)
    crop = parent_rgb[iy0:iy1, ix0:ix1]
    factor = tsize[1] * (iy1 - iy0) / max(1, (y1 - y0)) / (iy1 - iy0)           # tile pixels per parent pixel
    if method == "seedvr2":
        src, dst = work / "_zin.png", work / "_zout.png"
        _write(crop, src)
        up.seedvr2(src, dst, factor, seed, log)
        big = _read(dst)
        src.unlink(missing_ok=True)
        dst.unlink(missing_ok=True)
    else:
        import cv2
        big = cv2.resize(crop, (max(2, round(crop.shape[1] * factor)), max(2, round(crop.shape[0] * factor))),
                         interpolation=cv2.INTER_LANCZOS4)
    return zoom.resample_box(big, rect, tile.box, tsize, "cubic")


def redraw(img: np.ndarray, d, seed: int, work: Path, log: Callable) -> np.ndarray:
    """The detail pass over a tile at its full size: `d.method` at `d.strength`."""
    from .backends import detail
    if d.strength <= 0:
        return img
    src, dst = work / "_rin.png", work / "_rout.png"
    _write(img, src)
    try:
        if d.method == "qwen":
            detail.qwen_detail(src, dst, "Add fine detail to this picture in exactly the same style: " + prompt_of(d) +
                               " Keep every shape, outline, position, tone and colour exactly where it is.", seed, log=log)
        else:
            detail.zimage_img2img(src, dst, prompt_of(d), seed, d.strength, log)
        return _read(dst)
    finally:
        src.unlink(missing_ok=True)
        dst.unlink(missing_ok=True)


def make_tile(parent, tile: Tile, tsize: tuple[int, int], d, sr_method: str, seed: int, work: Path, log: Callable
              ) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict]:
    """One tile from its parent (a Level0 or a TileImage-like with .rgb, .depth_raw, .box): (picture uint8, raw depth,
    depth for the render, info)."""
    import cv2
    tw, th = tsize
    pw = parent.rgb.shape[1]
    parent_up = zoom.resample_box(parent.rgb, parent.box, tile.box, tsize, "cubic")
    big = enlarge(parent.rgb, parent.box, tile, tsize, sr_method, seed, work, log)
    drawn = redraw(big, d, seed, work, log)
    aligned, ainfo = zoom.align(drawn, parent_up)
    s = (tw / (tile.box[2] - tile.box[0])) / (pw / (parent.box[2] - parent.box[0]))        # tile pixels per parent pixel
    sigma = max(0.8, d.lock * s)
    locked = zoom.lock_low_frequencies(aligned, parent_up, sigma)
    out = np.clip(locked + 0.5, 0, 255).astype(np.uint8)
    pd = zoom.resample_box(parent.depth_raw.astype(np.float32), parent.box, tile.box, tsize, "linear")
    raw, grown = zoom.refine_depth(pd, out, grow=max(1, tw // 800))
    hf = lambda a: float(np.std(a.astype(np.float32) - cv2.GaussianBlur(a.astype(np.float32), (0, 0), sigma)))
    info = {"align": ainfo, "sigma": sigma, "scale": s, "detail_gain": hf(out) / max(hf(parent_up), 1e-3)}
    return out, raw, grown, info


@dataclass
class Built:
    """A tile as built: what the next level starts from (picture, raw depth, box) and what the render uses."""
    level: int
    box: tuple
    rgb: np.ndarray
    depth_raw: np.ndarray
    depth: np.ndarray
    key: str

    def image(self) -> TileImage:
        return TileImage(self.level, self.box, self.rgb, self.depth)


def tile_keys(tiles: list[Tile], base_key: str, tsize: tuple[int, int], d, sr_method: str, seed0: int) -> list[str]:
    """The cache key of every tile (a tile's key includes its parent's, so a changed parent redoes its children and
    nothing else). Cheap: no picture is looked at."""
    keys: list[str] = []
    spec = d.model_dump(mode="json", exclude={"levels", "ratio", "tile"})
    for t in tiles:
        pkey = base_key if t.parent < 0 else keys[t.parent]
        keys.append(digest("tile", zoom.VERSION, VERSIONS, t.level, [round(v, 5) for v in t.box], pkey, tsize, spec, sr_method, seed0))
    return keys


def build_pyramid(bdir: Path, base: Level0, f, seconds: float, size: tuple[int, int], sr_method: str,
                  log: Callable = print) -> list[Built]:
    """Every tile of the plan, built or loaded: parents before children, each cached under bdir/zoom/."""
    d = f.detail
    base_px = base.rgb.shape[1]
    tiles, sizes, ratio, tsize = make_plan(f, seconds, base_px, size)
    zdir = bdir / "zoom"
    zdir.mkdir(parents=True, exist_ok=True)
    if not tiles:
        log("  deep zoom: the camera never goes tighter than the frame's own pixels: no tiles needed")
        return []
    seed0 = f.seed if d.seed is None else d.seed
    keys = tile_keys(tiles, base.key, tsize, d, sr_method, seed0)
    log(f"  deep zoom: {len(tiles)} tiles in {len(sizes)} levels (x{ratio:.2f} detail per level, tiles {tsize[0]}x{tsize[1]}, "
        f"{sr_method} + {d.method if d.strength > 0 else 'no redraw'} at {d.strength:g})")
    built: list[Built] = []
    for i, t in enumerate(tiles):
        parent = base if t.parent < 0 else built[t.parent]
        key = keys[i]
        png, npz, js = zdir / f"L{t.level}_{key}.png", zdir / f"L{t.level}_{key}.npz", zdir / f"L{t.level}_{key}.json"
        if png.exists() and npz.exists() and js.exists():
            z = np.load(npz)
            built.append(Built(t.level, t.box, _read(png), z["raw"].astype(np.float32), z["depth"].astype(np.float32), key))
            continue
        t0 = time.time()
        log(f"  tile {i + 1}/{len(tiles)}: level {t.level}, box [{', '.join(f'{v:.3f}' for v in t.box)}]")
        rgb, raw, grown, info = make_tile(parent, t, tsize, d, sr_method, seed0 + 101 * t.level, zdir, log)
        _write(rgb, png.with_name("_tmp_" + png.name))
        np.savez(zdir / "_tmp.npz", raw=raw.astype(np.float16), depth=grown.astype(np.float16))
        (zdir / "_tmp.npz").replace(npz)
        png.with_name("_tmp_" + png.name).replace(png)
        js.write_text(json.dumps(info))
        log(f"    done in {time.time() - t0:.0f}s: aligned dx={info['align']['dx']:.2f} dy={info['align']['dy']:.2f} "
            f"px, new detail x{info['detail_gain']:.2f}")
        built.append(Built(t.level, t.box, rgb, raw, grown, key))
    return built


VERSIONS = 1
