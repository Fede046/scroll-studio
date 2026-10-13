"""showroom: the real product live in the page. three.js renders the product's normalised GLB (engine/product.py)
with environment lighting and a soft shadow; scroll drives yaw/pitch/explode/zoom keys. A Cycles still of the
first key is the poster until the model has loaded (and the fallback without WebGL)."""
from __future__ import annotations

import shutil

from ..project import BuildContext, BuildError
from ..spec import Product, ShowroomScene

WEB_TRIANGLES = 400_000     # the live model is thinned to this for phones; renders keep the full model


def _product(sec: ShowroomScene, ctx: BuildContext) -> Product:
    if sec.model == "product":
        p = ctx.project.load().product
        if p is None:
            raise BuildError(f"showroom '{sec.id}': model is 'product' but the site has no `product:`")
        return p
    return Product(name=sec.id, model=sec.model)


def build(sec: ShowroomScene, ctx: BuildContext, theme: dict) -> dict:
    from .. import product as prod
    p = _product(sec, ctx)
    info = prod.product_info(ctx.project, p, ctx.log)
    web_p = p.model_copy(update={"max_triangles": min(p.max_triangles, WEB_TRIANGLES)}) if info["triangles"] > WEB_TRIANGLES else p
    glb = prod.normalised_glb(ctx.project, web_p, ctx.log)
    dst = ctx.web / "model.glb"
    if not dst.exists() or dst.stat().st_size != glb.stat().st_size:
        shutil.copy(glb, dst)
    mb = dst.stat().st_size / 1e6
    if mb > 25:
        ctx.log(f"  note: the live model is {mb:.0f} MB; lower product.max_triangles or tessellation for phones")
    bg = sec.background or theme["colors"]["bg"]
    cfg = {
        "model": ctx.url(dst), "keys": sorted(sec.keys, key=lambda k: k.get("t", 0)), "background": bg,
        "lighting": sec.lighting, "exposure": sec.exposure, "shadow": sec.shadow, "spin": sec.spin,
        "size": info["size"], "parts": len(info["parts"]),
        "shift": (0.13 if sec.side == "right" else -0.13) if sec.layout == "cards" else 0,
    }
    if sec.poster:
        k0 = cfg["keys"][0] if cfg["keys"] else {}
        draft = bool(ctx.options.get("draft"))
        still = prod.product_still(ctx.project, p, "three-quarter", (960, 600) if draft else (1600, 1000),
                                   "transparent" if bg == "transparent" else bg, ctx.log,
                                   yaw=k0.get("yaw", -35), pitch=k0.get("pitch", 18),
                                   explode=k0.get("explode") or None, samples=32 if draft else 96)
        out = ctx.web / ("poster.png" if bg == "transparent" else "poster.jpg")
        from PIL import Image
        im = Image.open(still)
        (im if bg == "transparent" else im.convert("RGB")).save(out, **({} if bg == "transparent" else {"quality": 88}))
        cfg["poster"] = cfg["end"] = ctx.url(out)
    return cfg
