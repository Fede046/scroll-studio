"""zoom: deep zoom for frozen moments (`freeze.detail`): a push from the wide shot to a 20x close-up that is sharp at
every scale, with no pops, where every level agrees with the one above it.

One frame has only so many pixels: at a 0.05-wide framing box a 1920 px frame is a thumbnail enlarged 20 times. Instead
of one image, the beat gets a pyramid of tiles, each a crop of its parent that was enlarged, re-drawn at low strength
(so it gains fine detail in the same style) and then forced to agree with the parent: the parent's low frequencies
replace the tile's, so colours, shapes and tone are exactly the parent's and only fine detail is new. The render
samples, for every output pixel, the finest tile that covers it and fades each level in with the screen-space pixel
density (a mip chain turned inside out), so detail arrives as the camera does and nothing swaps.

This file is the geometry (which tiles the camera needs: pure and cheap), the tile builder (each tile its own cached
stage) and the pyramid renderer. See docs/ENGINE.md, "Deep zoom".
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Sequence

import numpy as np

from .freeze import View

VERSION = 1

# A tile's detail is on (alpha 1) while the view is at most FULL of the tile's width and fades out between FULL and GONE
# (view width / tile width). The planner builds a tile wherever the camera is inside the fade, and the renderer uses
# the same two numbers, so a tile is never asked for where the planner did not build one.
FULL = 0.95
GONE = 1.30
DEMAND = 1.15        # views up to this many tile widths ask for a tile (alpha is at least 0.4 there)
VIEW_PAD = 1.12      # a view is this much wider than it looks: the camera sways and the parallax pulls in more
FEATHER = 0.07       # a tile's border fades over this much of its width


def smoothstep(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


def lod_alpha(view_w: float, tile_w: float) -> float:
    """How much of a tile's detail shows when the camera's view is `view_w` wide (both in 0-1 of the frame)."""
    r = view_w / tile_w
    return float(smoothstep((GONE - r) / (GONE - FULL)))


@dataclass(frozen=True)
class Tile:
    """One tile of the pyramid: `box` = [x0, y0, x1, y1] in 0-1 of the frame; it is as many view units tall as wide, so a
    tile has the aspect of the frame. `parent` is an index into the plan (-1: the base frame)."""
    level: int
    box: tuple[float, float, float, float]
    parent: int

    @property
    def size(self) -> float:
        return self.box[2] - self.box[0]

    @property
    def center(self) -> tuple[float, float]:
        return (self.box[0] + self.box[2]) / 2, (self.box[1] + self.box[3]) / 2


def level_sizes(base_px: int, tile_px: int, ratio: float, levels: int) -> list[float]:
    """Nominal tile width (0-1 of the frame) at levels 1..levels: each level has `ratio` times the pixel density of the
    one above (level 0 is the base frame: base_px across)."""
    return [tile_px / (base_px * ratio ** k) for k in range(1, levels + 1)]


def auto_levels(w_min: float, base_px: int, out_px: int, ratio: float, cap: int = 8) -> tuple[int, float]:
    """(levels, ratio) for the tightest view to be native (a tile pixel per output pixel) at the last level: the base is
    native down to a view of out_px / base_px of the frame, so the levels together must add out_px / (w_min * base_px)
    times the density. `ratio` is the most one level may add; it is lowered so the levels share the gain evenly."""
    gain = out_px / (w_min * base_px)
    if gain <= 1.02:
        return 0, ratio
    n = int(min(cap, max(1, math.ceil(math.log(gain) / math.log(ratio) - 1e-9))))
    return n, gain ** (1.0 / n)


def _snap(v: float, step: float = 0.0005) -> float:
    return round(round(v / step) * step, 6)


def views_of(path, n: int) -> list[View]:
    """The camera's views at n moments of the beat (0 to 1)."""
    return [path.at(i / max(1, n - 1)) for i in range(n)]


