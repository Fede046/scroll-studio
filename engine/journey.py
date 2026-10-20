"""The one-take page: the whole landing page as one camera journey through one generated world.

A `journey:` on a film section is written as stops (places) with the page's blocks at each. This module turns it into
what the engine already builds and plays:

  expand      stops -> the film, by one of two approaches (measured, see docs/ENGINE.md):
              chain   (no `blockout`) beats. The first stop is a frozen moment of a picture made from the world and its
                      place. Every later stop is a camera move (a keyed move on a moving shot, flown through the picture
                      before it and painted by the video model, so the place is *arrived at*, not cut to) followed by a
                      frozen moment of the frame it arrived at, with a slow parallax while the page holds. Every join is
                      on the same frame. The camera can only go into what the picture before it shows.
              take    (a `blockout`) one continuous take: the world as rough shapes, the camera a real 3D path through it
                      that rests at every stop, a picture of every stop painted over the blockout's depth and the video
                      model painting between them, cut at the middle of a hold (the camera is at rest there).
  plan        the segments of the journey, in order: a move to a stop and the hold at it, with their film seconds and the
              scroll each gets (a move plays as you scroll through it, a hold is the page resting at a stop).
  timeline    the map from scroll progress to film time, and each stop's window, from the rendered lengths.
  analyse     where a stop's blocks sit on its picture (the calmest part, found from the picture) and the lettering
              colour and scrim that keep them readable (contrast-checked against the picture under them).
  build       the stage the film builder runs after the beats are joined: stop stills (the reduced-motion and
              no-JavaScript page), the analysis and the config the runtime plays (runtime/src/players/journey.ts).

Nothing here is specific to one site: the world, the stops and their blocks all come from the spec.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Optional

FULL = (0.0, 0.0, 1.0, 1.0)
VERSION = 1
CONTRAST = 4.5                 # WCAG AA for body text: the lettering against the picture under it, scrim included


def hold_id(stop) -> str:
    return f"{stop.id}-hold"


def travel_id(stop) -> str:
    return f"{stop.id}-travel"


def stop_seed(j, i: int, stop, extra: int = 0) -> int:
    return (stop.seed if stop.seed is not None else j.seed + i * 17) + extra


# ---------------------------------------------------------------- stops -> beats

def _hold_keys(stop):
    from .spec import FreezeKey
    if stop.frame is not None:
        box = tuple(stop.frame)
    else:
        b = stop.breathe / 2
        box = (b, b, 1 - b, 1 - b)
    return [FreezeKey(t=0.0, box=FULL), FreezeKey(t=0.4, box=box, hold=0.2), FreezeKey(t=1.0, box=FULL)]


def _travel_keys(move):
    from .spec import FreezeKey
    into = tuple(move.into) if move.into else (0.33, 0.28, 0.67, 0.72)
    boxes = [FULL, *[tuple(v) for v in move.via], into]
    n = len(boxes) - 1
    return [FreezeKey(t=round(k / n, 4), box=b) for k, b in enumerate(boxes)]


def default_motion(place: str) -> str:
    return ("the camera glides forward in one smooth unbroken move and comes to rest, steady, nothing cuts; only mist, "
            "light and flame move")


def expand(sec) -> None:
    """Set `sec.beats` (and the scene's layout, length and fade) from `sec.journey`. Runs when the spec is validated."""
    from .spec import Beat, BeatFrame, CameraMove, Freeze, ImageEdit, ImageInput
    j = sec.journey
    for name in ("beats", "steps"):
        if getattr(sec, name):
            raise ValueError(f"film '{sec.id}': a journey makes the film and its captions; do not also write `{name}`")
    if sec.take is not None or sec.video or sec.shot:
        raise ValueError(f"film '{sec.id}': a journey makes the film; do not also write `take`, `shot` or `video`")
    if j.blockout is not None:
        return _expand_take(sec)
    W, H = sec.beat_res[0] // 32 * 32, sec.beat_res[1] // 32 * 32
    beats = []
    for i, stop in enumerate(j.stops):
        seed = stop_seed(j, i, stop)
        prev = j.stops[i - 1] if i else None
        if i:
            m = stop.move
            beats.append(Beat(
                id=travel_id(stop), seconds=m.seconds, seed=stop_seed(j, i, stop),
                prompt=f"{stop.world or j.world}. {stop.place}", motion=m.motion or default_motion(stop.place),
                image=ImageInput(beat_frame=BeatFrame(beat=hold_id(prev), at="last", pick="last")),
                camera=CameraMove(keys=_travel_keys(m), ease=m.ease, subjects="", parallax=m.parallax, anchor=m.anchor,
                                  guide_strength=m.guide_strength, res=m.res, seed=m.seed if m.seed is not None else seed)))
        if stop.still is not None:
            fz = Freeze(image=stop.still, pick="last", camera=_hold_keys(stop), ease="smoother", parallax=stop.parallax,
                        grain=j.grain, seed=seed)
        elif stop.edit:
            src = ImageInput(beat_frame=BeatFrame(beat=travel_id(stop), at="last", pick="last"))
            fz = Freeze(image=ImageInput(edit=ImageEdit(source=src, instruction=stop.edit, region=stop.region, seed=seed)),
                        pick="last", camera=_hold_keys(stop), ease="smoother", parallax=stop.parallax, grain=j.grain, seed=seed)
        elif i:
            fz = Freeze(**{"from": travel_id(stop)}, pick="last", camera=_hold_keys(stop), ease="smoother",
                        parallax=stop.parallax, grain=j.grain, seed=seed)
        else:
            fz = Freeze(image=ImageInput(generate=f"{stop.world or j.world}. {stop.place}", size=(W, H), seed=seed), pick="last",
                        camera=_hold_keys(stop), ease="smoother", parallax=stop.parallax, grain=j.grain, seed=seed)
        beats.append(Beat(id=hold_id(stop), seconds=stop.seconds, seed=seed, freeze=fz))
    sec.beats = beats
    sec.beat_fade = j.fade
    sec.beat_restore = j.restore
    _finish(sec)


def _finish(sec) -> None:
    sec.layout = "overlay"
    sec.steps = []
    sec.length = round(sum(w for _, _, _, w in weights(sec)) + 1.0, 3)
    for name in ("beats", "beat_fade", "beat_restore", "layout", "steps", "length", "take"):   # derived: not part of the spec as written
        sec.__pydantic_fields_set__.discard(name)


NEGATIVE = "cuts, jump cuts, flicker, warped shapes, morphing, text, watermark, people, blur"


def _expand_take(sec) -> None:
    """One continuous take: the blockout's world, a camera path that rests at every stop, a picture of each stop painted
    over the blockout's depth, the video model painting between them in stretches cut at the middle of a hold."""
    from .spec import Take
    j = sec.journey
    b = j.blockout
    segs = plan(sec)
    keys, t = [], 0.0

    def key(at, pose):
        keys.append({"t": round(at, 3), "at": list(pose.at), "look": list(pose.look)})
    key(0.0, j.stops[0].pose)
    centre, start_of, end_of = {}, {}, {}
    for _, kind, i, secs, _ in segs:
        stop = j.stops[i]
        if kind == "move":
            n = len(stop.move.path)
            for k, pose in enumerate(stop.move.path, 1):
                key(t + secs * k / (n + 1), pose)
            t += secs
            key(t, stop.pose)
        else:
            start_of[i], centre[i] = t, t + secs / 2
            t += secs
            end_of[i] = t
            key(t, stop.pose)
    total = t
    frames = []
    for i, stop in enumerate(j.stops):
        frames.append({"name": stop.id, "t": 0.0 if i == 0 else round(centre[i], 3), "prompt": f"{stop.world or j.world}. {stop.place}",
                       "strength": 1.0 if i == 0 else b.keyframe_strength, **({"seed": stop.seed} if stop.seed is not None else {})})

    def stop_at(x: float) -> int:
        for i in range(len(j.stops)):
            if x < end_of[i] - 1e-6:
                return i
        return len(j.stops) - 1
    cuts = [0.0] + [centre[i] for i in range(1, len(j.stops))] + [total]
    bounds = [cuts[0]]
    for a, z in zip(cuts, cuts[1:]):                    # a stretch longer than the video model likes is split evenly
        n = max(1, math.ceil((z - a) / b.segment - 1e-9))
        bounds += [a + (z - a) * k / n for k in range(1, n + 1)]
    if len(bounds) > 2 and bounds[-1] - bounds[-2] < 2.5 and bounds[-1] - bounds[-3] <= b.segment + 1.5:
        del bounds[-2]                                  # a short tail (the last hold's second half) joins the stretch before it
    segments = []
    for n, (a, z) in enumerate(zip(bounds, bounds[1:])):
        p, q = stop_at(a + 1e-3), stop_at(z - 1e-3)
        places = [j.stops[k].place for k in range(p, q + 1)]
        motion = next((j.stops[k].move.motion for k in range(q, p, -1) if j.stops[k].move.motion), None)
        text = (f"{j.world}. One continuous smooth shot. The camera rests on {places[0]}"
                + "".join(f", then glides on to {x}" for x in places[1:]) + f". {motion + '. ' if motion else ''}Steady, no cuts, photoreal, cinematic.")
        segments.append({"id": f"seg{n + 1}", "range": [round(a, 3), round(z, 3)], "prompt": text})
    sec.take = Take.model_validate({
        "duration": round(total, 3), "fps": 24, "sky": b.sky, "light": list(b.light),
        "ground": b.ground.model_dump(mode="json") if b.ground else None,
        "objects": [o.model_dump(mode="json") for o in b.objects], "camera": keys, "lens": b.lens, "depth_far": b.depth_far,
        "keyframes": {"control_strength": b.control_strength, "res": list(b.keyframe_res), "seed": j.seed, "by_depth": True,
                      "frames": frames},
        "ltx": {"res": list(b.ltx_res), "seed": j.seed, "guide_strength": b.guide_strength, "guide_blur": b.guide_blur,
                "sampler": "euler_cfg_pp", "negative_prompt": b.negative or NEGATIVE, "segments": segments},
        "restore": j.restore})
    _finish(sec)


# ---------------------------------------------------------------- scroll

def plan(sec) -> list[tuple[str, str, int, float, float]]:
    """(id, 'move' | 'hold', stop index, film seconds, scroll in screen heights) for every segment of the journey, in
    order. A chain's ids are its beats'."""
    j = sec.journey
    out = []
    for i, stop in enumerate(j.stops):
        if i:
            m = stop.move
            out.append((travel_id(stop), "move", i, m.seconds, (m.scroll if m.scroll is not None else m.seconds * 0.5) * j.pace))
        out.append((hold_id(stop), "hold", i, stop.seconds, stop.hold * j.pace))
    return out


def weights(sec) -> list[tuple[str, str, int, float]]:
    """(id, 'move' | 'hold', stop index, scroll in screen heights) of every segment (see `plan`)."""
    return [(a, b, c, e) for a, b, c, _, e in plan(sec)]


def timeline(sec, durs: list[float], fades: list[float]) -> dict:
    """Scroll progress -> film time, and each stop's window, from the beats' rendered lengths (seconds) and the overlap
    at each join. Beat k owns the film from the middle of the overlap before it to the middle of the one after it, so the
    segments tile the film and a stop's hold is exactly the frozen moment."""
    ws = weights(sec)
    assert len(ws) == len(durs), "one length per beat"
    total_w = sum(w for *_, w in ws)
    starts, t = [], 0.0
    for k, d in enumerate(durs):
        starts.append(t)
        t += d - (fades[k] if k < len(fades) else 0.0)
    total = t
    bounds = [0.0] + [starts[k] + fades[k - 1] / 2 for k in range(1, len(durs))] + [total]
    pts, acc = [[0.0, 0.0]], 0.0
    spans = {}
    for k, (bid, kind, si, w) in enumerate(ws):
        p0 = acc / total_w
        acc += w
        p1 = acc / total_w
        pts.append([round(p1, 5), round(bounds[k + 1], 4)])
        spans[bid] = (kind, si, p0, p1, bounds[k], bounds[k + 1])
    stops = []
    for i, stop in enumerate(sec.journey.stops):
        _, _, h0, h1, t0, t1 = spans[hold_id(stop)]
        if i:
            _, _, m0, _, _, _ = spans[travel_id(stop)]
        else:
            m0 = h0
        nxt = sec.journey.stops[i + 1] if i + 1 < len(sec.journey.stops) else None
        n1 = spans[travel_id(nxt)][3] if nxt else h1
        a = h0 - 0.45 * (h0 - m0) if i else 0.0        # blocks begin to arrive as the camera is slowing into the stop
        stops.append({"id": stop.id, "label": stop.label or stop.id.replace("-", " ").replace("_", " ").title(),
                      "p0": round(h0, 5), "p1": round(h1, 5), "t0": round(t0, 3), "t1": round(t1, 3),
                      "in": [round(max(a, 0.0), 5), round(h0 if i else 0.0, 5)],
                      "out": [round(h1, 5), round(h1 + 0.3 * (n1 - h1), 5)] if nxt else [2.0, 2.0],
                      "travel": [round(m0, 5), round(h0, 5)] if i else None})
    return {"duration": round(total, 4), "map": pts, "stops": stops}


# ---------------------------------------------------------------- the picture under the blocks

REGIONS = {"left": (0.04, 0.12, 0.47, 0.88), "right": (0.53, 0.12, 0.96, 0.88), "center": (0.24, 0.24, 0.76, 0.76),
           "top": (0.08, 0.05, 0.92, 0.36), "bottom": (0.08, 0.62, 0.92, 0.95)}


def _lum(rgb):
    """Relative luminance 0-1 of an sRGB uint8 array (WCAG)."""
    import numpy as np
    c = np.asarray(rgb, np.float32) / 255.0
    c = np.where(c <= 0.03928, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    return c[..., 0] * 0.2126 + c[..., 1] * 0.7152 + c[..., 2] * 0.0722


def _busyness(rgb):
    """Per-pixel detail: the gradient of the (lightly blurred) luminance, so edges and texture are busy, haze is calm."""
    import cv2
    import numpy as np
    g = cv2.GaussianBlur(cv2.cvtColor(np.ascontiguousarray(rgb), cv2.COLOR_RGB2GRAY).astype(np.float32) / 255.0, (0, 0), 1.2)
    gx, gy = cv2.Sobel(g, cv2.CV_32F, 1, 0, ksize=3), cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=3)
    return np.sqrt(gx * gx + gy * gy)


def _crop(a, box):
    h, w = a.shape[:2]
    x0, y0, x1, y1 = box
    return a[int(y0 * h):max(int(y1 * h), int(y0 * h) + 1), int(x0 * w):max(int(x1 * w), int(x0 * w) + 1)]


def analyse(rgb, side: str = "auto", surface: str = "auto", prev_side: Optional[str] = None,
            focus: Optional[tuple[float, float]] = None, ink: tuple[str, str] = ("#f4efe6", "#14110d")) -> dict:
    """Where a stop's blocks sit on its picture and how they are lettered. `rgb`: the picture (H x W x 3 uint8).

    auto side: of left, right and bottom, the region with the least detail (gradient energy) and the least tonal spread
    (a calm patch of wall, haze or sky), nudged off the side the previous stop used so the page alternates, and away
    from `focus`. auto surface: light lettering on a dark region, dark on a light one. Either way a scrim (a soft veil
    of the opposite tone behind the blocks) is raised until the lettering reaches WCAG AA against the 90th-percentile
    brightest (or darkest) pixel of the region."""
    import cv2
    import numpy as np
    small = cv2.resize(np.ascontiguousarray(rgb), (320, max(1, int(320 * rgb.shape[0] / rgb.shape[1]))), interpolation=cv2.INTER_AREA)
    busy, lum = _busyness(small), _lum(small)
    scores = {}
    for name in ("left", "right", "bottom"):
        box = REGIONS[name]
        s = float(_crop(busy, box).mean()) + 0.35 * float(_crop(lum, box).std())
        if prev_side == name:
            s *= 1.12
        if focus is not None and box[0] <= focus[0] <= box[2] and box[1] <= focus[1] <= box[3]:
            s *= 1.6
        scores[name] = s
    chosen = side if side != "auto" else min(scores, key=scores.get)
    box = REGIONS[chosen]
    reg = _crop(lum, box)
    mean = float(reg.mean())
    light_ink, dark_ink = (_lum(np.array([[_hex(ink[0])]], np.uint8))[0, 0], _lum(np.array([[_hex(ink[1])]], np.uint8))[0, 0])
    if surface == "auto":
        surface = "light" if mean > 0.34 else "dark"             # a light picture takes dark lettering
    ink_l = dark_ink if surface == "light" else light_ink
    veil = 1.0 if surface == "light" else 0.0                    # the scrim's own luminance: white under dark ink
    worst = float(np.percentile(reg, 10 if surface == "light" else 90))   # darkest pixel dark ink must clear / brightest light ink must clear
    scrim = 0.0
    for _ in range(40):
        eff = (1 - scrim) * worst + scrim * veil
        ratio = (max(ink_l, eff) + 0.05) / (min(ink_l, eff) + 0.05)
        if ratio >= CONTRAST or scrim >= 0.92:
            break
        scrim += 0.03
    eff = (1 - scrim) * worst + scrim * veil
    ratio = (max(ink_l, eff) + 0.05) / (min(ink_l, eff) + 0.05)
    return {"side": chosen, "surface": surface, "scrim": round(scrim, 3), "contrast": round(ratio, 2),
            "mean": round(mean, 3), "scores": {k: round(v, 4) for k, v in scores.items()}}


def _hex(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


# ---------------------------------------------------------------- the stage

def lettering(theme: Optional[dict]) -> tuple[str, str]:
    """(light, dark) lettering colours: the theme's ink and background, whichever is the lighter first."""
    import numpy as np
    c = (theme or {}).get("colors", {}) or {}
    a, b = c.get("ink") or "#f4efe6", c.get("bg") or "#14110d"
    la, lb = (float(_lum(np.array([[_hex(x)]], np.uint8))[0, 0]) for x in (a, b))
    return (a, b) if la >= lb else (b, a)


def stop_frame_times(tl: dict) -> dict[str, float]:
    """The film time to take each stop's still from: the middle of its hold."""
    return {s["id"]: round((s["t0"] + s["t1"]) / 2, 3) for s in tl["stops"]}


def build(sec, ctx, film: Path, cfg: dict, theme: Optional[dict] = None) -> dict:
    """Add `cfg['journey']` for the player and write the stop stills. Cached as the stage `journey` (a re-render of the
    film or an edit of the stops re-runs it; it takes seconds)."""
    from .project import file_key, ffmpeg, probe
    from .freeze_beats import beat_clip_path
    from .scenes.film import join_fades
    j = sec.journey
    if sec.take is not None:       # one take: the segments are the plan, stretched to the film's real length
        nominal = [x[3] for x in plan(sec)]
        k = float(probe(film)["duration"]) / sum(nominal)
        durs, fades = [d * k for d in nominal], [0.0] * (len(nominal) - 1)
    else:
        durs = [float(probe(beat_clip_path(ctx.project, sec, b))["duration"]) for b in sec.beats]
        fades = join_fades(sec, durs)
    tl = timeline(sec, durs, fades)
    times = stop_frame_times(tl)
    ink = lettering(theme)
    sdir = ctx.web / "stops"
    out = ctx.work / "journey.json"
    outs = [out] + [sdir / f"{s.id}.jpg" for s in j.stops]
    key = {"film": file_key(film), "tl": tl, "stops": j.model_dump(mode="json", include={"stops": {"__all__": {"id", "side", "surface", "focus", "label"}}}), "v": VERSION}

    def run():
        import numpy as np
        from PIL import Image
        sdir.mkdir(parents=True, exist_ok=True)
        info, prev = {}, None
        for s in j.stops:
            jpg = sdir / f"{s.id}.jpg"
            ffmpeg("-ss", f"{times[s.id]:.3f}", "-i", film, "-frames:v", "1", "-vf", "scale='min(1920,iw)':-2", "-q:v", "2", jpg, log=ctx.log)
            rgb = np.asarray(Image.open(jpg).convert("RGB"))
            a = analyse(rgb, s.side, s.surface, prev, s.focus, ink)
            info[s.id] = a
            prev = a["side"]
            ctx.log(f"  stop {s.id}: blocks on the {a['side']}, {a['surface']} surface, scrim {a['scrim']}, contrast {a['contrast']}")
        out.write_text(json.dumps(info, indent=1))
    ctx.stage("journey", key, outs, run)
    info = json.loads(out.read_text())
    stops = []
    for s, t in zip(j.stops, tl["stops"]):
        a = info[s.id]
        stops.append({**t, "still": ctx.url(sdir / f"{s.id}.jpg"), "side": a["side"], "surface": a["surface"],
                      "scrim": a["scrim"], "focus": list(s.focus) if s.focus else None, "place": s.place})
    cfg["journey"] = {"duration": tl["duration"], "map": tl["map"], "stops": stops, "rail": j.rail,
                      "ink": {"light": ink[0], "dark": ink[1]}}
    return cfg


def describe(sec) -> list[dict]:
    """The journey as a table (`studio journey`): every segment, what it is, how long in the film and in scroll."""
    rows = []
    for sid, kind, i, secs, w in plan(sec):
        stop = sec.journey.stops[i]
        rows.append({"segment": sid, "kind": kind, "stop": stop.id, "film_seconds": secs, "scroll_screens": round(w, 2),
                     "blocks": [x.type for x in stop.blocks] if kind == "hold" else []})
    return rows


def report(project, section: Optional[str] = None) -> list[dict]:
    """Every journey of a project (or of one section): its approach, the plan table, the totals and, once the film is built,
    where each stop's blocks were put and the contrast they reach (`.build/<section>/journey.json`)."""
    from .project import BuildError
    site = project.load()
    out = []
    for sec in site.sections:
        if getattr(sec, "journey", None) is None or (section and sec.id != section):
            continue
        rows = describe(sec)
        built = project.build / sec.id / "journey.json"
        placed = json.loads(built.read_text()) if built.exists() else {}
        out.append({"section": sec.id, "approach": "take" if sec.journey.blockout else "chain",
                    "film_seconds": round(sum(r["film_seconds"] for r in rows), 2),
                    "scroll_screens": round(sum(r["scroll_screens"] for r in rows) + 1, 2),
                    "segments": rows, "placed": placed})
    if not out:
        raise BuildError("no journey in this project" + (f" section '{section}'" if section else ""))
    return out
