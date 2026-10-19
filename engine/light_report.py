"""`studio light`: what a `light` scene made, to look at. The times side by side with the drift measured against the world,
and a frame strip across every transition of the built page (the same scroll positions the viewer passes through), so you
can judge whether it reads as time passing in one place."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Optional

import numpy as np
from PIL import Image, ImageDraw

from . import light
from .project import Project
from .scenes.light import time_at


def sections(project: Project, only: Optional[str] = None) -> list:
    site = project.load()
    found = [s for s in site.sections if getattr(s, "type", None) == "light" and (only is None or s.id == only)]
    return found


def progress_at(holds: list[dict], tau: float) -> float:
    """The section progress at which the light is at (fractional) time `tau`: the inverse of time_at, by bisection on
    the monotone stretch between holds."""
    lo, hi = 0.0, 1.0
    if time_at(0.0, holds) >= tau:
        return 0.0
    if time_at(1.0, holds) < tau:
        return 1.0
    for _ in range(40):
        mid = (lo + hi) / 2
        if time_at(mid, holds) < tau:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def times_sheet(project: Project, sec, out_dir: Path) -> Path:
    """Every time of day, with its clock and measured drift (raw and aligned), as one sheet: out_dir/sheet.jpg."""
    work = project.build / sec.id
    rep = json.loads((work / "report.json").read_text())
    images = [light.load_rgb(work / "times" / f"{t['id']}.png") for t in rep["times"]]
    return light.contact_sheet(rep["times"], images, out_dir / "sheet.jpg")


def strips(project: Project, sec, out_dir: Path, frames: int = 7, size=(1280, 720), log: Callable = print) -> list[Path]:
    """For every pair of neighbouring times, `frames` screenshots of the built page while the light travels from the first
    to the second (at the scroll positions where the page's own schedule puts it), joined into one strip each."""
    from .snapshot import snapshot
    cfg = json.loads((project.build / sec.id / "config.json").read_text())
    holds = cfg["holds"]
    ids = [t["id"] for t in cfg["times"]]
    tmp = out_dir / "_frames"
    out = []
    for k in range(len(ids) - 1):
        taus = [k + i / (frames - 1) for i in range(frames)]
        ps = [progress_at(holds, t) for t in taus]
        if ps[-1] - ps[0] < 1e-4:          # the page never travels between these two (steps skip them): nothing to show
            continue
        shots = [f"{sec.id}:{p:.4f}" for p in ps]
        paths = snapshot(project.dist, shots, tmp, size=size, wait=1.2, log=lambda m: None)
        tw = 400
        th = round(tw * size[1] / size[0])
        strip = Image.new("RGB", (tw * frames, th + 22), (14, 14, 16))
        d = ImageDraw.Draw(strip)
        for i, (pth, t, p) in enumerate(zip(paths, taus, ps)):
            strip.paste(Image.open(pth).convert("RGB").resize((tw, th), Image.LANCZOS), (i * tw, 22))
            d.text((i * tw + 6, 5), f"{ids[k]} > {ids[k + 1]}  {t - k:.2f}  (scroll {p:.3f})", fill=(225, 225, 225))
        f = out_dir / f"strip_{k + 1}_{ids[k]}_to_{ids[k + 1]}.jpg"
        strip.save(f, quality=90)
        out.append(f)
        log(f"  {f.name}")
    import shutil
    shutil.rmtree(tmp, ignore_errors=True)
    return out


def sequence_diff(project: Project, sec) -> dict:
    """How far apart neighbouring times are in light (mean absolute difference of luma, 0-1) and in structure (edge
    agreement): a quick read on whether a step in the day is too big to feel like one place changing."""
    work = project.build / sec.id
    rep = json.loads((work / "report.json").read_text())
    imgs = [light.load_rgb(work / "times" / f"{t['id']}.png") for t in rep["times"]]
    out = []
    for k in range(len(imgs) - 1):
        a, b = imgs[k], imgs[k + 1]
        out.append({"from": rep["times"][k]["id"], "to": rep["times"][k + 1]["id"],
                    "luma_step": round(float(np.abs(light.luma(a) - light.luma(b)).mean()), 4),
                    "edges": round(light.edge_agreement(light.structure(a), light.structure(b)), 4)})
    return {"pairs": out}
