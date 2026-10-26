"""`edit.region`: an image edit that may only change part of the picture.

The spec, the cache keys (a region joins them only when set), shaping and compositing (outside the mask the result is the
source, exactly), the crop the editor is shown, the whole `resolve_image` path with ComfyUI replaced by a fake editor
(caching, saved mask and outline, chains of region edits), and the storyboard's view (cards, edit workspace fields).
No ComfyUI, Blender or GPU is needed: the models' own outputs are replaced by synthetic masks and a fake edit."""
from __future__ import annotations

import hashlib
import json
import textwrap
from pathlib import Path

import numpy as np
import pytest
import yaml
from PIL import Image
from pydantic import ValidationError

from engine import region
from engine.inputs import edit_path, image_key, resolve_image
from engine.project import Project, file_key
from engine.spec import EditRegion, ImageEdit, ImageInput
from engine.storyboard.edit import shots
from engine.storyboard.edit.workspace import Workspace


# ---------------------------------------------------------------- the spec

def test_the_documented_example_validates():
    img = ImageInput.model_validate(yaml.safe_load(textwrap.dedent('''\
        edit:
          source: { beat_frame: { beat: walk, at: last } }
          instruction: "Redraw her shoes in rich detail"
          region: { prompt: "the girl's shoes", pick: largest, grow: 12, feather: 8 }
          seed: 3
        ''')))
    r = img.edit.region
    assert r.prompt == "the girl's shoes" and r.pick == "largest" and r.grow == 12 and r.feather == 8
    assert not r.invert and r.scope == "crop" and r.context == 0.6


def test_a_bare_string_is_a_prompt_and_a_region_needs_a_target():
    assert ImageEdit(source="a.png", instruction="x", region="the shoes").region.prompt == "the shoes"
    assert EditRegion(box=(0.1, 0.1, 0.4, 0.5)).prompt is None
    assert EditRegion(points=[(0.5, 0.5)], negative_points=[(0.1, 0.1)], pick=2).pick == 2
    with pytest.raises(ValidationError):
        EditRegion()
    with pytest.raises(ValidationError):
        EditRegion(prompt="x", pick="biggest")
    with pytest.raises(ValidationError):
        EditRegion(prompt="x", nonsense=1)
    assert ImageEdit(source="a.png", instruction="x").region is None


def test_invert_and_scope():
    r = EditRegion(prompt="the sky", invert=True, scope="image")
    assert r.invert and r.scope == "image"


# ---------------------------------------------------------------- cache keys

@pytest.fixture
def project(tmp_path):
    root = tmp_path / "p"
    (root / "inputs").mkdir(parents=True)
    rng = np.random.default_rng(1)
    Image.fromarray(rng.integers(0, 256, (180, 320, 3), dtype=np.uint8)).save(root / "inputs" / "src.png")
    return Project(root)


def test_no_region_no_change_to_existing_keys(project):
    src = project.root / "inputs" / "src.png"
    e = ImageInput(edit={"source": "inputs/src.png", "instruction": "x", "seed": 3, "steps": 30})
    old = hashlib.sha1(json.dumps([[file_key(src)], "x", 3, 30, 2]).encode()).hexdigest()[:12]
    assert edit_path(project, e, [src]).name == f"edit_{old}.png"
    assert "region" not in json.dumps(image_key(e))          # the section / storyboard keys never saw the field
    assert "region" not in json.dumps(image_key(ImageInput(edit={"source": e, "instruction": "y"})))


def test_a_region_is_part_of_the_key_and_every_field_of_it_counts(project):
    src = project.root / "inputs" / "src.png"

    def name(**kw):
        e = ImageInput(edit={"source": "inputs/src.png", "instruction": "x", "seed": 3, "region": {"prompt": "the shoes", **kw}})
        return edit_path(project, e, [src]).name

    plain = edit_path(project, ImageInput(edit={"source": "inputs/src.png", "instruction": "x", "seed": 3}), [src]).name
    names = {plain, name(), name(grow=4), name(feather=2), name(pick="left"), name(invert=True), name(scope="image"),
             name(context=1.0), name(box=(0, 0, 1, 1)), name(points=[(0.5, 0.5)])}
    assert len(names) == 10
    assert name() == name()                                     # and stable
    # the image key (sections, storyboard) tells two regions apart too
    a = ImageInput(edit={"source": "a.png", "instruction": "x", "region": "the shoes"})
    b = ImageInput(edit={"source": "a.png", "instruction": "x", "region": "the hands"})
    assert image_key(a) != image_key(b)


