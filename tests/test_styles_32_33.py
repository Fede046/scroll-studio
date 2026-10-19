"""Styles 32 and 33 (scratch-film, smears): the templates render every block type from one spec, follow the style
contract (engine/styles/README.md), and the runtime keeps the rules that matter for phones, for scrolling and for
photosensitive visitors. No browser, no GPU, no network: fonts fall back to the Google link when they cannot be fetched."""
from __future__ import annotations

import re
import textwrap
from pathlib import Path

import pytest
import yaml

from engine.compile import themes
from engine.compile.compiler import build_site
from engine.project import Project

ROOT = Path(__file__).resolve().parent.parent
RT = ROOT / "runtime" / "src" / "styles"
STYLES = ("scratch-film", "smears")
SPEC = textwrap.dedent("""
    name: Testbed
    description: One of each block.
    theme: {preset: night}
    nav: {cta: {label: Go, href: "#end"}}
    sections:
      - {type: hero, badge: New, title: "Big <em>words.</em>", body: Lede, buttons: [{label: One, href: "#end"}, {label: Two, href: "#x"}]}
      - {type: intro, id: why, kicker: Why, title: "A <em>reason.</em>", body: Body, button: {label: More, href: "#"}}
      - type: features
        id: feat
        title: Rules
        items: [{tag: "01", title: A, body: a}, {tag: "02", title: B, body: b, meter: 0.4}, {title: C}]
      - type: product
        title: App
        body: Body
        tags: [iOS, Web]
        device: {app: X, title: T, options: [{title: One, selected: true}, {title: Two}], button: Go}
      - {type: stats, items: [{value: "11", unit: h, label: Hours}, {value: "0", label: None}]}
      - type: timeline
        title: Steps
        items: [{when: Day 1, title: Start, body: go}, {when: Day 2, title: Next}]
      - {type: quote, text: A quote., who: Someone}
      - {type: faq, title: Questions, items: [{q: "Why?", a: "Because."}, {q: "How?", a: "Like so."}]}
      - {type: gallery, title: Seen, items: [{title: One, href: "#"}, {title: Two, href: "#", kicker: k, body: b}]}
      - {type: orbit, title: Around, center: Hub, items: [{label: A, status: Live}, {label: B}]}
      - {type: cta, id: end, title: "Last <em>one.</em>", button: {label: Go, href: "#"}}
""")
CLS = {"scratch-film": "sf-reel", "smears": "sa-sheet"}


@pytest.fixture(scope="module")
def pages(tmp_path_factory):
    root = tmp_path_factory.mktemp("styles3233")
    (root / "site.yaml").write_text(SPEC, encoding="utf-8")
    p = Project(root)
    out = {}
    for style in STYLES:
        dest = root / "dist" / style
        build_site(p, style=style, out=dest, log=lambda m: None)
        out[style] = (dest / "index.html").read_text(encoding="utf-8")
    return out


@pytest.mark.parametrize("style", STYLES)
def test_style_registered(style):
    st = themes.styles()[style]
    assert st["label"] and st["about"] and st["fonts"]["display"]
    d = ROOT / "engine" / "styles" / style
    assert (d / "style.css").exists() and (d / "blocks.html.j2").exists() and (d / "chrome.html.j2").exists()
    assert (RT / f"{style}.ts").exists()


@pytest.mark.parametrize("style", STYLES)
def test_every_block_is_a_reel_or_sheet(pages, style):
    html = pages[style]
    assert f'data-style="{style}"' in html
    assert len(re.findall(rf'<section class="{CLS[style]} ', html)) == 11     # eleven blocks, each its own reel or sheet
    assert html.count("<h1") == 1                                             # one h1, the first heading on the page
    assert html.index("<h1") < html.index("<h2")
    assert "ss-reveal" not in html and "data-count" not in html               # a style has its own arrivals
    for needle in ("Big", "A quote.", "Because.", "Hub", "Day 2"):
        assert needle in html                                                 # every word is real text in reading order
    assert html.count("<details") == 2                                        # the FAQ stays native


@pytest.mark.parametrize("style", STYLES)
def test_kinds_and_anchors(pages, style):
    html = pages[style]
    for kind in ("hero", "intro", "features", "product", "stats", "timeline", "quote", "faq", "gallery", "orbit", "cta"):
        assert f'data-kind="{kind}"' in html, (style, kind)
    assert 'id="why"' in html and 'id="end"' in html and 'id="feat"' in html


