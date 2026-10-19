"""How different two directions are, so a set of six is six ideas and not one idea in six colourways.

Distance is 0 (the same direction) to 1 (nothing shared). Five things count, each judged on what a visitor would
notice: the *kind* of picture and page (photographic, illustrated, typographic, technical ...), the *experience*
(the style's scroll mechanic and layout), the colour (ground lightness and the accent's hue), the type (the faces' kind,
not their names) and the imagery (what the pictures are made of). A set whose closest pair is under MIN_DISTANCE has a
weak member and the writer replaces it.
"""
from __future__ import annotations

import colorsys

from . import typefaces, vocab

MIN_DISTANCE = 0.5
WEIGHTS = {"kind": 0.25, "style": 0.20, "palette": 0.20, "type": 0.10, "image": 0.25}

# groups of picture kinds that look related (half a point of difference between two members)
IMAGE_GROUP = {
    "film-photo": "photo", "studio-photo": "photo", "mono-photo": "photo", "still-photo": "photo", "reportage": "photo",
    "cine": "photo", "crt": "photo", "engraving": "drawn", "map-illustration": "drawn", "diagram": "drawn", "cel": "drawn",
    "paint-illustration": "paint", "oil": "paint", "print-illustration": "graphic", "flat-graphic": "graphic", "print": "graphic",
    "deco-graphic": "graphic", "paper": "craft", "render3d": "3d", "render-gloss": "3d", "pixel": "pixel", "": "unknown",
}


def hsl(hex_: str) -> tuple[float, float, float]:
    h = hex_.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    hh, ll, ss = colorsys.rgb_to_hls(r, g, b)
    return hh * 360, ss, ll


def palette_distance(a: dict, b: dict) -> float:
    ha, sa, la = hsl(a["accent"])
    hb, sb, lb = hsl(b["accent"])
    hue = abs(ha - hb)
    hue = min(hue, 360 - hue) / 180
    colourful = min(sa, sb)                       # two greys have no hue to differ by
    ground = abs(hsl(a["bg"])[2] - hsl(b["bg"])[2])
    d = 0.55 * ground + 0.35 * hue * (0.4 + 0.6 * colourful) + 0.10 * abs(sa - sb) + 0.10 * abs(la - lb)
    if a.get("mode") != b.get("mode"):
        d += 0.25
    return min(1.0, d * 1.25)


def style_distance(a, b) -> float:
    if a == b:
        return 0.0
    ca, cb = vocab.STYLE_CLUSTER.get(a or "none", "editorial"), vocab.STYLE_CLUSTER.get(b or "none", "editorial")
    return 0.55 if ca == cb else 1.0


def type_distance(a: dict, b: dict) -> float:
    fa, fb = typefaces.family_of(a["display"]), typefaces.family_of(b["display"])
    ba, bb = typefaces.family_of(a["body"]), typefaces.family_of(b["body"])
    return 0.7 * (fa != fb) + 0.3 * (ba != bb)


def image_distance(a: str, b: str) -> float:
    if a == b and a:
        return 0.0
    ga, gb = IMAGE_GROUP.get(a, "unknown"), IMAGE_GROUP.get(b, "unknown")
    if "unknown" in (ga, gb):
        return 0.7
    return 0.5 if ga == gb else 1.0


def distance(a, b, fixed: frozenset = frozenset()) -> float:
    """a, b: Direction. fixed: parts both directions keep from the site ('colors', 'fonts', 'style', 'imagery'): they
    cannot differ, so they do not count and the rest is scaled to fill the scale."""
    w = dict(WEIGHTS)
    for part, key in (("colors", "palette"), ("fonts", "type"), ("style", "style"), ("imagery", "image")):
        if part in fixed:
            w.pop(key, None)
    total = sum(w.values()) or 1.0
    d = 0.0
    if "kind" in w:
        d += w["kind"] * (0.0 if a.kind == b.kind else 1.0)
    if "style" in w:
        d += w["style"] * style_distance(a.style, b.style)
    if "palette" in w:
        d += w["palette"] * palette_distance(a.palette, b.palette)
    if "type" in w:
        d += w["type"] * type_distance(a.fonts, b.fonts)
    if "image" in w:
        d += w["image"] * image_distance(a.imagery_family, b.imagery_family)
    return d / total


def matrix(dirs, fixed: frozenset = frozenset()) -> list[list[float]]:
    return [[0.0 if i == j else distance(a, b, fixed) for j, b in enumerate(dirs)] for i, a in enumerate(dirs)]


def report(dirs, fixed: frozenset = frozenset()) -> dict:
    """{min, mean, closest: [a, b], weak: [[a, b, d]...]}: how far apart the set is."""
    pairs = [(dirs[i].id, dirs[j].id, distance(dirs[i], dirs[j], fixed)) for i in range(len(dirs)) for j in range(i + 1, len(dirs))]
    if not pairs:
        return {"min": 1.0, "mean": 1.0, "closest": [], "weak": []}
    lo = min(pairs, key=lambda p: p[2])
    return {"min": round(lo[2], 3), "mean": round(sum(p[2] for p in pairs) / len(pairs), 3), "closest": [lo[0], lo[1]],
            "weak": [[a, b, round(d, 3)] for a, b, d in pairs if d < MIN_DISTANCE],
            "kinds": len({d.kind for d in dirs}), "styles": len({d.style or "none" for d in dirs})}
