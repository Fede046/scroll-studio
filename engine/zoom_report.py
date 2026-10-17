"""Measuring a frozen beat's polish (`studio freeze <project> <beat> --report`): is it sharp at every scale, and does it
ever pop? Judged on the rendered clip, by numbers and by pictures, so a deep zoom is checked and not just looked at.

  sharpness table   for each zoom the camera reaches (1x, 2x, 4x ...), the frame where it first gets there: how many output
                    pixels its sharpest edges take (the 10-90% width of the strongest edges; 1-2 px is a crisp edge at the
                    screen's own resolution, 6 px is a picture enlarged six times) and its fine-detail energy
  difference plot   the mean change between consecutive frames, the whole clip; a spike is a pop (a level or a tile
                    swapping in, a depth edge snapping), a smooth hill is the camera moving. `spike` is the worst frame
                    against the median of its neighbours (1.0 = none stands out)
  frame strip       frames across the push, and the crops at the camera's keys
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Optional, Sequence

import numpy as np


def read_clip(clip: Path, size: Optional[tuple[int, int]] = None) -> np.ndarray:
    """All frames of a clip as (N, H, W, 3) uint8 (decoded by ffmpeg)."""
    import subprocess
    from .config import settings
    from .project import probe
    info = probe(clip)
    w, h = int(info["width"]), int(info["height"])
    vf = ["-vf", f"scale={size[0]}:{size[1]}"] if size and size != (w, h) else []
    if vf:
        w, h = size
    r = subprocess.run([settings()["ffmpeg"], "-hide_banner", "-loglevel", "error", "-i", str(clip), *vf, "-f", "rawvideo",
                        "-pix_fmt", "rgb24", "-"], capture_output=True, check=True)
    n = len(r.stdout) // (w * h * 3)
    return np.frombuffer(r.stdout, np.uint8, n * w * h * 3).reshape(n, h, w, 3)


def edge_width(rgb: np.ndarray, top: float = 0.01) -> float:
    """The median width, in pixels, of the strongest edges of a frame: along each axis, the places where the gradient is
    strongest (the top `top` share, local maxima only) and, for each, the contrast across it divided by the peak gradient
    (a step blurred over n pixels reads n). Narrow = sharp at the screen's resolution; wide = enlarged."""
    import cv2
    g = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY).astype(np.float32)
    widths = []
    for axis in (1, 0):
        a = g if axis == 1 else g.T
        d = np.abs(np.diff(a, axis=1))                              # gradient along the rows
        if d.max() < 1e-3:
            continue
        thr = np.quantile(d, 1 - top)
        peak = (d >= thr) & (d >= np.roll(d, 1, axis=1)) & (d >= np.roll(d, -1, axis=1))
        ys, xs = np.nonzero(peak)
        for y, x in zip(ys[:20000], xs[:20000]):
            lo, hi = max(0, x - 8), min(a.shape[1], x + 10)
            seg = a[y, lo:hi]
            contrast = float(seg.max() - seg.min())
            if contrast > 25:
                widths.append(contrast / max(d[y, x], 1e-3))
    return float(np.median(widths)) if widths else float("nan")


def fine_detail(rgb: np.ndarray) -> float:
    """Fine-detail energy: the mean absolute difference between the frame and a 2-pixel blur of it (grey levels)."""
    import cv2
    g = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY).astype(np.float32)
    return float(np.abs(g - cv2.GaussianBlur(g, (0, 0), 2.0)).mean())


def view_widths(camera, ease: str, n: int) -> np.ndarray:
    """The camera's view width (0-1 of the frame) at each of n frames of the beat."""
    from .freeze import CameraPath
    p = CameraPath(camera, ease)
    return np.array([p.at(i / max(1, n - 1)).w for i in range(n)])


def sharpness_table(frames: np.ndarray, widths: np.ndarray, zooms: Sequence[float] = (1, 2, 4, 8, 12, 16, 20)) -> list[dict]:
    """For each zoom factor (1 / view width) the camera reaches, the first frame on its way there: edge width and fine
    detail of that frame (None for a zoom the camera never reaches)."""
    rows = []
    for z in zooms:
        hit = np.nonzero(1.0 / widths >= z * 0.97)[0]
        if not len(hit):
            rows.append({"zoom": z, "frame": None})
            continue
        i = int(hit[0])
        rows.append({"zoom": z, "frame": i, "view": float(widths[i]), "edge_px": edge_width(frames[i]),
                     "detail": fine_detail(frames[i])})
    return rows


def frame_differences(frames: np.ndarray) -> np.ndarray:
    """Mean absolute change (grey levels) between each frame and the next."""
    f = frames.astype(np.int16)
    return np.abs(f[1:] - f[:-1]).mean(axis=(1, 2, 3))


def spike_ratio(d: np.ndarray, k: int = 3) -> float:
    """The worst frame-to-frame change against the median of its neighbours (1 = no frame stands out)."""
    worst = 1.0
    for i in range(len(d)):
        nb = np.concatenate([d[max(0, i - k):i], d[i + 1:i + 1 + k]])
        if len(nb) and np.median(nb) > 0.3:
            worst = max(worst, float(d[i] / np.median(nb)))
    return worst


