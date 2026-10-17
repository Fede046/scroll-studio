"""Deep zoom (`freeze.detail`): the tile plan, the agreement maths, the pyramid render, the pyramid's cache, and the spec.
No ComfyUI and no GPU: the enlarge step falls back to Lanczos, the redraw is off or stubbed, the render runs on torch's CPU."""
from __future__ import annotations

import numpy as np
import pytest
from pydantic import ValidationError

from engine import freeze as fz
from engine import zoom
from engine.spec import Freeze, FreezeDetail, FreezeLayers

CAMERA = [{"t": 0.0, "box": [0, 0, 1, 1]},
          {"t": 0.3, "box": [0.40, 0.38, 0.62, 0.97]},
          {"t": 0.55, "box": [0.455, 0.80, 0.555, 0.96], "hold": 0.1},
          {"t": 0.75, "box": [0.485, 0.845, 0.53, 0.89]},
          {"t": 1.0, "box": [0, 0, 1, 1]}]


def views(cam=CAMERA, n=240):
    return zoom.views_of(fz.CameraPath(cam, "inOutSine"), n)


# ---------------------------------------------------------------- the plan

def test_a_camera_that_stays_wide_needs_no_tiles():
    tiles, sizes, _ = zoom.plan_tiles(views([{"t": 0, "box": [0.2, 0.2, 0.9, 0.9]}]), base_px=3840, out_px=1920, tile_px=2400)
    assert tiles == [] and sizes == []


def test_levels_auto_stop_when_the_tightest_box_is_native():
    n, ratio = zoom.auto_levels(0.045, base_px=3840, out_px=1920, ratio=2.0)
    assert n == 4 or n == 3
    assert ratio ** n * 3840 * 0.045 >= 1920 * 0.999          # the last level has a tile pixel per output pixel at the tightest box
    assert ratio <= 2.0 + 1e-9
    assert zoom.auto_levels(0.6, 3840, 1920, 2.0)[0] == 0      # the base is native down to half the frame
    assert zoom.auto_levels(0.1, 1920, 1920, 2.0)[0] >= 3


def test_every_view_has_a_tile_of_its_level_and_every_tile_sits_inside_its_parent():
    vs = views()
    tiles, sizes, ratio = zoom.plan_tiles(vs, base_px=3840, out_px=1920, tile_px=2400)
    assert tiles and len(sizes) >= 3
    for i, t in enumerate(tiles):
        x0, y0, x1, y1 = t.box
        assert 0 <= x0 < x1 <= 1 + 1e-9 and 0 <= y0 < y1 <= 1 + 1e-9
        assert (x1 - x0) == pytest.approx((y1 - y0))                       # the frame's aspect, in view units
        assert (x1 - x0) == pytest.approx(sizes[t.level - 1], abs=1e-5)
        if t.parent >= 0:
            assert t.parent < i                                            # parents are built first
            p = tiles[t.parent]
            assert p.level == t.level - 1
            assert p.box[0] - 1e-9 <= x0 and p.box[1] - 1e-9 <= y0 and x1 <= p.box[2] + 1e-9 and y1 <= p.box[3] + 1e-9
        else:
            assert t.level == 1
    # the tightest view is held by a finest-level tile
    tight = min(vs, key=lambda v: v.w)
    last = [t for t in tiles if t.level == len(sizes)]
    assert last and any(zoom._covered(t.box, tight, zoom.VIEW_PAD) > 0.95 for t in last)


def test_the_plan_is_stable_when_the_camera_moves_a_little():
    a, _, _ = zoom.plan_tiles(views(), base_px=3840, out_px=1920, tile_px=2400)
    cam = [dict(k) for k in CAMERA]
    cam[3] = {"t": 0.75, "box": [0.4855, 0.8455, 0.5305, 0.8905]}          # the laces box moved by a twentieth of a percent
    b, _, _ = zoom.plan_tiles(views(cam), base_px=3840, out_px=1920, tile_px=2400)
    assert [t.box for t in a] == [t.box for t in b]


