"""Styles 30 and 31 (paint-on-glass, multiplane): the templates render every block type from one spec as beats the
runtime can drive, follow the style contract (engine/styles/README.md), and the runtime keeps the rules measured to
matter. No browser, no GPU, no network."""
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
STYLES = {"paint-on-glass": "data-pg", "multiplane": "data-mp"}
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
        items: [{tag: "01", title: A, body: a}, {tag: "02", title: B, body: b, meter: 0.4}, {tag: Long tag, title: C}]
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
# beats: hero 1, intro 1, features 1 + 3, product 1, stats 1, timeline 1 + 2, quote 1, faq 1 + 2, gallery 1, orbit 1, cta 1
BEATS = 18


@pytest.fixture(scope="module")
def pages(tmp_path_factory):
    root = tmp_path_factory.mktemp("styles3031")
    (root / "site.yaml").write_text(SPEC, encoding="utf-8")
    p = Project(root)
    out = {}
    for style in STYLES:
        dest = root / "dist" / style
        build_site(p, style=style, out=dest, log=lambda m: None)
        out[style] = (dest / "index.html").read_text(encoding="utf-8")
    return out


@pytest.mark.parametrize("style", list(STYLES))
def test_style_registered(style):
    st = themes.styles()[style]
    assert st["label"] and st["about"] and st["fonts"]["display"]
    d = ROOT / "engine" / "styles" / style
    assert (d / "style.css").exists() and (d / "blocks.html.j2").exists() and (d / "chrome.html.j2").exists()
    assert (ROOT / "runtime" / "src" / "styles" / f"{style}.ts").exists()


@pytest.mark.parametrize("style,attr", list(STYLES.items()))
def test_every_block_is_made_of_beats(pages, style, attr):
    html = pages[style]
    assert f'data-style="{style}"' in html
    assert len(re.findall(rf'\s{attr}="', html)) == BEATS             # a section, or one item of a list, is a beat
    assert html.count("<h1") == 1 and html.index("<h1") < html.index("<h2")
    assert "ss-reveal" not in html and "data-count" not in html        # a style has its own arrivals
    for needle in ("Big", "A quote.", "Because.", "Hub", "Long tag", "Like so."):
        assert needle in html                                          # every word is real text in reading order
    assert html.count("<details") == 2                                 # the FAQ stays native


def test_paint_on_glass_markup(pages):
    html = pages["paint-on-glass"]
    assert 'class="pg-canvas"' in html and 'class="pg-script"' in html
    assert html.count("pg-copy") >= BEATS                              # every beat has a measurable box of words
    assert re.search(r'data-side="[lrc]"', html) and 'data-k="3"' in html
    assert "pg-num" in html and "pg-kicker" in html                    # a numeral tag is painted large, a long tag is a label


def test_multiplane_markup(pages):
    html = pages["multiplane"]
    assert 'class="mp-world"' in html and 'class="mp-gauge"' in html
    assert html.count("mp-plane mp-copy") == BEATS                     # every beat's words are a plane
    assert 'data-mp-d="0.84"' in html                                  # the phone is a prop at its own distance
    assert html.count("mp-sec") >= 11


def test_runtime_keeps_the_rules():
    """Measured or contracted: nothing writes custom properties on <html> (restyles the whole document), scrolling is
    never intercepted, and reduced motion has its own path."""
    pg = (ROOT / "runtime/src/styles/paint-on-glass.ts").read_text(encoding="utf-8")
    mp = (ROOT / "runtime/src/styles/multiplane.ts").read_text(encoding="utf-8")
    for src in (pg, mp):
        assert not re.search(r"documentElement\.style\.setProperty|html\.style\.setProperty|root\.style\.setProperty", src)
        assert "preventDefault" not in src and "wheel" not in src.replace("mouseWheel", "")
        assert "reduced" in src and "prefers-reduced" not in src or "reduced" in src
    assert "passive: true" in pg and "passive: true" in mp
    css = (ROOT / "engine/styles/paint-on-glass/style.css").read_text(encoding="utf-8") + \
          (ROOT / "engine/styles/multiplane/style.css").read_text(encoding="utf-8")
    assert css.count("@media (prefers-reduced-motion: reduce)") >= 2
    assert "html:not(.pg-live)" in css and "html:not(.mp-live)" in css   # the page without the runtime is styled too


def test_style_yaml_is_valid():
    for style in STYLES:
        d = yaml.safe_load((ROOT / "engine" / "styles" / style / "style.yaml").read_text(encoding="utf-8"))
        assert d["mode"] in ("light", "dark") and set(d["colors"]) >= {"bg", "ink", "accent"}
        assert d["fonts"]["display"] and d["font_axes"]
