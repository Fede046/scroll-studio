"""The editable model of a storyboard: shots, the images (slots) they show, and the fields behind both.

Built from site.yaml alone (nothing renders, nothing is probed), so it is cheap enough to rebuild on every request.
Every field knows the YAML path it is written to (`specdoc.Op`), so a save is "these paths got these values", and
every image knows the chain of generators behind it:

  shot      one card: a beat, a take, a block's image(s), theme.art. Ids are the storyboard's own card ids, so the
            sheet, the approvals and `studio build --only` all speak of the same shots.
  slot      one image a shot shows: a beat's start or end image, a take's keyframe, a hero image, a strip item.
  node      one step of the chain that makes a slot's image: `generate` (prompt, seed), `edit` (instruction, seed,
            steps) on top of another node, a product still, a gradient, a file, or a take keyframe. A beat that
            animates its own `prompt` has a one-node chain whose fields are the beat's prompt and seed.

A node whose whole recipe (its own settings and everything under it) is the same in several places is *shared*: the
base image of a run of crop edits, say. Cards show only the nodes unique to their shot; shared ones are listed once,
at the top, and an edit to one is written to every place it appears.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any, Optional, get_args

import yaml

from ...inputs import image_key
from ...plan import image_refs, section_locked
from ...project import Project
from ...spec import FilmScene, ImageInput, Site, is_scene
from . import specdoc
from .specdoc import MISSING, dotted

# recipe fields that name what a node draws (they are restored when an older variant is picked)
TEXT, AREA, INT, FLOAT, BOOL, SELECT = "text", "area", "int", "float", "bool", "select"


@dataclass
class Fld:
    name: str                       # short and unique within a shot: "prompt", "seed", "still.instruction"
    label: str
    type: str
    paths: list[tuple]              # where it is written (several when a shared node appears in several places)
    raw: Any = None                 # what the file holds at paths[0] now (None when the key is absent)
    value: Any = None               # what the engine uses (the default when the key is absent)
    options: Optional[list] = None
    hint: str = ""
    recipe: bool = False            # part of what draws the image (restored with an older variant)
    hidden: bool = False            # shown elsewhere on the card
    readonly: bool = False
    attr: Optional[tuple] = None    # attribute path on the ImageInput, to try a recipe in memory

    @property
    def path(self) -> tuple:
        return self.paths[0]

    def public(self) -> dict:
        return {"name": self.name, "label": self.label, "type": self.type, "paths": [dotted(p) for p in self.paths],
                "raw": self.raw, "value": self.value, "options": self.options, "hint": self.hint,
                "readonly": self.readonly, "hidden": self.hidden}


@dataclass
class Node:
    kind: str                       # generate | edit | product | gradient | file | keyframe
    label: str
    ref: Any = None                 # the ImageRef that draws it (None for a keyframe)
    alpha: bool = False
    fields: list[Fld] = field(default_factory=list)
    sig: str = ""
    depth: int = 0                  # 0 = the slot's own (outermost) node
    summary: str = ""
    regen: bool = False             # a new seed gives a different image
    key: str = ""                   # variant store key (see Board.finish)
    shared: bool = False
    used_by: list[str] = field(default_factory=list)
    extra: dict = field(default_factory=dict)

    def field(self, name: str) -> Optional[Fld]:
        return next((f for f in self.fields if f.name == name), None)

    def recipe(self) -> dict:
        return {f.name.split(".")[-1]: f.value for f in self.fields if f.recipe}

    def recipe_paths(self) -> dict[str, list[tuple]]:
        return {f.name.split(".")[-1]: f.paths for f in self.fields if f.recipe}

    @property
    def seed_field(self) -> Optional[Fld]:
        return next((f for f in self.fields if f.recipe and f.name.split(".")[-1] == "seed"), None)


@dataclass
class Slot:
    id: str                         # "door/still"
    name: str                       # "still"
    label: str                      # "start image"
    shot: str
    nodes: list[Node] = field(default_factory=list)
    alpha: bool = False

    @property
    def top(self) -> Node:
        return self.nodes[0]

    @property
    def key(self) -> str:
        return self.nodes[0].key


@dataclass
class Shot:
    id: str
    section: str
    kind: str
    title: str
    index: int = -1                 # position of the section in sections
    fields: list[Fld] = field(default_factory=list)
    slots: list[Slot] = field(default_factory=list)
    lock_paths: list[tuple] = field(default_factory=list)
    locked: bool = False
    seconds: float = 0.0
    note: str = ""

    def field(self, name: str) -> Optional[Fld]:
        for f in self.fields:
            if f.name == name:
                return f
        for s in self.slots:
            for n in s.nodes:
                for f in n.fields:
                    if f.name == name:
                        return f
        return None

    def all_fields(self) -> list[Fld]:
        out = list(self.fields)
        for s in self.slots:
            for n in s.nodes:
                out += n.fields
        return out

    def sig(self) -> str:
        """Changes when anything about the shot changes: what the approval is tied to."""
        body = [[dotted(f.path), f.raw] for f in self.all_fields()] + [self.locked]
        return hashlib.sha1(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()[:14]


@dataclass
class Board:
    project: Project
    site: Site
    raw: dict
    text: str
    rev: str
    shots: list[Shot] = field(default_factory=list)
    shared: list[Node] = field(default_factory=list)       # nodes that appear in several slots, not as a slot's own

    def shot(self, sid: str) -> Optional[Shot]:
        return next((s for s in self.shots if s.id == sid), None)

    def slot(self, slot_id: str) -> Optional[Slot]:
        for s in self.shots:
            for sl in s.slots:
                if sl.id == slot_id:
                    return sl
        return None

    def node(self, key: str) -> Optional[tuple[Node, Optional[Shot], Optional[Slot]]]:
        for s in self.shots:
            for sl in s.slots:
                for n in sl.nodes:
                    if n.key == key:
                        return n, s, sl
        return None

    def allowed_paths(self) -> set[str]:
        out = set()
        for s in self.shots:
            for f in s.all_fields():
                out.update(dotted(p) for p in f.paths)
        return out

    def lock_ops(self, shot: Shot, locked: bool) -> list[specdoc.Op]:
        if locked:
            return [specdoc.Op(shot.lock_paths[0], True)] if shot.lock_paths else []
        ops = []
        for p in shot.lock_paths:
            if specdoc.get(self.raw, p) is True:
                ops.append(specdoc.Op(p, False))
        return ops


# ---------------------------------------------------------------- helpers

def _plain(text: Optional[str]) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text or "")).strip()


class _B:
    """Field maker bound to the raw YAML."""
    def __init__(self, raw: dict):
        self.raw = raw

    def got(self, path) -> Any:
        v = specdoc.get(self.raw, path)
        return None if v is MISSING else v

    def fld(self, name, label, type_, path, value=None, **kw) -> Fld:
        raw = self.got(path)
        return Fld(name, label, type_, [tuple(path)], raw, raw if value is None else value, **kw)


def _sig(obj) -> str:
    return hashlib.sha1(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()[:16]


def _view_options() -> list[str]:
    from ...spec import ProductView
    return list(get_args(ProductView))


# ---------------------------------------------------------------- image chains

def _node_for(b: _B, m: ImageInput, path: tuple, alpha: bool, prefix: str, depth: int) -> Node:
    """The node an ImageInput is (the same precedence `resolve_image` uses; a `crop` rides on whichever it wraps)."""
    from ...spec import ProductShot
    P = tuple(path)
    n = Node("generate", "", ref=m, alpha=alpha, depth=depth)
    n.sig = _sig([image_key(m), alpha])
    if m.product is not None:
        shot = m.product if isinstance(m.product, ProductShot) else None
        praw = b.got(P + ("product",))
        is_map = isinstance(praw, dict)
        scene_val = (shot.scene if shot is not None else None) or m.scene
        has_scene = bool(scene_val)
        n.kind, n.label = "product", "product in a scene" if has_scene else "product still"
        view = shot.view if shot is not None else m.product
        n.fields.append(b.fld(f"{prefix}.view", "view", SELECT, P + ("product", "view") if is_map else P + ("product",),
                              view, options=_view_options(), recipe=True,
                              attr=("product", "view") if is_map else ("product",)))
        if is_map and "scene" in praw or (b.got(P + ("scene",)) is None and is_map):
            sp, sattr = P + ("product", "scene"), ("product", "scene")
        else:
            sp, sattr = P + ("scene",), ("scene",)
        n.fields.append(b.fld(f"{prefix}.scene", "scene (the place it stands in)", AREA, sp, scene_val or "", recipe=True,
                              attr=sattr, hint="a prompt; empty = a studio light, no generated scene"))
        if is_map and ("seed" in praw or "scene" in praw):
            seed_p, seed_attr = P + ("product", "seed"), ("product", "seed")
            seed_v = shot.seed if shot is not None and "seed" in shot.model_fields_set else m.seed
        else:
            seed_p, seed_attr, seed_v = P + ("seed",), ("seed",), m.seed
        n.fields.append(b.fld(f"{prefix}.seed", "seed", INT, seed_p, seed_v, recipe=True, attr=seed_attr))
        if is_map:
            for key, lab in (("zoom", "zoom"), ("yaw", "yaw"), ("pitch", "pitch")):
                cur = getattr(shot, key, None) if shot is not None else None
                n.fields.append(b.fld(f"{prefix}.{key}", lab, FLOAT, P + ("product", key), 1.0 if (cur is None and key == "zoom") else cur,
                                      recipe=True, attr=("product", key)))
        n.regen = has_scene
        n.summary = f"{view}" + (f" in: {scene_val}" if has_scene else "")
        return n
    if m.file:
        n.kind, n.label = "file", "file"
        n.fields.append(b.fld(f"{prefix}.file", "file", TEXT, P + ("file",), m.file, attr=("file",), readonly=False))
        n.summary = m.file
        return n
    if m.edit:
        e = m.edit
        n.kind, n.label = "edit", "edit"
        n.fields += [
            b.fld(f"{prefix}.instruction", "edit instruction", AREA, P + ("edit", "instruction"), e.instruction,
                  recipe=True, attr=("edit", "instruction")),
            b.fld(f"{prefix}.seed", "seed", INT, P + ("edit", "seed"), e.seed, recipe=True, attr=("edit", "seed")),
            b.fld(f"{prefix}.steps", "steps", INT, P + ("edit", "steps"), e.steps, recipe=True, attr=("edit", "steps"))]
        n.regen = True
        n.summary = e.instruction + (f"  (+{len(e.refs)} reference image{'s' if len(e.refs) > 1 else ''})" if e.refs else "")
        return n
    if m.gradient:
        n.kind, n.label, n.regen = "gradient", "gradient", True
        n.fields.append(b.fld(f"{prefix}.seed", "seed (stars, grain)", INT, P + ("seed",), m.seed, recipe=True, attr=("seed",)))
        n.summary = "gradient " + " > ".join(m.gradient.colors)
        return n
    n.kind, n.label, n.regen = "generate", "generate", True
    n.fields += [
        b.fld(f"{prefix}.prompt", "prompt", AREA, P + ("generate",), m.generate, recipe=True, attr=("generate",)),
        b.fld(f"{prefix}.seed", "seed", INT, P + ("seed",), m.seed, recipe=True, attr=("seed",))]
    n.summary = m.generate or ""
    return n


def chain(b: _B, ref, path: tuple, alpha: bool, prefix: str) -> list[Node]:
    """The nodes behind an image ref, outermost first. `path` is where the ref sits in the YAML."""
    nodes: list[Node] = []
    cur, cpath = ref, tuple(path)
    while True:
        if isinstance(cur, str):
            n = Node("file", "file", ref=cur, alpha=alpha, depth=len(nodes), summary=cur)
            n.sig = _sig([cur, alpha])
            name = f"{prefix}.file" if not nodes else f"{prefix}@{len(nodes)}.file"
            n.fields.append(b.fld(name, "file", TEXT, cpath, cur, attr=None))
            nodes.append(n)
            return nodes
        pre = prefix if not nodes else f"{prefix}@{len(nodes)}"
        n = _node_for(b, cur, cpath, alpha, pre, len(nodes))
        nodes.append(n)
        if cur.product is None and not cur.file and cur.edit:
            cur, cpath = cur.edit.source, cpath + ("edit", "source")
            continue
        return nodes


def _beat_nodes(b: _B, sec: FilmScene, i: int, j: int, beat) -> list[Node]:
    """A beat's start image: its `image` chain, or (no `image:`) the still its own prompt and seed draw."""
    bp = ("sections", i, "beats", j)
    if beat.image is not None:
        return chain(b, beat.image, bp + ("image",), False, "still")
    W, H = sec.beat_res[0] // 32 * 32, sec.beat_res[1] // 32 * 32
    ref = ImageInput(generate=beat.prompt, size=(W, H), seed=beat.seed)
    n = Node("generate", "generate", ref=ref, regen=True, summary=beat.prompt)
    n.sig = _sig([image_key(ref), False, "beat", i, j])      # a beat's own still is never shared
    n.fields += [b.fld("still.prompt", "prompt", AREA, bp + ("prompt",), beat.prompt, recipe=True, hidden=True, attr=("generate",)),
                 b.fld("still.seed", "seed", INT, bp + ("seed",), beat.seed, recipe=True, hidden=True, attr=("seed",))]
    return [n]