def test_lod_alpha_is_one_when_the_view_fits_and_zero_when_it_is_wide():
    assert zoom.lod_alpha(0.1, 0.2) == 1.0
    assert zoom.lod_alpha(0.2 * zoom.FULL, 0.2) == 1.0
    assert zoom.lod_alpha(0.2 * zoom.GONE, 0.2) == 0.0 and zoom.lod_alpha(0.5, 0.2) == 0.0
    xs = [zoom.lod_alpha(w, 0.2) for w in np.linspace(0.05, 0.4, 60)]
    assert all(a >= b - 1e-9 for a, b in zip(xs, xs[1:]))                  # fades monotonically as the view widens


# ---------------------------------------------------------------- agreeing with the parent

def test_resample_box_is_exact_geometry():
    rng = np.random.default_rng(1)
    img = (rng.random((64, 96, 3)) * 255).astype(np.uint8)
    same = zoom.resample_box(img, (0, 0, 1, 1), (0, 0, 1, 1), (96, 64), "cubic")
    assert np.abs(same.astype(int) - img.astype(int)).max() <= 1
    half = zoom.resample_box(img, (0, 0, 1, 1), (0.5, 0.0, 1.0, 0.5), (48, 32), "linear")       # the top-right quarter, at 1:1
    assert np.abs(half.astype(int) - img[:32, 48:].astype(int)).max() <= 1
    inner = zoom.resample_box(img, (0.5, 0.0, 1.0, 0.5), (0.5, 0.0, 1.0, 0.5), (48, 32), "cubic")    # a box over its own picture
    assert inner.shape == (32, 48, 3)


def test_lock_keeps_the_parents_low_frequencies_and_the_childs_detail():
    import cv2
    rng = np.random.default_rng(2)
    parent = cv2.GaussianBlur((rng.random((96, 128, 3)) * 255).astype(np.float32), (0, 0), 6)
    child = 255 - parent * 0.6 + (rng.random((96, 128, 3)) - 0.5) * 60                         # inverted, with its own noise
    out = zoom.lock_low_frequencies(child, parent, 4.0)
    lp = lambda a: cv2.GaussianBlur(a.astype(np.float32), (0, 0), 4.0)
    assert np.abs(lp(out) - lp(parent)).mean() < 1.5                                           # coarse structure: the parent's
    hp = lambda a: a - lp(a)
    assert np.abs(hp(out) - hp(child)).mean() < 1.0                                            # fine structure: the child's
    assert np.abs(lp(out) - lp(child)).mean() > 5                                              # (the child was really different)


