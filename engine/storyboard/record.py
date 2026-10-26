"""storyboard/storyboard.json: what the last storyboard showed (per card: its fingerprint and frames), so the next run
can say what changed and keep the frames of locked cards and of cards outside --only."""
from __future__ import annotations

import json
import time

from ..project import Project, file_key


def path(project: Project):
    return project.root / "storyboard" / "storyboard.json"


def load(project: Project) -> dict:
    p = path(project)
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except (OSError, ValueError):
        return {}


def frame_keys(card) -> list:
    out = []
    for f in card.frames:
        try:
            out.append(file_key(f.path) | {"dir": f.path.parent.name})
        except OSError:
            out.append(str(f.path))
    return out


def save(project: Project, level: str, cards: list, summary: dict) -> None:
    p = path(project)
    p.parent.mkdir(parents=True, exist_ok=True)
    data = {"level": level, "time": time.strftime("%Y-%m-%d %H:%M:%S"), "summary": summary,
            "cards": {c.id: {**c.public(), "frame_keys": frame_keys(c)} for c in cards}}
    p.write_text(json.dumps(data, indent=1), encoding="utf-8")
