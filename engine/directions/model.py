"""A direction: one complete art direction for the site, and everything needed to show it and to pick it."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Optional


@dataclass
class Direction:
    id: str                         # a, b, c ...
    school: str                     # vocab.SCHOOLS key
    name: str                       # "Golden Hour"
    kind: str                       # photo | cinema | illustration | typographic | dimensional | technical | craft | painterly | retro
    concept: str                    # one line: the idea
    palette: dict                   # name, mode, bg, bg2, ink, accent, accent2, accent_ink
    fonts: dict                     # display, body, mono, weight, em, italic_em, labels, note, display_class, body_class
    style: Optional[str]            # an engine style, or None for the default editorial layout
    style_label: str = ""
    style_about: str = ""           # what scrolling does in this style (the engine's own words, first sentence)
    imagery: Optional[dict] = None  # medium, light, lens, mood, palette (keys of spec.Imagery)
    imagery_family: str = ""
    light_name: str = ""
    motion: list = field(default_factory=list)      # page, camera, type notes
    voice: str = ""
    pace: float = 1.0               # scroll.speed
    radius: str = ""
    board: str = "overlay"
    stance: str = ""                # closest to today | a step away | a different site
    distance_from_current: float = 0.0
    fit: float = 0.0
    why: list = field(default_factory=list)
    stills: list = field(default_factory=list)      # [{role, section, title, prompt, image}] filled by board.py

    def public(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "Direction":
        keys = Direction.__dataclass_fields__.keys()
        return Direction(**{k: v for k, v in d.items() if k in keys})

    @property
    def mode(self) -> str:
        return self.palette.get("mode", "dark")