# ---------------------------------------------------------------- the board

def _captions(b: _B, steps, base: tuple, only_beat: Optional[str] = None) -> list[Fld]:
    out = []
    n = 0
    for k, st in enumerate(steps):
        if only_beat is not None and (st.state or {}).get("beat") != only_beat:
            continue
        if not st.title:
            continue
        n += 1
        out.append(b.fld("caption" if n == 1 else f"caption{n}", "caption" if n == 1 else f"caption {n}", TEXT,
                         base + ("steps", k, "title"), st.title, hint="HTML allowed: <em>accent words</em>"))
    return out


def build(project: Project) -> Board:
    text = specdoc.read_text(project)
    raw = yaml.safe_load(text) or {}
    site = Site.model_validate(raw)
    b = _B(raw)
    board = Board(project, site, raw, text, specdoc.rev_of(text))
    for i, sec in enumerate(site.sections):
        sp = ("sections", i)
        try:
            board.shots += _section(b, board, sec, i, sp)
        except Exception as e:           # one odd section never hides the others
            sid = getattr(sec, "id", None) or sec.type
            board.shots.append(Shot(sid, sid, sec.type, sid, i, note=f"could not be read for editing: {type(e).__name__}: {e}"))
    if site.theme.art:
        board.shots.append(_art(b, site))
    finish(board)
    return board


