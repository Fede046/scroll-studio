"""How much work a build may do: the full build, a plan (nothing renders) or a storyboard preview.

`planning()`: a dry run (engine/plan.py). Builders run as usual, but `BuildContext.stage` records each stage that
would run instead of running it, and code that renders outside a stage (an image input, a product still, the product
model's normalisation) calls `would_render()`, which raises `WouldRender` while planning.

`previewing(level)`: a storyboard (engine/storyboard). Product stills render at low samples (cached apart: their keys
hold the samples, so a preview is never taken for a final), generated scenes skip the harmonising pass and theme.art
stays a still. At `sketch` nothing is sent to ComfyUI: an image that is not in the cache yet becomes a placeholder card
(kept outside every cache a full build reads).
"""
from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

LEVELS = ("sketch", "stills", "animatic")


class WouldRender(Exception):
    """Raised while planning where the build would render something outside a stage."""
    def __init__(self, kind: str, what: str):
        super().__init__(f"{kind}: {what}")
        self.kind, self.what = kind, what


@dataclass(frozen=True)
class Preview:
    level: str                 # sketch | stills | animatic
    samples: int               # Cycles samples for product stills and product passes
    scale: float               # product stills: size factor (sketch renders them small)
    comfy: bool                # may images be generated (Z-Image, Qwen-Image-Edit)?

    @property
    def sketch(self) -> bool:
        return self.level == "sketch"


PRESETS = {
    "sketch": Preview("sketch", samples=8, scale=0.5, comfy=False),
    "stills": Preview("stills", samples=16, scale=1.0, comfy=True),
    "animatic": Preview("animatic", samples=16, scale=1.0, comfy=True),
}

_PLAN: ContextVar[bool] = ContextVar("ss_plan", default=False)
_PREVIEW: ContextVar[Optional[Preview]] = ContextVar("ss_preview", default=None)


@contextmanager
def planning():
    token = _PLAN.set(True)
    try:
        yield
    finally:
        _PLAN.reset(token)


def is_planning() -> bool:
    return _PLAN.get()


def would_render(kind: str, what: str) -> None:
    """Call right before rendering outside a stage: raises WouldRender while planning, else does nothing."""
    if _PLAN.get():
        raise WouldRender(kind, what)


@contextmanager
def previewing(level: str):
    token = _PREVIEW.set(PRESETS[level])
    try:
        yield PRESETS[level]
    finally:
        _PREVIEW.reset(token)


def preview() -> Optional[Preview]:
    return _PREVIEW.get()


def placeholder(cache: Path, text: str, size: tuple[int, int], label: str = "not generated yet",
                colour: str = "#24262b") -> Path:
    """A card standing in for an image that is not rendered yet: the prompt set on a flat panel, with a label.
    Written under `cache` (a storyboard folder), never where a real render would be looked up."""
    from PIL import Image, ImageDraw
    w, h = int(size[0]), int(size[1])
    digest = hashlib.sha1(json.dumps([text, w, h, label, colour, 2]).encode()).hexdigest()[:14]
    out = cache / f"placeholder_{digest}.png"
    if out.exists():
        return out
    cache.mkdir(parents=True, exist_ok=True)
    im = Image.new("RGB", (w, h), colour)
    d = ImageDraw.Draw(im)
    pad = max(12, w // 24)
    big = font(max(12, w // 34))
    small = font(max(10, w // 52))
    # a thin frame and a diagonal, the storyboard convention for "shot to come"
    d.rectangle([pad // 2, pad // 2, w - pad // 2, h - pad // 2], outline="#4a4d55", width=max(1, w // 600))
    d.line([pad // 2, h - pad // 2, w - pad // 2, pad // 2], fill="#30333a", width=max(1, w // 800))
    d.text((pad, pad), label.upper(), fill="#9aa0aa", font=small)
    y = pad + int(small.size * 2.2)
    for line in wrap(text, big, w - 2 * pad)[: max(1, (h - y - pad) // int(big.size * 1.3))]:
        d.text((pad, y), line, fill="#e6e7ea", font=big)
        y += int(big.size * 1.3)
    im.save(out)
    return out


# ---------------------------------------------------------------- type for cards and sheets

_FONTS = ("C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/arial.ttf", "/System/Library/Fonts/Helvetica.ttc",
          "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/TTF/DejaVuSans.ttf")
_BOLD = ("C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/arialbd.ttf", "/System/Library/Fonts/Helvetica.ttc",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf")


def font(size: int, bold: bool = False):
    from PIL import ImageFont
    for f in (_BOLD if bold else _FONTS):
        if Path(f).exists():
            try:
                return ImageFont.truetype(f, size)
            except OSError:
                continue
    return ImageFont.load_default(size=size)


def wrap(text: str, fnt, width: int) -> list[str]:
    """Greedy word wrap to a pixel width."""
    words, lines, cur = (text or "").split(), [], ""
    for wd in words:
        trial = f"{cur} {wd}".strip()
        if fnt.getlength(trial) <= width or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = wd
    if cur:
        lines.append(cur)
    return lines
