"""Notes: plain-language requests for change ("warmer light", "she should look older", "tighten the pacing"), kept as an
inbox in `<project>/storyboard/notes.json`.

The page only collects them. An agent (Claude, through the MCP tools `storyboard_notes` and `resolve_note`, or from
`studio storyboard <project> --notes`) reads each one next to the shot's current spec and images, decides what it means
(a field edited, a new variant rendered, the copy rewritten), does it through the same editing tools, and resolves the
note with a short reply. While a note is `working`, edits and renders made to its shot (or to anything, for a general
note) are attached to it as `changes`, so the page can say what a note led to.

  note = {id, shot ("general" or a shot id), text, time, status (open | working | done), reply, changes [str],
          variants [{shot, slot, n}], resolved}
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Iterable, Optional

from ...project import BuildError, Project

STATUSES = ("open", "working", "done")
GENERAL = "general"
_LOCK = threading.RLock()


def path(project: Project) -> Path:
    return project.root / "storyboard" / "notes.json"


def mtime(project: Project) -> float:
    try:
        return path(project).stat().st_mtime
    except OSError:
        return 0.0


def _load(project: Project) -> dict:
    p = path(project)
    try:
        data = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except (OSError, ValueError):
        data = {}
    data.setdefault("notes", [])
    data.setdefault("next", 1 + max([int(str(n["id"]).lstrip("n") or 0) for n in data["notes"]] + [0]))
    return data


def _save(project: Project, data: dict) -> None:
    p = path(project)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, p)


def _stamp() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def all_notes(project: Project) -> list[dict]:
    return _load(project)["notes"]


def get(project: Project, nid: str) -> dict:
    n = next((n for n in all_notes(project) if n["id"] == nid), None)
    if n is None:
        raise BuildError(f"no note {nid}")
    return n


def add(project: Project, shot: str, text: str) -> dict:
    text = (text or "").strip()
    if not text:
        raise BuildError("a note needs some text")
    with _LOCK:
        data = _load(project)
        n = {"id": f"n{data['next']}", "shot": shot or GENERAL, "text": text, "time": _stamp(), "status": "open",
             "reply": "", "changes": [], "variants": [], "resolved": None}
        data["next"] += 1
        data["notes"].append(n)
        _save(project, data)
        return n


def _update(project: Project, nid: str, fn) -> dict:
    with _LOCK:
        data = _load(project)
        n = next((n for n in data["notes"] if n["id"] == nid), None)
        if n is None:
            raise BuildError(f"no note {nid}")
        fn(n)
        _save(project, data)
        return n


def claim(project: Project, ids: Iterable[str]) -> list[dict]:
    """Mark open notes as being worked on."""
    out = []
    for nid in ids:
        def f(n):
            if n["status"] == "open":
                n["status"] = "working"
        out.append(_update(project, nid, f))
    return out


def resolve(project: Project, nid: str, reply: str = "", changes: Optional[list[str]] = None,
            variants: Optional[list[dict]] = None, status: str = "done") -> dict:
    if status not in STATUSES:
        raise BuildError(f"status must be one of {', '.join(STATUSES)}")

    def f(n):
        n["status"] = status
        if reply:
            n["reply"] = reply.strip()
        for c in changes or []:
            if c not in n["changes"]:
                n["changes"].append(c)
        for v in variants or []:
            if v not in n["variants"]:
                n["variants"].append(v)
        n["resolved"] = _stamp() if status == "done" else None
    return _update(project, nid, f)


def reopen(project: Project, nid: str, more: str = "") -> dict:
    def f(n):
        n["status"] = "open"
        n["resolved"] = None
        if more.strip():
            n["text"] = n["text"].rstrip() + "\n+ " + more.strip()
    return _update(project, nid, f)


def delete(project: Project, nid: str) -> None:
    with _LOCK:
        data = _load(project)
        data["notes"] = [n for n in data["notes"] if n["id"] != nid]
        _save(project, data)


def record(project: Project, shot: str, what: str, variant: Optional[dict] = None) -> None:
    """Attach an edit or render to the notes being worked on (those for this shot, and the general ones)."""
    try:
        with _LOCK:
            data = _load(project)
            hit = False
            for n in data["notes"]:
                if n["status"] == "working" and n["shot"] in (shot, GENERAL):
                    if what not in n["changes"]:
                        n["changes"].append(what)
                    if variant and variant not in n["variants"]:
                        n["variants"].append(variant)
                    hit = True
            if hit:
                _save(project, data)
    except Exception:
        pass


def open_notes(project: Project, include_working: bool = False) -> list[dict]:
    keep = ("open", "working") if include_working else ("open",)
    return [n for n in all_notes(project) if n["status"] in keep]
