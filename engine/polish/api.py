"""The polish report as the CLI, the MCP server and the storyboard editor use it: find, cache, write, read back."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Optional

from . import analyze as A
from .explain import SHORT
from .run import (METRICS, VERSION, Nothing, content_key, find_film, inspect_film, plan_spans)

Log = Callable[[str], None]


def inspect_dir(project) -> Path:
    return project.build / "inspect"


def report_path(project, name: str) -> tuple[Path, Path]:
    d = inspect_dir(project)
    return d / f"{name}.json", d / f"{name}.html"


def load_report(project, name: str) -> Optional[dict]:
    p = report_path(project, name)[0]
    if not p.exists():
        return None
    try:
        r = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return r if r.get("version") == VERSION else None


def _digest(*parts) -> str:
    import hashlib
    return hashlib.sha1(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()[:16]


def _write(project, name: str, report: dict) -> None:
    from .report import render_html
    j, h = report_path(project, name)
    j.parent.mkdir(parents=True, exist_ok=True)
    j.write_text(json.dumps(report, indent=1, default=float), encoding="utf-8")
    h.write_text(render_html(report), encoding="utf-8")


def _run(project, name: str, film: Path, spans, fade: float, spec_info: dict, force: bool, embed: bool,
         log: Log, progress) -> dict:
    clip_keys = [(s.id, content_key(s.clip)) if s.clip is not None and s.clip.exists() else (s.id, None) for s in spans]
    key = _digest(VERSION, content_key(film), clip_keys, [(s.id, round(s.start, 2), round(s.end, 2)) for s in spans],
                  round(fade, 3), spec_info, bool(embed))
    prev = None if force else load_report(project, name)
    if prev is not None and prev.get("key") == key and report_path(project, name)[1].exists():
        prev["cached"] = True
        log(f"inspect {name}: unchanged since {prev.get('generated')}: using the saved report")
        return prev
    out_dir = inspect_dir(project)
    rep = inspect_film(film, spans, fade, out_dir, name, spec_info, log=log, progress=progress, embed=embed)
    rep["key"] = key
    rep["film"]["content"] = content_key(film)
    rep["cached"] = False
    _write(project, name, rep)
    return rep


def inspect_section(project, section_id: str, force: bool = False, embed: bool = False, log: Log = print,
                    progress: Callable[[float, str], None] = lambda f, m="": None) -> dict:
    """Inspect one film section's built film. Cached: the same film and clips give back the saved report at once."""
    from ..project import BuildError
    site = project.load()
    sec = next((s for s in site.sections if getattr(s, "id", None) == section_id), None)
    if sec is None:
        raise BuildError(f"no section '{section_id}' in {project.name}")
    if sec.type != "film":
        raise BuildError(f"section '{section_id}' is a {sec.type} section: inspect looks at film sections (beats, take or video)")
    film = find_film(project, sec)
    import cv2
    cap = cv2.VideoCapture(str(film))
    secs = (cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0) / (cap.get(cv2.CAP_PROP_FPS) or 24.0)
    cap.release()
    spans, fade = plan_spans(project, sec, secs)
    spec_info = {"zoom": {s.id: s.zoom for s in spans}}
    rep = _run(project, section_id, film, spans, fade, spec_info, force, embed, log, progress)
    rep["section"] = section_id
    return rep


def inspect_video(project, file: str, name: Optional[str] = None, force: bool = False, embed: bool = False,
                  log: Log = print, progress=lambda f, m="": None) -> dict:
    """Inspect any video file as one unbroken shot (a screen recording, a clip): the same report, no beats."""
    from ..project import BuildError
    p = Path(file)
    if not p.exists():
        p = project.path(file)
    if not p.exists():
        raise BuildError(f"no video at {file}")
    import cv2
    cap = cv2.VideoCapture(str(p))
    secs = (cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0) / (cap.get(cv2.CAP_PROP_FPS) or 24.0)
    cap.release()
    name = name or p.stem
    spans = [A.BeatSpan(name, 0.0, secs, None, "film")]
    rep = _run(project, name, p, spans, 0.0, {}, force, embed, log, progress)
    rep["section"] = name
    return rep


def inspect_project(project, section: Optional[str] = None, force: bool = False, embed: bool = False,
                    log: Log = print) -> list[dict]:
    """Inspect `section`, or every film section that has a built film."""
    if section:
        return [inspect_section(project, section, force, embed, log)]
    out = []
    for s in project.load().sections:
        if s.type != "film":
            continue
        try:
            out.append(inspect_section(project, s.id, force, embed, log))
        except Nothing as e:
            log(f"skipped {s.id}: {e}")
    return out


def beat_badges(project) -> dict[str, dict]:
    """beat id -> badge for the storyboard: its worst issue from the saved report (nothing is measured here), or a clean
    badge. `stale` is true when the film changed since the report was made. Beats with no report are left out."""
    out: dict[str, dict] = {}
    try:
        site = project.load()
    except Exception:
        return out
    for sec in site.sections:
        if sec.type != "film" or not sec.beats:
            continue
        rep = load_report(project, sec.id)
        if rep is None:
            continue
        try:
            stale = content_key(find_film(project, sec)) != rep["film"].get("content")
        except Exception:
            stale = True
        first = {}
        for n, x in enumerate(rep["issues"]):                      # the worst issue of a beat is its first in the list
            first.setdefault(x["beat"], n)
        for b in rep["beats"]:
            w = b.get("worst")
            sev = w["severity"] if w else 0.0
            out[b["id"]] = {"section": sec.id, "severity": sev, "level": (w or {}).get("level") or ("clean" if sev < 0.25 else "slight"),
                            "metric": w["metric"] if w else None, "tag": SHORT.get(w["metric"]) if w else None,
                            "reason": w["reason"] if w else "No polish problems found.", "t": w["t"] if w else None,
                            "scores": b["scores"], "issues": b.get("issues", 0), "stale": stale,
                            "report": f"{sec.id}.html", "anchor": first.get(b["id"])}
    return out
