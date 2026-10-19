"""The boards: stills for every direction, one page with all the directions side by side, and a PNG contact sheet.

  <project>/directions/
    directions.json   the directions, how they were written, what was picked
    board.html        the page (served by `studio directions --serve`, or open the file; self-contained with stills/ and fonts/)
    board.png         the contact sheet: the same page, photographed
    stills/           small JPEGs of every still
    fonts/            the directions' Google Fonts, self-hosted (so the page and the PNG show the real type)
    backups/          site.yaml as it was before each pick

The stills are Z-Image Turbo, drawn through the same `generate_image` the build uses, at small size and with the same
seed in every direction, so what differs between two boards is the direction and nothing else.
"""
from __future__ import annotations

import base64
import hashlib
import html
import json
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Callable

from ..compile import fonts as fontlib
from ..compile import themes
from ..inputs import generate_image, generated_digest
from ..project import BuildError, Project
from . import shots, typefaces
from .model import Direction

STILL_SIZE = (768, 432)         # drawn at this size (multiples of 16)
THUMB = 640                     # shipped width of a still
HERE = Path(__file__).parent


def folder(project: Project) -> Path:
    d = project.root / "directions"
    d.mkdir(parents=True, exist_ok=True)
    return d


def stills_dir(project: Project) -> Path:
    d = folder(project) / "stills"
    d.mkdir(exist_ok=True)
    return d


# ---------------------------------------------------------------- stills

def draw_stills(project: Project, dirs: list[Direction], moments: list[shots.Moment], log: Callable[[str], None] = print,
                generate: bool = True, progress: Callable[[float, str], None] = lambda f, m="": None) -> None:
    """Fill direction.stills: for each moment a still in that direction's imagery (a placeholder card without ComfyUI)."""
    from ..backends import comfy
    from ..fidelity import placeholder
    out = stills_dir(project)
    alive = generate and comfy.alive()
    if generate and not alive:
        log("  ComfyUI is not running: the boards get placeholder cards (start ComfyUI and run `studio directions --stills`)")
    w, h = STILL_SIZE
    jobs = [(d, k, m, shots.prompt_for(m, d.imagery)) for d in dirs for k, m in enumerate(moments)]
    if alive:
        # every still is queued at once: ComfyUI may be shared, and one run of consecutive Z-Image jobs loads the model
        # once instead of once per still between other people's jobs
        from concurrent.futures import ThreadPoolExecutor
        todo = [j for j in jobs if not (project.build / "_generated" / f"{generated_digest(j[3], w, h, j[2].seed)}.png").exists()]
        if todo:
            log(f"  drawing {len(todo)} stills ({len(jobs) - len(todo)} cached)")
            comfy.free()
        done_n = 0
        with ThreadPoolExecutor(max_workers=max(1, min(len(todo), 32))) as ex:
            futs = {ex.submit(generate_image, project, j[3], w, h, j[2].seed, log, False): j for j in todo}
            for f, j in futs.items():
                f.result()
                done_n += 1
                progress(0.85 * done_n / max(1, len(todo)), f"{j[0].name}: {j[2].role}")
    done = 0
    for d in dirs:
        d.stills = []
        for k, m in enumerate(moments):
            prompt = shots.prompt_for(m, d.imagery)
            if alive:
                src = generate_image(project, prompt, w, h, m.seed, log, False)
            else:
                src = placeholder(project.build / "_storyboard" / "placeholders", prompt, (w, h), "direction still, not drawn yet",
                                  d.palette["bg2"])
            tag = hashlib.sha1(f"{src}{src.stat().st_size}".encode()).hexdigest()[:8]
            jpg = out / f"{d.id}{k}_{tag}.jpg"
            if not jpg.exists():
                from PIL import Image
                im = Image.open(src).convert("RGB")
                im.thumbnail((THUMB, THUMB), Image.LANCZOS)
                for old in out.glob(f"{d.id}{k}_*.jpg"):
                    old.unlink()
                im.save(jpg, quality=86)
            d.stills.append({"role": m.role, "section": m.section, "title": m.title, "kicker": m.kicker, "prompt": prompt,
                             "seed": m.seed, "image": f"stills/{jpg.name}", "placeholder": not alive,
                             "title_html": m.title_html, "title_short": html.escape(_short(m.title)), "slug": re.sub(r"[^a-z0-9]+", "-", (m.section or m.type).lower()).strip("-") + ".html"})
            done += 1
        log(f"  {d.id.upper()} {d.name}: {len(d.stills)} stills")
    keep = {Path(s["image"]).name for d in dirs for s in d.stills}
    for f in out.glob("*.jpg"):
        if f.name not in keep:
            f.unlink()