def _lock_paths(sec, sp: tuple, take_path: Optional[tuple] = None) -> list[tuple]:
    paths = []
    if take_path is not None:
        paths.append(take_path + ("locked",))
    if is_scene(sec):
        paths.append(sp + ("locked",))
    return paths


def _section(b: _B, board: Board, sec, i: int, sp: tuple) -> list[Shot]:
    out: list[Shot] = []
    if is_scene(sec):
        if sec.type == "film":
            out += _film(b, sec, i, sp)
        elif sec.type == "artwork":
            out.append(_scene_images(b, sec, i, sp, [("image", sec.image, ("image",), False)], f"{sec.id} (artwork)"))
        elif sec.type == "vector" and sec.image:
            out.append(_scene_images(b, sec, i, sp, [("image", sec.image, ("image",), False)], f"{sec.id} (vector)"))
        elif sec.type == "parallax":
            refs = [(f"photo{k + 1}", st.image, ("steps", k, "image"), False) for k, st in enumerate(sec.steps) if st.image is not None]
            if refs:
                out.append(_scene_images(b, sec, i, sp, refs, f"{sec.id} (parallax)"))
        elif sec.type in ("sequence", "showroom"):
            s = Shot(sec.id, sec.id, sec.type, f"{sec.id} ({'product turn' if sec.type == 'sequence' else 'live 3D'})", i,
                     fields=_captions(b, sec.steps, sp), lock_paths=_lock_paths(sec, sp), locked=section_locked(sec),
                     note="rendered by Blender / three.js: nothing to regenerate here")
            out.append(s)
    if not is_scene(sec) or sec.type in ("type", "chart", "code", "map", "scene3d", "splat"):
        sh = _block(b, board, sec, i, sp)
        if sh is not None:
            out.append(sh)
    return out


