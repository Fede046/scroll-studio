"""Direction boards: the spec, the imagery treatment, the writer (deterministic, differs in kind, obeys constraints), the
vocabulary's own quality (contrast, loadable fonts, real styles), the board page, and picking (a minimal diff that never
touches copy, with a backup and an undo). No ComfyUI, GPU or network: stills are placeholder cards, fonts are not fetched."""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from engine import imagery
from engine.compile import themes
from engine.directions import measure, shots, typefaces, vocab, writer
from engine.directions import run as dr
from engine.directions.pick import ops_for
from engine.inputs import generated_path
from engine.project import Project
from engine.spec import Directions, ImageInput, Imagery, Site

SPEC = textwrap.dedent('''\
    # Casa Test: a cliff hotel
    name: Casa Test
    description: Twelve rooms on a cliff above the Atlantic.
    theme: { preset: dusk }   # warm dark
    nav:
      cta: { label: Reserve, href: "#reserve" }
    sections:
      - id: stay
        type: parallax
        layout: cards
        steps:
          - intro: true
            kicker: Casa Test
            title: Twelve rooms <em>above the Atlantic.</em>
            body: A whitewashed house on the cliffs of southern Portugal, with nothing between you and the sea.
            image:
              generate: Architectural photograph of a whitewashed hotel on a cliff above the Atlantic at golden hour, infinity pool, warm low sunlight, photorealistic, shot on a medium format camera, 35mm lens
              seed: 21
          - kicker: The terrace
            title: Breakfast <em>at the edge.</em>
            body: Coffee, figs and warm bread served on the terrace from eight.
      - type: intro
        id: house
        kicker: The house
        title: Small on purpose.
        body: Twelve rooms, one kitchen and a staff who learn your name by the second morning.
      - type: features
        items:
          - { tag: "Sea room", title: Ocean Rooms, body: "Window seat, stone bath, the sound of the sea all night." }
      - type: cta
        id: reserve
        title: Come for a week. <em>Stay for the light.</em>
        button: { label: Reserve, href: "#" }
    footer: { left: "© Casa Test" }
    ''')


