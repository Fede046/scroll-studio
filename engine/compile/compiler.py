"""Site compiler: spec + built scene assets + runtime bundle -> dist/ (plain static files)."""
from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path
from typing import Callable, Optional

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup

from ..config import STATIC
from ..inputs import credit as image_credit, resolve_image
from ..project import BuildContext, BuildError, Project, ffmpeg
from ..spec import Site, is_scene
from . import fonts, themes

TEMPLATES = Path(__file__).resolve().parent / "templates"


def _env() -> Environment:
    env = Environment(loader=FileSystemLoader(TEMPLATES), autoescape=select_autoescape(["html", "j2"]),
                      trim_blocks=True, lstrip_blocks=True)
    # Copy fields allow a little inline markup (<em>, <br>, <b>, <i>); everything else is escaped.
    allowed = re.compile(r"&lt;(/?)(em|b|i|br|strong)\s*/?&gt;")
    def rich(text):
        if text is None:
            return ""
        esc = str(Markup.escape(text))
        return Markup(allowed.sub(lambda m: f"<{m.group(1)}{m.group(2)}>", esc))
    env.filters["rich"] = rich
    env.filters["vh"] = lambda v: f"{float(v) * 100:.0f}vh"
    env.filters["countable"] = lambda v: bool(re.fullmatch(r"\d+(\.\d+)?", str(v).replace(",", "")))
    return env


