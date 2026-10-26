"""Picking a direction: write it into site.yaml as the smallest readable diff.

What a direction sets: `theme` (style, mode, colors, fonts, display weight and emphasis, radius), `imagery` (how every image
and film prompt is phrased) and `scroll.speed` (the pace). Nothing else: the name, the description, the sections and every
word of copy are never touched. Only what differs from what the site already resolves to is written (a colour the preset
already has is not repeated), the old file is kept in directions/backups/, and the write goes through the storyboard
editor's spec writer, which changes only those lines (comments, ordering and quoting stay as they were) and refuses an
edit that would make the spec invalid.
"""
from __future__ import annotations

import difflib
import time
from pathlib import Path
from typing import Optional

import yaml

from ..compile import themes
from ..project import BuildError, Project
from ..spec import Theme
from ..storyboard.edit import specdoc
from .model import Direction

COLOR_KEYS = ("bg", "bg2", "ink", "accent", "accent2", "accent_ink")


def _base(theme_raw: dict, style: Optional[str]) -> dict:
    """What the theme resolves to with only the preset and the style (no colour, font or weight overrides)."""
    t = Theme(preset=theme_raw.get("preset", "night"), style=style)
    return themes.resolve(t)


def ops_for(raw: dict, d: Direction) -> list[specdoc.Op]:
    """The edits that make the site wear direction `d`, as few and as small as possible."""
    theme = raw.get("theme")
    theme_raw = dict(theme) if isinstance(theme, dict) else {}
    ops: list[specdoc.Op] = []
    base = _base(theme_raw, d.style)

    pal = d.palette
    colors = {k: pal[k] for k in COLOR_KEYS if pal.get(k) and str(pal[k]).lower() != str(base["colors"].get(k, "")).lower()}
    f = d.fonts
    fonts = {r: f[r] for r in ("display", "body", "mono") if f.get(r) and f[r] != base["fonts"].get(r)}
    scalars = {}
    if d.mode != base["mode"]:
        scalars["mode"] = d.mode
    if f.get("weight") and int(f["weight"]) != int(base["display_weight"]):
        scalars["display_weight"] = int(f["weight"])
    if f.get("em") and f["em"] != base["em"]:
        scalars["display_em"] = f["em"]
    if f.get("italic_em") is not None and bool(f["italic_em"]) != bool(base["em_italic"]) and f.get("em", "accent") == "accent":
        scalars["display_italic_em"] = bool(f["italic_em"])
    if f.get("labels") and f["labels"] != base["labels"]:
        scalars["labels"] = f["labels"]
    if d.radius and d.radius != base["radius"]:
        scalars["radius"] = d.radius

    if not isinstance(theme, dict):            # no theme block yet: the default preset, plus what the direction sets
        new_theme: dict = {}
        if d.style:
            new_theme["style"] = d.style
        new_theme.update(scalars)
        if colors:
            new_theme["colors"] = colors
        if fonts:
            new_theme["fonts"] = fonts
        if new_theme:
            ops.append(specdoc.Op(("theme",), new_theme))
    else:
        # style
        if d.style:
            if theme_raw.get("style") != d.style:
                ops.append(specdoc.Op(("theme", "style"), d.style))
        elif "style" in theme_raw:
            ops.append(specdoc.Op(("theme", "style"), delete=True))
        # scalars the direction sets, and ones it leaves at the base that the site had overridden
        for key in ("mode", "display_weight", "display_em", "display_italic_em", "labels", "radius"):
            if key in scalars:
                if theme_raw.get(key) != scalars[key]:
                    ops.append(specdoc.Op(("theme", key), scalars[key]))
            elif key in theme_raw:
                ops.append(specdoc.Op(("theme", key), delete=True))
        # colors and fonts replace the old overrides as one mapping (only what differs from the base)
        for key, val in (("colors", colors), ("fonts", fonts)):
            if val:
                if theme_raw.get(key) != val:
                    ops.append(specdoc.Op(("theme", key), val))
            elif key in theme_raw:
                ops.append(specdoc.Op(("theme", key), delete=True))
    # imagery: how every generated image and film is phrased
    if d.imagery:
        im = {k: v for k, v in d.imagery.items() if v}
        if raw.get("imagery") != im:
            ops.append(specdoc.Op(("imagery",), im))
    # pace
    scroll = raw.get("scroll") if isinstance(raw.get("scroll"), dict) else {}
    cur = scroll.get("speed", 1.0)
    if abs(float(d.pace) - float(cur)) > 1e-9:
        if "scroll" in raw and isinstance(raw.get("scroll"), dict):
            if abs(d.pace - 1.0) < 1e-9:
                ops.append(specdoc.Op(("scroll", "speed"), delete=True))
            else:
                ops.append(specdoc.Op(("scroll", "speed"), float(d.pace)))
        elif abs(d.pace - 1.0) > 1e-9:
            ops.append(specdoc.Op(("scroll",), {"speed": float(d.pace)}))
    return ops


# ---------------------------------------------------------------- laying the block out

def _scalar(v) -> str:
    return specdoc.render_scalar(v, None, True)


def _flow(d: dict) -> str:
    return "{ " + ", ".join(f"{k}: {_scalar(v)}" for k, v in d.items()) + " }"