def _scene_images(b: _B, sec, i: int, sp: tuple, refs, title: str) -> Shot:
    s = Shot(sec.id, sec.id, "image", title, i, fields=_captions(b, sec.steps, sp), lock_paths=_lock_paths(sec, sp),
             locked=section_locked(sec))
    for name, ref, rel, alpha in refs:
        s.slots.append(_slot(b, s, name, name, ref, sp + rel, alpha))
    return s


def _slot(b: _B, shot: Shot, name: str, label: str, ref, path: tuple, alpha: bool) -> Slot:
    sl = Slot(f"{shot.id}/{name}", name, label, shot.id, alpha=alpha)
    sl.nodes = chain(b, ref, path, alpha, name)
    return sl


def _block(b: _B, board: Board, sec, i: int, sp: tuple) -> Optional[Shot]:
    refs = image_refs(sec)
    if not refs:
        return None
    sid = getattr(sec, "id", None) or f"{sec.type}-{i + 1}"
    paths = {"backdrop": ("backdrop",), "image": ("image",), "screen": ("device", "image"), "behind": ("behind", "image")}
    s = Shot(sid, sid, "product" if any(not isinstance(r, str) and getattr(r, "product", None) is not None for _, r, _ in refs)
             else "image", f"{sid} ({sec.type})", i, locked=bool(getattr(sec, "locked", False)))
    if specdoc.get(b.raw, sp + ("title",)) is not MISSING and getattr(sec, "title", None):
        s.fields.append(b.fld("caption", "title", TEXT, sp + ("title",), sec.title, hint="HTML allowed: <em>accent words</em>"))
    for label, ref, alpha in refs:
        if label in paths:
            rel, name = paths[label], label
        elif label.startswith("item "):
            k = int(label.split()[1]) - 1
            rel, name = ("items", k, "image"), f"item{k + 1}"
        else:
            continue
        s.slots.append(_slot(b, s, name, label, ref, sp + rel, alpha))
    return s