# ---------------------------------------------------------------- shaping and compositing

def disc(h=180, w=320, cx=160, cy=90, r=30) -> np.ndarray:
    yy, xx = np.mgrid[:h, :w]
    return (((xx - cx) ** 2 + (yy - cy) ** 2) <= r * r).astype(np.uint8) * 255


def test_shape_grows_feathers_and_inverts():
    raw = disc()
    plain = region.shape(raw, 0, 0)
    assert set(np.unique(plain)) <= {0, 255} and plain.sum() == raw.sum()
    grown = region.shape(raw, 10, 0)
    shrunk = region.shape(raw, -10, 0)
    assert (grown > 0).sum() > (plain > 0).sum() > (shrunk > 0).sum() > 0
    soft = region.shape(raw, 0, 12)
    assert 0 < soft[90, 160 + 30 + 2] < 255 and soft[90, 160] == 255 and soft[0, 0] == 0
    inv = region.shape(raw, 0, 12, invert=True)
    assert np.array_equal(inv, 255 - soft)


def test_specks_far_from_the_region_are_dropped_but_a_second_part_stays(monkeypatch):
    monkeypatch.setattr(region, "MIN_CROP", 16)
    raw = disc(cx=80, r=25) | disc(cx=240, r=25)                 # two shoes
    raw[5, 5] = raw[6, 5] = raw[5, 6] = 255                       # and a stray dot
    m = region.shape(raw, 0, 0)
    assert m[90, 80] == 255 and m[90, 240] == 255 and m[5, 5] == 0
    x0, y0, x1, y1 = region.crop_box(m, 0.0)
    assert y0 > 30                                                # the dot does not stretch the crop


def test_composite_is_exact_outside_the_mask_and_the_edit_inside():
    rng = np.random.default_rng(5)
    src = rng.integers(0, 256, (180, 320, 3), dtype=np.uint8)
    edit = rng.integers(0, 256, (180, 320, 3), dtype=np.uint8)
    mask = region.shape(disc(), 6, 14)
    out = region.composite(src, edit, mask)
    assert out.dtype == np.uint8 and out.shape == src.shape
    assert np.array_equal(out[mask == 0], src[mask == 0])
    assert np.array_equal(out[mask == 255], edit[mask == 255])
    mid = (mask > 0) & (mask < 255)
    assert mid.any()
    lo, hi = np.minimum(src, edit)[mid].astype(int), np.maximum(src, edit)[mid].astype(int)
    assert (out[mid] >= lo - 1).all() and (out[mid] <= hi + 1).all()      # a blend of the two, to within rounding
    # four channels: the alpha channel stays the source's
    a4 = np.concatenate([src, np.full((180, 320, 1), 200, np.uint8)], axis=2)
    e4 = np.concatenate([edit, np.full((180, 320, 1), 255, np.uint8)], axis=2)
    o4 = region.composite(a4, np.where(np.arange(4) == 3, a4, e4), mask)
    assert (o4[..., 3] == 200).all()


def test_crop_box_holds_the_mask_with_context_inside_the_picture():
    mask = region.shape(disc(cx=40, cy=30, r=12), 0, 4)          # a small thing near a corner
    x0, y0, x1, y1 = region.crop_box(mask, 0.6)
    ys, xs = np.nonzero(mask)
    assert x0 <= xs.min() and x1 > xs.max() and y0 <= ys.min() and y1 > ys.max()
    assert 0 <= x0 < x1 <= 320 and 0 <= y0 < y1 <= 180
    assert x1 - x0 == 320 or x1 - x0 >= min(region.MIN_CROP, 320)    # never a sliver: the editor needs surroundings
    big = region.shape(np.ones((180, 320), np.uint8) * 255, 0, 0)
    assert region.crop_box(big, 0.6) == (0, 0, 320, 180)
    tall = np.zeros((1000, 1000), np.uint8)
    tall[100:900, 480:500] = 255                                  # a thin pole: the crop is squarer than the pole
    a, b, c, d = region.crop_box(tall, 0.2)
    assert (d - b) / (c - a) <= region.MAX_CROP_ASPECT + 0.05


def test_outline_is_transparent_away_from_the_edge():
    mask = region.shape(disc(), 0, 6)
    ov = np.asarray(region.outline(mask))
    assert ov.shape == (180, 320, 4) and ov[0, 0, 3] == 0
    assert ov[90, 160 + 30, 3] > 200 and 0 < ov[90, 160, 3] < 80      # the line on the edge, a faint tint inside