def plan_tiles(views: Sequence[View], *, base_px: int, out_px: int, tile_px: int, ratio: float = 2.0,
               levels: Optional[int] = None, pad: float = VIEW_PAD, demand: float = DEMAND
               ) -> tuple[list[Tile], list[float], float]:
    """The tiles the camera needs, level by level. A view asks for tiles of every level whose tile is about as wide as
    the view or wider (the finest of them is the one that makes it sharp, the others hold the pyramid together: a tile's
    parent must contain it). For each level the fewest tiles that hold what is asked of them are chosen (greedy set cover
    over the tiles of a lattice, origins every quarter tile): a view that fits in a tile must be wholly inside one, a view
    as wide as the tile's fade-out only mostly. A tile sits inside a parent tile of the level above, and lies on the
    lattice, so a small change to the camera keeps the tiles it did not touch, and they are not rebuilt.
    Returns (tiles, parents before children; the nominal tile width per level; the ratio between levels)."""
    w_min = min((v.w for v in views), default=1.0)
    if levels is None:
        L, ratio = auto_levels(w_min, base_px, out_px, ratio)
    else:
        L = int(levels)
        ratio = max(1.05, min(ratio, (out_px / (w_min * base_px)) ** (1.0 / L))) if L and w_min * base_px < out_px else ratio
    sizes = level_sizes(base_px, tile_px, ratio, L)
    vx = np.array([v.cx for v in views])
    vy = np.array([v.cy for v in views])
    vw = np.array([v.w for v in views])
    # the deepest level a view asks for: the finest whose tile is at most 1/demand of the view wide or wider
    lvl = np.zeros(len(views), int)
    for k, S in enumerate(sizes, start=1):
        if S < 1.0:
            lvl[vw <= demand * S] = k
    tiles: list[Tile] = []
    for k, S in enumerate(sizes, start=1):
        ask = np.nonzero(lvl >= k)[0]
        if S >= 1.0 or not len(ask):
            continue
        parents = [i for i, t in enumerate(tiles) if t.level == k - 1]
        boxes = _candidates(S, vx[ask], vy[ask], tiles, parents)
        if not len(boxes):
            continue
        cov = _coverage(boxes, vx[ask], vy[ask], vw[ask], pad)                       # (candidates, views)
        need = np.interp(vw[ask] / S, [0.8, demand], [0.98, 0.55])
        served = cov >= need[None, :]
        left = np.ones(len(ask), bool)
        chosen: list[int] = []
        while left.any():
            gain = (served & left[None, :]).sum(axis=1)
            j = int(np.argmax(gain))
            if gain[j] == 0:
                break
            chosen.append(j)
            left &= ~served[j]
        for i in np.nonzero(left)[0]:                                               # a view no tile holds enough of: the best it can have
            j = int(np.argmax(cov[:, i]))
            if cov[j, i] > 0.3 and j not in chosen:
                chosen.append(j)
        for j in sorted(set(chosen), key=lambda j: (boxes[j][1], boxes[j][0])):
            box = tuple(float(v) for v in boxes[j])
            p = -1
            if k > 1:
                p = next((i for i in parents if _holds(tiles[i].box, box)), -1)
            tiles.append(Tile(k, box, p))
    return tiles, sizes, ratio                      # a parent always comes before its children