@pytest.fixture
def project(tmp_path, monkeypatch):
    root = tmp_path / "casa-test"
    root.mkdir()
    (root / "site.yaml").write_text(SPEC, encoding="utf-8")
    from engine.directions import board
    monkeypatch.setattr(board, "vendor_fonts", lambda project, dirs, log: [])     # no network
    from engine.backends import comfy
    monkeypatch.setattr(comfy, "alive", lambda: False)                         # placeholder cards, never a real render
    monkeypatch.setattr(board, "screenshot", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no chrome in tests")))
    return Project(root)


def site_of(project):
    return project.load(), project.raw()


# ---------------------------------------------------------------- the spec

def test_spec_fields_and_defaults():
    d = Directions()
    assert d.count == 6 and d.seed == 1 and d.stills == 4 and d.keep == []
    assert Directions.model_validate({"brief": "calmer", "styles": {"avoid": ["ascii-art"]},
                                      "palettes": {"brand": ["#c2612a"]}}).palettes.brand == ["#c2612a"]
    with pytest.raises(ValidationError):
        Directions.model_validate({"count": 1})
    with pytest.raises(ValidationError):
        Directions.model_validate({"keep": ["copy"]})
    with pytest.raises(ValidationError):
        Imagery.model_validate({"light": "x"})                    # medium is required
    s = Site.model_validate({"name": "x", "sections": [], "imagery": {"medium": "35mm film"}, "directions": {"count": 4}})
    assert s.imagery.restyle is True and s.directions.count == 4


# ---------------------------------------------------------------- the imagery treatment

IM = Imagery(medium="35mm film photograph, Kodak Portra 400", light="low golden-hour sun", lens="35mm, eye level",
             mood="unhurried", palette="honey and sea blue")
PROMPT = ("Architectural photograph of a whitewashed hotel on a cliff above the Atlantic at golden hour, infinity pool, "
          "warm low sunlight, photorealistic, shot on a medium format camera, 35mm lens")


def test_restyle_drops_what_the_treatment_replaces():
    out = imagery.phrase(IM, PROMPT)
    assert out.startswith("35mm film photograph, Kodak Portra 400.")
    low = out.lower()
    for gone in ("photorealistic", "medium format", "architectural photograph", "at golden hour", "warm low sunlight"):
        assert gone not in low
    assert "whitewashed hotel on a cliff above the Atlantic" in out and "infinity pool" in out
    assert "low golden-hour sun" in out and "35mm, eye level" in out and out.endswith("honey and sea blue.") is False


def test_restyle_off_only_adds_and_treated_prompts_are_not_treated_twice():
    keep = IM.model_copy(update={"restyle": False})
    assert "photorealistic" in imagery.phrase(keep, PROMPT)
    once = imagery.phrase(IM, PROMPT)
    assert imagery.phrase(IM, once) == once


def test_video_prompts_have_no_lens():
    assert "eye level" not in imagery.phrase(IM, "a door opens", video=True)
    assert "eye level" in imagery.phrase(IM, "a door opens")


def test_nothing_changes_without_imagery_and_keys_move_when_it_is_set(project):
    ref = ImageInput(generate="a stone terrace, morning", seed=3)
    before = generated_path(project, ref)
    assert imagery.of(project) is None and imagery.treat(project, "x") == "x"
    raw = yaml.safe_load(SPEC)
    raw["imagery"] = {"medium": "gouache painting"}
    project.spec_path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    after = generated_path(project, ref)
    assert imagery.of(project).medium == "gouache painting"
    assert after != before and after.parent == before.parent


def test_take_and_shot_prompts_are_treated(project):
    raw = yaml.safe_load(SPEC)
    raw["imagery"] = {"medium": "gouache painting", "light": "soft window light"}
    project.spec_path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    shot = {"keyframes": {"frames": [{"name": "a", "t": 0, "prompt": "A road, photorealistic"}]},
            "ltx": {"segments": [{"id": "s", "range": [0, 4], "prompt": "the camera pushes along a road"}], "prompt": "a road"}}
    out = imagery.treat_shot(project, shot)
    assert out["keyframes"]["frames"][0]["prompt"].startswith("gouache painting.")
    assert "photorealistic" not in out["keyframes"]["frames"][0]["prompt"]
    assert out["ltx"]["segments"][0]["prompt"].startswith("gouache painting.") and out["ltx"]["prompt"].startswith("gouache")
    assert shot["ltx"]["prompt"] == "a road"                                  # the spec's own dicts are left alone


# ---------------------------------------------------------------- the vocabulary

def test_every_palette_reads_and_every_font_loads():
    for sc in vocab.SCHOOLS:
        assert sc.palettes and sc.pairings and sc.looks and sc.styles and len(sc.concepts) >= 2 and len(sc.motion) == 3
        for p in sc.palettes:
            d = writer.palette_dict(p)
            assert themes.contrast(themes._rgb(d["ink"]), themes._rgb(d["bg"])) >= 7, f"{sc.key}/{p.name}: ink on ground"
            assert themes.contrast(themes._rgb(d["ink"]), themes._rgb(d["bg2"])) >= 6, f"{sc.key}/{p.name}: ink on bands"
            assert themes.contrast(themes._rgb(d["accent"]), themes._rgb(d["accent_ink"])) >= 4.5, f"{sc.key}/{p.name}: button text"
            assert themes.contrast(themes._rgb(d["accent"]), themes._rgb(d["bg"])) >= 1.6, f"{sc.key}/{p.name}: accent on ground"
        for pr in sc.pairings:
            for fam in (pr.display, pr.body, pr.mono):
                assert fam in typefaces.CLASS and fam in themes.FONT_AXES, f"{fam} is not a known, loadable family"
            if pr.italic_em:
                assert pr.display in typefaces.ITALIC, f"{pr.display} has no italic"
        for st in sc.styles:
            assert st == "none" or st in themes.styles(), f"{sc.key}: unknown style {st}"
        for lk in sc.looks:
            for key in lk.lights:
                assert key in vocab.LIGHTS


def test_the_directions_fonts_are_in_the_engines_axis_table():
    assert themes.FONT_AXES["Anton"] == "" and themes.FONT_AXES["Playfair Display"].startswith("ital,wght")
    links = themes.font_links({"fonts": {"display": "Bebas Neue", "body": "Karla"}, "font_axes": {}})
    assert "family=Bebas+Neue&" in links[0] and "Karla:ital,wght@0,200..800" in links[1]


# ---------------------------------------------------------------- the writer

def test_deterministic_and_seeded(project):
    site, raw = site_of(project)
    a = writer.write(site, raw)
    b = writer.write(site, raw)
    assert [d.public() for d in a["directions"]] == [d.public() for d in b["directions"]]
    c = writer.write(site, raw, seed=5)
    assert [d.school + d.palette["name"] + str(d.style) for d in c["directions"]] != \
           [d.school + d.palette["name"] + str(d.style) for d in a["directions"]]


def test_directions_differ_in_kind_not_colour(project):
    site, raw = site_of(project)
    for seed in (1, 2, 3, 4):
        res = writer.write(site, raw, seed=seed)
        ds = res["directions"]
        assert len(ds) == 6 and [d.id for d in ds] == list("abcdef")
        assert res["diversity"]["min"] >= measure.MIN_DISTANCE, res["diversity"]
        assert len({d.school for d in ds}) == 6 and len({d.style or "none" for d in ds}) >= 5
        assert len({d.kind for d in ds}) >= 4
        assert len({d.fonts["display"] for d in ds}) >= 5
        for d in ds:
            assert d.concept.startswith("Casa Test") or "Casa Test" in d.concept
            assert d.imagery and d.imagery["medium"] and d.motion and d.palette["mode"] in ("light", "dark")
            assert d.stance in ("closest to today", "a step away", "a different site")


def test_a_set_of_colourways_is_rejected_and_repaired():
    a = writer.compose(vocab.SCHOOL["golden-hour"], _brief(), writer.Rules(_brief()), 1)
    b = writer.compose(vocab.SCHOOL["golden-hour"], _brief(), writer.Rules(_brief()), 1, salt="other")
    b.palette = dict(b.palette, name="Another", accent="#2f6f68")
    assert measure.distance(a, b) < measure.MIN_DISTANCE          # same school: one idea in two colourways
    far = writer.compose(vocab.SCHOOL["blueprint"], _brief(), writer.Rules(_brief()), 1)
    assert measure.distance(a, far) > 0.7


def _brief(**cfg):
    from engine.directions.brief import read
    raw = yaml.safe_load(SPEC)
    raw["directions"] = cfg or None
    if not cfg:
        raw.pop("directions")
    return read(Site.model_validate(raw), raw)


def _write(**cfg):
    raw = yaml.safe_load(SPEC)
    raw["directions"] = cfg
    return writer.write(Site.model_validate(raw), raw)


def test_the_brief_steers_the_directions():
    res = _write(brief="a loud, playful, nostalgic site for a game night", moods=["bold"], count=3)
    assert {"loud", "playful", "nostalgic", "bold"} <= set(res["brief"]["moods"])
    assert len(res["directions"]) == 3
    quiet = _write(brief="calm, quiet, minimal", count=3)
    assert {d.school for d in quiet["directions"]} & {"quiet-studio", "wabi-sabi", "golden-hour"}


def test_style_constraints():
    res = _write(styles={"only": ["none", "halftone", "blueprint", "sand"]}, count=4)
    assert {d.style or "none" for d in res["directions"]} <= {"none", "halftone", "blueprint", "sand"}
    res = _write(styles={"avoid": ["none", "gradient-mesh"]})
    assert all(d.style not in (None, "gradient-mesh") for d in res["directions"])
    with pytest.raises(ValueError, match="unknown style 'no-such-style'"):
        _write(styles={"only": ["no-such-style"]}, count=2)


def test_font_and_palette_constraints():
    res = _write(fonts={"avoid": ["Inter", "Inter Tight", "Space Grotesk"]})
    for d in res["directions"]:
        assert not ({d.fonts["display"], d.fonts["body"], d.fonts["mono"]} & {"Inter", "Inter Tight", "Space Grotesk"})
    res = _write(fonts={"only": ["Fraunces", "Figtree", "Cormorant Garamond", "Karla"]}, count=3)
    for d in res["directions"]:
        assert {d.fonts["display"], d.fonts["body"]} <= {"Fraunces", "Figtree", "Cormorant Garamond", "Karla"}
    res = _write(palettes={"avoid": ["pink", "magenta", "red"]})
    for d in res["directions"]:
        h, s, _ = measure.hsl(d.palette["accent"])
        assert s <= 0.25 or not (290 <= h < 345 or h >= 345 or h < 15), d.palette
    res = _write(palettes={"only": ["Portra", "Raw Linen", "Seamless"]}, count=3)
    assert {d.palette["name"] for d in res["directions"]} <= {"Portra", "Raw Linen", "Seamless"}


def test_brand_colours_become_the_accent_of_every_direction():
    res = _write(palettes={"brand": ["#c2612a", "#f0c9a0"]})
    for d in res["directions"]:
        assert d.palette["accent"] == "#c2612a" and d.palette["accent2"] == "#f0c9a0"
        assert themes.contrast(themes._rgb(d.palette["accent"]), themes._rgb(d.palette["accent_ink"])) >= 4.5


def test_keep_holds_part_of_the_current_look():
    res = _write(keep=["colors", "fonts"], count=4)
    cur = themes.resolve(Site.model_validate(yaml.safe_load(SPEC)).theme)
    for d in res["directions"]:
        assert d.palette["bg"] == cur["colors"]["bg"] and d.palette["accent"] == cur["colors"]["accent"]
        assert d.fonts["display"] == cur["fonts"]["display"]
    assert len({d.school for d in res["directions"]}) == 4 and res["diversity"]["min"] >= measure.MIN_DISTANCE
    res = _write(keep=["style"], count=3)
    assert {d.style for d in res["directions"]} == {None}


def test_impossible_constraints_are_reported():
    raw = yaml.safe_load(SPEC)
    raw["directions"] = {"styles": {"only": ["pixel-art"]}, "count": 5}
    res = writer.write(Site.model_validate(raw), raw)
    assert len(res["directions"]) < 5 and any("only" in w for w in res["warnings"])


def test_reroll_replaces_one_and_keeps_the_rest(project):
    site, raw = site_of(project)
    res = writer.write(site, raw)
    ds = res["directions"]
    new = writer.reroll(site, raw, ds, "c")
    assert new.id == "c" and new.school not in {d.school for d in ds}


# ---------------------------------------------------------------- what a board shows

def test_the_moments_are_the_hero_and_key_sections():
    raw = yaml.safe_load(SPEC)
    ms = shots.pick(raw, 4, 1)
    assert [m.role for m in ms][0] == "hero" and ms[0].index == 0 and ms[0].from_prompt
    assert "whitewashed hotel on a cliff" in ms[0].subject and "photorealistic" not in ms[0].subject
    assert ms[-1].index == len(raw["sections"]) - 1 and ms[-1].role == "closing"
    assert ms[0].title_html == "Twelve rooms <em>above the Atlantic.</em>"
    assert all(m.seed for m in ms) and len({m.seed for m in ms}) == len(ms)
    assert len(shots.pick(raw, 1, 1)) == 1
    p = shots.prompt_for(ms[0], {"medium": "gouache painting", "light": "soft light"})
    assert p.startswith("gouache painting.") and "no text" in p


def test_the_stills_are_the_same_subjects_in_every_direction(project):
    site, raw = site_of(project)
    st = dr.make(project, count=3, images=False, sheet=False, log=lambda m: None)
    subjects = [[s["seed"] for s in d["stills"]] for d in st["directions"]]
    assert subjects[0] == subjects[1] == subjects[2]
    prompts = [d["stills"][0]["prompt"] for d in st["directions"]]
    assert len(set(prompts)) == 3 and all("whitewashed hotel" in p for p in prompts)


def test_make_writes_the_page_the_state_and_marks_nothing_picked(project):
    st = dr.make(project, count=4, seed=2, images=False, sheet=False, log=lambda m: None)
    d = Path(st["files"]["html"]).parent
    page = (d / "board.html").read_text(encoding="utf-8")
    assert page.count('class="dir') == 4 and "studio directions casa-test --pick a" in page
    for x in st["directions"]:
        assert x["name"] in page and x["palette"]["accent"] in page and x["fonts"]["display"] in page
    assert dr.load(project)["seed"] == 2 and dr.load(project)["picked"] is None
    assert len(list((d / "stills").glob("*.jpg"))) == 16


# ---------------------------------------------------------------- picking

def copy_of(raw):
    r = {k: v for k, v in raw.items() if k not in ("theme", "imagery", "scroll", "directions")}
    return r


def test_pick_is_a_minimal_diff_that_never_touches_copy(project):
    before_text = project.spec_path.read_text(encoding="utf-8")
    before = yaml.safe_load(before_text)
    dr.make(project, count=4, images=False, sheet=False, log=lambda m: None)
    res = dr.pick(project, "b", lambda m: None)
    after_text = project.spec_path.read_text(encoding="utf-8")
    after = yaml.safe_load(after_text)
    assert copy_of(after) == copy_of(before), "a direction must not change the name, description, sections or footer"
    assert Site.model_validate(after)                                       # still a valid spec
    assert "imagery" in after and after["imagery"]["medium"]
    d = res["direction"]
    t = after["theme"]
    assert t.get("style") == d["style"] if d["style"] else "style" not in t
    assert themes.resolve(Site.model_validate(after).theme)["fonts"]["display"] == d["fonts"]["display"]
    assert themes.resolve(Site.model_validate(after).theme)["colors"]["accent"].lower() == d["palette"]["accent"].lower()
    assert after_text.startswith("# Casa Test: a cliff hotel") and "# warm dark" in after_text    # comments survive
    removed = [l for l in res["diff"].splitlines() if l.startswith("-") and not l.startswith("---")]
    assert len(removed) <= 3, res["diff"]                                    # only the theme line is rewritten
    assert Path(res["backup"]).read_text(encoding="utf-8") == before_text    # the backup is the old file, byte for byte
    assert dr.load(project)["picked"]["id"] == "b"
    assert "picked" in (Path(project.root) / "directions" / "board.html").read_text(encoding="utf-8")


def test_only_what_differs_from_the_base_is_written(project):
    site, raw = site_of(project)
    ds = writer.write(site, raw)["directions"]
    d = ds[0]
    d.palette = dict(d.palette, **{k: themes.resolve(site.theme)["colors"][k] for k in ("bg", "bg2", "ink", "accent", "accent2", "accent_ink")})
    d.style = None
    d.fonts = dict(d.fonts, display=themes.resolve(site.theme)["fonts"]["display"], body=themes.resolve(site.theme)["fonts"]["body"],
                   mono=themes.resolve(site.theme)["fonts"]["mono"], weight=themes.resolve(site.theme)["display_weight"],
                   em=themes.resolve(site.theme)["em"], italic_em=themes.resolve(site.theme)["em_italic"], labels=themes.resolve(site.theme)["labels"])
    d.radius = themes.resolve(site.theme)["radius"]
    d.pace = 1.0
    d.imagery = None
    assert ops_for(raw, d) == []


def test_pick_twice_replaces_and_undo_restores_the_file(project):
    original = project.spec_path.read_bytes()
    dr.make(project, count=4, images=False, sheet=False, log=lambda m: None)
    dr.pick(project, "a", lambda m: None)
    first = project.spec_path.read_text(encoding="utf-8")
    res = dr.pick(project, "c", lambda m: None)
    second = yaml.safe_load(project.spec_path.read_text(encoding="utf-8"))
    assert second["imagery"]["medium"] == res["direction"]["imagery"]["medium"]
    assert copy_of(second) == copy_of(yaml.safe_load(original.decode()))
    assert first != project.spec_path.read_text(encoding="utf-8")
    dr.undo(project, lambda m: None)
    assert project.spec_path.read_text(encoding="utf-8") == first
    assert len(list((project.root / "directions" / "backups").glob("site-*.yaml"))) == 2
    assert dr.pick(project, "c", lambda m: None)["changed"]               # and again
    assert dr.pick(project, "c", lambda m: None)["changed"] == []         # already there: nothing to write


def test_pick_without_a_theme_block_and_by_name(tmp_path, monkeypatch):
    from engine.directions import board
    monkeypatch.setattr(board, "vendor_fonts", lambda project, dirs, log: [])
    root = tmp_path / "bare"
    root.mkdir()
    (root / "site.yaml").write_text("name: Bare\ndescription: A bakery.\nsections:\n  - type: intro\n    title: Hello\n    body: Bread.\n",
                                    encoding="utf-8")
    p = Project(root)
    st = dr.make(p, count=3, images=False, sheet=False, log=lambda m: None)
    name = st["directions"][1]["name"]
    dr.pick(p, name.lower(), lambda m: None)
    after = yaml.safe_load((root / "site.yaml").read_text(encoding="utf-8"))
    assert after["sections"] == [{"type": "intro", "title": "Hello", "body": "Bread."}] and after["name"] == "Bare"
    assert "theme" in after or "imagery" in after
    with pytest.raises(Exception):
        dr.pick(p, "zzz", lambda m: None)


def test_a_picked_direction_builds_the_same_page_in_its_style(project):
    """The picked spec compiles: theme resolution (colours, fonts, style) and the font links all work."""
    dr.make(project, count=6, images=False, sheet=False, log=lambda m: None)
    for letter in "abcdef":
        dr.pick(project, letter, lambda m: None)
        site = project.load()
        t = themes.resolve(site.theme)
        assert t["colors"]["bg"].startswith("#") and themes.font_links(t)
        if site.theme.style:
            assert site.theme.style in themes.styles()
        themes.css_vars(t)


# ---------------------------------------------------------------- the served page

def test_the_api_picks_and_serves_the_board(project):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from engine.directions.api import make_router
    dr.make(project, count=3, images=False, sheet=False, log=lambda m: None)
    app = FastAPI()
    app.include_router(make_router(lambda name: project))
    c = TestClient(app)
    page = c.get("/dir/casa-test")
    assert page.status_code == 200 and '<base href="/dir/casa-test/files/">' in page.text
    assert c.get("/api/dir/casa-test/state").json()["seed"] == 1
    st = c.get("/api/dir/casa-test/state").json()
    assert c.get("/dir/casa-test/files/" + st["directions"][0]["stills"][0]["image"]).status_code == 200
    assert c.get("/dir/casa-test/files/../site.yaml").status_code in (403, 404)
    r = c.post("/api/dir/casa-test/pick", json={"id": "b"})
    assert r.status_code == 200 and r.json()["ok"] and r.json()["changed"]
    assert c.post("/api/dir/casa-test/pick", json={"id": "zz"}).status_code == 400
    assert c.post("/api/dir/casa-test/undo").status_code == 200
    r = c.post("/api/dir/casa-test/reroll", json={"id": "a"})
    assert r.status_code == 200 and r.json()["ok"]
