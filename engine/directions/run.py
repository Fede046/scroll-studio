"""Directions, start to finish: write them, draw their boards, keep the state, pick one.

  make(project)              brief + seed -> directions -> stills -> board.html + board.png + directions.json
  load(project)              the saved state (None before the first make)
  reroll(project, id)        another idea in place of one direction
  redraw(project)            draw the stills again (ComfyUI was down; the imagery changed)
  pick(project, id)          write the direction into site.yaml (backup kept)
  undo(project)              put the file back as it was before the last pick
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Callable, Optional

from ..project import BuildError, Project
from ..spec import Directions
from . import board, measure, pick as picker, shots, writer
from .model import Direction

Log = Callable[[str], None]
Progress = Callable[[float, str], None]


def state_path(project: Project) -> Path:
    return board.folder(project) / "directions.json"


def load(project: Project) -> Optional[dict]:
    p = state_path(project)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except ValueError:
        return None


def save(project: Project, state: dict) -> None:
    state_path(project).write_text(json.dumps(state, indent=1, ensure_ascii=False), encoding="utf-8", newline="\n")


def config(project: Project, count: Optional[int] = None, seed: Optional[int] = None, brief: Optional[str] = None) -> Directions:
    """The site's `directions:` block with command-line overrides on top."""
    site = project.load()
    cfg = site.directions or Directions()
    upd = {k: v for k, v in (("count", count), ("seed", seed), ("brief", brief)) if v is not None}
    return Directions.model_validate({**cfg.model_dump(mode="json"), **upd}) if upd else cfg


def _finish(project: Project, state: dict, log: Log, sheet: bool = True) -> dict:
    """Write the page and the contact sheet from the state, save it."""
    state["made"] = time.strftime("%Y-%m-%d %H:%M")
    save(project, state)
    page = board.write_page(project, state, log)
    png = None
    if sheet:
        try:
            png = board.screenshot(board.folder(project), "board.html", board.folder(project) / "board.png", log=log)
        except Exception as e:                     # no Chrome here: the page is still the deliverable
            log(f"  no contact sheet ({str(e).splitlines()[0][:120]})")
    state["files"] = {"html": str(page), "png": str(png) if png else None, "json": str(state_path(project))}
    save(project, state)
    return state


def make(project: Project, count: Optional[int] = None, seed: Optional[int] = None, brief: Optional[str] = None,
         images: bool = True, sheet: bool = True, log: Log = print, progress: Progress = lambda f, m="": None) -> dict:
    """Write the directions for this site and draw their boards."""
    site = project.load()
    raw = project.raw()
    cfg = config(project, count, seed, brief)
    t0 = time.time()
    progress(0.02, "writing directions")
    res = writer.write(site, raw, cfg, cfg.seed, cfg.count)
    dirs: list[Direction] = res["directions"]
    log(f"directions for {site.name}: {len(dirs)} (seed {cfg.seed}); " + "; ".join(res["brief"]["notes"]))
    for w in res["warnings"]:
        log(f"  warning: {w}")
    for r in res["replaced"]:
        log(f"  weak pair: {r['replaced']} was too close to {r['was_close_to']} (distance {r['distance']:.2f}); now {r['with']}")
    moments = shots.pick(raw, cfg.stills, cfg.seed)
    log(f"  stills: " + ", ".join(f"{m.role} ({m.section})" for m in moments))
    board.draw_stills(project, dirs, moments, log, generate=images, progress=lambda f, m="": progress(0.05 + 0.8 * f, m))
    state = {"version": 1, "project": project.name, "seed": cfg.seed, "count": cfg.count, "brief": res["brief"],
             "keep": res["keep"], "diversity": res["diversity"], "replaced": res["replaced"], "warnings": res["warnings"],
             "moments": [m.public() for m in moments], "directions": [d.public() for d in dirs],
             "picked": None, "seconds": round(time.time() - t0, 1)}
    progress(0.9, "board")
    _finish(project, state, log, sheet)
    state["seconds"] = round(time.time() - t0, 1)
    save(project, state)
    progress(1.0, "done")
    log(f"directions: {len(dirs)} boards in {state['seconds']:.0f}s -> {state['files']['html']}")
    return state


