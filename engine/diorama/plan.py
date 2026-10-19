"""From a `diorama` scene to a plan the page draws: the world's ground and props, the resolved places, and the camera's
beats (one per step: the world seen whole, or a dive to a place) with where in the scroll each rests."""
from __future__ import annotations

import math
from typing import Optional

import numpy as np

from . import recipes
from .recipes import HERO, WATER_KINDS, dress, pal_of, resolve_where, snap_free, face_default
from .world import GRID, World, forward, yaw_of

VERSION = 1


def _base_of(sec) -> str:
    return sec.world.base or ("round" if sec.world.kind in ("harbour", "town") else "square")


def step_windows(steps) -> list[tuple[float, float]]:
    """Where each step sits in the scene's progress (0-1): its share of the scroll, as the page lays the cards out."""
    total = sum(s.length for s in steps) or 1.0
    out, acc = [], 0.0
    for s in steps:
        out.append((acc / total, (acc + s.length) / total))
        acc += s.length
    return out


def resolve_places(w: World, sec, pal, rng) -> list[dict]:
    spots = dict(w.spots)
    used: set[str] = set()
    placed: list[dict] = []
    for i, pl in enumerate(sec.places):
        kind = pl.kind
        spot = None
        loc = resolve_where(w, pl.where, spots)
        if loc is not None:
            x, z, face = loc
            for name, sp in spots.items():
                if abs(sp.x - x) < 1e-6 and abs(sp.z - z) < 1e-6:
                    spot = sp
                    used.add(name)
        else:
            face = None
            want = [sp for n, sp in spots.items() if n not in used and (kind is None or kind in sp.kinds)
                    and (sp.water == (kind in WATER_KINDS))]
            if not want:
                want = [sp for n, sp in spots.items() if n not in used and not sp.water]
            if want:
                spot = want[0]
                used.add(spot.name)
                x, z, face = spot.x, spot.z, spot.face
            else:
                a = 2 * math.pi * i / max(len(sec.places), 1) + 0.6
                x, z = math.cos(a) * w.R * 0.55, math.sin(a) * w.R * 0.55
        if kind is None:
            kind = spot.kinds[0] if spot is not None and spot.kinds else "house"
        h, r = HERO.get(kind, (3.0, 2.0))
        water_kind = kind in WATER_KINDS
        if loc is not None and spot is None or (spot is None and loc is None):
            x, z = snap_free(w, x, z, r * pl.scale * 0.7, water_ok=water_kind)
        yaw = face if face is not None else face_default(w, x, z, water_pref=not water_kind)
        if pl.where is not None and not isinstance(pl.where, str) and face is None:
            yaw = face_default(w, x, z)
        rec = {"name": pl.name, "kind": kind, "x": x, "z": z, "yaw": yaw, "scale": pl.scale, "h": h * pl.scale,
               "r": r * pl.scale, "step": pl.step, "side": pl.side, "sign": pl.sign or pl.name, "color": pl.color}
        placed.append(rec)
    # the heroes first (they reserve their ground), then each place's dressing and sign
    for pl in placed:
        w.add(pl["kind"], pl["x"], pl["z"], pl["yaw"], pl["scale"], pl["color"], 0, pl["r"] * 0.9, place=placed.index(pl))
    for pl in placed:
        dress(sec.world.kind, w, pl, pal, rng)
        sx, sz = recipes.local(pl["x"], pl["z"], pl["yaw"], -(pl["r"] + 0.8), pl["r"] * 0.55 + 0.7)
        if not w.inside_pt(sx, sz, 0.3) or (w.water_at(sx, sz) and pl["kind"] not in WATER_KINDS):
            sx, sz = recipes.local(pl["x"], pl["z"], pl["yaw"], (pl["r"] + 0.8), pl["r"] * 0.55 + 0.7)
        w.add("sign", sx, sz, pl["yaw"], 0.8 + 0.12 * min(pl["scale"], 2), None, 0, 0.4, text=pl["sign"])
    return placed


def assign_steps(sec, placed: list[dict]) -> list[Optional[int]]:
    """For each step: the index of the place it lives at, or None for a wide beat (an intro, a closing step)."""
    n = len(sec.steps)
    out: list[Optional[int]] = [None] * n
    taken: set[int] = set()
    for pi, pl in enumerate(placed):
        if pl["step"] is not None and pl["step"] < n:
            out[pl["step"]] = pi
            taken.add(pi)
    # steps that name a place in their state
    names = {pl["name"].lower(): pi for pi, pl in enumerate(placed)}
    for si, st in enumerate(sec.steps):
        nm = str((st.state or {}).get("place", "")).lower()
        if nm and nm in names and out[si] is None and names[nm] not in taken:
            out[si] = names[nm]
            taken.add(names[nm])
    rest = [pi for pi in range(len(placed)) if pi not in taken]
    for si, st in enumerate(sec.steps):
        if out[si] is None and not st.intro and rest and not (st.state or {}).get("wide"):
            out[si] = rest.pop(0)
    return out


