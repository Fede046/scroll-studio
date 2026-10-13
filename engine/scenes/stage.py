"""stage: someone comes into the light. Nothing to render ahead of time; the figure is a drawn outline.

The figure is one closed curve (Catmull-Rom through an outline, mirrored with small differences so it doesn't look
stamped). It has no face on purpose: it is the visitor, and the last shot sees them from behind.
"""
from ..project import BuildContext
from ..spec import StageScene

# The right half, from the top of the head down the outside and back up the inside leg to the crotch
# (x from the centre line, y down). About 7.8 heads tall; the trousers keep the legs together to the knee.
OUTLINE = [
    (0, 7), (7, 7.5), (13, 9), (19, 11.5), (24, 16), (28, 23), (30.5, 31), (31, 40), (33, 44), (34, 50), (33, 57),
    (30, 61), (27, 67), (23, 72), (20, 78), (20, 85), (21, 91),
    (28, 96), (39, 99.5), (50, 102.5), (58, 106.5), (64, 112), (68, 121), (70, 134),
    (70, 152), (69, 172), (67, 194), (66, 210), (66, 224), (63, 246), (60, 266), (61, 278), (62, 293), (61, 308),
    (57, 320), (52, 321), (50, 312), (49, 296), (49, 280), (51, 262), (54, 242), (55, 222), (55, 204), (53, 184),
    (52, 166), (49, 152),
    (46, 160), (44, 180), (42, 200), (42, 218), (44, 238), (46, 256), (47, 270),
    (47, 288), (47, 310), (46, 334), (44, 358), (42, 380), (43, 398), (43, 418), (41, 444), (37, 470), (33, 494),
    (35, 507), (35, 516), (31, 523), (20, 524), (16, 519), (17, 505), (18, 486), (19, 460), (19, 434), (17, 404),
    (15, 382), (12, 352), (8, 322), (4, 300), (0, 293),
]
ARM, LEG = range(23, 46), range(53, 72)
VIEWBOX = "-80 0 160 530"   # feet at 524; the head's top at 7


def _left() -> list[tuple[float, float]]:
    """The left half: the mirror image, but not a perfect one (an arm a little away, weight on one leg)."""
    out = []
    for i, (x, y) in enumerate(OUTLINE):
        dx = 0.0
        if i in ARM:
            dx = 3.5 * max(0.0, (y - 130) / 190)
        if i in LEG:
            dx = -2.5 * max(0.0, min(1.0, (y - 300) / 100)) + 4 * max(0.0, (y - 420) / 100)
        if i < 18 and y < 30:
            dx = 1.2 * ((i * 7) % 3 - 1)
        out.append((-(x + dx), y))
    return out


def figure_path() -> str:
    pts = OUTLINE[:-1] + list(reversed(_left()[1:]))[:-1]
    n = len(pts)
    d = f"M{pts[0][0]:.1f},{pts[0][1]:.1f}"
    for i in range(n):
        p0, p1, p2, p3 = pts[i - 1], pts[i], pts[(i + 1) % n], pts[(i + 2) % n]
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        d += f"C{c1[0]:.1f},{c1[1]:.1f} {c2[0]:.1f},{c2[1]:.1f} {p2[0]:.1f},{p2[1]:.1f}"
    return d + "Z"


def _lum(h: str) -> float:
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def build(sec: StageScene, ctx: BuildContext, theme: dict) -> dict:
    c = theme["colors"]
    # the room is the theme's darkest colour and the light its palest, whichever way round the theme is
    dark, light = sorted((c["bg"], c["ink"]), key=_lum)
    beats = len(sec.lines) + (1 if sec.platform else 0)
    return {
        "figure": figure_path(), "viewbox": VIEWBOX,
        "dark": dark, "light": light, "page": c["bg"], "ink": c["ink"], "accent": c["accent"], "glow": c["accent2"],
        "weights": sec.weights, "lines": len(sec.lines), "platform": bool(sec.platform),
        # one screen per line, a little more for the platform, the turn and the flood of light
        "length": sec.length or round(beats * 0.9 + 3.2, 2),
    }