def dirs_of(state: dict) -> list[Direction]:
    return [Direction.from_dict(d) for d in state["directions"]]


def _need(project: Project) -> dict:
    state = load(project)
    if not state:
        raise BuildError(f"no direction boards yet: run `studio directions {project.name}`")
    return state


def reroll(project: Project, which: str, images: bool = True, sheet: bool = True, log: Log = print) -> dict:
    """Another idea in place of one direction; the others stay."""
    state = _need(project)
    site, raw = project.load(), project.raw()
    cfg = config(project, state["count"], state["seed"])
    dirs = dirs_of(state)
    if which not in [d.id for d in dirs]:
        raise BuildError(f"no direction '{which}' (have: {', '.join(d.id for d in dirs)})")
    state["rerolls"] = state.get("rerolls", 0) + 1
    new = writer.reroll(site, raw, dirs, which, cfg, f"{state['seed']}-r{state['rerolls']}")
    old = next(d for d in dirs if d.id == which)
    log(f"  {which.upper()}: {old.name} -> {new.name}")
    dirs[dirs.index(old)] = new
    moments = [shots.Moment(**{k: v for k, v in m.items() if k in shots.Moment.__dataclass_fields__}) for m in state["moments"]]
    keep = [d for d in dirs if d is not new]
    saved = {d.id: d.stills for d in keep}
    board.draw_stills(project, [new], moments, log, generate=images)
    for d in keep:
        d.stills = saved[d.id]
    state["directions"] = [d.public() for d in dirs]
    state["diversity"] = measure.report(dirs, frozenset(state.get("keep", [])))
    if (state.get("picked") or {}).get("id") == which:
        state["picked"] = None
    return _finish(project, state, log, sheet)


def redraw(project: Project, images: bool = True, sheet: bool = True, log: Log = print,
           progress: Progress = lambda f, m="": None) -> dict:
    """Draw every still again (cached ones are kept): after ComfyUI was down, or the site's prompts changed."""
    state = _need(project)
    raw = project.raw()
    cfg = config(project, state["count"], state["seed"])
    dirs = dirs_of(state)
    moments = shots.pick(raw, cfg.stills, cfg.seed)
    board.draw_stills(project, dirs, moments, log, generate=images, progress=progress)
    state["moments"] = [m.public() for m in moments]
    state["directions"] = [d.public() for d in dirs]
    return _finish(project, state, log, sheet)


def pick(project: Project, which: str, log: Log = print, sheet: bool = True) -> dict:
    """Write direction `which` (a letter, or its name) into site.yaml; the page marks it picked."""
    state = _need(project)
    dirs = dirs_of(state)
    d = next((x for x in dirs if x.id == which.lower() or x.name.lower() == which.lower() or x.school == which.lower()), None)
    if d is None:
        raise BuildError(f"no direction '{which}' (have: " + ", ".join(f"{x.id} = {x.name}" for x in dirs) + ")")
    res = picker.apply(project, d, log)
    state["picked"] = {"id": d.id, "name": d.name, "time": time.strftime("%Y-%m-%d %H:%M:%S"), **{k: res.get(k) for k in ("changed", "backup")}}
    save(project, state)
    try:
        board.write_page(project, state, lambda m: None)
    except Exception:
        pass
    return {"direction": d.public(), **res}


def undo(project: Project, log: Log = print) -> dict:
    res = picker.undo(project)
    state = load(project)
    if state:
        state["picked"] = None
        save(project, state)
        try:
            board.write_page(project, state, lambda m: None)
        except Exception:
            pass
    log(f"  site.yaml put back ({res.get('restored_from', '')})")
    return res