def _art(b: _B, site: Site) -> Shot:
    art = site.theme.art
    ap = ("theme", "art")
    s = Shot("theme-art", "theme.art", "art", "theme.art", -1)
    sl = Slot("theme-art/image", "image", "art image", s.id)
    if art.file:
        sl.nodes = chain(b, art.file, ap + ("file",), False, "image")
    else:
        ref = ImageInput(generate=art.prompt, size=art.size, seed=art.seed)
        n = Node("generate", "generate", ref=ref, regen=True, summary=art.prompt or "")
        n.sig = _sig([image_key(ref), False, "art"])
        n.fields += [b.fld("image.prompt", "prompt", AREA, ap + ("prompt",), art.prompt, recipe=True, attr=("generate",)),
                     b.fld("image.seed", "seed", INT, ap + ("seed",), art.seed, recipe=True, attr=("seed",))]
        sl.nodes = [n]
    s.slots.append(sl)
    if art.motion:
        s.fields.append(b.fld("motion", "motion", AREA, ap + ("motion",), art.motion))
        s.fields.append(b.fld("seconds", "seconds", FLOAT, ap + ("seconds",), art.seconds))
        s.seconds = art.seconds
    return s


def _film(b: _B, sec: FilmScene, i: int, sp: tuple) -> list[Shot]:
    if sec.video:
        return [Shot(sec.id, sec.id, "video", sec.id, i, fields=_captions(b, sec.steps, sp), lock_paths=_lock_paths(sec, sp),
                     locked=section_locked(sec), note=f"film: {sec.video}")]
    if sec.beats:
        out = []
        for j, bt in enumerate(sec.beats):
            bp = sp + ("beats", j)
            virtual = bt.image is None
            s = Shot(bt.id, sec.id, "beat", f"{sec.id} / {bt.id}", i, seconds=bt.seconds - bt.trim,
                     lock_paths=[bp + ("locked",), sp + ("locked",)], locked=bt.locked or sec.locked)
            s.fields += _captions(b, sec.steps, sp, only_beat=bt.id)
            s.fields.append(b.fld("prompt", "prompt" if virtual else "motion prompt", AREA, bp + ("prompt",), bt.prompt,
                                  hint=("draws the opening frame and steers the motion" if virtual
                                        else "steers the motion (the opening frame comes from the image below)")))
            s.fields.append(b.fld("motion", "motion", AREA, bp + ("motion",), bt.motion))
            s.fields.append(b.fld("seconds", "seconds", FLOAT, bp + ("seconds",), bt.seconds, hint="1 to 10"))
            if virtual:
                s.fields.append(b.fld("seed", "seed", INT, bp + ("seed",), bt.seed,
                                      hint="the still's seed; also the motion's unless motion_seed is set"))
            else:
                s.fields.append(b.fld("seed", "motion seed base", INT, bp + ("seed",), bt.seed,
                                      hint="seeds the motion (the image has its own seeds below)"))
            s.fields.append(b.fld("trim", "trim", FLOAT, bp + ("trim",), bt.trim, hint="seconds cut from the clip's start"))
            s.fields.append(b.fld("strength", "strength", FLOAT, bp + ("strength",), bt.strength, hint="0.3 to 1"))
            s.fields.append(b.fld("motion_seed", "motion seed", INT, bp + ("motion_seed",), bt.motion_seed,
                                  hint="re-rolls the motion and keeps the still"))
            start = Slot(f"{bt.id}/still", "still", "start image", s.id)
            start.nodes = _beat_nodes(b, sec, i, j, bt)
            s.slots.append(start)
            if bt.end_image is not None:
                end = Slot(f"{bt.id}/end", "end", "end image", s.id)
                end.nodes = chain(b, bt.end_image, bp + ("end_image",), False, "end")
                s.slots.append(end)
            out.append(s)
        return out
    return [_take(b, sec, i, sp)]