def _candidates(S: float, xs: np.ndarray, ys: np.ndarray, tiles: list[Tile], parents: list[int]) -> np.ndarray:
    """The boxes a tile of width S may take for views centred at (xs, ys): the lattice (origins every S / 4, and the frame's
    far edge) within a tile's width of some view, each inside a parent tile (moved inside the one that holds its centre best
    when it is not). (N, 4), sorted, without duplicates."""
    step = S / 4
    n = int(math.floor((1 - S) / step + 1e-9))
    grid = np.array([i * step for i in range(n + 1)] + ([1 - S] if (1 - S) - n * step > 1e-6 else []))
    gx = np.nonzero((np.abs((grid[:, None] + S / 2) - xs[None, :]) <= S).any(axis=1))[0]
    gy = np.nonzero((np.abs((grid[:, None] + S / 2) - ys[None, :]) <= S).any(axis=1))[0]
    out = set()
    for i in gx:
        for j in gy:
            x0, y0 = _snap(grid[i]), _snap(grid[j])
            box = (x0, y0, round(x0 + S, 6), round(y0 + S, 6))
            if parents:
                host = None
                if not any(_holds(tiles[q].box, box) for q in parents):
                    cx, cy = x0 + S / 2, y0 + S / 2
                    host = max(parents, key=lambda q: min(cx - tiles[q].box[0], tiles[q].box[2] - cx, cy - tiles[q].box[1], tiles[q].box[3] - cy))
                    o = tiles[host].box
                    if S >= o[2] - o[0]:
                        continue
                    x0 = min(max(x0, o[0]), o[2] - S)
                    y0 = min(max(y0, o[1]), o[3] - S)
                    box = (round(x0, 6), round(y0, 6), round(x0 + S, 6), round(y0 + S, 6))
            out.add(box)
    return np.array(sorted(out, key=lambda b: (b[1], b[0])), dtype=float).reshape(-1, 4)


def _coverage(boxes: np.ndarray, vx, vy, vw, pad: float) -> np.ndarray:
    """(candidates, views): the share of each view (with its sway) that each box holds."""
    h = (vw * pad / 2)[None, :]
    ix = np.clip(np.minimum(boxes[:, 2:3], vx[None, :] + h) - np.maximum(boxes[:, 0:1], vx[None, :] - h), 0, None)
    iy = np.clip(np.minimum(boxes[:, 3:4], vy[None, :] + h) - np.maximum(boxes[:, 1:2], vy[None, :] - h), 0, None)
    return ix * iy / (2 * h) ** 2


def _holds(outer, box) -> bool:
    e = 1e-9
    return outer[0] <= box[0] + e and outer[1] <= box[1] + e and outer[2] >= box[2] - e and outer[3] >= box[3] - e


def _covered(box, v: View, pad: float) -> float:
    """The share of the view (with its sway) that the tile's box holds."""
    h = v.w * pad / 2
    ix = max(0.0, min(box[2], v.cx + h) - max(box[0], v.cx - h))
    iy = max(0.0, min(box[3], v.cy + h) - max(box[1], v.cy - h))
    return ix * iy / (2 * h) ** 2


def _serves(t: Tile, v: View, pad: float) -> bool:
    """The tile holds enough of the view: all of it for a view that fits in the tile, less as the view grows towards the
    width where the tile's detail has all but faded (a wide view needs a tile only for the part it covers)."""
    need = float(np.interp(v.w / t.size, [0.8, DEMAND], [0.98, 0.55]))
    return _covered(t.box, v, pad) >= need


# ---------------------------------------------------------------- making a tile agree with its parent

def resample_box(img: np.ndarray, src_box, dst_box, out_size: tuple[int, int], interp: str = "cubic") -> np.ndarray:
    """The part of `img` (a picture covering `src_box`, 0-1 frame units) that lies in `dst_box`, resampled to
    `out_size` (W, H) exactly: the geometry is the boxes', not a rounded crop's."""
    import cv2
    H, W = img.shape[:2]
    ow, oh = out_size
    sx, sy = (src_box[2] - src_box[0]), (src_box[3] - src_box[1])
    xs = (dst_box[0] + (np.arange(ow, dtype=np.float64) + 0.5) / ow * (dst_box[2] - dst_box[0]) - src_box[0]) / sx * W - 0.5
    ys = (dst_box[1] + (np.arange(oh, dtype=np.float64) + 0.5) / oh * (dst_box[3] - dst_box[1]) - src_box[1]) / sy * H - 0.5
    mx, my = np.meshgrid(xs.astype(np.float32), ys.astype(np.float32))
    flag = {"cubic": cv2.INTER_CUBIC, "linear": cv2.INTER_LINEAR, "lanczos": cv2.INTER_LANCZOS4}[interp]
    return cv2.remap(img, mx, my, flag, borderMode=cv2.BORDER_REPLICATE)