# ---------------------------------------------------------------- the whole path, with a fake editor

class FakeComfy:
    """Stands in for ComfyUI: uploads are paths, `run` returns the graph's first input, `fetch` writes a recoloured,
    upscaled copy of it (what Qwen-Image-Edit would hand back: another size, other pixels everywhere)."""
    def __init__(self):
        self.edits, self.sizes, self.graphs = 0, [], []

    def install(self, monkeypatch):
        from engine.backends import comfy
        monkeypatch.setattr(comfy, "alive", lambda: True)
        monkeypatch.setattr(comfy, "free", lambda: None)
        monkeypatch.setattr(comfy, "upload", lambda p: str(p))
        monkeypatch.setattr(comfy, "run", self.run)
        monkeypatch.setattr(comfy, "fetch", self.fetch)

    def run(self, graph, poll=2):
        self.graphs.append(graph)
        return graph["img0"]["inputs"]["image"]

    def fetch(self, images, out_dir):
        self.edits += 1
        im = Image.open(images).convert("RGB")
        self.sizes.append(im.size)
        a = np.asarray(im).astype(np.int16)
        a = np.clip(a * 0.5 + np.array([120, 40, 0]), 0, 255).astype(np.uint8)       # everything shifts, as a real edit does
        big = Image.fromarray(a).resize((im.width * 2 + 16, im.height * 2 + 16), Image.BILINEAR)
        d = Path(out_dir)
        d.mkdir(parents=True, exist_ok=True)
        big.save(d / "0001.png")
        return str(d)


