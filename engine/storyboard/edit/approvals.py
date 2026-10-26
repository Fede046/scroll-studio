"""Approvals: a storyboard-only state in `<project>/storyboard/state.json` (it is not part of the spec).

A shot is *approved* with the signature of everything about it at that moment (its fields, its images' recipes, its
lock); change any of it and the approval reads *changed* until it is approved again. The sheet and `studio build --plan`
list the shots that are not approved.
"""
from __future__ import annotations

import json
import os
import time
from typing import Callable, Optional

from ...project import Project
from . import shots as shots_mod


def path(project: Project):
    return project.root / "storyboard" / "state.json"


def load(project: Project) -> dict:
    p = path(project)
    try:
        data = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except (OSError, ValueError):
        data = {}
    data.setdefault("approved", {})
    return data


def _save(project: Project, data: dict) -> None:
    p = path(project)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
    os.replace(tmp, p)


def status(project: Project, board: shots_mod.Board) -> dict[str, str]:
    """{shot id: approved | changed | no}"""
    ap = load(project)["approved"]
    out = {}
    for s in board.shots:
        a = ap.get(s.id)
        out[s.id] = "no" if not a else ("approved" if a.get("sig") == s.sig() else "changed")
    return out


def set_approved(project: Project, board: shots_mod.Board, shot_id: str, approved: bool) -> str:
    s = board.shot(shot_id)
    if s is None:
        raise KeyError(shot_id)
    data = load(project)
    if approved:
        data["approved"][shot_id] = {"sig": s.sig(), "time": time.strftime("%Y-%m-%d %H:%M:%S")}
    else:
        data["approved"].pop(shot_id, None)
    _save(project, data)
    return "approved" if approved else "no"


def summary(project: Project, board: Optional[shots_mod.Board] = None) -> Optional[dict]:
    """{approved, total, pending: [ids]} when the project has used approvals (state.json exists), else None."""
    if not path(project).exists():
        return None
    try:
        board = board or shots_mod.build(project)
    except Exception:
        return None
    st = status(project, board)
    pending = [i for i, v in st.items() if v != "approved"]
    return {"approved": len(st) - len(pending), "total": len(st), "pending": pending, "status": st}


def mention(project: Project, log: Callable[[str], None]) -> None:
    """For `studio build`'s plan: which shots the storyboard has not approved."""
    s = summary(project)
    if s and s["pending"]:
        log(f"storyboard: {s['approved']} of {s['total']} shots approved; not approved: {', '.join(s['pending'][:12])}"
            + (" ..." if len(s["pending"]) > 12 else "") + " (studio storyboard --edit)")