def plot_series(series: dict[str, np.ndarray], out: Path, title: str, ylabel: str, size=(1500, 520), log_y: bool = False) -> None:
    """A line plot (no plotting library: drawn with PIL) of named series over the same frames."""
    from PIL import Image, ImageDraw
    W, H = size
    L, R, T, B = 70, 20, 40, 50
    im = Image.new("RGB", size, (255, 255, 255))
    d = ImageDraw.Draw(im)
    allv = np.concatenate([np.asarray(v, float) for v in series.values()])
    allv = allv[np.isfinite(allv)]
    hi = float(allv.max()) * 1.08 if len(allv) else 1.0
    lo = 0.0
    n = max(len(v) for v in series.values())
    colours = [(200, 40, 40), (30, 110, 200), (40, 150, 70), (170, 90, 200)]
    for g in range(5):
        y = T + (H - T - B) * g / 4
        d.line((L, y, W - R, y), fill=(225, 225, 225))
        d.text((8, y - 6), f"{hi - (hi - lo) * g / 4:.2f}", fill=(80, 80, 80))
    for i, (name, v) in enumerate(series.items()):
        v = np.asarray(v, float)
        pts = [(L + (W - L - R) * j / max(1, n - 1), T + (H - T - B) * (1 - (x - lo) / max(hi - lo, 1e-9))) for j, x in enumerate(v)
               if np.isfinite(x)]
        if len(pts) > 1:
            d.line(pts, fill=colours[i % 4], width=2)
        d.rectangle((L + 10 + 260 * i, 12, L + 24 + 260 * i, 26), fill=colours[i % 4])
        d.text((L + 30 + 260 * i, 12), name, fill=(0, 0, 0))
    d.text((L, H - 22), f"{title}   (x: frame, 0-{n})   y: {ylabel}", fill=(60, 60, 60))
    im.save(out)


def contact_strip(frames: np.ndarray, idx: Sequence[int], out: Path, labels: Optional[Sequence[str]] = None, cols: int = 4,
                  width: int = 640) -> None:
    from PIL import Image, ImageDraw
    h, w = frames.shape[1:3]
    th = round(width * h / w)
    rows = math.ceil(len(idx) / cols)
    sheet = Image.new("RGB", (cols * width, rows * th), (20, 20, 20))
    for k, i in enumerate(idx):
        im = Image.fromarray(frames[i]).resize((width, th), Image.LANCZOS)
        d = ImageDraw.Draw(im)
        label = labels[k] if labels else f"frame {i}"
        d.rectangle((0, 0, 8 * len(label) + 10, 16), fill=(0, 0, 0))
        d.text((5, 2), label, fill=(255, 255, 0))
        sheet.paste(im, ((k % cols) * width, (k // cols) * th))
    sheet.save(out)


def side_by_side(clips: dict[str, np.ndarray], at: Sequence[int], out: Path, crop: Optional[tuple[float, float, float, float]] = None,
                 width: int = 760) -> None:
    """The same frame numbers of several clips side by side (rows: moments, columns: clips), optionally cropped to a box
    (0-1 of the frame) and enlarged without smoothing so softness shows."""
    from PIL import Image, ImageDraw
    names = list(clips)
    first = clips[names[0]]
    h, w = first.shape[1:3]
    x0, y0, x1, y1 = crop or (0, 0, 1, 1)
    cw, ch = int((x1 - x0) * w), int((y1 - y0) * h)
    th = round(width * ch / cw)
    sheet = Image.new("RGB", (len(names) * width, len(at) * th), (20, 20, 20))
    for r, i in enumerate(at):
        for c, name in enumerate(names):
            fr = clips[name][min(i, len(clips[name]) - 1)]
            im = Image.fromarray(fr[int(y0 * h):int(y0 * h) + ch, int(x0 * w):int(x0 * w) + cw]).resize((width, th), Image.LANCZOS)
            d = ImageDraw.Draw(im)
            label = f"{name}  frame {i}"
            d.rectangle((0, 0, 8 * len(label) + 10, 16), fill=(0, 0, 0))
            d.text((5, 2), label, fill=(255, 255, 0))
            sheet.paste(im, (c * width, r * th))
    sheet.save(out)


def report(clip: Path, camera, ease: str, out_dir: Path, name: str = "after", others: Optional[dict[str, Path]] = None,
           log=print) -> dict:
    """Everything above for one rendered clip (and, in the plot and the side-by-sides, others to compare it with). Returns
    the numbers (also written to report.json)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    clips = {name: read_clip(clip)}
    for k, p in (others or {}).items():
        clips[k] = read_clip(p)
    frames = clips[name]
    n = len(frames)
    widths = view_widths(camera, ease, n)
    result = {"clip": str(clip), "frames": n}
    result["sharpness"] = sharpness_table(frames, widths)
    for k, v in clips.items():
        if k != name:
            result.setdefault("others", {})[k] = sharpness_table(v, view_widths(camera, ease, len(v)))
    diffs = {k: frame_differences(v) for k, v in clips.items()}
    result["spike"] = {k: spike_ratio(v) for k, v in diffs.items()}
    result["max_diff"] = {k: float(v.max()) for k, v in diffs.items()}
    plot_series(diffs, out_dir / "frame_difference.png", "mean change between consecutive frames", "grey levels")
    plot_series({"1 / view width (zoom)": 1.0 / widths}, out_dir / "zoom.png", "the camera's zoom", "x")
    idx = [int(round(i)) for i in np.linspace(0, n - 1, 12)]
    contact_strip(frames, idx, out_dir / "strip.jpg", [f"{i}: {1 / widths[i]:.1f}x" for i in idx])
    (out_dir / "report.json").write_text(json.dumps(result, indent=1))
    rows = ["zoom   frame  view    edge px  detail"]
    for r in result["sharpness"]:
        rows.append(f"{r['zoom']:>4}x  " + ("  -" if r["frame"] is None else
                    f"{r['frame']:>5}  {r['view']:.3f}  {r['edge_px']:>7.2f}  {r['detail']:>6.2f}"))
    log("\n".join(rows))
    log(f"spike ratio: " + ", ".join(f"{k} {v:.2f}" for k, v in result["spike"].items()))
    return result