# ---------------------------------------------------------------- the page

def _short(title: str, limit: int = 30) -> str:
    """A headline cut at a word for the small stills."""
    t = (title or "").strip()
    if len(t) <= limit:
        return t
    cut = t[:limit].rsplit(" ", 1)[0].rstrip(" ,.;:")
    return cut + "…"


def _em_style(d: Direction) -> str:
    f = d.fonts
    return "italic" if (f.get("italic_em") or f.get("em") == "bold") else "normal"


def _em_color(d: Direction) -> str:
    return "var(--accent)" if d.fonts.get("em", "accent") == "accent" else "var(--ink)"


def _em_weight(d: Direction) -> str:
    return {"accent": "inherit", "bold": "700", "heavy": "900"}.get(d.fonts.get("em", "accent"), "inherit")


def _css_font(name: str, kind: str = "") -> str:
    if kind == "mono" or typefaces.CLASS.get(name) == "mono":
        fb = 'ui-monospace, "Cascadia Mono", Consolas, monospace'
    elif name in themes.SERIFS:
        fb = "Georgia, serif"
    else:
        fb = "system-ui, sans-serif"
    return f'"{name}", {fb}'


def _swatch_ink(hex_: str) -> str:
    return "#111111" if themes.contrast(themes._rgb(hex_), themes._rgb("#111111")) >= themes.contrast(themes._rgb(hex_), themes._rgb("#ffffff")) else "#ffffff"


def _safe_title(text: str) -> str:
    """A headline as HTML keeping only <em>."""
    t = html.escape(re.sub(r"</?(?!em\b)[a-z][^>]*>", "", text or "", flags=re.I), quote=False)
    return t.replace("&lt;em&gt;", "<em>").replace("&lt;/em&gt;", "</em>")


def _hero_title(m: shots.Moment) -> str:
    t = m.title_html or html.escape(m.title)
    if "<em>" not in t:
        words = t.rstrip(".").split()
        if len(words) >= 3:
            tail = " ".join(words[-2:])
            t = " ".join(words[:-2]) + f" <em>{tail}</em>" + ("." if m.title.endswith(".") else "")
    return t


def font_links(dirs: list[Direction]) -> list[str]:
    links, seen = [], set()
    for d in dirs:
        for role in ("display", "body", "mono"):
            fam = d.fonts[role]
            if fam in seen:
                continue
            seen.add(fam)
            links += themes.font_links({"fonts": {"x": fam}, "font_axes": {}})
    return links


def vendor_fonts(project: Project, dirs: list[Direction], log) -> list[str]:
    """The directions' fonts self-hosted under directions/fonts (their CSS href), else the Google Fonts links."""
    links = font_links(dirs)
    try:
        href = fontlib.vendor(links, folder(project), log)
    except Exception as e:
        log(f"  fonts not self-hosted ({e.__class__.__name__})")
        href = None
    return [href] if href else links