def lock_low_frequencies(child: np.ndarray, parent: np.ndarray, sigma: float, ring: float = 8.0) -> np.ndarray:
    """The parent's low frequencies with the child's fine detail: parent_lowpass + (child - child_lowpass), both float.
    Everything coarser than `sigma` pixels is exactly the parent's; only what is finer is the child's. A sharper edge than
    the parent's would overshoot into a pale rim, so the result is held to within `ring` grey levels of the range the
    parent has around each pixel (a window of about `sigma` x 2): detail is free inside the parent's tones, ringing is not."""
    import cv2
    c = child.astype(np.float32)
    p = parent.astype(np.float32)
    out = cv2.GaussianBlur(p, (0, 0), sigma) + c - cv2.GaussianBlur(c, (0, 0), sigma)
    if ring is not None:
        r = max(2, int(round(sigma * 1.5)))
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))
        out = np.clip(out, cv2.erode(p, k) - ring, cv2.dilate(p, k) + ring)
    return out


def align(child: np.ndarray, ref: np.ndarray, max_shift: float = 0.04, work: int = 640) -> tuple[np.ndarray, dict]:
    """Register `child` to `ref` (same size, uint8/float RGB): an affine fit by enhanced correlation (ECC) on a blurred,
    reduced copy, applied to the full-size child. The re-drawn tile may sit a pixel or two off its parent (a diffusion
    pass nudges shapes): the correlation finds that shift and the slight scale that comes with it. Returns the warped
    child and what was found; an implausible fit (more than `max_shift` of the width, or 4% of scale) is not applied."""
    import cv2
    H, W = ref.shape[:2]
    k = min(1.0, work / W)
    def prep(a):
        g = cv2.cvtColor(a.astype(np.float32) / 255.0, cv2.COLOR_RGB2GRAY)
        g = cv2.resize(g, (max(8, int(W * k)), max(8, int(H * k))), interpolation=cv2.INTER_AREA)
        return cv2.GaussianBlur(g, (0, 0), 1.2)
    a, b = prep(ref), prep(child)
    warp = np.eye(2, 3, dtype=np.float32)
    info = {"applied": False, "dx": 0.0, "dy": 0.0, "scale": 1.0}
    try:
        _, warp = cv2.findTransformECC(a, b, warp, cv2.MOTION_AFFINE, (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 80, 1e-6), None, 5)
    except cv2.error:
        return child, info
    warp = warp.astype(np.float64)
    warp[:, 2] /= k                                          # translation back to full-size pixels
    scale = math.sqrt(abs(np.linalg.det(warp[:, :2])))
    dx, dy = warp[0, 2] + (warp[0, 0] - 1) * W / 2 + warp[0, 1] * H / 2, warp[1, 2] + warp[1, 0] * W / 2 + (warp[1, 1] - 1) * H / 2
    info.update(dx=float(dx), dy=float(dy), scale=float(scale))
    if max(abs(dx), abs(dy)) > max_shift * W or abs(scale - 1) > 0.04:
        return child, info
    out = cv2.warpAffine(child, warp.astype(np.float32), (W, H), flags=cv2.INTER_CUBIC | cv2.WARP_INVERSE_MAP,
                         borderMode=cv2.BORDER_REPLICATE)
    info["applied"] = True
    return out, info


