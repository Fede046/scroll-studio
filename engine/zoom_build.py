"""Building the deep-zoom pyramid of a frozen beat (`freeze.detail`): one cached stage per tile.

For every tile of the plan (engine/zoom.py), a level at a time, parents first:

  parent_up   the parent's picture over the tile's box, resampled to the tile's size (exact geometry, bicubic)
  enlarge     a crop of the parent enlarged to the tile's size: SeedVR2 (or Lanczos when it is not installed)
  redraw      Z-Image Turbo img2img at low strength: fine detail in the picture's own style. Both passes of every tile of
              a level run in one ComfyUI job (the models load once, and the job is not interleaved with other people's)
  despeckle   the stray bright and dark dots a redraw leaves
  align       ECC registration of the redrawn tile to parent_up (a redraw may nudge shapes a pixel or two)
  lock        parent_up's low frequencies + the tile's fine detail: colours and shapes are exactly the parent's
  depth       the parent's depth over the tile, snapped to the tile's own edges (guided filter), the near side grown
  planes      with `layers`: the alpha of each plane refined at the tile's resolution, the plate continued, plane depths

Each tile is cached by what made it (its box, its parent's key, the detail settings), under .build/<section>/beats/<id>/
zoom/, so changing the deepest box redoes only the tiles that moved and never repeats the others.
"""
from __future__ import annotations

import hashlib
import json
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import numpy as np

from . import zoom
from .freeze import FPS, CameraPath
from .zoom import Tile, TileImage

GENERIC_PROMPT = ("the same style, lighting, line work and colours as the picture, extremely fine detail, crisp, sharp, "
                  "clean edges, nothing added that is not already there")
VERSIONS = 3


@dataclass
class Level0:
    """The base level the pyramid starts from: the (upscaled) frame, its raw depth (edge-snapped, not grown) at the
    beat's size, and a key naming what made them. `layers`: the frame's planes (layers.LayerSet) when it is layered."""
    rgb: np.ndarray
    depth_raw: np.ndarray
    key: str
    layers: object = None

    box = (0.0, 0.0, 1.0, 1.0)

    def planes(self):
        """(alpha (P,H,W) float, hole (H,W) float, background picture uint8): what a layered tile starts from."""
        from . import layers as L
        if not hasattr(self, "_bg"):
            self._bg = L.base_background(self.rgb, self.layers)
        return self.layers.alpha, self.layers.hole, self._bg


@dataclass
class Built:
    """A tile as built: what the next level starts from (picture, raw depth, box) and what the render uses. A layered tile
    also has its planes: alphas (P,H,W) u8, hole (H,W) u8, background picture, and the plane depths."""
    level: int
    box: tuple
    rgb: np.ndarray
    depth_raw: np.ndarray
    depth: np.ndarray
    key: str
    alpha: Optional[np.ndarray] = None
    hole: Optional[np.ndarray] = None
    bg: Optional[np.ndarray] = None
    pdepth: Optional[np.ndarray] = None
    bgdepth: Optional[np.ndarray] = None

    def planes(self):
        return self.alpha.astype(np.float32) / 255, self.hole.astype(np.float32) / 255, self.bg

    def image(self) -> TileImage:
        return TileImage(self.level, self.box, self.rgb, self.depth, self.alpha, self.bg, self.pdepth, self.bgdepth)


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


def tile_keys(tiles: list[Tile], base_key: str, tsize: tuple[int, int], d, sr_method: str, seed0: int) -> list[str]:
    """The cache key of every tile (a tile's key includes its parent's, so a changed parent redoes its children and
    nothing else). Cheap: no picture is looked at."""
    keys: list[str] = []
    spec = d.model_dump(mode="json", exclude={"levels", "ratio", "tile"})
    for t in tiles:
        pkey = base_key if t.parent < 0 else keys[t.parent]
        keys.append(digest("tile", zoom.VERSION, VERSIONS, t.level, [round(v, 5) for v in t.box], pkey, tsize, spec, sr_method, seed0))
    return keys


def prompt_of(d) -> str:
    return (d.prompt.strip().rstrip(".") + ". " if d.prompt.strip() else "") + GENERIC_PROMPT


def _read(p: Path) -> np.ndarray:
    from PIL import Image
    return np.asarray(Image.open(p).convert("RGB"))


def _write(a: np.ndarray, p: Path) -> None:
    from PIL import Image
    Image.fromarray(a).save(p)