def write_page(project: Project, state: dict, log: Callable[[str], None] = print) -> Path:
    """directions/board.html from the saved state."""
    from jinja2 import Environment, FileSystemLoader, select_autoescape
    dirs = [Direction.from_dict(d) for d in state["directions"]]
    moments = [m for m in state.get("moments", [])]
    env = Environment(loader=FileSystemLoader(str(HERE)), autoescape=select_autoescape(["html", "j2"]))
    env.globals.update(css_font=_css_font, em_style=_em_style, em_color=_em_color, em_weight=_em_weight, swatch_ink=_swatch_ink)
    hero = shots.Moment(**{k: v for k, v in moments[0].items() if k in shots.Moment.__dataclass_fields__}) if moments else None
    brief = state["brief"]
    read_line = "; ".join(brief.get("notes") or [])
    tpl = env.get_template("board.html.j2")
    page = tpl.render(site={"name": brief["name"], "description": brief["description"]}, brief=brief, directions=dirs,
                      font_links=vendor_fonts(project, dirs, log), seed=state["seed"], count=state["count"],
                      made=state["made"], diversity=state["diversity"], replaced=state.get("replaced") or [],
                      warnings=state.get("warnings") or [], picked=(state.get("picked") or {}).get("id"),
                      project=project.name, read_line=read_line, hero_title_html=_hero_title(hero) if hero else html.escape(brief["name"]),
                      state_json=json.dumps({"seed": state["seed"], "picked": state.get("picked")}).replace("</", "<\\/"))
    out = folder(project) / "board.html"
    out.write_text(page, encoding="utf-8", newline="\n")
    return out


# ---------------------------------------------------------------- the contact sheet

def screenshot(root: Path, page: str, out: Path, width: int = 1800, log: Callable[[str], None] = print) -> Path:
    """The page photographed whole by headless Chrome, once its fonts and pictures have loaded."""
    import requests
    from ..record import CDP, _chrome, _free_port
    from ..serve import serve
    port, dbg = _free_port(), _free_port()
    httpd = serve(root, port, background=True)
    prof = tempfile.mkdtemp(prefix="dirs_")
    proc = subprocess.Popen([_chrome(), "--headless=new", f"--remote-debugging-port={dbg}", f"--user-data-dir={prof}",
                             f"--window-size={width},1000", "--hide-scrollbars", "--force-device-scale-factor=1", "about:blank"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        ws = None
        for _ in range(80):
            try:
                ws = next(t["webSocketDebuggerUrl"] for t in requests.get(f"http://127.0.0.1:{dbg}/json", timeout=1).json()
                          if t["type"] == "page")
                break
            except Exception:
                time.sleep(0.25)
        if not ws:
            raise BuildError("could not connect to headless Chrome for the contact sheet")
        cdp = CDP(ws)
        cdp.call("Emulation.setDeviceMetricsOverride", width=width, height=1000, deviceScaleFactor=1, mobile=False)
        cdp.call("Page.enable")
        cdp.call("Page.navigate", url=f"http://127.0.0.1:{port}/{page}")
        for _ in range(120):
            if cdp.js("document.readyState") == "complete":
                break
            time.sleep(0.25)
        cdp.js("document.fonts.ready.then(() => true)")
        for _ in range(60):
            if cdp.js("Array.from(document.images).every(i => i.complete)"):
                break
            time.sleep(0.25)
        time.sleep(0.8)
        height = int(cdp.js("Math.ceil(document.documentElement.scrollHeight)") or 1000)
        cdp.call("Emulation.setDeviceMetricsOverride", width=width, height=height, deviceScaleFactor=1, mobile=False)
        time.sleep(0.5)
        png = base64.b64decode(cdp.call("Page.captureScreenshot", format="png", captureBeyondViewport=True,
                                        clip={"x": 0, "y": 0, "width": width, "height": height, "scale": 1})["data"])
        out.write_bytes(png)
        cdp.ws.close()
    finally:
        proc.terminate()
        httpd.shutdown()
        shutil.rmtree(prof, ignore_errors=True)
    log(f"  contact sheet: {out}")
    return out