def _block(name: str, d: dict) -> str:
    """`name:` and its keys, one per line; a mapping of plain values (colors, fonts) on one line."""
    out = [f"{name}:"]
    for k, v in d.items():
        if isinstance(v, dict) and v and all(not isinstance(x, (dict, list)) for x in v.values()):
            out.append(f"  {k}: {_flow(v)}")
        elif isinstance(v, (dict, list)):
            body = yaml.safe_dump({k: v}, sort_keys=False, allow_unicode=True, default_flow_style=False, width=10 ** 6).rstrip("\n")
            out.extend("  " + ln for ln in body.splitlines())
        else:
            out.append(f"  {k}: {specdoc.render_scalar(v, None, False)}")
    return "\n".join(out)


def _region(text: str, root, key: str):
    """(start, end) of a top-level key's whole entry: from its line start to the end of its value."""
    for k, v in root.value:
        if k.value == key:
            ls = text.rfind("\n", 0, k.start_mark.index) + 1
            end = specdoc._leaf_end(v)
            if not v.flow_style and "#" in text[ls:end]:
                raise specdoc._Splice("a comment inside the block")
            return ls, end
    return None


def _eol(text: str, i: int) -> int:
    j = text.find("\n", i)
    return len(text) if j < 0 else j


BLOCKS = ("theme", "imagery", "scroll")        # in the order they are written, one after another


def laid_out(text: str, want: dict, touched: set) -> str:
    """site.yaml text with the touched top-level blocks (theme, imagery, scroll) written as readable blocks and every other
    line as it was. A block that is already there is replaced where it stands; a new one goes after the previous block
    (theme, then imagery, then scroll), else after the description, else after the name."""
    root = specdoc._compose(text)
    regs = {k: _region(text, root, k) for k in BLOCKS}
    new = {k: (_block(k, want[k]) if want.get(k) else None) for k in BLOCKS if k in touched}
    edits = []                                   # (start, end, replacement)
    for k in BLOCKS:
        if k not in touched or not regs[k]:
            continue
        a, b = regs[k]
        if new[k]:
            edits.append((a, b, new[k]))
        else:                                    # the block is gone from the result: drop its lines
            edits.append((a, min(len(text), _eol(text, b) + 1), ""))
    pending = [k for k in BLOCKS if k in touched and new.get(k) and not regs[k]]
    if pending:
        anchor = None
        for k in reversed(BLOCKS[:BLOCKS.index(pending[0])]):
            if regs[k]:
                anchor = regs[k]
                break
        anchor = anchor or _region(text, root, "description") or _region(text, root, "name")
        if anchor is None:
            raise specdoc._Splice("nowhere to put the new block")
        at = _eol(text, anchor[1])
        edits.append((at, at, "\n" + "\n".join(new[k] for k in pending)))
    for a, b, rep in sorted(edits, key=lambda e: -e[0]):
        text = text[:a] + rep + text[b:]
    return text


def compose_text(text: str, raw: dict, ops: list[specdoc.Op]) -> str:
    """The new site.yaml: the touched blocks laid out readably, everything else byte for byte (line endings kept). The result's
    plain-data meaning is checked against the ops; if the layout cannot be made safely, the spec writer's own edit is used."""
    want = specdoc._apply_plain(raw, ops)
    touched = {o.path[0] for o in ops}
    crlf = "\r\n" in text
    try:
        new = laid_out(text.replace("\r\n", "\n"), want, touched)
        if (yaml.safe_load(new) or {}) == want:
            return new.replace("\n", "\r\n") if crlf else new
    except Exception:
        pass
    return specdoc.apply_ops(text, ops)


def touches_copy(ops: list[specdoc.Op]) -> bool:
    return any(op.path[0] not in ("theme", "imagery", "scroll") for op in ops)


def backups_dir(project: Project) -> Path:
    d = project.root / "directions" / "backups"
    d.mkdir(parents=True, exist_ok=True)
    return d


def apply(project: Project, d: Direction, log=print) -> dict:
    """Write direction `d` into site.yaml. Returns {changed: [paths], backup, diff, rev}."""
    with specdoc.lock(project):
        text = specdoc.read_text(project)
        raw = yaml.safe_load(text) or {}
        ops = ops_for(raw, d)
        if touches_copy(ops):                       # cannot happen from ops_for; the rule is checked anyway
            raise BuildError("a direction never changes copy")
        if not ops:
            return {"changed": [], "backup": None, "diff": "", "rev": specdoc.rev_of(text),
                    "note": f"site.yaml already has direction {d.id.upper()} ({d.name})"}
        new = compose_text(text, raw, ops)
        specdoc.validate(new)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        backup = backups_dir(project) / f"site-{stamp}-before-{d.id}.yaml"
        backup.write_bytes(text.encode("utf-8"))
        res = specdoc.save_text(project, new, label=f"pick direction {d.id}: {d.name}")
        diff = "".join(difflib.unified_diff(text.splitlines(True), new.splitlines(True), "site.yaml (before)", "site.yaml (after)", n=1))
        log(f"  picked {d.id.upper()} {d.name}: " + ", ".join(".".join(map(str, o.path)) for o in ops))
        return {"changed": [".".join(map(str, o.path)) for o in ops], "backup": str(backup), "diff": diff, "rev": res["rev"],
                "history": res.get("history")}


def undo(project: Project) -> dict:
    """Put back the site.yaml from before the last pick, if nothing has changed it since."""
    bdir = backups_dir(project)
    files = sorted(bdir.glob("site-*-before-*.yaml"))
    if not files:
        raise BuildError("no picked direction to undo (directions/backups is empty)")
    return specdoc.undo(project) | {"restored_from": str(files[-1])}
