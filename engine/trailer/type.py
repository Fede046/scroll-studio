"""The trailer's type layer: captions, callouts and the end card, set in HTML with the site's own (self-hosted)
fonts and theme colours, captured frame by frame as transparent PNGs by headless Chrome.

Each frame is drawn by `seek(t)` in type.html (no wall-clock animation), so captures are exact. Frames whose
drawing is identical (a caption holding still) are captured once and shared through index.json.
"""
from __future__ import annotations

import base64
import json
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Callable

from ..compile import fonts, themes
from ..project import BuildError

HERE = Path(__file__).resolve().parent

# per format: canvas, safe areas (TikTok/Reels/Shorts UI in 9:16) and type sizes, in pixels
LAYOUT = {
    "16x9": dict(W=1920, H=1080, padL=128, padR=128, padB=112, safeT=96, safeB=150, discB=56, title=116, kicker=30,
                 callout=176, card=132, measure="1240px", card_measure="1500px", tag_measure="1080px", end_title=172,
                 tagline=46, cta=38, url=30, disc=24, logo=80),
    "9x16": dict(W=1080, H=1920, padL=84, padR=172, padB=470, safeT=270, safeB=500, discB=420, title=112, kicker=34,
                 callout=168, card=124, measure="824px", card_measure="800px", tag_measure="760px", end_title=148,
                 tagline=50, cta=46, url=34, disc=29, logo=96),
}


def _rgb(h: str):
    return themes._rgb(h)


def theme_css(theme: dict, fmt: str) -> str:
    """The site's tokens plus what the trailer needs: light type over footage, readable accents, safe areas."""
    L = LAYOUT[fmt]
    c = theme["colors"]
    base = themes.css_vars(theme)
    dark = theme["mode"] == "dark"
    on_film = c["ink"] if dark else c["bg"]          # over footage the type is always the light one
    film_bg = (16, 16, 16)
    em_film = max((c["accent"], c["accent2"]), key=lambda h: themes.contrast(_rgb(h), film_bg))
    if themes.contrast(_rgb(em_film), film_bg) < 3:
        em_film = on_film
    bgs = [_rgb(c["bg"]), _rgb(c["bg2"])]
    em_card = themes._css_rgb(themes._readable_accent(_rgb(c["accent"]), _rgb(c["ink"]), bgs, 3.0))
    em_weight = {"bold": "700", "heavy": "900"}.get(theme["em"], "inherit")
    caps = theme.get("labels", "caps") == "caps"
    r, g, b = (round(v) for v in _rgb(on_film))
    disp_w = int(theme["display_weight"])
    tokens = {
        "--W": f"{L['W']}px", "--H": f"{L['H']}px",
        "--on-film": on_film, "--on-film-2": f"rgba({r}, {g}, {b}, .84)", "--em-film": em_film, "--em-card": em_card,
        "--em-weight": em_weight, "--callout-weight": str(min(900, max(disp_w, 600))),
        "--font-label": "var(--font-mono)" if caps else "var(--font-body)",
        "--label-case": "uppercase" if caps else "none", "--label-track": ".2em" if caps else ".01em",
        "--pill": f"max({theme['radius']}, 3px)",
        "--scrim": ("linear-gradient(to top, rgba(0,0,0,.66) 0%, rgba(0,0,0,.5) 22%, rgba(0,0,0,.16) 46%, rgba(0,0,0,0) 62%)"
                    if fmt == "16x9" else
                    "linear-gradient(to top, rgba(0,0,0,.25) 0%, rgba(0,0,0,.62) 22%, rgba(0,0,0,.5) 36%, rgba(0,0,0,.12) 52%, rgba(0,0,0,0) 62%)"),
    }
    for k in ("padL", "padR", "padB", "safeT", "safeB", "discB", "title", "kicker", "callout", "card", "end_title",
              "tagline", "cta", "url", "disc", "logo"):
        tokens["--" + k.replace("_", "-")] = f"{L[k]}px"
    for k in ("measure", "card_measure", "tag_measure"):
        tokens["--" + k.replace("_", "-")] = L[k]
    return base + "\n:root {\n" + "\n".join(f"  {k}: {v};" for k, v in tokens.items()) + "\n}"


