"""Resolve spec inputs to files: project files as-is, `generate:` images through local Z-Image Turbo."""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Optional

from .project import BuildError, Project
from .spec import ImageInput, ImageRef


def resolve_path(project: Project, ref: str, log=print) -> Path:
    """A project file, or an http(s) URL downloaded once into .build/_downloads (cached by URL)."""
    if ref.startswith(("http://", "https://")):
        import requests
        name = hashlib.sha1(ref.encode()).hexdigest()[:12] + "_" + ref.split("?")[0].rsplit("/", 1)[-1][-60:]
        out = project.build / "_downloads" / name
        if not out.exists():
            out.parent.mkdir(parents=True, exist_ok=True)
            log(f"  downloading {ref}")
            ua = {"User-Agent": "ScrollStudio/0.1 (+https://github.com/Okohedeki/scroll-studio)"}
            with requests.get(ref, stream=True, timeout=60, headers=ua) as r:
                r.raise_for_status()
                tmp = out.with_suffix(out.suffix + ".part")
                with open(tmp, "wb") as f:
                    for chunk in r.iter_content(1 << 20):
                        f.write(chunk)
                tmp.replace(out)
            _lfs_check(ref, out, log)
        return out
    p = project.path(ref)
    if not p.exists():
        raise BuildError(f"input not found: {ref}")
    return p


def _lfs_check(url: str, out: Path, log=print) -> None:
    """A big file in a GitHub repo is often stored with Git LFS: raw.githubusercontent.com then serves a 130-byte
    pointer, not the file. Fetch the real content from media.githubusercontent.com instead."""
    if out.stat().st_size > 1024 or not out.read_bytes().startswith(b"version https://git-lfs"):
        return
    import re
    import requests
    m = re.match(r"https://(?:raw\.githubusercontent\.com/([^/]+)/([^/]+)/(.+)|github\.com/([^/]+)/([^/]+)/(?:raw|blob)/(.+))", url)
    if not m:
        out.unlink()
        raise BuildError(f"{url} is a Git LFS pointer, not the file; use the host's direct download link")
    owner, repo, rest = (m.group(1), m.group(2), m.group(3)) if m.group(1) else (m.group(4), m.group(5), m.group(6))
    media = f"https://media.githubusercontent.com/media/{owner}/{repo}/{rest.split('?')[0]}"
    log(f"  {Path(url.split('?')[0]).name} is stored with Git LFS: downloading it from {media}")
    tmp = out.with_suffix(out.suffix + ".part")
    with requests.get(media, stream=True, timeout=120, headers={"User-Agent": "ScrollStudio/0.1"}) as r:
        r.raise_for_status()
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
    tmp.replace(out)


# Image-input fields added after earlier builds were keyed: left out of keys while unset, so adding a field never
# re-renders finished work.
LATE_FIELDS = ("product", "scene")


def stable_dump(model) -> dict:
    """model_dump for cache keys: late fields that are unset (None) are dropped, at any depth."""
    def strip(v):
        if isinstance(v, dict):
            return {k: strip(x) for k, x in v.items() if not (k in LATE_FIELDS and x is None)}
        if isinstance(v, list):
            return [strip(x) for x in v]
        return v
    return strip(model.model_dump(mode="json"))


def image_key(ref: ImageRef) -> dict:
    if isinstance(ref, str):
        return {"file": ref}
    d = stable_dump(ref)
    d.pop("credit", None)
    return d


def resolve_image(project: Project, ref: ImageRef, log=print, alpha: bool = False) -> Path:
    """alpha: the caller can show a transparent image (hero/product blocks), so a product still may stay RGBA."""
    if isinstance(ref, str):
        ref = ImageInput(file=ref)
    if ref.crop:
        src = resolve_image(project, ref.model_copy(update={"crop": None}), log, alpha)
        digest = hashlib.sha1(json.dumps([str(src), src.stat().st_size, list(ref.crop)]).encode()).hexdigest()[:12]
        out = project.build / "_generated" / f"crop_{digest}.png"
        if not out.exists():
            from PIL import Image
            im = Image.open(src)
            x0, y0, x1, y1 = ref.crop
            out.parent.mkdir(parents=True, exist_ok=True)
            im.crop((round(x0 * im.width), round(y0 * im.height), round(x1 * im.width), round(y1 * im.height))).save(out)
        return out
    if ref.product is not None:
        from .product import image_still
        return image_still(project, ref, log, alpha)
    if ref.file:
        return resolve_path(project, ref.file, log)
    if ref.edit:
        return _edit(project, ref, log)
    if ref.gradient:
        w, h = (int(v) for v in ref.size)
        digest = hashlib.sha1(json.dumps([ref.gradient.model_dump(mode="json"), w, h, ref.seed, 1]).encode()).hexdigest()[:12]
        out = project.build / "_generated" / f"grad_{digest}.png"
        if not out.exists():
            out.parent.mkdir(parents=True, exist_ok=True)
            render_gradient(ref.gradient, (w, h), ref.seed).save(out)
        return out
    if not ref.generate:
        raise BuildError("an image input needs `file`, `generate`, `gradient` or `product`")
    w, h = (int(v) // 16 * 16 for v in ref.size)
    digest = hashlib.sha1(json.dumps([ref.generate, w, h, ref.seed]).encode()).hexdigest()[:12]
    out = project.build / "_generated" / f"{digest}.png"
    if out.exists():
        return out
    from .backends import comfy
    if not comfy.alive():
        raise BuildError("this image is generated locally, but ComfyUI is not running at "
                         f"{comfy.COMFY}. Start it (docs/INSTALL.md) or replace `generate:` with a `file:`.")
    log(f"  generating image ({w}x{h}, seed {ref.seed}): {ref.generate[:80]}…")
    comfy.free()
    images = comfy.run(comfy.build_txt2img_graph(ref.generate, w, h, ref.seed, prefix=f"studio/{digest}"), poll=2)
    tmp = comfy.fetch(images, str(out.parent / f"_{digest}"))
    out.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(Path(tmp) / "0001.png"), out)
    shutil.rmtree(tmp, ignore_errors=True)
    return out


