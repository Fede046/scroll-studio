"""cuts_shapes: the engine's half of a match cut. Finds the shape that ends one section and the shape that starts the next.

  picture   the picture a section shows at its first or last moment, as the page fits it.
  shapes    from a prompt (Florence-2 finds it, SAM 2.1 cuts it out: engine/region.py), from a box, or, when nothing is
            named, from the picture itself: flat regions (colour clusters) that are big enough to read, compact and
            stand out, paired by outline (Hu moments), size and place.
  analyse   anchors for every match cut of a site, cached in `.build/_cuts/` by the two pictures and what names the shapes.

An anchor is `{box: [x0, y0, x1, y1] in 0-1 of the picture, aspect, of?, fit?, scale?}`; the page maps it to the screen
the way the section fits that picture (runtime/src/lib/cuts-match.ts). `{sel: "<css>"}` names a page element instead.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Callable, Optional

VERSION = 1          # bump when the shapes found for the same pictures would come out differently
WORK = 640           # the long side shapes are looked for at when no model is involved

# the slow dolly a parallax photo ends in or starts in (runtime/src/players/parallax.ts MOVES at t=1 / t=0)
_PARALLAX_ZOOM = {"dolly": (1.04, 1.14), "pan": (1.08, 1.08), "orbit": (1.07, 1.07), "rise": (1.06, 1.09)}


# ---------------------------------------------------------------- pictures

def _published(project, dist, url: str) -> Optional[Path]:
    for base in ([Path(dist)] if dist else []) + [project.dist]:
        if (base / url).exists():
            return base / url
    return None


def picture(project, entry: dict, which: str, dist=None) -> Optional[dict]:
    """The picture a section shows at its `first` or `last` moment, as the page fits it: {path, of, fit, scale}. A scene's
    poster and end frame, a hero's or product's image, a section's backdrop; None when the section has no picture (a block
    of text: its shapes are page elements, named with a selector)."""
    s = entry["s"]
    cfg = entry.get("config") or {}
    path: Optional[Path] = None
    of, fit, scale = None, "cover", 1.0
    if entry.get("scene"):
        url = cfg.get("poster" if which == "first" else "end")
        if url:
            rel = url.split(f"assets/{s.id}/", 1)[-1]
            for base in (project.build / s.id / "web", (Path(dist) / "assets" / s.id) if dist else None):
                if base is not None and (base / rel).exists():
                    path = base / rel
                    break
        if s.type == "sequence" and cfg.get("fit") == "contain":
            fit = "contain"
        if s.type == "parallax" and cfg.get("chapters"):
            move = cfg["chapters"][0 if which == "first" else -1].get("move", cfg.get("move", "dolly"))
            scale = _PARALLAX_ZOOM.get(move, (1.0, 1.0))[0 if which == "first" else 1]
        if s.type == "artwork" and which == "first":
            path = None
    elif s.type == "hero" and entry.get("img") and not entry.get("video"):
        path, of = _published(project, dist, entry["img"]), ".ss-hero__media img"
    elif s.type == "product" and entry.get("img"):
        path, of = _published(project, dist, entry["img"]), ".ss-product__img"
    if path is None and entry.get("backdrop"):
        path, of, fit, scale = _published(project, dist, entry["backdrop"]), ".ss-backdrop", "cover", 1.0
    if path is None or not Path(path).exists():
        return None
    return {"path": Path(path), "of": of, "fit": fit, "scale": scale}


# ---------------------------------------------------------------- shapes

def mask_shape(mask) -> Optional[dict]:
    """A shape from a mask (255 inside): its box and the numbers a match is judged on."""
    import cv2
    import numpy as np
    m = (np.asarray(mask) > 127).astype(np.uint8)
    if m.sum() == 0:
        return None
    n, lab, stats, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
    biggest = stats[1:, cv2.CC_STAT_AREA].max()
    keep = [i for i in range(1, n) if stats[i, cv2.CC_STAT_AREA] >= 0.05 * biggest]
    sel = np.isin(lab, keep).astype(np.uint8)
    ys, xs = np.nonzero(sel)
    h, w = sel.shape
    x0, x1, y0, y1 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
    cnts, _ = cv2.findContours(sel, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    big = max(cnts, key=cv2.contourArea)
    area, per = float(cv2.contourArea(big)), float(cv2.arcLength(big, True)) or 1.0
    hull = cv2.contourArea(cv2.convexHull(big)) or 1.0
    rect = cv2.minAreaRect(big)
    ra = max(rect[1][0] * rect[1][1], 1.0)
    circ, solid, rectness = min(1.0, 4 * np.pi * area / per ** 2), area / hull, min(1.0, area / ra)
    kind = "round" if circ > 0.82 and solid > 0.9 else "rect" if rectness > 0.86 and solid > 0.9 else "blob"
    return {"box": [round(float(x0) / w, 4), round(float(y0) / h, 4), round(float(x1) / w, 4), round(float(y1) / h, 4)],
            "share": round(float(sel.sum()) / (w * h), 4), "kind": kind, "circularity": round(float(circ), 3),
            "solidity": round(float(solid), 3), "contour": big}


def iou(a, b) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def candidates(im, limit: int = 12) -> list[dict]:
    """Shapes on a picture that are worth matching, found without any model: flat regions (colour clusters, split into
    connected parts) that are big enough to read, compact, and stand out from what is around them."""
    import cv2
    import numpy as np
    a = np.asarray(im.convert("RGB"))
    h0, w0 = a.shape[:2]
    k = WORK / max(h0, w0)
    if k < 1:
        a = cv2.resize(a, (round(w0 * k), round(h0 * k)), interpolation=cv2.INTER_AREA)
    h, w = a.shape[:2]
    lab = cv2.cvtColor(cv2.GaussianBlur(a, (0, 0), 1.6), cv2.COLOR_RGB2LAB).reshape(-1, 3).astype(np.float32)
    out: list[dict] = []
    cv2.setRNGSeed(7)
    for kk in (5, 8):
        crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 12, 1.0)
        _, labels, _ = cv2.kmeans(lab, kk, None, crit, 2, cv2.KMEANS_PP_CENTERS)
        labels = labels.reshape(h, w)
        for c in range(kk):
            m = (labels == c).astype(np.uint8)
            m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
            m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
            n, lab_cc, stats, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
            for i in range(1, n):
                share = stats[i, cv2.CC_STAT_AREA] / (w * h)
                if not 0.006 <= share <= 0.45:
                    continue
                mask = ((lab_cc == i) * 255).astype(np.uint8)
                mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
                sh = mask_shape(mask)
                if sh is None or sh["solidity"] < 0.72:
                    continue
                ring = (cv2.dilate(mask, np.ones((15, 15), np.uint8)) > 0) & (mask == 0)
                inside = a[mask > 0].mean(axis=0)
                around = a[ring].mean(axis=0) if ring.any() else inside
                sh["contrast"] = round(float(np.abs(inside - around).mean() / 255), 3)
                if sh["contrast"] < 0.06:
                    continue
                x0, y0, x1, y1 = sh["box"]
                if x0 < 0.003 and y0 < 0.003 and x1 > 0.997 and y1 > 0.997:
                    continue            # the whole picture
                sh["saliency"] = round(min(1.0, sh["share"] / 0.04) * 0.5 + sh["contrast"] * 2 + (0.3 if sh["kind"] != "blob" else 0), 3)
                out.append(sh)
    out.sort(key=lambda s: -s["saliency"])
    kept: list[dict] = []
    for s in out:            # one candidate per place: the more salient of any two that overlap almost entirely
        if all(iou(s["box"], t["box"]) < 0.7 for t in kept):
            kept.append(s)
    return kept[:limit]


def pair_shapes(cands_a: list[dict], cands_b: list[dict]) -> Optional[tuple[dict, dict, float]]:
    """The best pair of shapes, one from each picture: alike in outline (Hu moments of the contours, the same family),
    alike in size, near each other, and both worth looking at. Returns (a, b, confidence 0-1)."""
    import cv2
    import numpy as np
    best = None
    for a in cands_a:
        for b in cands_b:
            d = min(float(cv2.matchShapes(a["contour"], b["contour"], cv2.CONTOURS_MATCH_I1, 0.0)), 2.0)
            size = abs(np.log(max(b["share"], 1e-4) / max(a["share"], 1e-4))) / 2
            ca = ((a["box"][0] + a["box"][2]) / 2, (a["box"][1] + a["box"][3]) / 2)
            cb = ((b["box"][0] + b["box"][2]) / 2, (b["box"][1] + b["box"][3]) / 2)
            dist = float(np.hypot(ca[0] - cb[0], ca[1] - cb[1]))
            cost = d * 1.5 + (0 if a["kind"] == b["kind"] else 0.6) + size * 0.5 + dist * 0.4 - (a["saliency"] + b["saliency"]) * 0.25
            if best is None or cost < best[0]:
                best = (cost, a, b)
    if best is None:
        return None
    cost, a, b = best
    return a, b, round(float(1 / (1 + np.exp(cost))), 3)


def anchor(shape: dict, pic: dict, size: tuple[int, int], how: str) -> dict:
    """The anchor the page carries for a shape found on a picture."""
    out = {"box": shape["box"], "aspect": round(size[0] / size[1], 4), "how": how}
    if shape.get("kind"):
        out["kind"] = shape["kind"]
    if pic.get("of"):
        out["of"] = pic["of"]
    if pic.get("fit") and pic["fit"] != "cover":
        out["fit"] = pic["fit"]
    if pic.get("scale") and abs(pic["scale"] - 1) > 1e-3:
        out["scale"] = pic["scale"]
    return out


def find_by_prompt(project, path, prompt: str, log=print) -> Optional[dict]:
    """The shape a prompt names on a picture (Florence-2 finds it, SAM 2.1 cuts it out); None if nothing matches."""
    from PIL import Image

    from . import region
    from .project import BuildError
    from .spec import EditRegion
    try:
        mask = region.find(project, path, EditRegion(prompt=prompt, pick="largest"), log)
    except BuildError as e:
        log(f"    note: {e}")
        return None
    return mask_shape(Image.open(mask).convert("L"))


# ---------------------------------------------------------------- a site's match cuts

def analyse(project, pairs: list, labels: list[str], entries: list[dict], dist=None,
            log: Callable[[str], None] = print) -> dict:
    """Anchors for every match cut: {cut number: {"a": anchor, "b": anchor, ...}}. `pairs` is [(i, j, Transition)] for every
    cut (engine/cuts.py cut_pairs), `labels` names each for the log. A side that cannot be found leaves the cut out, and the
    page softens it into a dissolve. Cached in .build/_cuts by the two pictures and what names the shapes."""
    from PIL import Image

    from .fidelity import preview
    from .project import file_key
    out: dict = {}
    pv = preview()
    no_model = pv is not None and not pv.comfy
    for n, (ia, ib, t) in enumerate(pairs):
        if t.type != "match":
            continue
        label = labels[n]
        pa = picture(project, entries[ia], "last", dist)
        pb = picture(project, entries[ib], "first", dist)
        shape_a = t.shape
        shape_b = t.becomes or t.shape
        key = [VERSION, [file_key(p["path"]) for p in (pa, pb) if p], [pa and pa["of"], pb and pb["of"]],
               shape_a.model_dump(mode="json") if shape_a else None, shape_b.model_dump(mode="json") if shape_b else None, no_model]
        cache = project.build / "_cuts" / f"match_{hashlib.sha1(json.dumps(key, sort_keys=True, default=str).encode()).hexdigest()[:12]}.json"
        if cache.exists():
            out[n] = json.loads(cache.read_text())
            log(f"  [{label}] match: shapes from the cache")
            continue

        def side(spec, pic, which):
            if spec is not None and spec.selector:
                return {"sel": spec.selector}
            if pic is None:
                return None
            size = Image.open(pic["path"]).size
            if spec is not None and spec.box:
                return anchor({"box": list(spec.box)}, pic, size, "box")
            if spec is not None and spec.prompt:
                if no_model:
                    log(f'    note: [{label}] "{spec.prompt}" needs ComfyUI (Florence-2 and SAM 2.1), not used in this sketch')
                    return None
                sh = find_by_prompt(project, pic["path"], spec.prompt, log)
                if sh is None:
                    log(f'    note: [{label}] nothing matching "{spec.prompt}" on the {which} picture')
                    return None
                return anchor(sh, pic, size, "prompt")
            return None

        res: dict = {"a": side(shape_a, pa, "last"), "b": side(shape_b, pb, "first")}
        if shape_a is None and shape_b is None and pa is not None and pb is not None:
            ia_, ib_ = Image.open(pa["path"]), Image.open(pb["path"])
            pair = pair_shapes(candidates(ia_), candidates(ib_))
            if pair is not None:
                a, b, score = pair
                log(f"  [{label}] match: found {a['kind']} and {b['kind']} shapes by contour (confidence {score:.2f})")
                res = {"a": anchor(a, pa, ia_.size, "contour"), "b": anchor(b, pb, ib_.size, "contour"), "score": score}
        res = {k: v for k, v in res.items() if v is not None}
        if res.get("a") and res.get("b"):
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(res))
            out[n] = res
        else:
            log(f"  [{label}] match: no shapes to meet on, so the cut dissolves (name them with `shape:` and `becomes:`)")
    return out