@pytest.mark.parametrize("dx, dy", [(3.0, -2.0), (-1.5, 1.0)])
def test_align_finds_the_shift_of_a_redrawn_tile(dx, dy):
    import cv2
    rng = np.random.default_rng(3)
    base = cv2.GaussianBlur((rng.random((272, 480)) * 255).astype(np.float32), (0, 0), 5)
    ref = np.dstack([base] * 3).clip(0, 255).astype(np.uint8)
    M = np.float32([[1, 0, dx], [0, 1, dy]])
    moved = cv2.warpAffine(ref, M, (480, 272), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
    fixed, info = zoom.align(moved, ref)
    assert info["applied"]
    inner = (slice(20, -20), slice(20, -20))
    assert np.abs(fixed[inner].astype(int) - ref[inner].astype(int)).mean() < np.abs(moved[inner].astype(int) - ref[inner].astype(int)).mean() / 2.5
    assert abs(abs(info["dx"]) - abs(dx)) < 0.6


def test_align_leaves_an_implausible_fit_alone():
    rng = np.random.default_rng(4)
    a = (rng.random((100, 160, 3)) * 255).astype(np.uint8)
    b = (rng.random((100, 160, 3)) * 255).astype(np.uint8)                 # nothing in common
    out, info = zoom.align(b, a)
    assert (not info["applied"]) or max(abs(info["dx"]), abs(info["dy"])) <= 0.04 * 160


def test_tile_depth_snaps_to_the_tiles_own_edges():
    rgb = np.zeros((96, 160, 3), np.uint8)
    rgb[:, 80:] = 255                                                       # an edge at x = 80
    parent = np.zeros((96, 160), np.float32)
    parent[:, 77:] = 1.0                                                    # the enlarged parent's depth edge is 3 px off
    raw, grown = zoom.refine_depth(parent, rgb, grow=2)
    row = raw[48]
    assert row[60] < 0.2 and row[100] > 0.8
    # the depth edge moved to the picture's edge (it sat at 77 before)
    assert row[77:80].mean() < 0.8                                          # was 1.0 there: pulled back to the picture's edge
    assert (grown >= raw - 0.15).all()                                      # growing only adds near pixels


# ---------------------------------------------------------------- the render

def _pyramid_scene():
    """A base with a soft pattern and one tile (the middle) that holds the same pattern plus fine detail."""
    import cv2
    rng = np.random.default_rng(5)
    H, W = 128, 224
    soft = cv2.GaussianBlur((rng.random((H, W, 3)) * 255).astype(np.float32), (0, 0), 4)
    base = soft.clip(0, 255).astype(np.uint8)
    depth = np.tile(np.linspace(0.2, 0.8, W, dtype=np.float32), (H, 1))
    box = (0.25, 0.25, 0.75, 0.75)
    up = zoom.resample_box(base, (0, 0, 1, 1), box, (W, H), "cubic").astype(np.float32)
    detail = cv2.GaussianBlur((rng.random((H, W, 3)) - 0.5).astype(np.float32) * 120, (0, 0), 0.8)
    tile = zoom.lock_low_frequencies(up + detail, up, 3.0)
    d = zoom.resample_box(depth, (0, 0, 1, 1), box, (W, H), "linear")
    return base, depth, [zoom.TileImage(1, box, np.clip(tile, 0, 255).astype(np.uint8), d)]


def spike_ratio(d: np.ndarray, k: int = 3) -> float:
    """How far the worst frame-to-frame difference stands above the median of its neighbours (1 = it does not)."""
    worst = 1.0
    for i in range(len(d)):
        nb = np.concatenate([d[max(0, i - k):i], d[i + 1:i + 1 + k]])
        if len(nb) and np.median(nb) > 0.5:
            worst = max(worst, d[i] / np.median(nb))
    return float(worst)


def test_pyramid_render_adds_detail_when_the_camera_arrives_and_never_jumps():
    from engine import zoom_render
    base, depth, tiles = _pyramid_scene()
    cam = [{"t": 0, "box": [0, 0, 1, 1]}, {"t": 0.35, "box": [0.4, 0.4, 0.6, 0.6], "hold": 0.3}, {"t": 1, "box": [0, 0, 1, 1]}]
    kw = dict(size=(224, 128), seconds=2.0, parallax=0.5, device="cpu")
    with_tiles = list(zoom_render.render_frames(base, depth, tiles, cam, **kw))
    without = list(zoom_render.render_frames(base, depth, [], cam, **kw))
    assert len(with_tiles) == len(without) == 48

    def hf(a):
        import cv2
        g = cv2.cvtColor(a, cv2.COLOR_RGB2GRAY).astype(np.float32)
        return float(np.abs(g - cv2.GaussianBlur(g, (0, 0), 1.5)).mean())
    mid = 24                                                               # on the hold: the tile is fully on
    assert hf(with_tiles[mid]) > hf(without[mid]) * 1.5                    # the close-up has detail the plain render lacks
    assert hf(with_tiles[0]) == pytest.approx(hf(without[0]), rel=0.02)    # the wide shot is the base
    # no pops: the frame-to-frame change is a smooth curve (no frame stands out against its neighbours)
    d1 = np.array([np.abs(a.astype(int) - b.astype(int)).mean() for a, b in zip(with_tiles, with_tiles[1:])])
    assert spike_ratio(d1) < 1.5, spike_ratio(d1)


def test_the_low_frequencies_do_not_change_when_a_level_fades_in():
    """Colour and shape at the tile are the base's: the blurred frame with and without the tile agree."""
    import cv2
    from engine import zoom_render
    base, depth, tiles = _pyramid_scene()
    cam = [{"t": 0, "box": [0.3, 0.3, 0.7, 0.7]}]
    kw = dict(size=(224, 128), seconds=1.0, parallax=0.0, device="cpu")
    a = list(zoom_render.render_frames(base, depth, tiles, cam, **kw))[0].astype(np.float32)
    b = list(zoom_render.render_frames(base, depth, [], cam, **kw))[0].astype(np.float32)
    la, lb = cv2.GaussianBlur(a, (0, 0), 3.0), cv2.GaussianBlur(b, (0, 0), 3.0)
    assert np.abs(la - lb)[12:-12, 12:-12].mean() < 2.5


# ---------------------------------------------------------------- the spec

def test_detail_and_layers_in_the_spec():
    f = Freeze.model_validate({"image": "a.png", "detail": {}, "layers": "auto"})
    assert isinstance(f.detail, FreezeDetail) and f.detail.levels == "auto" and f.detail.strength == 0.35
    assert isinstance(f.layers, FreezeLayers) and f.layers.subjects == "auto"
    assert Freeze.model_validate({"image": "a.png", "detail": True}).detail.ratio == 2.0
    g = Freeze.model_validate({"image": "a.png", "layers": [{"prompt": "the girl"}, {"box": [0.1, 0.1, 0.2, 0.5]}]})
    assert [s.prompt for s in g.layers.subjects] == ["the girl", None]
    assert Freeze.model_validate({"image": "a.png"}).detail is None
    with pytest.raises(ValidationError):
        Freeze.model_validate({"image": "a.png", "detail": {"strength": 3}})
    with pytest.raises(ValidationError, match="prompt, a box or points"):
        Freeze.model_validate({"image": "a.png", "layers": [{}]})


def test_unset_detail_and_layers_do_not_change_old_stage_keys():
    """A frozen beat made before these fields existed keeps its key (nothing is re-rendered by updating)."""
    import textwrap
    from engine import freeze_beats as fb
    from engine.project import Project
    import tempfile, pathlib
    with tempfile.TemporaryDirectory() as d:
        root = pathlib.Path(d)
        (root / "inputs").mkdir()
        (root / "inputs" / "a.png").write_bytes(b"x")
        (root / "site.yaml").write_text(textwrap.dedent("""\
            name: T
            theme: { preset: night }
            sections:
              - id: s
                type: film
                beat_res: [128, 96]
                beats:
                  - { id: f, seconds: 2, freeze: { image: inputs/a.png } }
                  - { id: g, seconds: 2, freeze: { image: inputs/a.png, detail: {} } }
            """), encoding="utf-8")
        p = Project(root)
        sec = p.load().sections[0]
        k0, k1 = fb.beat_key(p, sec, sec.beats[0]), fb.beat_key(p, sec, sec.beats[1])
        assert "detail" not in k0["freeze"] and "layers" not in k0["freeze"]
        assert k1["freeze"]["detail"]["strength"] == 0.35 and k0 != k1


# ---------------------------------------------------------------- the stage: tiles are cached one by one

SPEC = '''name: T
theme: { preset: night }
sections:
  - id: s
    type: film
    beat_res: [192, 96]
    beats:
      - id: z
        seconds: 2
        freeze:
          image: inputs/still.png
          upscale_method: lanczos
          detail: { strength: 0, tile: 1.25 }
          camera:
            - { t: 0, box: [0, 0, 1, 1] }
            - { t: 0.5, box: [0.40, 0.40, 0.46, 0.46], hold: 0.2 }
            - { t: 1, box: [0, 0, 1, 1] }
'''


@pytest.fixture
def zproject(tmp_path, monkeypatch):
    import shutil
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg is not installed")
    from PIL import Image
    from engine.project import Project
    from engine.backends import depth as depthmod
    root = tmp_path / "p"
    (root / "inputs").mkdir(parents=True)
    (root / "site.yaml").write_text(SPEC, encoding="utf-8")
    rng = np.random.default_rng(9)
    import cv2
    img = cv2.GaussianBlur((rng.random((96, 192, 3)) * 255).astype(np.float32), (0, 0), 2).astype(np.uint8)
    Image.fromarray(img).save(root / "inputs" / "still.png")
    monkeypatch.setattr(depthmod, "estimate", lambda im, size="small": np.tile(np.linspace(0, 1, im.width, dtype=np.float32), (im.height, 1)))
    return Project(root)


def test_deep_zoom_beat_renders_and_caches_tile_by_tile(zproject):
    import yaml
    from engine import freeze_beats as fb
    sec = zproject.load().sections[0]
    b = sec.beats[0]
    logs = []
    clip = fb.render_beat(zproject, sec, b, logs.append)
    bdir = fb.beat_dir(zproject, sec, b)
    tiles = sorted((bdir / "zoom").glob("L*.png"))
    assert clip.exists() and len(tiles) >= 3 and (bdir / "depth_raw.npy").exists()
    assert any("deep zoom:" in m for m in logs)
    stamp = clip.stat().st_mtime_ns
    logs.clear()
    fb.render_beat(zproject, sec, b, logs.append)
    assert clip.stat().st_mtime_ns == stamp and any("up to date" in m for m in logs)
    # moving only the deepest box a little: the tiles it did not touch are kept, the clip is re-rendered
    before = {p.name: p.stat().st_mtime_ns for p in tiles}
    spec = yaml.safe_load((zproject.root / "site.yaml").read_text())
    spec["sections"][0]["beats"][0]["freeze"]["camera"][1]["box"] = [0.55, 0.40, 0.61, 0.46]
    zproject.save(spec)
    sec2 = zproject.load().sections[0]
    fb.render_beat(zproject, sec2, sec2.beats[0], logs.append)
    after = {p.name: p.stat().st_mtime_ns for p in (bdir / "zoom").glob("L*.png")}
    kept = [n for n in before if n in after and after[n] == before[n]]
    assert kept, "no tile was kept"
    assert set(after) - set(before), "the new box has its own tiles"
    assert clip.stat().st_mtime_ns != stamp


def test_deep_zoom_tiles_agree_with_their_parent(zproject):
    """Every tile's low frequencies are its parent's: the enlarged parent and the tile differ only in fine detail."""
    import cv2
    from engine import freeze_beats as fb, zoom_build
    from PIL import Image
    sec = zproject.load().sections[0]
    b = sec.beats[0]
    fb.render_beat(zproject, sec, b, lambda m: None)
    bdir = fb.beat_dir(zproject, sec, b)
    up = np.asarray(Image.open(bdir / "up.png").convert("RGB"))
    f = b.freeze
    tiles, sizes, ratio, tsize = zoom_build.make_plan(f, b.seconds, up.shape[1], fb.beat_size(sec))
    first = next(t for t in tiles if t.level == 1)
    got = sorted((bdir / "zoom").glob("L1_*.png"))
    tile_img = [np.asarray(Image.open(p).convert("RGB")) for p in got if not p.name.endswith(".bg.png")]
    assert tile_img
    ref = zoom.resample_box(up, (0, 0, 1, 1), first.box, tsize, "cubic").astype(np.float32)
    d = None
    for t in tile_img:
        lp = lambda a: cv2.GaussianBlur(a.astype(np.float32), (0, 0), 6.0)
        e = np.abs(lp(t) - lp(ref)).mean()
        d = e if d is None else min(d, e)
    assert d < 3.0