def _edit(project: Project, ref: ImageInput, log=print) -> Path:
    """An image made by editing others with Qwen-Image-Edit, cached by the sources' content and the instruction."""
    from .backends import comfy
    from .project import file_key
    e = ref.edit
    srcs = [resolve_image(project, r, log) for r in [e.source, *e.refs[:2]]]
    digest = hashlib.sha1(json.dumps([[file_key(s) for s in srcs], e.instruction, e.seed, e.steps, 2]).encode()).hexdigest()[:12]
    out = project.build / "_generated" / f"edit_{digest}.png"
    if out.exists():
        return out
    if not comfy.alive():
        raise BuildError(f"this image is edited locally with Qwen-Image-Edit, but ComfyUI is not running at {comfy.COMFY}.")
    log(f"  editing image (Qwen-Image-Edit, seed {e.seed}): {e.instruction[:80]}")
    comfy.free()
    names = [comfy.upload(str(s)) for s in srcs]
    images = comfy.run(comfy.build_qwen_edit_graph(names, e.instruction, e.seed, e.steps, prefix=f"studio/edit_{digest}"), poll=2)
    tmp = comfy.fetch(images, str(out.parent / f"_edit_{digest}"))
    out.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(Path(tmp) / "0001.png"), out)
    shutil.rmtree(tmp, ignore_errors=True)
    comfy.free()
    return out


def credit(ref: Optional[ImageRef]) -> Optional[str]:
    return ref.credit if isinstance(ref, ImageInput) else None


def _rgb(hex_color: str):
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return [int(h[i:i + 2], 16) for i in (0, 2, 4)]


def render_gradient(g, size: tuple[int, int], seed: int = 7):
    """A `gradient:` backdrop: colour stops swept along `angle`, glows blended in, stars and grain on top."""
    import math
    import numpy as np
    from PIL import Image
    w, h = size
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    a = math.radians(g.angle)
    dx, dy = math.sin(a), -math.cos(a)                      # 180° sweeps top to bottom, 90° left to right
    extent = abs(w / 2 * dx) + abs(h / 2 * dy) or 1.0
    t = np.clip((((xx - w / 2) * dx + (yy - h / 2) * dy) / extent + 1) / 2, 0, 1)
    stops = np.array([_rgb(c) for c in g.colors], dtype=np.float32)
    pos = t * (len(stops) - 1)
    i = np.minimum(np.floor(pos).astype(int), len(stops) - 2)
    f = (pos - i)[..., None]
    img = stops[i] * (1 - f) + stops[i + 1] * f
    for glow in g.glows:
        r = max(glow.radius * max(w, h), 1.0)
        d = np.hypot(xx - glow.x * w, yy - glow.y * h) / r
        k = (glow.strength * np.exp(-d * d))[..., None]
        img = img * (1 - k) + np.array(_rgb(glow.color), dtype=np.float32) * k
    rng = np.random.default_rng(seed)
    if g.stars:
        for _ in range(g.stars):
            sx, sy = rng.uniform(0, w), rng.uniform(0, h * 0.7)
            size_px, bright = rng.uniform(0.6, 1.8), rng.uniform(0.25, 0.9)
            x0, x1 = max(int(sx - 5), 0), min(int(sx + 6), w)
            y0, y1 = max(int(sy - 5), 0), min(int(sy + 6), h)
            if x1 <= x0 or y1 <= y0:
                continue
            d = np.hypot(xx[y0:y1, x0:x1] - sx, yy[y0:y1, x0:x1] - sy) / size_px
            k = (bright * np.exp(-d * d))[..., None]
            img[y0:y1, x0:x1] = img[y0:y1, x0:x1] * (1 - k) + 255 * k
    if g.grain:
        img = img + rng.normal(0, g.grain * 255, (h, w, 1)).astype(np.float32)
    return Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))