@dataclass
class Prep:
    """A tile about to be made: the crop of its parent (whole parent pixels, a little wider than the box), the box of that
    crop, the tile's parent picture over its box, and the size the crop is enlarged to."""
    index: int
    tile: Tile
    parent: object
    crop: np.ndarray
    rect: tuple
    parent_up: np.ndarray
    short: int
    size16: tuple[int, int]


def prepare(index: int, parent, tile: Tile, tsize: tuple[int, int]) -> Prep:
    ph, pw = parent.rgb.shape[:2]
    pb = parent.box
    ps = pb[2] - pb[0]
    x0, x1 = (tile.box[0] - pb[0]) / ps * pw, (tile.box[2] - pb[0]) / ps * pw
    y0, y1 = (tile.box[1] - pb[1]) / ps * ph, (tile.box[3] - pb[1]) / ps * ph
    ix0, ix1 = max(0, int(math.floor(x0)) - 2), min(pw, int(math.ceil(x1)) + 2)
    iy0, iy1 = max(0, int(math.floor(y0)) - 2), min(ph, int(math.ceil(y1)) + 2)
    rect = (pb[0] + ix0 / pw * ps, pb[1] + iy0 / ph * ps, pb[0] + ix1 / pw * ps, pb[1] + iy1 / ph * ps)
    f = tsize[1] / max(1e-6, (y1 - y0))                              # tile pixels per parent pixel
    cw, ch = ix1 - ix0, iy1 - iy0
    r16 = lambda v: max(16, int(round(v / 16)) * 16)
    return Prep(index, tile, parent, parent.rgb[iy0:iy1, ix0:ix1], rect, zoom.resample_box(parent.rgb, pb, tile.box, tsize, "cubic"),
                int(round(min(cw, ch) * f)), (r16(cw * f), r16(ch * f)))


def enhance(preps: list[Prep], d, sr_method: str, seed: int, work: Path, log: Callable) -> list[np.ndarray]:
    """Each tile's crop enlarged and re-drawn (uint8, at its `size16`), the whole level in one ComfyUI job."""
    import cv2
    from .backends import detail
    use_sr = sr_method == "seedvr2"
    strength = d.strength if d.method == "zimage" else 0.0
    if not use_sr and strength <= 0 and d.method != "qwen":
        return [cv2.resize(p.crop, p.size16, interpolation=cv2.INTER_LANCZOS4) for p in preps]
    crops = []
    for p in preps:
        path = work / f"_crop_{p.index}.png"
        _write(p.crop, path)
        crops.append(path)
    outs = detail.enhance_batch(crops, [p.short for p in preps], [p.size16 for p in preps], prompt_of(d), seed, strength,
                                use_sr, work, log)
    imgs = [_read(o) for o in outs]
    for p in crops + outs:
        p.unlink(missing_ok=True)
    if d.method == "qwen":                                             # one editor pass per tile (experimental)
        for i, p in enumerate(preps):
            src, dst = work / "_q_in.png", work / "_q_out.png"
            _write(imgs[i], src)
            detail.qwen_detail(src, dst, "Add fine detail to this picture in exactly the same style: " + prompt_of(d) +
                               " Keep every shape, outline, position, tone and colour exactly where it is.", seed + i, log=log)
            imgs[i] = _read(dst)
            src.unlink(missing_ok=True)
            dst.unlink(missing_ok=True)
    return imgs


