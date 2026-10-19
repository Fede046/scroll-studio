"""Imagery: one treatment for every prompt a site sends to the image and video models.

`imagery:` in site.yaml (picked from a direction by `studio directions`) names the medium, light, lens, mood and palette
of the shoot. The prompts in the spec stay about the subject; the treatment is added where the prompt is used:

  * `generate:` images (`resolve_image`), which covers beat frames, parallax steps, backdrops, hero images, theme art
  * a beat's clip prompt (the video model sees the same shoot)
  * a take's / shot's keyframes and segment prompts (`treat_shot`)

With `restyle` on (the default) the phrases in the original prompt that the treatment replaces are dropped first
('photorealistic', 'shot on a medium format camera', '35mm lens', 'golden hour'), so a prompt written for one look does
not argue with another. Nothing is added when the site has no `imagery:`, and cache keys only change when it is set.
"""
from __future__ import annotations

import re
from typing import Optional

import yaml

from .spec import Imagery

_CACHE: dict[str, tuple] = {}


def of(project) -> Optional[Imagery]:
    """The site's `imagery:` (read from site.yaml, re-read when the file changes), or None."""
    path = project.spec_path
    try:
        st = path.stat()
    except OSError:
        return None
    hit = _CACHE.get(str(path))
    sig = (st.st_mtime_ns, st.st_size)
    if hit and hit[0] == sig:
        return hit[1]
    im = None
    try:
        with open(path, encoding="utf-8") as f:
            raw = (yaml.safe_load(f) or {}).get("imagery")
        if raw:
            im = Imagery.model_validate(raw)
    except Exception:       # an invalid spec is reported by the build itself
        im = None
    _CACHE[str(path)] = (sig, im)
    return im


# ---------------------------------------------------------------- dropping what the treatment replaces

MEDIUM = re.compile(
    r"^(?:photoreal\w*|hyper-?realistic|cinematic(?: still| photograph| lighting| grade)?|film still|ultra[- ]?detailed|"
    r"highly detailed|intricate details?|[48]k|hdr|sharp focus|award[- ]winning|professional photography|stock photo|"
    r"(?:editorial|travel|architectural|lifestyle|magazine|documentary|product|fashion)(?: \w+)? photography|"
    r"(?:editorial |magazine |travel )?\w*\s?magazine(?: style)?|high-end [\w ]+ (?:advertising )?style|"
    r"(?:shot|taken|captured|photographed) (?:on|with|by) .*|.*\b(?:dslr|medium format|large format|film camera|camera)\b.*|"
    r"(?:\w+ )?(?:photo|photograph|render|illustration)(?:-?realistic)?(?: style)?)$", re.I)
LIGHT = re.compile(r"\b(?:sunlight|sunrise|sunset|golden hour|blue hour|twilight|dusk|dawn|lighting|backlit|rim light|"
                   r"(?:soft |warm |cool |natural |window |diffused |morning |afternoon |evening |ambient |pale |low |"
                   r"harsh |hard )+light|light|shadows?|glow)\b", re.I)
LENS = re.compile(r"(?:\b\d{2,3}\s?mm\b|\blens\b|\bf/\d|shallow depth of field|\bbokeh\b|wide[- ]angle|telephoto|\bmacro\b|"
                  r"depth of field)", re.I)
INLINE_LIGHT = re.compile(r"\s+(?:at|during|in|under|in the) (?:the )?(?:golden hour|blue hour|magic hour|sunrise|sunset|dusk|dawn|twilight)\b", re.I)
LEAD = re.compile(r"^(?:[A-Za-z-]+ ){0,2}(?:photograph|photo|photography|image|picture|render|illustration|painting) of ", re.I)


def _clauses(text: str) -> list[str]:
    return [c.strip() for c in re.split(r",\s+|;\s+|\.\s+", text.strip().rstrip(".")) if c.strip()]


def restyle(prompt: str, im: Imagery) -> str:
    """The prompt without the medium, lens and light phrases that `im` sets itself."""
    out = []
    for i, c in enumerate(_clauses(prompt)):
        words = len(c.split())
        if MEDIUM.match(c):
            continue
        if i == 0:
            c2 = LEAD.sub("", c)
            if c2 != c:
                c = c2[:1].upper() + c2[1:]
        if im.lens and LENS.search(c) and words <= 7:
            continue
        if im.light:
            if LIGHT.search(c) and words <= 6:
                continue
            c = INLINE_LIGHT.sub("", c)
        out.append(c)
    return ", ".join(out) if out else prompt.strip()


def phrase(im: Imagery, prompt: str, video: bool = False) -> str:
    """`prompt` shot the way `im` says. video: the clip prompt (no lens: the camera moves)."""
    prompt = (prompt or "").strip()
    head = im.medium.strip().rstrip(".")
    if not prompt:
        return head
    if prompt.lower().startswith(head.lower()):      # already treated
        return prompt
    core = restyle(prompt, im) if im.restyle else prompt
    core = core.rstrip(". ")
    parts = [im.light, None if video else im.lens, im.palette, im.mood]
    tail = ". ".join(p.strip().rstrip(".") for p in parts if p)
    return f"{head}. {core}." + (f" {tail}." if tail else "")


def treat(project, prompt: str, video: bool = False) -> str:
    """The prompt as it is sent to the model for this project: unchanged unless the site sets `imagery:`."""
    im = of(project)
    return phrase(im, prompt, video) if im and prompt else prompt


def treat_shot(project, shot: dict) -> dict:
    """A take's / shot's keyframe and segment prompts treated (a copy; the spec's dicts are left alone)."""
    im = of(project)
    if im is None:
        return shot
    shot = dict(shot)
    kf = shot.get("keyframes")
    if kf and kf.get("frames"):
        kf = dict(kf)
        kf["frames"] = [dict(f, prompt=phrase(im, f["prompt"])) if f.get("prompt") else f for f in kf["frames"]]
        shot["keyframes"] = kf
    ltx = shot.get("ltx")
    if ltx and (ltx.get("segments") or ltx.get("prompt")):
        ltx = dict(ltx)
        if ltx.get("segments"):
            ltx["segments"] = [dict(s, prompt=phrase(im, s["prompt"], video=True)) if s.get("prompt") else s
                               for s in ltx["segments"]]
        if ltx.get("prompt"):
            ltx["prompt"] = phrase(im, ltx["prompt"], video=True)
        shot["ltx"] = ltx
    return shot