def _knockout(im):
    """Push a light studio background to pure white so a multiply blend makes it vanish into the panel.

    The background colour is sampled from the image's edges; every channel is scaled so it maps to 255, then
    pixels that end up near-white are eased the rest of the way. Shadows and the product keep their shading.
    """
    import numpy as np
    from PIL import Image
    a = np.asarray(im).astype(np.float32)
    h, w = a.shape[:2]
    b = max(4, min(h, w) // 30)
    edge = np.concatenate([a[:b].reshape(-1, 3), a[-b:].reshape(-1, 3), a[:, :b].reshape(-1, 3), a[:, -b:].reshape(-1, 3)])
    bg = np.percentile(edge, 75, axis=0)
    if bg.mean() < 170:   # not a light studio background: leave the image alone
        return im
    a = np.clip(a * (255.0 / np.maximum(bg, 1)), 0, 255)
    lum = a @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
    t = np.clip((lum - 232) / 16, 0, 1)[..., None]
    t = t * t * (3 - 2 * t)
    a = a * (1 - t) + 255 * t
    return Image.fromarray(a.astype(np.uint8))


def _translated(cfg: dict, base: dict, sec: dict) -> dict:
    """A scene's config for a page in another language. Configs echo some spec fields verbatim (a type scene's text
    and words); those take the translation's values, and everything built stays shared."""
    return {k: sec[k] if k in base and k in sec and v == base[k] else v for k, v in cfg.items()}


def runtime_ready() -> bool:
    return (STATIC / "runtime" / "index.js").exists()


def nav_links(site: Site) -> list[dict]:
    if site.nav.links:
        return [l.model_dump() for l in site.nav.links]
    return [{"label": s.nav_label, "href": f"#{s.id}"} for s in site.sections if getattr(s, "nav_label", None) and s.id]


def build_site(project: Project, log: Callable[[str], None] = print,
               progress: Callable[[float, str], None] = lambda f, m="": None,
               only: Optional[str] = None, force: bool = False, options: Optional[dict] = None) -> Path:
    from ..scenes import builder_for

    site = project.load()
    if not runtime_ready():
        raise BuildError("the browser runtime is not built. Run `npm install && npm run build` in the repo root "
                         "(or `studio setup`).")
    theme = themes.resolve(site.theme)
    dist = project.dist
    dist.mkdir(parents=True, exist_ok=True)
    (dist / "assets").mkdir(exist_ok=True)

    # Scenes are built once, from site.yaml; every language shares their media.
    configs = {}
    scenes = [s for s in site.sections if is_scene(s)]
    for k, sec in enumerate(scenes):
        if only and sec.id != only:
            prev = project.build / sec.id / "config.json"
            if not prev.exists():
                raise BuildError(f"section {sec.id} has never been built; build it first")
            configs[sec.id] = json.loads(prev.read_text())
        else:
            log(f"[{sec.id}] {sec.type}")
            ctx = BuildContext(project, sec.id, log=log, force=force, options=options or {},
                               progress=lambda f, m="", k=k: progress((k + f) / max(len(scenes), 1), m))
            configs[sec.id] = builder_for(sec.type)(sec, ctx, theme)
            (ctx.work / "config.json").write_text(json.dumps(configs[sec.id]))
        web = project.build / sec.id / "web"
        if web.exists():
            dst = dist / "assets" / sec.id
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(web, dst)
    base_scenes = {sec.id: sec.model_dump(mode="json") for sec in scenes}

    # Block media given as project files are copied into the site; URLs pass through untouched.
    media = dist / "assets" / "_media"
    def publish(ref):
        if not ref or ref.startswith(("http://", "https://", "/", "assets/", "../")):
            return ref
        src = project.path(ref)
        if not src.exists():   # e.g. a gallery preview not generated on this machine: the tile falls back to its image
            log(f"  note: {ref} not found, skipped")
            return None
        media.mkdir(parents=True, exist_ok=True)
        shutil.copy(src, media / src.name)
        return f"assets/_media/{src.name}"

    # Images inside blocks (hero, product, strip) can be files, URLs or generated; each is resized once to the
    # width it is shown at and written as WebP.
    def block_image(ref, width: int, credits: list, knockout: bool = False) -> Optional[str]:
        if ref is None:
            return None
        src = resolve_image(project, ref, log)
        st = src.stat()
        digest = hashlib.sha1(json.dumps([str(src), st.st_size, int(st.st_mtime), width, knockout, 1]).encode()).hexdigest()[:12]
        out = media / f"{digest}.webp"
        if not out.exists():
            from PIL import Image
            media.mkdir(parents=True, exist_ok=True)
            im = Image.open(src).convert("RGB")
            if im.width > width:
                im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
            if knockout:
                im = _knockout(im)
            im.save(out, "WEBP", quality=86, method=6)
        if image_credit(ref):
            credits.append(image_credit(ref))
        return f"assets/_media/{out.name}"

    # Clips inside blocks (a product's video) are re-encoded once for the web: H.264 no wider than they are shown,
    # no sound, the index up front so they start playing before they have finished downloading.
    def block_video(ref: Optional[str], width: int) -> Optional[str]:
        if not ref or ref.startswith(("http://", "https://", "/", "assets/", "../")):
            return ref
        src = project.path(ref)
        if not src.exists():
            log(f"  note: {ref} not found, skipped")
            return None
        st = src.stat()
        digest = hashlib.sha1(json.dumps([str(src), st.st_size, int(st.st_mtime), width, 1]).encode()).hexdigest()[:12]
        out = media / f"{digest}.mp4"
        if not out.exists():
            media.mkdir(parents=True, exist_ok=True)
            log(f"  {ref}: encoding for the web")
            ffmpeg("-i", str(src), "-an", "-vf", f"scale='min({width},iw)':-2", "-c:v", "libx264", "-preset", "slow",
                   "-crf", "27", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out), log=log)
        return f"assets/_media/{out.name}"

    rt = dist / "runtime"
    if rt.exists():
        shutil.rmtree(rt)
    shutil.copytree(STATIC / "runtime", rt)

    # A nav logo given as an image file is copied in like any other media; SVG path data passes through.
    logo = site.nav.logo
    if logo and not logo.startswith("M"):
        logo = publish(logo)

    links = themes.font_links(theme)
    font_css = fonts.vendor(links, dist, log)
    env = _env()
    css_vars = themes.css_vars(theme, log)
    page_links = [{"label": p.title, "href": f"{p.slug}/"} for p in site.pages]
    languages = [{"lang": site.lang, "href": "index.html"}] + [{"lang": t.lang, "href": f"{t.lang}.html"} for t in site.translations]

    def render(s: Site, out: Path) -> list[dict]:
        """One language's page from its spec: the scene configs built above, the blocks' media, the template."""
        sections, credits = [], []
        for i, sec in enumerate(s.sections):
            e = {"s": sec, "scene": is_scene(sec), "config": None, "sdata": None,
                 "first": i == 0}   # only the opening section gets the page's h1
            if e["scene"]:
                e["config"] = _translated(configs[sec.id], base_scenes[sec.id], sec.model_dump(mode="json"))
                e["sdata"] = sec.model_dump(mode="json", include={"hud", "steps", "layout", "length"})
                credits += e["config"].get("credits", [])
            elif sec.type == "gallery":
                e["s"] = sec.model_copy(update={"items": [it.model_copy(update={"image": publish(it.image), "video": publish(it.video)})
                                                          for it in sec.items]})
            sections.append(e)
        for e in sections:
            b = e["s"]
            e["backdrop"] = block_image(getattr(b, "backdrop", None), 2400, credits)
            if b.type == "hero":
                e["img"], e["video"] = block_image(b.image, 2400, credits), publish(b.video)
                e["screen"] = block_image(b.device.image, 800, credits) if b.device and b.device.image else None
                e["clip"] = publish(b.device.video) if b.device and b.device.video else None
            elif b.type == "product":
                e["img"] = block_image(b.image, 1600, credits, knockout=b.knockout and b.surface != "dark" and not b.video)
                e["video"] = block_video(b.video, 1600)
                e["screen"] = block_image(b.device.image, 800, credits) if b.device and b.device.image else None
                e["clip"] = publish(b.device.video) if b.device and b.device.video else None
                e["behind"] = block_image(b.behind.image, 800, credits) if b.behind and b.behind.image else None
                e["behind_clip"] = publish(b.behind.video) if b.behind and b.behind.video else None
            elif b.type == "strip":
                e["imgs"] = [block_image(it.image, 900, credits) for it in b.items]

        # CTA backgrounds can borrow a scene's final frame
        finals = {e["s"].id: (e["config"] or {}).get("end") for e in sections if e["scene"]}
        for e in sections:
            bg = getattr(e["s"], "background", None)
            if e["s"].type == "cta" and bg:
                e["bg"] = finals.get(bg[6:]) if bg.startswith("scene:") else publish(bg)

        nav = nav_links(s) + [l for l, p in zip(page_links, s.pages) if p.nav]
        html = env.get_template("site.html.j2").render(
            site=s, sections=sections, theme=theme, css_vars=css_vars, logo=logo,
            font_css=font_css, font_links=[] if font_css else links, nav_links=nav, page_links=page_links, credits=credits,
            configs={e["s"].id: e["config"] for e in sections if e["scene"]},
            languages=[dict(l, current=l["lang"] == s.lang) for l in languages] if len(languages) > 1 else [],
        )
        out.write_text(html, encoding="utf-8")
        return nav

    nav = render(site, dist / "index.html")
    for t in site.translations:
        render(project.load_translation(t), dist / f"{t.lang}.html")
        log(f"{t.lang} -> {dist / f'{t.lang}.html'}")

    # Plain pages (privacy policy, support): Markdown set in the site's theme at /<slug>/. They live one
    # level down, so every site-relative link gets the `base` prefix.
    if site.pages:
        import markdown
        base = "../"
        def rebase(href: str) -> str:
            return href if href.startswith(("http://", "https://", "mailto:", "tel:")) else base + href
        for p in site.pages:
            src = project.path(p.source)
            if not src.exists():
                raise BuildError(f"page '{p.slug}': {p.source} not found")
            body = markdown.markdown(src.read_text(encoding="utf-8"), extensions=["sane_lists", "smarty", "tables", "fenced_code", "toc"],
                                     extension_configs={"toc": {"permalink": False}})
            page_html = env.get_template("page.html.j2").render(
                site=site, page=p, body=Markup(body), theme=theme, css_vars=css_vars, base=base,
                logo=rebase(logo) if logo and not logo.startswith("M") else logo,
                font_css=rebase(font_css) if font_css else None, font_links=[] if font_css else links,
                nav_links=[{"label": l["label"], "href": rebase(l["href"])} for l in nav],
                page_links=[{"label": l["label"], "href": rebase(l["href"])} for l in page_links],
            )
            out = dist / p.slug
            out.mkdir(parents=True, exist_ok=True)
            (out / "index.html").write_text(page_html, encoding="utf-8")
            log(f"page -> {out / 'index.html'}")

    progress(1.0, "done")
    log(f"site -> {dist / 'index.html'}")
    return dist / "index.html"