def camera_plan(w: World, sec, placed: list[dict], stepmap: list[Optional[int]]) -> dict:
    cam = sec.camera
    tan_half = math.tan(math.radians(cam.fov) / 2)
    beats = []
    prev_yaw: Optional[float] = None
    view_side = 1 if sec.side == "right" else -1
    if sec.layout == "overlay":
        view_side = 1
    for si, pi in enumerate(stepmap):
        if pi is not None:
            pl = placed[pi]
            gy = w.height_at(pl["x"], pl["z"])
            off = 24.0 * (1 if pi % 2 == 0 else -1)
            yaw = math.degrees(pl["yaw"]) + off
            fr = max(2.5 * pl["r"], min(pl["h"], 6.4) + 1.4)
            dist = fr / (0.72 * 2 * tan_half) / cam.dive
            side = {"left": -1, "right": 1}.get(pl["side"] or "", view_side)
            beats.append({"kind": "place", "place": pi, "yaw": yaw, "pitch": cam.dive_pitch, "dist": round(dist, 2),
                          "target": [round(pl["x"], 3), round(gy + min(pl["h"], 6.0) * 0.42, 3), round(pl["z"], 3)],
                          "side": side})
        else:
            beats.append({"kind": "wide", "yaw": None, "pitch": cam.pitch, "dist": None, "target": [0, 0.5, 0], "side": 0})
    # wide beats take their yaw from the neighbours: before the first place, 38 degrees behind it; after, 38 past it
    place_idx = [i for i, b in enumerate(beats) if b["kind"] == "place"]
    if place_idx:
        first, last = place_idx[0], place_idx[-1]
        for i, b in enumerate(beats):
            if b["kind"] != "wide":
                continue
            if i < first:
                b["yaw"] = beats[first]["yaw"] - 38.0
            elif i > last:
                b["yaw"] = beats[last]["yaw"] + 38.0
            else:
                lo = max(j for j in place_idx if j < i)
                hi = min(j for j in place_idx if j > i)
                b["yaw"] = (beats[lo]["yaw"] + beats[hi]["yaw"]) / 2
    else:
        for b in beats:
            b["yaw"] = 20.0
    # unwrap the yaws into one continuous orbit
    for b in beats:
        y = b["yaw"]
        if prev_yaw is None:
            b["yaw"] = round(y, 2)
        else:
            d = (y - prev_yaw) % 360.0
            if cam.orbit == "ccw":
                pass
            elif cam.orbit == "cw":
                d = d - 360.0 if d > 1e-6 else 0.0
            else:
                d = d - 360.0 if d > 180.0 else d
            b["yaw"] = round(prev_yaw + d, 2)
        prev_yaw = b["yaw"]
    wins = step_windows(sec.steps)
    for b, (a, c) in zip(beats, wins):
        b["a"], b["b"] = round(a, 5), round(c, 5)
    return {"fov": cam.fov, "pitch": cam.pitch, "dive_pitch": cam.dive_pitch, "hold": cam.hold, "drift": cam.drift,
            "fit": round(w.R * 1.14, 2), "beats": beats}


def build(sec, table: str, draft: bool = False):
    """The whole plan and the ground texture (uint8 N x N x 3) for a diorama scene."""
    wd = sec.world
    kind = wd.kind
    w = World(wd.size, _base_of(sec), wd.seed, wd.density, draft)
    pal = pal_of(w, wd.palette, kind)
    rng = np.random.default_rng(wd.seed + 101)
    info = recipes.setup(kind, w, pal, wd)
    placed = resolve_places(w, sec, pal, rng)
    recipes.fill(kind, w, pal, info, rng)
    for ex in wd.props:
        w.add(ex.kind, ex.at[0], ex.at[1], math.radians(ex.turn), ex.scale, ex.color, 0, 0.5 * ex.scale)
    w.finish_props()
    for pl in placed:
        pl["y"] = round(w.height_at(pl["x"], pl["z"]), 3)
    stepmap = assign_steps(sec, placed)
    camera = camera_plan(w, sec, placed, stepmap)
    hg = w.height_grid(GRID)
    plan = {
        "v": VERSION, "kind": kind, "size": wd.size, "base": w.base, "table": table,
        "water": {"level": w.water_level, "has": bool(w.has_water)},
        "grid": GRID, "heights": [round(float(v), 2) for v in hg.reshape(-1)],
        "props": w.props,
        "places": [{"name": p["name"], "kind": p["kind"], "x": round(p["x"], 3), "y": p["y"], "z": round(p["z"], 3),
                    "yaw": round(p["yaw"], 3), "h": round(p["h"], 2), "r": round(p["r"], 2), "sign": p["sign"]} for p in placed],
        "steps": stepmap,
        "camera": camera,
    }
    return plan, w.texture(), w