def _take(b: _B, sec: FilmScene, i: int, sp: tuple) -> Shot:
    take = sec.take
    tp = sp + ("take",) if take else sp + ("shot",)
    d = take.model_dump(mode="json") if take else dict(sec.shot)
    s = Shot(sec.id, sec.id, "take" if take else "shot", f"{sec.id} (one take)" if take else sec.id, i,
             seconds=float(d.get("duration") or 10), lock_paths=_lock_paths(sec, sp, tp if take else None),
             locked=section_locked(sec))
    s.fields += _captions(b, sec.steps, sp)
    if d.get("duration") is not None:
        s.fields.append(b.fld("duration", "seconds", FLOAT, tp + ("duration",), float(d["duration"]),
                              hint="changes the camera timing; keyframe times are in seconds"))
    for k, seg in enumerate((d.get("ltx") or {}).get("segments") or []):
        s.fields.append(b.fld(f"motion.{seg.get('id', k)}", f"motion {seg.get('id', k)} ({seg['range'][0]:g}-{seg['range'][1]:g} s)",
                              AREA, tp + ("ltx", "segments", k, "prompt"), seg.get("prompt", "")))
    kf = d.get("keyframes") or {}
    for k, fr in enumerate(kf.get("frames") or []):
        name = fr["name"]
        base = tp + ("keyframes", "frames", k)
        pre = f"key.{name}"
        n = Node("keyframe", f"keyframe {name} @ {fr['t']}" + ("" if fr["t"] == "end" else " s"), regen=True, depth=0,
                 summary=fr.get("prompt", ""))
        n.sig = _sig(["keyframe", i, name])
        n.fields += [
            b.fld(f"{pre}.prompt", "prompt", AREA, base + ("prompt",), fr.get("prompt", ""), recipe=True),
            b.fld(f"{pre}.seed", "seed", INT, base + ("seed",), fr.get("seed", kf.get("seed", 7)), recipe=True,
                  hint="the keyframes' shared seed unless this one is set"),
            b.fld(f"{pre}.control_strength", "depth control", FLOAT, base + ("control_strength",),
                  fr.get("control_strength", kf.get("control_strength", 0.8)), recipe=True, hint="0 to 1"),
            b.fld(f"{pre}.t", "time", FLOAT if not isinstance(fr["t"], str) else TEXT, base + ("t",), fr["t"], recipe=True,
                  readonly=isinstance(fr["t"], str))]
        n.extra = {"section": sec.id, "section_index": i, "frame": name, "frame_index": k, "take_path": list(tp)}
        sl = Slot(f"{sec.id}/key.{name}", f"key.{name}", f"keyframe {name} @ {fr['t']}" + ("" if fr["t"] == "end" else " s"), s.id)
        sl.nodes = [n]
        s.slots.append(sl)
    return s