def test_the_two_styles_differ_in_kind(pages):
    sf, sa = pages["scratch-film"], pages["smears"]
    assert "sf-gate" in sf and "sf-strip" in sf and "sa-impact" not in sf       # a projection and a strip
    assert "sa-impact" in sa and "sa-trail" in sa and "sf-gate" not in sa       # impact frames and a trail
    assert 'data-sa="title"' in sa and 'data-tone="leader"' in sf


def test_runtimes_keep_the_scroll_and_phone_rules():
    """Measured elsewhere in the batch: a custom property on <html> restyles the whole page (a throttled phone fell to
    22 fps). Both styles write only translate and per-element styles, put the text on a belt the runtime positions,
    and never take a vertical gesture."""
    sf = (RT / "scratch-film.ts").read_text(encoding="utf-8")
    sa = (RT / "smears.ts").read_text(encoding="utf-8")
    belt = (RT / "_belt.ts").read_text(encoding="utf-8")
    assert not re.search(r"documentElement\.style\.setProperty|html\.style\.setProperty", sf + sa + belt)
    assert "makeBelts" in sf and "makeBelts" in sa and "position: sticky" in belt
    assert "TICK = 1000 / 24" in sa                                           # smears: a 24-a-second clock, samples on twos
    assert "n % 2 === 0" in sa
    assert "pan-y" in (ROOT / "engine" / "styles" / "scratch-film" / "style.css").read_text(encoding="utf-8")
    pen = sf.split("addEventListener(\"pointermove\"")[1].split("const stroke")[0]
    assert "preventDefault" not in pen                                        # a vertical touch is never taken


def test_smears_has_no_blur():
    """The film has none (Persichetti, in docs/styles/styles-32-33.md): out of focus is a colour offset."""
    for f in (RT / "smears.ts", ROOT / "engine" / "styles" / "smears" / "style.css"):
        assert not re.search(r"blur\(", f.read_text(encoding="utf-8")), f


def _luma(h: str) -> float:
    h = h.lstrip("#")
    c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    lin = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in c]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def test_flicker_palettes_are_safe():
    """WCAG 2.3.1: scratch-film's dye grounds change within a luminance band of 0.1, its flash frames and the smears
    impact colours are mid-luminance, and nothing is saturated red."""
    draw = (RT / "_film-draw.ts").read_text(encoding="utf-8")
    grounds = re.search(r"GROUNDS = \[(.*?)\]", draw).group(1)
    g = [_luma(x) for x in re.findall(r"#[0-9a-f]{6}", grounds)]
    assert max(g) - min(g) < 0.1
    sa = (RT / "smears.ts").read_text(encoding="utf-8")
    impact = re.findall(r"#[0-9a-fA-F]{6}", re.search(r"HIT: Record<string, string> = \{(.*?)\}", sa).group(1))
    for c in re.findall(r"#[0-9a-fA-F]{6}", draw) + impact:
        r, gg, b = (int(c[i:i + 2], 16) for i in (1, 3, 5))
        assert not (r / max(1, r + gg + b) >= 0.8 and r > 150), c            # not a saturated red
    flash = re.search(r"FLASH = \[(.*?)\]", draw).group(1)
    for c in re.findall(r"#[0-9a-fA-F]{6}", flash) + impact:
        assert 0.1 < _luma(c) < 0.5, c                                        # a flash frame is neither white nor black
    assert "now - lastFlash > 450" in (RT / "scratch-film.ts").read_text(encoding="utf-8")
    assert "now - impactAt > 520" in sa                                       # never more than two a second


@pytest.mark.parametrize("style", STYLES)
def test_reduced_motion_and_yaml(style):
    css = (ROOT / "engine" / "styles" / style / "style.css").read_text(encoding="utf-8")
    assert "@media (prefers-reduced-motion: reduce)" in css
    d = yaml.safe_load((ROOT / "engine" / "styles" / style / "style.yaml").read_text(encoding="utf-8"))
    assert d["mode"] in ("light", "dark") and set(d["colors"]) >= {"bg", "ink", "accent"}
    ts = (RT / f"{style}.ts").read_text(encoding="utf-8")
    assert "if (reduced)" in ts                                               # no belt, no loop, a still
