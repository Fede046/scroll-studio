"""diorama: a miniature world, drawn live in the page.

The build lays the world out (engine/diorama/: ground texture, height grid, props, places, camera beats) and writes
`world.json`, `ground.jpg` and `map.jpg` (a flat map of the world, the picture shown until WebGL is up and when it is
missing). Cached by the world, the places, the camera and the steps' timing; the look (tilt-shift, sun, grade) is a
runtime setting and never rebuilds anything."""
from __future__ import annotations

import json

from ..project import BuildContext
from ..spec import DioramaScene

VERSION = 1


def _hex(c: str) -> tuple[int, int, int]:
    c = c.lstrip("#")
    if len(c) == 3:
        c = "".join(x * 2 for x in c)
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def _map_image(plan: dict, tex, table: str, size: int = 1280):
    """A flat picture of the world: the painted ground inside its outline, on the table colour, with the places pinned."""
    import numpy as np
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
    S = plan["size"]
    ground = Image.fromarray(tex).convert("RGB").resize((size, size), Image.LANCZOS)
    # the world's outline as a mask
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    x, z = (xx + 0.5) / size * 2 - 1, (yy + 0.5) / size * 2 - 1
    inside = (x * x + z * z < 1.0) if plan["base"] == "round" else (np.abs(x) ** 8 + np.abs(z) ** 8 < 1.0)
    mask = Image.fromarray((inside * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(1.2))
    W, H = 1600, 900
    bg = Image.new("RGB", (W, H), _hex(table))
    scale = H * 0.78 / size
    s = int(size * scale)
    g = ground.resize((s, s), Image.LANCZOS)
    m = mask.resize((s, s), Image.LANCZOS)
    ox, oy = (W - s) // 2, (H - s) // 2 + 20
    shadow = Image.new("L", (W, H), 0)
    shadow.paste(m, (ox + 8, oy + 18))
    shadow = shadow.filter(ImageFilter.GaussianBlur(22)).point(lambda v: int(v * 0.35))
    bg.paste(Image.new("RGB", (W, H), (60, 44, 30)), (0, 0), shadow)
    bg.paste(g, (ox, oy), m)
    d = ImageDraw.Draw(bg)
    try:
        font = ImageFont.truetype("arial.ttf", 24)
    except OSError:
        font = ImageFont.load_default()
    for i, p in enumerate(plan["places"]):
        px = ox + (p["x"] / S + 0.5) * s
        py = oy + (p["z"] / S + 0.5) * s
        d.ellipse((px - 17, py - 17, px + 17, py + 17), fill=(30, 36, 44), outline=(255, 255, 255), width=3)
        d.text((px, py), str(i + 1), fill=(255, 255, 255), font=font, anchor="mm")
        d.text((px + 24, py), p["name"], fill=(30, 36, 44), font=font, anchor="lm")
    return bg


def build(sec: DioramaScene, ctx: BuildContext, theme: dict) -> dict:
    from .. import diorama
    table = sec.look.table or theme["colors"]["bg"]
    draft = bool(ctx.options.get("draft"))
    out_plan, out_ground, out_map = ctx.web / "world.json", ctx.web / "ground.jpg", ctx.web / "map.jpg"
    key = {"v": VERSION + diorama.plan.VERSION, "draft": draft, "table": table, "layout": sec.layout, "side": sec.side,
           "scene": sec.model_dump(mode="json", include={"world", "places", "camera"}),
           "steps": [{"intro": s.intro, "length": s.length, "place": (s.state or {}).get("place"), "wide": (s.state or {}).get("wide")}
                     for s in sec.steps]}

    def run():
        from PIL import Image
        plan, tex, w = diorama.build(sec, table, draft)
        counts: dict[str, int] = {}
        for p in plan["props"]:
            counts[p["k"]] = counts.get(p["k"], 0) + 1
        out_plan.write_text(json.dumps(plan, separators=(",", ":")), encoding="utf-8")
        Image.fromarray(tex).save(out_ground, quality=88 if not draft else 80)
        _map_image(plan, tex, table).save(out_map, quality=86)
        ctx.log(f"  {len(plan['props'])} props, {len(plan['places'])} places, {len(plan['camera']['beats'])} beats "
                f"({', '.join(f'{k} {v}' for k, v in sorted(counts.items(), key=lambda kv: -kv[1])[:6])})")

    ctx.stage("diorama", key, [out_plan, out_ground, out_map], run)
    return {
        "plan": ctx.url(out_plan), "ground": ctx.url(out_ground), "map": ctx.url(out_map),
        "look": {**sec.look.model_dump(mode="json"), "table": table},
        "side": 1 if sec.side == "right" else -1, "layout": sec.layout,
    }