def refine_depth(parent_up: np.ndarray, rgb: np.ndarray, grow: int = 0) -> tuple[np.ndarray, np.ndarray]:
    """A tile's depth from its parent's, enlarged to the tile (float 0-1, `parent_up`): snapped to the edges of the
    tile's own picture with the guided filter (so a boot's outline moves the depth edge, however fine), then the
    near side grown `grow` pixels. Returns (raw, grown); the raw one is what the next level starts from."""
    import cv2
    from .freeze import guided_filter
    H, W = rgb.shape[:2]
    g = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY).astype(np.float32) / 255
    raw = np.clip(guided_filter(g, np.clip(parent_up.astype(np.float32), 0, 1), max(3, W // 250), 2e-3), 0, 1)
    if grow <= 0:
        return raw, raw
    d8 = cv2.dilate((raw * 255).astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * grow + 1, 2 * grow + 1)))
    return raw, cv2.GaussianBlur(d8, (0, 0), max(0.8, grow * 0.8)).astype(np.float32) / 255


@dataclass
class TileImage:
    """A built tile: its picture (uint8 H x W x 3), its depth for the render (float 0-1, grown) and where it sits. With
    layered depth it also carries, at its own resolution, the alpha of every subject plane (P, H, W uint8), the
    background plane's picture (the plate where subjects stood), and the plane depths (P, H, W) and background depth."""
    level: int
    box: tuple
    rgb: np.ndarray
    depth: np.ndarray
    alpha: Optional[np.ndarray] = None
    bg: Optional[np.ndarray] = None
    pdepth: Optional[np.ndarray] = None
    bgdepth: Optional[np.ndarray] = None

    @property
    def size(self) -> float:
        return self.box[2] - self.box[0]


def raw_depth(depth: np.ndarray, rgb: np.ndarray, size: tuple[int, int]) -> np.ndarray:
    """A depth map (0 far .. 1 near, any size) at `size`, snapped to the edges of `rgb` with the guided filter like
    freeze.prepare_depth but not grown: deep zoom starts every tile's depth from this, so a depth edge stays on the
    thing's outline however far the camera is in."""
    import cv2
    from .freeze import guided_filter
    W, H = size
    d = cv2.resize(depth.astype(np.float32), (W, H), interpolation=cv2.INTER_CUBIC)
    g = cv2.cvtColor(cv2.resize(rgb, (W, H), interpolation=cv2.INTER_AREA), cv2.COLOR_RGB2GRAY).astype(np.float32) / 255
    return np.clip(guided_filter(g, np.clip(d, 0, 1), max(3, W // 240), 2e-3), 0, 1).astype(np.float32)


def despeckle(img: np.ndarray, radius: int = 4, contrast: float = 22.0, max_area: int = 60) -> tuple[np.ndarray, int]:
    """Remove the specks a redraw leaves: small, compact bright dots on a dark ground and dark dots on a light one (the
    sampler's stray pixels, which at 20x are the first thing the eye finds). A speck is a part of the picture smaller
    than `radius` pixels that stands out from its surroundings by `contrast` levels (white or black top-hat), is
    compact (a stitch or a hair is thin and long, and is kept), and is at most `max_area` pixels; it is replaced by
    what surrounds it. Returns (picture, specks removed)."""
    import cv2
    g = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * radius + 1, 2 * radius + 1))
    hot = (cv2.morphologyEx(g, cv2.MORPH_TOPHAT, k) > contrast).astype(np.uint8)
    cold = (cv2.morphologyEx(g, cv2.MORPH_BLACKHAT, k) > contrast).astype(np.uint8)
    mask = np.zeros(g.shape, np.uint8)
    n = 0
    for m in (hot, cold):
        cnt, lab, st, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
        for i in range(1, cnt):
            x, y, w, h, area = st[i]
            if area <= max_area and max(w, h) <= 2 * radius + 1 and max(w, h) <= 2.2 * min(w, h):
                mask[lab == i] = 255
                n += 1
    if not n:
        return img, 0
    mask = cv2.dilate(mask, np.ones((3, 3), np.uint8))
    return cv2.inpaint(img, mask, 3, cv2.INPAINT_TELEA), n