# ---------------------------------------------------------------- shared nodes and variant keys

def _safe(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", s)


def finish(board: Board) -> None:
    """Give every node its variant-store key and find the nodes shared between slots."""
    first: dict[str, tuple[Slot, int]] = {}
    users: dict[str, list[str]] = {}
    for sh in board.shots:
        for sl in sh.slots:
            for n in sl.nodes:
                if n.kind == "keyframe":
                    n.key = f"{_safe(sh.id)}/{_safe(sl.name)}"
                    continue
                if n.sig not in first:
                    first[n.sig] = (sl, n.depth)
                    n.key = f"{_safe(sl.shot)}/{_safe(sl.name)}" + (f"~{n.depth}" if n.depth else "")
                else:
                    osl, od = first[n.sig]
                    n.key = f"{_safe(osl.shot)}/{_safe(osl.name)}" + (f"~{od}" if od else "")
                users.setdefault(n.sig, []).append(sh.id)
    # merge the fields of identical nodes so an edit reaches every place the node is written
    by_sig: dict[str, list[Node]] = {}
    for sh in board.shots:
        for sl in sh.slots:
            for n in sl.nodes:
                if n.kind != "keyframe":
                    by_sig.setdefault(n.sig, []).append(n)
    for sig, ns in by_sig.items():
        if len(ns) < 2 or ns[0].kind == "file":
            continue
        used = list(dict.fromkeys(users[sig]))
        for n in ns:
            n.shared, n.used_by = True, used
        for f0 in ns[0].fields:
            for other in ns[1:]:
                f1 = next((f for f in other.fields if f.name.split(".")[-1] == f0.name.split(".")[-1]), None)
                if f1 is not None:
                    for p in f1.paths:
                        if p not in f0.paths:
                            f0.paths.append(p)
        for n in ns[1:]:
            for f in n.fields:
                f0 = next((g for g in ns[0].fields if g.name.split(".")[-1] == f.name.split(".")[-1]), None)
                if f0 is not None:
                    f.paths = f0.paths
    outer = {n.sig for sh in board.shots for sl in sh.slots for n in sl.nodes[:1]}
    seen = set()
    for sh in board.shots:
        for sl in sh.slots:
            for n in sl.nodes:
                if n.shared and n.sig not in outer and n.key not in seen:
                    seen.add(n.key)
                    board.shared.append(n)