def finish(p: Prep, drawn: np.ndarray, d, tsize: tuple[int, int]) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict]:
    """The tile from its enlarged and re-drawn crop: (picture uint8, raw depth, depth for the render, info)."""
    import cv2
    tw, th = tsize
    parent, tile = p.parent, p.tile
    big = zoom.resample_box(drawn, p.rect, tile.box, tsize, "cubic")
    specks = 0
    if d.strength > 0:
        big, specks = zoom.despeckle(big, contrast=18.0)
    aligned, ainfo = zoom.align(big, p.parent_up)
    s = (tw / (tile.box[2] - tile.box[0])) / (parent.rgb.shape[1] / (parent.box[2] - parent.box[0]))      # tile px per parent px
    sigma = max(0.8, d.lock * s)
    out = np.clip(zoom.lock_low_frequencies(aligned, p.parent_up, sigma) + 0.5, 0, 255).astype(np.uint8)
    pd = zoom.resample_box(parent.depth_raw.astype(np.float32), parent.box, tile.box, tsize, "linear")
    raw, grown = zoom.refine_depth(pd, out, grow=max(1, tw // 800))
    hf = lambda a: float(np.std(a.astype(np.float32) - cv2.GaussianBlur(a.astype(np.float32), (0, 0), sigma)))
    info = {"align": ainfo, "sigma": sigma, "scale": s, "specks": specks, "detail_gain": hf(out) / max(hf(p.parent_up), 1e-3)}
    return out, raw, grown, info


def layer_planes(parent, tile: Tile, rgb: np.ndarray, raw: np.ndarray, tsize: tuple[int, int]):
    """A layered tile's planes from its parent's: refined alphas, hole, background picture, plane depths."""
    from . import layers as L
    pa, ph, pb = parent.planes()
    rs = lambda img, sb, db: zoom.resample_box(np.ascontiguousarray(img), sb, db, tsize, "linear")
    alpha, hole, bg = L.tile_layers(pa, ph, pb, rgb, parent.box, tile.box, rs)
    ppd = parent.layers.depth if hasattr(parent, "layers") else parent.pdepth                   # (P, h, w) float
    pd, bd = L.tile_plane_depths(raw, hole, np.stack([zoom.resample_box(np.ascontiguousarray(x, dtype=np.float32), parent.box, tile.box, tsize, "linear") for x in ppd]))
    return alpha, hole, bg, pd, bd


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
    built: list[Optional[Built]] = [None] * len(tiles)
    layered = base.layers is not None
    for level in range(1, len(sizes) + 1):
        todo: list[Prep] = []
        for i, t in enumerate(tiles):
            if t.level != level:
                continue
            key = keys[i]
            png, npz, js = zdir / f"L{level}_{key}.png", zdir / f"L{level}_{key}.npz", zdir / f"L{level}_{key}.json"
            bgp = png.with_name(png.stem + ".bg.png")
            if png.exists() and npz.exists() and js.exists() and (not layered or bgp.exists()):
                z = np.load(npz)
                b = Built(level, t.box, _read(png), z["raw"].astype(np.float32), z["depth"].astype(np.float32), key)
                if layered:
                    b.alpha, b.hole, b.bg = z["alpha"], z["hole"], _read(bgp)
                    b.pdepth, b.bgdepth = z["pdepth"].astype(np.float32), z["bgdepth"].astype(np.float32)
                built[i] = b
            else:
                todo.append(prepare(i, base if t.parent < 0 else built[t.parent], t, tsize))
        if not todo:
            continue
        t0 = time.time()
        log(f"  level {level}: {len(todo)} tile(s) to make (of {sum(1 for t in tiles if t.level == level)})")
        drawn = enhance(todo, d, sr_method, seed0 + 101 * level, zdir, log)
        log(f"    enlarged and re-drawn in {time.time() - t0:.0f}s")
        for p, img in zip(todo, drawn):
            i, t, key = p.index, p.tile, keys[p.index]
            rgb, raw, grown, info = finish(p, img, d, tsize)
            png, npz, js = zdir / f"L{level}_{key}.png", zdir / f"L{level}_{key}.npz", zdir / f"L{level}_{key}.json"
            b = Built(level, t.box, rgb, raw, grown, key)
            extra: dict = {}
            if layered:
                alpha, hole, bg, pd, bd = layer_planes(p.parent, t, rgb, raw, tsize)
                b.alpha, b.hole, b.bg, b.pdepth, b.bgdepth = alpha, hole, bg, pd, bd
                extra = {"alpha": alpha, "hole": hole, "pdepth": pd.astype(np.float16), "bgdepth": bd.astype(np.float16)}
                _write(bg, png.with_name(png.stem + ".bg.png"))
            tmp = png.with_name("_tmp_" + png.name)
            _write(rgb, tmp)
            np.savez(zdir / "_tmp.npz", raw=raw.astype(np.float16), depth=grown.astype(np.float16), **extra)
            (zdir / "_tmp.npz").replace(npz)
            tmp.replace(png)
            js.write_text(json.dumps(info))
            built[i] = b
            log(f"    tile {i + 1}/{len(tiles)} [{', '.join(f'{v:.3f}' for v in t.box)}]: aligned dx={info['align']['dx']:.2f} "
                f"dy={info['align']['dy']:.2f} px, {info['specks']} specks, new detail x{info['detail_gain']:.2f}")
    return built    # type: ignore[return-value]