@pytest.fixture
def fake(monkeypatch):
    f = FakeComfy()
    f.install(monkeypatch)

    def find(project, src, rg, log=print):
        """A synthetic mask where SAM would cut one out: an ellipse in the spec's box (or the picture's middle)."""
        im = Image.open(src)
        W, H = im.size
        x0, y0, x1, y1 = rg.box or (0.4, 0.4, 0.6, 0.6)
        yy, xx = np.mgrid[:H, :W]
        cx, cy, rx, ry = (x0 + x1) / 2 * W, (y0 + y1) / 2 * H, (x1 - x0) / 2 * W, (y1 - y0) / 2 * H
        m = ((((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2) <= 1).astype(np.uint8) * 255
        out = project.build / "_generated" / f"region_{hashlib.sha1(str((file_key(src), rg.box)).encode()).hexdigest()[:10]}.png"
        out.parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(m, "L").save(out)
        return out
    monkeypatch.setattr(region, "find", find)
    return f


def px(path) -> np.ndarray:
    return np.asarray(Image.open(path).convert("RGB"))


def test_edit_inside_the_region_is_the_source_everywhere_else(project, fake):
    ref = ImageInput(edit={"source": "inputs/src.png", "instruction": "redraw it", "seed": 3,
                           "region": {"box": [0.3, 0.3, 0.5, 0.7], "grow": 4, "feather": 6}})
    out = resolve_image(project, ref, log=lambda m: None)
    src, res = px(project.inputs / "src.png"), px(out)
    mask = np.asarray(Image.open(region.sidecars(out)[0]))
    assert res.shape == src.shape and mask.shape == src.shape[:2]
    assert mask.any() and (mask == 0).mean() > 0.8
    assert np.array_equal(res[mask == 0], src[mask == 0])                 # byte-identical outside the region
    assert (res[mask == 255] != src[mask == 255]).any(axis=1).mean() > 0.9 # and changed inside it
    # the saved mask is the compositing weight: the image can be rebuilt from source, mask and the editor's output
    assert Image.open(region.sidecars(out)[1]).mode == "RGBA"
    assert out.parent == project.build / "_generated" and out.name.startswith("edit_")
    assert region.outline_of(out) is not None


def test_the_editor_sees_a_padded_crop_of_a_small_region(project, fake, monkeypatch):
    monkeypatch.setattr(region, "MIN_CROP", 64)
    ref = ImageInput(edit={"source": "inputs/src.png", "instruction": "x", "region": {"box": [0.45, 0.45, 0.55, 0.55]}})
    resolve_image(project, ref, log=lambda m: None)
    w, h = fake.sizes[0]
    assert (w, h) != (320, 180) and w < 320 and h <= 180               # a crop of the picture, not the picture
    whole = ImageInput(edit={"source": "inputs/src.png", "instruction": "x",
                             "region": {"box": [0.45, 0.45, 0.55, 0.55], "scope": "image"}})
    resolve_image(project, whole, log=lambda m: None)
    assert fake.sizes[1] == (320, 180)


def test_cached_by_the_region_and_nothing_renders_twice(project, fake):
    ref = ImageInput(edit={"source": "inputs/src.png", "instruction": "x", "region": {"box": [0.2, 0.2, 0.4, 0.4]}})
    a = resolve_image(project, ref, log=lambda m: None)
    assert fake.edits == 1
    assert resolve_image(project, ref, log=lambda m: None) == a and fake.edits == 1
    b = resolve_image(project, ImageInput(edit={"source": "inputs/src.png", "instruction": "x",
                                                "region": {"box": [0.2, 0.2, 0.4, 0.4], "feather": 20}}), log=lambda m: None)
    assert b != a and fake.edits == 2
    no = resolve_image(project, ImageInput(edit={"source": "inputs/src.png", "instruction": "x"}), log=lambda m: None)
    assert no not in (a, b) and fake.edits == 3
    assert not region.sidecars(no)[0].exists()                           # a plain edit has no region files


def test_invert_edits_everything_but_the_region(project, fake):
    ref = ImageInput(edit={"source": "inputs/src.png", "instruction": "x",
                           "region": {"box": [0.4, 0.3, 0.6, 0.7], "invert": True, "feather": 0}})
    out = resolve_image(project, ref, log=lambda m: None)
    src, res = px(project.inputs / "src.png"), px(out)
    mask = np.asarray(Image.open(region.sidecars(out)[0]))
    inside = region.shape(np.asarray(Image.open(sorted((project.build / "_generated").glob("region_*.png"))[0])), 0, 0)
    assert np.array_equal(mask, 255 - inside)
    assert np.array_equal(res[inside == 255], src[inside == 255])         # the region itself is untouched
    assert fake.sizes[0] == (320, 180)                                    # the editor saw the whole picture


def test_chained_region_edits_keep_everything_outside_each_region(project, fake):
    """shoes, then hands on the shoes' result, then the whole girl: each step leaves the rest of ITS source alone."""
    boxes = [[0.10, 0.60, 0.25, 0.90], [0.60, 0.30, 0.75, 0.50], [0.05, 0.05, 0.45, 0.95]]
    ref = "inputs/src.png"
    prev = project.inputs / "src.png"
    results = []
    for i, box in enumerate(boxes):
        ref = ImageInput(edit={"source": ref, "instruction": f"step {i}", "seed": 3, "region": {"box": box, "feather": 5}})
        out = resolve_image(project, ref, log=lambda m: None)
        src, res = px(prev), px(out)
        mask = np.asarray(Image.open(region.sidecars(out)[0]))
        assert mask.any() and np.array_equal(res[mask == 0], src[mask == 0]), f"step {i} touched pixels outside its region"
        assert (res != src).any()
        results.append(out)
        prev = out
    assert len({str(r) for r in results}) == 3 and fake.edits == 3
    # rebuilding the chain re-renders nothing
    again = ImageInput(edit={"source": ImageInput(edit={"source": ImageInput(edit={
        "source": "inputs/src.png", "instruction": "step 0", "seed": 3, "region": {"box": boxes[0], "feather": 5}}),
        "instruction": "step 1", "seed": 3, "region": {"box": boxes[1], "feather": 5}}),
        "instruction": "step 2", "seed": 3, "region": {"box": boxes[2], "feather": 5}})
    assert resolve_image(project, again, log=lambda m: None) == results[-1] and fake.edits == 3


def test_a_region_with_nothing_left_is_an_error(project, fake):
    ref = ImageInput(edit={"source": "inputs/src.png", "instruction": "x", "region": {"box": [0.4, 0.4, 0.6, 0.6], "grow": -80}})
    from engine.project import BuildError
    with pytest.raises(BuildError):
        resolve_image(project, ref, log=lambda m: None)


# ---------------------------------------------------------------- the storyboard

SPEC = textwrap.dedent('''\
    name: Test
    theme: { preset: night }
    sections:
      - id: story
        type: film
        beat_res: [1024, 576]
        beats:
          - id: shoes
            seconds: 4
            prompt: the walk
            motion: the camera drops to her shoes
            image:
              edit:
                instruction: Redraw her shoes in rich detail
                region: "the girl's shoes"
                source: { generate: "a drawn crowd", seed: 11, size: [1024, 576] }
          - id: hands
            seconds: 4
            prompt: the walk
            motion: the camera rises to her hands
            image:
              edit:
                instruction: Redraw her hands in rich detail
                region: { prompt: "her hands", pick: left, grow: 6, feather: 4 }
                source:
                  edit:
                    instruction: Redraw her shoes in rich detail
                    region: "the girl's shoes"
                    source: { generate: "a drawn crowd", seed: 11, size: [1024, 576] }
          - id: plain
            seconds: 4
            prompt: no region here
            motion: it moves
            image:
              edit:
                instruction: warmer light
                source: { generate: "a drawn crowd", seed: 11, size: [1024, 576] }
        steps:
          - { title: Hello, state: { beat: shoes } }
''')


@pytest.fixture
def board_project(tmp_path):
    root = tmp_path / "bp"
    root.mkdir()
    (root / "site.yaml").write_text(SPEC, encoding="utf-8")
    return Project(root)


def test_the_workspace_offers_the_region_fields(board_project):
    b = shots.build(board_project)
    shoes = b.shot("shoes").slots[0].nodes[0]
    assert shoes.kind == "edit" and "only inside" in shoes.summary
    names = [f.name for f in shoes.fields]
    assert names[-1].endswith(".region")                               # the bare-string form: one text field
    assert shoes.field(names[-1]).value == "the girl's shoes"
    hands = b.shot("hands").slots[0].nodes[0]
    assert [f.name.split(".")[-1] for f in hands.fields][-4:] == ["prompt", "pick", "grow", "feather"]
    assert hands.field("still.region.pick").value == "left" and "pick" in hands.recipe() and hands.recipe()["grow"] == 6
    assert shots.build(board_project).shot("plain").slots[0].nodes[0].field("still.region") is not None
    assert "only inside" not in b.shot("plain").slots[0].nodes[0].summary
    # the shoes edit is the same in the first two shots: shared, and edited in both places at once
    inner = b.shot("hands").slots[0].nodes[1]
    assert inner.kind == "edit" and inner.shared and inner.sig == shoes.sig


def test_region_fields_write_back_into_site_yaml(board_project):
    ws = Workspace(board_project)
    ws.set_fields("hands", {"still.region.grow": 20, "still.region.prompt": "her left hand"})
    d = yaml.safe_load(board_project.spec_path.read_text(encoding="utf-8"))
    reg = d["sections"][0]["beats"][1]["image"]["edit"]["region"]
    assert reg == {"prompt": "her left hand", "pick": "left", "grow": 20, "feather": 4}
    ws.set_fields("plain", {"still.region": "the lamp post"})            # adding a region to an edit that had none
    d = yaml.safe_load(board_project.spec_path.read_text(encoding="utf-8"))
    assert d["sections"][0]["beats"][2]["image"]["edit"]["region"] == "the lamp post"
    assert board_project.load().sections[0].beats[2].image.edit.region.prompt == "the lamp post"
    with pytest.raises(Exception):
        ws.set_fields("plain", {"still.region": ""})                      # a region needs a target


def test_cards_describe_the_region():
    from engine.storyboard.cards import describe
    d = describe(ImageInput(edit={"source": {"generate": "a crowd"}, "instruction": "more detail", "region": "the shoes"}))
    assert d.startswith("edit [only in: the shoes]: more detail")
    d = describe(ImageInput(edit={"source": {"generate": "a crowd"}, "instruction": "x", "region": {"prompt": "sky", "invert": True}}))
    assert "[outside: sky]" in d
    assert describe(ImageInput(edit={"source": {"generate": "a crowd"}, "instruction": "x"})).startswith("edit: x")


def test_the_sheet_draws_the_outline_and_the_workspace_serves_it(project, fake, tmp_path):
    from engine.storyboard.cards import Card, Frame
    from engine.storyboard.sheet import thumbs
    ref = ImageInput(edit={"source": "inputs/src.png", "instruction": "x", "region": {"box": [0.3, 0.3, 0.5, 0.7]}})
    out = resolve_image(project, ref, log=lambda m: None)
    plain = project.build / "_generated" / "plain.png"
    Image.open(out).save(plain)                                           # the same pixels, with no outline beside it
    cards = [Card("a", "s", "image", "a", frames=[Frame(out, "still", "final")]),
             Card("b", "s", "image", "b", frames=[Frame(plain, "still", "final")])]
    files = thumbs(cards, tmp_path / "sb")
    a = np.asarray(Image.open(tmp_path / "sb" / files["a"][0]).convert("RGB")).astype(int)
    b = np.asarray(Image.open(tmp_path / "sb" / files["b"][0]).convert("RGB")).astype(int)
    assert a.shape == b.shape and np.abs(a - b).sum() > 0                  # the outlined card differs from the plain one
