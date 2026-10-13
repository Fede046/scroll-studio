"""The site's product (`site.product`), declared once and used everywhere.

The model is resolved (project file, URL or TRELLIS photo), converted (STEP via OpenCascade, 3MF via trimesh),
normalised by Blender (axes, units, base at the origin, part materials, decimation only when absurdly heavy) and
cached as one GLB under `.build/_product/`. Stills of it are rendered by Cycles in a studio light, also cached.

Public API, for scene builders, the CLI/MCP and the trailer builder. `product` may always be omitted (or None):
it then means `site.product` of the project.

    get(project, product=None) -> Product
        The site's product spec, or BuildError if the site declares none.
    normalised_glb(project, product=None, log=print) -> Path
        `.build/_product/<digest>.glb`: Y-up, metres, base centre at the origin, front towards +Z (glTF), part
        materials applied; explodable parts carry node extras ss_part / ss_explode (offset in metres).
    product_info(project, product=None, log=print) -> dict
        The parts report written beside the GLB: size [x, y, z] m (z up), height, triangles, units, parts
        [{index, name, mesh, path, triangles, materials [{name, color}], size, centre, explode, anchor}], rules
        [{match, material, hits}].
    product_still(project, product=None, view="three-quarter", size=(1600, 1200), background="transparent",
                  log=print, **shot) -> Path
        A PNG still. view: front, three-quarter, side, top, back, hero-low, exploded. background: "transparent"
        (RGBA with a soft shadow), "theme" (the site theme's background) or a hex colour. shot: any ProductShot
        field (yaw, pitch, zoom, explode, lens, hdri, samples, shadow).
    credits(product) -> list[str]        footer credit line(s) for the model
    concept_line(product) -> str | None  "Concept page. Not affiliated with <maker>." when product.concept
    take_track(project, section_id, log=print) -> Path
        `.build/<section>/product/track.json` for a film section with a take product: per frame, where the product
        is on screen (normalised 0-1, y down): {"fps", "size", "frames": [{"f", "visible", "centre", "base",
        "box": [x0, y0, x1, y1]}]}. Built with the take (stage `track`); this computes it if missing.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

from .config import ROOT, settings
from .project import BuildError, Project
from .spec import ImageInput, Product, ProductShot

VERSION = 1           # bump when the normalisation changes, so every cached GLB is rebuilt
STILL_VERSION = 2
SCRIPTS = Path(__file__).resolve().parent / "backends" / "blender_scripts"
FORMATS = (".glb", ".gltf", ".obj", ".fbx", ".stl", ".ply", ".step", ".stp", ".3mf")
TESSELLATION = {"draft": (0.1, 0.5), "normal": (0.05, 0.3), "fine": (0.02, 0.15)}   # linear mm, angular rad
UNITS_3MF = {"millimeter": "mm", "centimeter": "cm", "meter": "m", "inch": "in", "foot": "ft"}

# view name -> camera (yaw 0 is the front; pitch is the camera's height in degrees above the horizon)
VIEWS = {
    "front": {"yaw": 0, "pitch": 6},
    "three-quarter": {"yaw": -35, "pitch": 20},
    "side": {"yaw": 90, "pitch": 6},
    "top": {"yaw": 0, "pitch": 89},
    "back": {"yaw": 180, "pitch": 12},
    "hero-low": {"yaw": -28, "pitch": -7, "lens": 32, "low": True, "zoom": 1.05},
    "exploded": {"yaw": -35, "pitch": 24, "explode": 1.0},
    "detail": {"aim": True, "lens": 85},     # a macro view of shot `part`, aimed from the side it faces out of
}


def _sha(path: Path) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 22), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def _digest(obj) -> str:
    return hashlib.sha1(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()[:14]


def _cache(project: Project) -> Path:
    d = project.build / "_product"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get(project: Project, product: Optional[Product] = None) -> Product:
    if product is not None:
        return product
    p = project.load().product
    if p is None:
        raise BuildError("this needs the site's product: add `product: {name: ..., model: ...}` at the top of site.yaml")
    return p


def _blender(script: str, args: list, log=print, what: str = "Blender") -> None:
    cmd = [settings()["blender"], "-b", "--factory-startup", "--python-exit-code", "1", "-P", str(SCRIPTS / script), "--",
           *[str(x) for x in args]]
    try:
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
    except FileNotFoundError:
        raise BuildError(f"Blender not found at {settings()['blender']}: install Blender 4.2+ or set `blender` in studio.toml")
    tail = []
    for line in p.stdout:
        tail = (tail + [line])[-40:]
        if line.startswith(("IMPORTED", "NORMALISED", "DECIMATE", "EXPORTED")):
            log("  " + line.strip())
    if p.wait() != 0:
        raise BuildError(f"{what} failed:\n" + "".join(tail))


def _source(project: Project, product: Product, log=print) -> tuple[Path, str, Optional[str], dict]:
    """The model as a file Blender can import, its original format, units to force (or None), and a content key."""
    from .inputs import resolve_path
    if product.model:
        src = resolve_path(project, product.model, log)
        ext = src.suffix.lower()
        if ext not in FORMATS:
            raise BuildError(f"product.model {product.model}: unsupported format {ext or '(none)'} "
                             f"(use {', '.join(f.lstrip('.') for f in FORMATS)})")
        key = {"model": _sha(src), "ext": ext}
        cache = _cache(project)
        if ext in (".step", ".stp"):
            lin, ang = TESSELLATION[product.tessellation]
            key["tess"] = [lin, ang]
            out = cache / f"step_{_digest(key)}.glb"
            if not out.exists():
                log(f"  converting STEP with OpenCascade ({product.tessellation}: {lin} mm, {ang} rad): {src.name}")
                _child(["step", src, out, lin, ang], out)
            if product.units != "auto":
                log("  note: STEP files carry their own units; product.units is ignored for them")
            return out, "step", "m", key
        if ext == ".3mf":
            out = cache / f"3mf_{_digest(key)}.glb"
            meta = cache / f"3mf_{_digest(key)}.json"
            if not (out.exists() and meta.exists()):
                log(f"  converting 3MF: {src.name}")
                info = _child(["3mf", src, out], out)
                meta.write_text(json.dumps(info))
            units = json.loads(meta.read_text()).get("units", "millimeter")
            return out, "3mf", product.units if product.units != "auto" else UNITS_3MF.get(units, "mm"), key
        return src, ext.lstrip("."), None, key
    if product.from_photo:
        from .backends.trellis import image_to_mesh
        photo = resolve_path(project, product.from_photo, log)
        key = {"photo": _sha(photo)}
        mesh = image_to_mesh(photo, _cache(project) / f"trellis_{_digest(key)}", log)
        return mesh, "ply", None, key
    raise BuildError("product needs `model` (a 3D file or URL) or `from_photo`")


def _child(args: list, out: Path) -> dict:
    p = subprocess.run([sys.executable, "-m", "engine.backends.cad", *[str(a) for a in args]], cwd=ROOT,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if p.returncode != 0 or not out.exists():
        raise BuildError("model conversion failed:\n" + (p.stderr or p.stdout)[-2000:])
    try:
        return json.loads(p.stdout.strip().splitlines()[-1])
    except Exception:
        return {}


def _prepare(project: Project, product: Product, log=print) -> tuple[Path, Path]:
    from .inputs import resolve_path
    src, fmt, units, skey = _source(project, product, log)
    textures = {}
    for r in product.parts:
        if r.texture and r.texture not in textures:
            textures[r.texture] = str(resolve_path(project, r.texture, log))
    opts = {"up": product.up, "units": units or product.units, "rotation": list(product.rotation),
            "parts": [r.model_dump(mode="json", exclude_none=True) for r in product.parts],
            "max_triangles": product.max_triangles, "textures": textures}
    if product.exclude:
        opts["exclude"] = list(product.exclude)
    key = {"v": VERSION, "script": _sha(SCRIPTS / "product_prep.py"), "src": skey, "fmt": fmt, "opts": {**opts, "textures": {k: _sha(Path(v)) for k, v in textures.items()}}}
    cache = _cache(project)
    digest = _digest(key)
    glb, report = cache / f"{digest}.glb", cache / f"{digest}.json"
    if glb.exists() and report.exists():
        return glb, report
    log(f"  normalising product model ({fmt}) -> {glb.name}")
    optfile = cache / f"{digest}.opts.json"
    optfile.write_text(json.dumps(opts, indent=1), encoding="utf-8")
    tmp = cache / f"{digest}.tmp.glb"
    _blender("product_prep.py", ["--model", src, "--fmt", fmt, "--opts", optfile, "--out", tmp, "--report", report],
             log, "normalising the product model")
    tmp.replace(glb)
    info = json.loads(report.read_text(encoding="utf-8"))
    for r in info.get("rules", []):
        if not r["hits"]:
            log(f"  warning: product.parts rule match={r['match']!r}"
                f"{' material=' + repr(r['material']) if r['material'] else ''} matched nothing (see studio product --parts)")
    mb = glb.stat().st_size / 1e6
    if mb > 40:
        log(f"  note: the product GLB is {mb:.0f} MB; lower max_triangles or tessellation for the live showroom")
    return glb, report


def normalised_glb(project: Project, product: Optional[Product] = None, log=print) -> Path:
    return _prepare(project, get(project, product), log)[0]


def product_info(project: Project, product: Optional[Product] = None, log=print) -> dict:
    return json.loads(_prepare(project, get(project, product), log)[1].read_text(encoding="utf-8"))


def _hex(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def theme_background(project: Project) -> str:
    from .compile import themes
    return themes.resolve(project.load().theme)["colors"]["bg"]


def product_still(project: Project, product: Optional[Product] = None, view: str = "three-quarter",
                  size: tuple[int, int] = (1600, 1200), background: str = "transparent", log=print, **shot) -> Path:
    product = get(project, product)
    if view not in VIEWS:
        raise BuildError(f"unknown product view {view!r} (have: {', '.join(VIEWS)})")
    glb, report = _prepare(project, product, log)
    cam = dict(VIEWS[view])
    for k in ("yaw", "pitch", "zoom", "explode", "lens", "part", "fstop"):
        if shot.get(k) is not None:
            cam[k] = shot[k]
    if view == "detail" and not cam.get("part"):
        raise BuildError("the detail view needs `part`: a glob on a part name (studio product <project> --parts)")
    if cam.get("explode"):
        n = len(json.loads(report.read_text(encoding="utf-8"))["parts"])
        if n < 2:
            raise BuildError(f"the exploded view needs a model with several parts; {product.name}'s model has {n}")
    samples, hdri, shadow = int(shot.get("samples") or 128), shot.get("hdri") or "studio", shot.get("shadow", True)
    w, h = int(size[0]), int(size[1])
    key = {"v": STILL_VERSION, "script": _sha(SCRIPTS / "product_still.py"), "glb": glb.name, "cam": cam, "size": [w, h], "samples": samples, "hdri": hdri, "shadow": bool(shadow)}
    stills = _cache(project) / "stills"
    stills.mkdir(exist_ok=True)
    digest = _digest(key)
    png = stills / f"{digest}.png"
    if not png.exists():
        log(f"  product still: {view} {w}x{h}, {samples} samples")
        tmp = stills / f"{digest}.tmp.png"
        _blender("product_still.py", ["--glb", glb, "--out", tmp, "--size", f"{w}x{h}", "--view", json.dumps(cam),
                                      "--samples", samples, "--hdri", hdri, "--shadow", int(bool(shadow))],
                 log, "rendering the product still")
        tmp.replace(png)
    if background in (None, "", "transparent"):
        return png
    colour = theme_background(project) if background in ("theme", "auto") else background
    if not colour.startswith("#"):
        raise BuildError(f"product still background {background!r}: use transparent, theme or a hex colour")
    flat = stills / f"{digest}_{colour.lstrip('#').lower()}.png"
    if not flat.exists():
        from PIL import Image
        im = Image.open(png).convert("RGBA")
        bg = Image.new("RGBA", im.size, _hex(colour) + (255,))
        Image.alpha_composite(bg, im).convert("RGB").save(flat)
    return flat


def image_still(project: Project, ref: ImageInput, log=print, alpha: bool = False) -> Path:
    """`image: {product: <view or shot>}`: transparent where the caller can show it (alpha), else the theme bg."""
    shot = ref.product if isinstance(ref.product, ProductShot) else ProductShot(view=ref.product)
    bg = shot.background
    if bg == "auto":
        bg = "transparent" if alpha else "theme"
    opts = shot.model_dump(exclude={"view", "background"})
    return product_still(project, None, shot.view, tuple(ref.size), bg, log, **opts)


def credits(product: Optional[Product]) -> list[str]:
    if product is None:
        return []
    line = product.credit or (f"{product.name} 3D model by {product.maker}" if product.maker else f"{product.name} 3D model")
    if product.licence and product.licence.lower() not in line.lower():
        line += f", {product.licence}"
    return [line]


def concept_line(product: Optional[Product]) -> Optional[str]:
    if product is None or not product.concept:
        return None
    return f"Concept page. Not affiliated with {product.maker}." if product.maker else "Concept page. Not an official product page."


def take_height(project: Project, layer) -> float:
    """A take product's height: as set, else the site product's real height (metres) when it uses site.product."""
    if layer.height is not None:
        return float(layer.height)
    if not (layer.model or layer.from_photo) and project.load().product is not None:
        return float(product_info(project)["height"])
    return 1.0


def take_track(project: Project, section_id: str, log=print) -> Path:
    from .project import BuildContext
    from .scenes import film
    site = project.load()
    sec = next((s for s in site.sections if getattr(s, "id", None) == section_id), None)
    if sec is None or sec.type != "film" or not sec.take or not sec.take.product:
        raise BuildError(f"section {section_id!r} is not a film with a take product")
    ctx = BuildContext(project, section_id, log=log)
    film.take_shot(sec, ctx)
    return film.track(sec, ctx)
