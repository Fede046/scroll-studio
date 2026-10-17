"""The deep-zoom render (engine/zoom.py): freeze.Renderer over a pyramid of tiles.

Per frame the camera's view is a width `w` of the frame. The depth the camera marches through is composed for that view
(the base depth refined by every tile that is on), then the colour is sampled from the base and from each level's tiles,
coarse to fine. A level is on in proportion to `lod_alpha` (the view's width against the tile's, so detail fades in as
the camera arrives and out as it leaves), a tile fades out at its own border (`FEATHER`), and tiles of one level that
overlap are blended by those weights. Because every tile carries its parent's low frequencies exactly, fading a level in
adds fine detail only: nothing moves and nothing changes colour.
"""
from __future__ import annotations

import math
from typing import Optional, Sequence

import numpy as np

from .zoom import FEATHER, VIEW_PAD, TileImage, lod_alpha


def _renderer_class():
    from .freeze import Renderer

    class PyramidRenderer(Renderer):
        DEPTH_MARGIN = 1.7          # the view's depth texture is this much wider than the view (the parallax looks outside it)

        def __init__(self, rgb, depth, size, tiles: Sequence[TileImage], device=None):
            super().__init__(rgb, depth, size, device)
            torch = self.torch
            self.tiles = []
            for t in sorted(tiles, key=lambda t: t.level):
                x = torch.from_numpy(np.ascontiguousarray(t.rgb)).to(self.dev).permute(2, 0, 1)[None].float()
                mips = [x]
                while mips[-1].shape[-1] > self.W // 2 and len(mips) < 4:
                    mips.append(torch.nn.functional.avg_pool2d(mips[-1], 2))
                d = torch.from_numpy(np.ascontiguousarray(t.depth, dtype=np.float32)).to(self.dev)[None, None]
                self.tiles.append((t, mips, d))

        # -- which tiles count in this view
        def _active(self, cx, cy, w):
            out = []
            half = w * VIEW_PAD * 0.6
            for t, mips, d in self.tiles:
                a = lod_alpha(w, t.size)
                if a <= 1e-3:
                    continue
                if cx + half < t.box[0] or cx - half > t.box[2] or cy + half < t.box[1] or cy - half > t.box[3]:
                    continue
                out.append((t, mips, d, a))
            return out

        def _weight(self, t, u):
            """(local grid (1, h, w, 2) in -1..1, feather weight (h, w)) of tile `t` at base positions `u` (h, w, 2)."""
            torch = self.torch
            uv = (u - torch.tensor([t.box[0], t.box[1]], device=self.dev)) / t.size
            e = (torch.minimum(uv, 1 - uv).amin(dim=-1) / FEATHER).clamp(0, 1)
            return (uv.clamp(0, 1) * 2 - 1)[None], e * e * (3 - 2 * e)

        def _compose(self, u, sample, base, active):
            """Coarse to fine: `base`, then for each level the weight-averaged tiles, laid over it by coverage x alpha."""
            out = base
            i = 0
            while i < len(active):
                lvl = active[i][0].level
                num = den = None
                while i < len(active) and active[i][0].level == lvl:
                    t, mips, d, a = active[i]
                    grid, wt = self._weight(t, u)
                    wt = wt * a
                    val = sample(t, mips, d, grid)
                    num = val * wt if num is None else num + val * wt
                    den = wt if den is None else den + wt
                    i += 1
                cov = den.clamp(max=1.0)
                out = out * (1 - cov) + (num / den.clamp(min=1e-6)) * cov
            return out

        # -- the depth of this view
        def _local_depth(self, c, w, active):
            torch = self.torch
            F = torch.nn.functional
            m = self.DEPTH_MARGIN
            hd, wd = max(8, int(self.H / 2 * m)), max(8, int(self.W / 2 * m))
            o = self._grid_of(wd, hd)                                   # -0.5 .. 0.5
            u = (c + w * m * o).clamp(0, 1)
            base = F.grid_sample(self.depth, self._grid(u), mode="bilinear", padding_mode="border", align_corners=False)[0, 0]

            def sample(t, mips, d, grid):
                return F.grid_sample(d, grid, mode="bilinear", padding_mode="border", align_corners=False)[0, 0]

            self._d0 = c - w * m / 2
            self._dsz = w * m
            self._dtex = self._compose(u, sample, base, active)[None, None]

        def _march(self, c, s, w, e, f):
            """freeze.Renderer._march against this view's depth texture (finer than the base depth wherever a tile is on)."""
            torch = self.torch
            F = torch.nn.functional
            o = self.o_solve
            n = self.STEPS
            hit = star = prev_gap = prev_d = None
            for k in range(n + 1):
                d = 1.0 - k / n
                u = self._source_at(c, s, w, e, f, d, o).clamp(0, 1)
                ul = ((u - self._d0) / self._dsz).clamp(0, 1)
                gap = F.grid_sample(self._dtex, self._grid(ul), mode="bilinear", padding_mode="border", align_corners=False)[0, 0] - d
                if k == 0:
                    hit = gap >= 0
                    star = torch.where(hit, torch.ones_like(gap), torch.zeros_like(gap))
                else:
                    new = (~hit) & (gap >= 0)
                    frac = (-prev_gap) / (gap - prev_gap).clamp(min=1e-6)
                    star = torch.where(new, prev_d + (d - prev_d) * frac, star)
                    hit = hit | new
                prev_gap, prev_d = gap, d
            return star

        # -- the colour
        def _sample_mips(self, mips, grid, texels_per_px):
            F = self.torch.nn.functional
            lod = min(max(math.log2(max(texels_per_px, 1e-6)), 0.0), len(mips) - 1)
            lo, fr = int(lod), lod - int(lod)
            out = F.grid_sample(mips[lo], grid, mode="bicubic", padding_mode="border", align_corners=False)
            if fr > 0.02 and lo + 1 < len(mips):
                out = out * (1 - fr) + F.grid_sample(mips[lo + 1], grid, mode="bicubic", padding_mode="border",
                                                     align_corners=False) * fr
            return out[0]

        def frame(self, cx: float, cy: float, w: float, sx: float, sy: float, e: float, f: float):
            torch = self.torch
            F = torch.nn.functional
            c = torch.tensor([cx, cy], device=self.dev)
            active = self._active(cx, cy, w)
            if sx or sy or e:
                s = torch.tensor([sx, sy], device=self.dev)
                self._local_depth(c, w, active)
                star = self._march(c, s, w, e, f)[None, None]
                star = F.interpolate(star, size=(self.H, self.W), mode="bilinear", align_corners=False)[0, 0]
                u = self._source_at(c, s, w, e, f, star, self.o)
            else:
                u = c + w * self.o
            u = u.clamp(0, 1)
            base = self._sample_mips(self.levels, self._grid(u), max(w * self.src_w / self.W, 1e-6))

            def sample(t, mips, d, grid):
                return self._sample_mips(mips, grid, t.rgb.shape[1] * w / (t.size * self.W))

            return self._compose(u, sample, base, active)

    return PyramidRenderer


