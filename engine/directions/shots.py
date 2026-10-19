"""Which moments of the page a board shows, and what each one is a picture of.

A board is the hero and two or three key sections as stills. The *subject* of a still comes from the site: the prompt
the section already has for its image (with the medium, lens and light phrases dropped, because the direction brings its
own), or, for a section with no image, its headline and first sentence. Every direction paints the same subjects with the
same seeds, so what differs between boards is the direction and nothing else.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from ..imagery import phrase, restyle
from ..spec import Imagery
from .brief import plain

SCENES = {"film", "parallax", "artwork", "scene3d", "sequence", "showroom", "splat", "map", "chart", "code", "vector", "type"}
WEIGHT = {"hero": 5, "film": 4, "parallax": 4, "artwork": 3, "sequence": 3, "showroom": 3, "product": 3, "gallery": 3,
          "strip": 3, "features": 2.5, "orbit": 2, "timeline": 2, "stats": 1, "quote": 1.5, "intro": 1.5, "cta": 1.5,
          "faq": 0.5, "splat": 3, "map": 2, "scene3d": 2.5, "chart": 2, "vector": 2, "type": 1.5, "code": 2}
FRAMING = {"hero": "wide establishing view", "detail": "closer view of a detail", "feature": "medium view", "closing": "quiet closing view"}
NEUTRAL = Imagery(medium="x", light="x", lens="x")       # restyle() drops every medium, light and lens phrase


@dataclass
class Moment:
    role: str                # hero | feature | detail | closing
    index: int               # section index
    section: str             # section id (or type)
    type: str
    title: str               # the headline shown on the still
    kicker: str
    subject: str             # what the picture shows
    from_prompt: bool        # the subject comes from the site's own image prompt (else from its copy)
    seed: int = 0
    title_html: str = ""     # the headline as written, keeping only <em>

    def public(self) -> dict:
        return {"role": self.role, "index": self.index, "section": self.section, "type": self.type, "title": self.title,
                "kicker": self.kicker, "subject": self.subject, "from_prompt": self.from_prompt, "seed": self.seed,
                "title_html": self.title_html}


def _find_prompts(node, out: list, depth: int = 0) -> None:
    if depth > 8:
        return
    if isinstance(node, dict):
        for k, v in node.items():
            if k == "generate" and isinstance(v, str):
                out.append(v)
            elif k == "prompt" and isinstance(v, str) and depth and node.get("motion") is not None:
                out.append(v)                                 # a beat's opening frame
            elif k in ("take", "shot") and isinstance(v, dict):
                for f in ((v.get("keyframes") or {}).get("frames") or []):
                    if isinstance(f, dict) and f.get("prompt"):
                        out.append(f["prompt"])
            elif isinstance(v, (dict, list)):
                _find_prompts(v, out, depth + 1)
    elif isinstance(node, list):
        for v in node:
            _find_prompts(v, out, depth + 1)


def first_sentence(text: str, limit: int = 220) -> str:
    text = plain(text)
    m = re.match(r"(.+?[.!?])(\s|$)", text)
    s = m.group(1) if m else text
    return s[:limit].rstrip(" ,;:")


def safe_title(text) -> str:
    """A headline as HTML, keeping only <em>."""
    t = re.sub(r"</?(?!em>)[a-zA-Z][^>]*>", "", str(text or ""))
    t = t.replace("&", "&amp;").replace("<em>", "[[em]]").replace("</em>", "[[/em]]").replace("<", "&lt;").replace(">", "&gt;")
    return re.sub(r"\s+", " ", t.replace("[[em]]", "<em>").replace("[[/em]]", "</em>")).strip()


def _copy_raw(sec: dict) -> tuple[str, str, str]:
    """(title, kicker, body) of a section as written: a block's own, or a scene's first step with a headline."""
    if sec.get("title") or sec.get("body"):
        return sec.get("title") or "", sec.get("kicker") or "", sec.get("body") or ""
    for st in sec.get("steps") or []:
        if isinstance(st, dict) and st.get("title"):
            return st.get("title") or "", st.get("kicker") or "", st.get("body") or ""
    items = sec.get("items") or []
    if items and isinstance(items[0], dict):
        it = items[0]
        return (it.get("title") or it.get("label") or sec.get("kicker") or ""), (it.get("tag") or ""), (it.get("body") or it.get("caption") or "")
    if sec.get("text"):
        return sec.get("text") or "", "", ""
    return str(sec.get("id") or sec.get("type") or ""), "", ""


def _copy(sec: dict) -> tuple[str, str, str]:
    """(title, kicker, body) as plain text."""
    return tuple(plain(x) for x in _copy_raw(sec))


def _subject(sec: dict, name: str, description: str, role: str) -> tuple[str, bool]:
    prompts: list = []
    _find_prompts({k: v for k, v in sec.items() if k != "product"}, prompts)
    if prompts:
        return restyle(prompts[0], NEUTRAL).rstrip(". "), True
    title, kicker, body = _copy(sec)
    parts = [title.rstrip(".!?"), first_sentence(body)]
    if role == "hero" and not body:
        parts.append(first_sentence(description))
    text = ". ".join(p for p in parts if p)
    if len(text.split()) < 8 and description:       # a headline alone says little: the site's own line gives it a place
        text = text + ". " + first_sentence(description)
    if not text:
        text = first_sentence(description) or name
    return text, False


def pick(raw: dict, n: int = 4, seed: int = 1) -> list[Moment]:
    """The hero, then up to n-1 key sections: a closing one, and the best of the rest spread down the page."""
    secs = [s for s in (raw.get("sections") or []) if isinstance(s, dict)]
    if not secs:
        return []
    name, desc = plain(raw.get("name")), plain(raw.get("description"))

    def weight(i: int, s: dict) -> float:
        w = WEIGHT.get(s.get("type"), 1.0)
        pr: list = []
        _find_prompts({k: v for k, v in s.items() if k != "product"}, pr)
        if pr:
            w += 2.5
        t, k, b = _copy(s)
        if t == "":
            w -= 1.5
        if not pr and len((t + " " + b).split()) < 5:
            w -= 2.0                       # too little copy to say what the picture shows ('Rooms')
        return w

    chosen = [0]
    if n > 1 and len(secs) > 1:
        last = len(secs) - 1
        closing = last if secs[last].get("type") in ("cta", "quote", "intro", "hero", "faq") or last != 0 else None
        if secs[last].get("type") in ("faq",) and last > 1:
            closing = last - 1
        want_closing = n >= 3
        middle = [i for i in range(1, len(secs)) if i != closing]
        # best-weighted first, but prefer sections far from those already chosen (spread down the page)
        for _ in range(n - 1 - (1 if want_closing and closing else 0)):
            if not middle:
                break
            best = max(middle, key=lambda i: weight(i, secs[i]) + 0.35 * min(abs(i - c) for c in chosen))
            chosen.append(best)
            middle.remove(best)
        if want_closing and closing:
            chosen.append(closing)
    chosen = sorted(set(chosen))[:n]
    out = []
    for k, i in enumerate(chosen):
        s = secs[i]
        role = "hero" if i == chosen[0] else ("closing" if i == chosen[-1] and len(chosen) >= 3 else ("detail" if k % 2 == 0 else "feature"))
        title, kicker, body = _copy(s)
        subject, from_prompt = _subject(s, name, desc, role)
        if role == "hero" and not title:
            title = name
        raw_title = _copy_raw(s)[0]
        out.append(Moment(role, i, str(s.get("id") or s.get("type")), str(s.get("type")), title or name, kicker, subject,
                          from_prompt, seed=1000 * seed + 37 * k + 11, title_html=safe_title(raw_title) or safe_title(name)))
    return out


def prompt_for(m: Moment, imagery: dict | None) -> str:
    """The still's prompt in a direction: its subject framed for the role, shot the way the direction's imagery says."""
    core = f"{m.subject.rstrip('. ')}, {FRAMING.get(m.role, 'medium view')}, no text or lettering"
    if not imagery:
        return core
    return phrase(Imagery(**imagery), core)
