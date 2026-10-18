"""Styles 28 and 29 (stop-motion, paper-cut-out): the templates render every block type from one spec, follow the style
contract (engine/styles/README.md), and the runtime keeps the two rules that were measured to matter for phones.
No browser, no GPU, no network: fonts fall back to the Google link when they cannot be fetched."""
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


@pytest.fixture(scope="module")
def pages(tmp_path_factory):
    root = tmp_path_factory.mktemp("styles2829")
    (root / "site.yaml").write_text(SPEC, encoding="utf-8")
    p = Project(root)
    out = {}
    for style in ("stop-motion", "paper-cut-out"):
        dest = root / "dist" / style
        build_site(p, style=style, out=dest, log=lambda m: None)
        out[style] = (dest / "index.html").read_text(encoding="utf-8")
    return out


@pytest.mark.parametrize("style", ["stop-motion", "paper-cut-out"])
def test_style_registered(style):
    st = themes.styles()[style]
    assert st["label"] and st["about"] and st["fonts"]["display"]
    d = ROOT / "engine" / "styles" / style
    assert (d / "style.css").exists() and (d / "blocks.html.j2").exists() and (d / "chrome.html.j2").exists()
    assert (ROOT / "runtime" / "src" / "styles" / f"{style}.ts").exists()


@pytest.mark.parametrize("style,sel", [("stop-motion", "sm-set"), ("paper-cut-out", "pc-sheet")])
def test_every_block_is_a_set(pages, style, sel):
    html = pages[style]
    assert f'data-style="{style}"' in html
    assert len(re.findall(rf'<section class="{sel} ', html)) == 11      # eleven blocks, each its own set or sheet
    assert html.count("<h1") == 1                                      # one h1, the first heading on the page
    assert html.index("<h1") < html.index("<h2")
    assert "ss-reveal" not in html and "data-count" not in html        # a style has its own arrivals
    for needle in ("Big", "A quote.", "Because.", "Hub"):
        assert needle in html                                          # every word is real text in reading order


def test_kinds_and_anchors(pages):
    for style, prefix in (("stop-motion", "sm"), ("paper-cut-out", "pc")):
        html = pages[style]
        for kind in ("hero", "intro", "features", "product", "stats", "timeline", "quote", "faq", "gallery", "orbit", "cta"):
            assert f'data-kind="{kind}"' in html, (style, kind)
        assert 'id="why"' in html and 'id="end"' in html and 'id="feat"' in html
        assert html.count("<details") == 2                             # the FAQ stays native


def test_runtime_keeps_the_phone_rules():
    """Measured: a custom property written on <html> restyles the whole document (4x-throttled phone fell to 22 fps),
    and pieces must move with translate/rotate, not by changing layout."""
    sm = (ROOT / "runtime" / "src" / "styles" / "stop-motion.ts").read_text(encoding="utf-8")
    pc = (ROOT / "runtime" / "src" / "styles" / "paper-cut-out.ts").read_text(encoding="utf-8")
    assert not re.search(r"documentElement\.style\.setProperty|html\.style\.setProperty", sm + pc)
    assert "83" in sm and "SHOT" in sm                                  # the 12-a-second cap
    css = (ROOT / "engine" / "styles" / "stop-motion" / "style.css").read_text(encoding="utf-8") + \
          (ROOT / "engine" / "styles" / "paper-cut-out" / "style.css").read_text(encoding="utf-8")
    assert "@media (prefers-reduced-motion: reduce)" in css


def test_style_yaml_is_valid():
    for style in ("stop-motion", "paper-cut-out"):
        d = yaml.safe_load((ROOT / "engine" / "styles" / style / "style.yaml").read_text(encoding="utf-8"))
        assert d["mode"] in ("light", "dark") and set(d["colors"]) >= {"bg", "ink", "accent"}