def font_specs(theme: dict) -> list[str]:
    f, w = theme["fonts"], int(theme["display_weight"])
    return [f'{w} 100px "{f["display"]}"', f'italic {w} 100px "{f["display"]}"', f'700 100px "{f["display"]}"',
            f'italic 700 100px "{f["display"]}"', f'{max(w, 600)} 100px "{f["display"]}"', f'400 40px "{f["body"]}"',
            f'600 40px "{f["body"]}"', f'italic 400 40px "{f["body"]}"', f'500 30px "{f["mono"]}"']


def render(timeline: dict, theme: dict, fmt: str, out: Path, log: Callable[[str], None] = print,
           progress: Callable[[float, str], None] = lambda f, m="": None) -> Path:
    """Capture the type layer of one format into out/: unique RGBA PNGs and index.json (one entry per frame: a
    file name, or null when nothing is drawn)."""
    from ..record import CDP, _chrome, _free_port
    from ..serve import serve
    import requests
    L = LAYOUT[fmt]
    W, H, fps, n = L["W"], L["H"], timeline["fps"], timeline["frames"]
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    site = Path(tempfile.mkdtemp(prefix="ss_type_"))
    css = fonts.vendor(themes.font_links(theme), site, log)
    if css is None:
        log("  note: the theme's fonts could not be fetched or found in the cache; the trailer falls back to system faces")
    page = (HERE / "type.html").read_text(encoding="utf-8")
    page = page.replace("/*VARS*/", theme_css(theme, fmt))
    page = page.replace("/*TIMELINE*/null", json.dumps({**timeline, "fonts": font_specs(theme)}))
    (site / "index.html").write_text(page, encoding="utf-8")
    port, dbg = _free_port(), _free_port()
    httpd = serve(site, port, background=True)
    prof = tempfile.mkdtemp(prefix="cdp_")
    proc = subprocess.Popen([_chrome(), "--headless=new", f"--remote-debugging-port={dbg}", f"--user-data-dir={prof}",
                             f"--window-size={W},{H}", "--hide-scrollbars", "--force-device-scale-factor=1",
                             "--font-render-hinting=none", "about:blank"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    index: list = []
    try:
        ws = None
        for _ in range(80):
            try:
                tabs = requests.get(f"http://127.0.0.1:{dbg}/json", timeout=1).json()
                ws = next(t["webSocketDebuggerUrl"] for t in tabs if t["type"] == "page")
                break
            except Exception:
                time.sleep(0.25)
        if not ws:
            raise BuildError("trailer: could not start headless Chrome for the type layer")
        cdp = CDP(ws)
        cdp.call("Emulation.setDeviceMetricsOverride", width=W, height=H, deviceScaleFactor=1, mobile=False)
        cdp.call("Emulation.setDefaultBackgroundColorOverride", color={"r": 0, "g": 0, "b": 0, "a": 0})
        cdp.call("Page.enable")
        cdp.call("Page.navigate", url=f"http://127.0.0.1:{port}/index.html")
        for _ in range(160):
            if cdp.js("document.readyState") == "complete" and cdp.js("typeof window.seek") == "function":
                break
            time.sleep(0.1)
        cdp.js("window.ready")
        last_sig, last_file, shots = None, None, 0
        for i in range(n):
            sig = cdp.js(f"window.seek({i / fps:.5f})")
            if not sig:
                index.append(None)
                last_sig = None
                continue
            if sig != last_sig:
                png = cdp.call("Page.captureScreenshot", format="png")["data"]
                last_file = f"{shots:05d}.png"
                (out / last_file).write_bytes(base64.b64decode(png))
                shots += 1
                last_sig = sig
            index.append(last_file)
            if i % 24 == 0:
                progress(i / n, f"type {fmt} {i}/{n}")
        cdp.ws.close()
    finally:
        proc.terminate()
        httpd.shutdown()
        shutil.rmtree(prof, ignore_errors=True)
        shutil.rmtree(site, ignore_errors=True)
    (out / "index.json").write_text(json.dumps(index))
    log(f"  type {fmt}: {n} frames, {len(set(x for x in index if x))} drawn")
    return out