def render_frames(rgb: np.ndarray, depth: np.ndarray, tiles: Sequence[TileImage], camera, *, size: tuple[int, int],
                  seconds: float, first_frame: int = 0, parallax: float = 0.6, dolly: Optional[float] = None,
                  ease: str = "inOutSine", blur: float = 0.0, grain: float = 0.0, seed: int = 7, fps: int = 24,
                  device: Optional[str] = None):
    """freeze.render_frames over a pyramid of tiles: the same camera, parallax, blur and grain, but every pixel is taken
    from the finest tile that covers it. `rgb`, `depth`: the base level (what freeze.render_frames takes)."""
    from .freeze import CameraPath, Timeline
    n = max(2, int(round(seconds * fps)))
    path = CameraPath(camera, ease)
    small = depth
    if depth.shape[1] > 480:
        import cv2
        small = cv2.resize(depth, (480, max(1, round(480 * depth.shape[0] / depth.shape[1]))), interpolation=cv2.INTER_AREA)
    tl = Timeline(path, seconds, small, parallax, dolly, fps)
    r = _renderer_class()(rgb, depth, size, tiles, device)
    subs = 5 if blur > 0 else 1
    for i in range(first_frame, n):
        acc = None
        for j in range(subs):
            off = (j / (subs - 1) - 0.5) * blur if subs > 1 else 0.0
            fr = r.frame(**tl.at((i + off) / (n - 1)))
            acc = fr if acc is None else acc + fr
        fr = acc / subs
        if grain > 0:
            fr = r.grain(fr, grain, seed * 100003 + i)
        yield r.to_u8(fr)
