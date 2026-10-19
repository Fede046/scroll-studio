"""The one-take page (`journey:`): the spec, its expansion into beats, the scroll timeline, where the blocks sit on a
picture, and the page markup. No ComfyUI and no GPU."""
from __future__ import annotations

import json

import numpy as np
import pytest
from pydantic import ValidationError

from engine import journey as jy
from engine.spec import Site

STOPS = [
    {"id": "door", "place": "The open front door", "blocks": [{"type": "hero", "title": "Fenmoor", "body": "A house"}]},
    {"id": "hearth", "place": "The hall", "move": {"into": [0.4, 0.3, 0.62, 0.8], "seconds": 4},
     "blocks": [{"type": "features", "items": [{"title": "A"}, {"title": "B"}]}]},
    {"id": "table", "place": "The long table", "hold": 2.0, "move": {"seconds": 5, "scroll": 3, "via": [[0.2, 0.2, 0.8, 0.8]]},
     "blocks": [{"type": "stats", "items": [{"value": "4", "label": "rooms"}]}, {"type": "quote", "text": "Quiet"}]},
]


def site(stops=None, **film) -> Site:
    return Site.model_validate({"name": "T", "sections": [{"id": "stay", "type": "film", "beat_res": [1024, 576], **film,
                                                           "journey": {"world": "a stone house", "stops": stops or STOPS}}]})


def test_expands_to_hold_and_travel_beats():
    sec = site().sections[0]
    assert [b.id for b in sec.beats] == ["door-hold", "hearth-travel", "hearth-hold", "table-travel", "table-hold"]
    door, travel, hold = sec.beats[0], sec.beats[1], sec.beats[2]
    assert door.freeze is not None and door.freeze.image.generate.startswith("a stone house.")   # the first picture: the world and its place
    assert travel.camera is not None and travel.image.beat_frame.beat == "door-hold"             # a move starts on the last frame before it
    assert [k.box for k in travel.camera.keys] == [(0, 0, 1, 1), (0.4, 0.3, 0.62, 0.8)]
    assert hold.freeze.from_ == "hearth-travel" and hold.freeze.pick == "last"                   # a hold freezes where the move arrived
    via = sec.beats[3].camera.keys
    assert [k.box for k in via][1] == (0.2, 0.2, 0.8, 0.8) and [k.t for k in via] == [0, 0.5, 1]  # waypoints are evenly spaced


def test_holds_start_and_end_on_the_whole_picture():
    for b in site().sections[0].beats:
        if b.freeze is not None:
            ks = b.freeze.camera
            assert ks[0].box == (0, 0, 1, 1) and ks[-1].box == (0, 0, 1, 1) and b.freeze.ease == "smoother"


def test_scroll_length_is_the_sum_of_holds_and_moves_plus_a_screen():
    sec = site().sections[0]
    ws = {b: w for b, _, _, w in jy.weights(sec)}
    assert ws["hearth-travel"] == 2.0 and ws["table-travel"] == 3 and ws["table-hold"] == 2.0   # default: half the seconds
    assert sec.length == pytest.approx(sum(ws.values()) + 1)
    slow = site().sections[0]
    assert slow.length == sec.length


def test_pace_scales_every_distance():
    base = site().sections[0].length
    s = Site.model_validate({"name": "T", "sections": [{"id": "stay", "type": "film", "journey": {"world": "w", "pace": 2, "stops": STOPS}}]})
    assert s.sections[0].length == pytest.approx((base - 1) * 2 + 1)


def test_edit_and_still_stops():
    stops = [dict(STOPS[0]), dict(STOPS[1], edit="a crate on the table", region="the table")]
    sec = site(stops).sections[0]
    h = sec.beats[2]
    assert h.freeze.image.edit.source.beat_frame.beat == "hearth-travel" and h.freeze.image.edit.region.prompt == "the table"
    stops = [dict(STOPS[0], still="inputs/door.png"), STOPS[1]]
    assert site(stops).sections[0].beats[0].freeze.image == "inputs/door.png"


def test_spec_errors():
    with pytest.raises(ValidationError, match="unique"):
        site([STOPS[0], dict(STOPS[0])])
    with pytest.raises(ValidationError, match="limits an `edit`"):
        site([STOPS[0], dict(STOPS[1], region="the table")])
    with pytest.raises(ValidationError, match="use one"):
        site([STOPS[0], dict(STOPS[1], edit="x", still="a.png")])
    with pytest.raises(ValidationError, match="do not also write `beats`"):
        site(beats=[{"id": "x", "prompt": "a", "motion": "b"}])
    with pytest.raises(ValidationError):
        site(STOPS[:1])                                  # a journey goes somewhere


def test_the_spec_as_written_is_what_is_saved():
    s = site()
    d = s.sections[0].model_dump(mode="json", exclude_unset=True)
    assert "beats" not in d and "steps" not in d and "length" not in d and "beat_fade" not in d
    again = Site.model_validate({"name": "T", "sections": [d]})
    assert [b.id for b in again.sections[0].beats] == [b.id for b in s.sections[0].beats]


def test_schema_documents_the_journey():
    schema = Site.model_json_schema()
    for name in ("Journey", "JourneyStop", "JourneyMove"):
        assert all(p.get("description") for p in schema["$defs"][name]["properties"].values()), name


# ---------------------------------------------------------------- the timeline

def tl(fades=0.25):
    sec = site().sections[0]
    durs = [3.0, 4.0 + 1 / 24, 3.0, 5.0 + 1 / 24, 3.0]
    return sec, jy.timeline(sec, durs, [fades] * (len(durs) - 1))


def test_timeline_tiles_the_film_and_scroll():
    sec, t = tl()
    pts = t["map"]
    assert pts[0] == [0.0, 0.0] and pts[-1][0] == pytest.approx(1.0) and pts[-1][1] == pytest.approx(t["duration"], abs=1e-3)
    assert all(b[0] > a[0] and b[1] > a[1] for a, b in zip(pts, pts[1:]))
    assert t["duration"] == pytest.approx(3 + 4 + 1 / 24 + 3 + 5 + 1 / 24 + 3 - 4 * 0.25, abs=1e-3)


def test_a_hold_is_exactly_its_frozen_moment():
    sec, t = tl(fades=0.0)
    s = {x["id"]: x for x in t["stops"]}
    assert (s["door"]["t0"], s["door"]["t1"]) == (0.0, 3.0)
    assert s["hearth"]["t1"] - s["hearth"]["t0"] == pytest.approx(3.0)
    total = sum(w for *_, w in jy.weights(sec))
    assert s["hearth"]["p0"] == pytest.approx((1.4 + 2.0) / total, abs=1e-4) and s["hearth"]["p1"] == pytest.approx((1.4 + 2.0 + 1.4) / total, abs=1e-4)


def test_stop_windows_arrive_before_the_hold_and_leave_after_it():
    _, t = tl()
    first, mid, last = t["stops"][0], t["stops"][1], t["stops"][2]
    assert first["in"] == [0.0, 0.0] and first["travel"] is None            # the first stop is there from the first frame
    assert mid["in"][0] < mid["in"][1] == mid["p0"] and mid["travel"][1] == mid["p0"]
    assert mid["out"][0] == mid["p1"] < mid["out"][1] < last["p0"]
    assert last["out"] == [2.0, 2.0]                                         # the last stop never leaves


# ---------------------------------------------------------------- where the blocks sit

def picture(busy_side: str, bright: float = 0.1, w=480, h=270) -> np.ndarray:
    rng = np.random.default_rng(1)
    a = np.full((h, w, 3), int(bright * 255), np.uint8)
    noise = rng.integers(0, 255, (h, w // 2, 3), dtype=np.uint8)
    if busy_side == "left":
        a[:, : w // 2] = noise
    else:
        a[:, w // 2:] = noise
    return a


def test_blocks_go_to_the_calm_side():
    assert jy.analyse(picture("left"))["side"] == "right"
    assert jy.analyse(picture("right"))["side"] == "left"


def test_the_side_can_be_set_and_sides_alternate_when_it_is_a_toss_up():
    assert jy.analyse(picture("left"), side="left")["side"] == "left"
    flat = np.full((270, 480, 3), 60, np.uint8)
    a = jy.analyse(flat, prev_side="left")
    assert a["side"] != "left"                                               # nudged off the side the stop before used


def test_lettering_follows_the_light_and_always_clears_aa():
    dark = jy.analyse(np.full((270, 480, 3), 25, np.uint8))
    light = jy.analyse(np.full((270, 480, 3), 235, np.uint8))
    assert dark["surface"] == "dark" and light["surface"] == "light"
    assert dark["contrast"] >= jy.CONTRAST and light["contrast"] >= jy.CONTRAST
    mid = jy.analyse(np.full((270, 480, 3), 120, np.uint8))                  # a mid grey needs a scrim to read
    assert mid["scrim"] > 0 and mid["contrast"] >= jy.CONTRAST
    forced = jy.analyse(np.full((270, 480, 3), 235, np.uint8), surface="dark")   # light lettering on a bright picture: a heavy scrim
    assert forced["scrim"] > 0.5 and forced["contrast"] >= jy.CONTRAST


def test_lettering_colours_come_from_the_theme():
    assert jy.lettering({"colors": {"ink": "#eeeeee", "bg": "#050505"}}) == ("#eeeeee", "#050505")
    assert jy.lettering({"colors": {"ink": "#222222", "bg": "#efe8da"}}) == ("#efe8da", "#222222")


# ---------------------------------------------------------------- the page

def render(first=True):
    from engine.compile.compiler import _env
    sec = site().sections[0]
    t = tl()[1]
    stops = [{**s, "still": f"assets/stay/stops/{s['id']}.jpg", "side": side, "surface": "dark", "scrim": 0.2, "focus": None}
             for s, side in zip(t["stops"], ["left", "right", "bottom"])]
    cfg = {"poster": "p.jpg", "journey": {**{k: t[k] for k in ("duration", "map")}, "stops": stops, "rail": True,
                                        "ink": {"light": "#eee", "dark": "#111"}}}
    ex = {"first": first, "jx": {s.id: [{} for _ in s.blocks] for s in sec.journey.stops}}
    mod = _env().get_template("scene.html.j2").module
    return mod.render(sec, cfg, sec.model_dump(mode="json", include={"hud", "steps", "layout", "length"}), ex)


def test_the_page_is_readable_without_javascript():
    html = str(render())
    assert html.count("<h1") == 1 and html.index("<h1") < html.index("Quiet")          # one h1: the opening stop's hero
    assert html.count('class="jy-stop ') == 3 and html.count("<img src=\"assets/stay/stops/") == 3   # every stop has its still
    for text in ("Fenmoor", "A house", ">A<", ">B<", "rooms", "Quiet"):
        assert text in html
    assert 'alt="The long table"' in html                                                # the still is described by its place
    assert 'data-scene="film"' in html and 'class="ss-config"' in html


def test_later_sections_do_not_get_the_h1():
    assert "<h1" not in str(render(first=False))


def test_rail_links_to_every_stop():
    html = str(render())
    for sid in ("door", "hearth", "table"):
        assert f'href="#{sid}"' in html and f'id="{sid}"' in html
    cfg = json.loads(html.split('class="ss-config">')[1].split("</script>")[0])
    assert [s["id"] for s in cfg["journey"]["stops"]] == ["door", "hearth", "table"]


# ---------------------------------------------------------------- the take approach (a blockout)

POSES = [{"at": [0, -0.4, 1.5], "look": [0, 12, 1.3]}, {"at": [0.9, 2.5, 1.5], "look": [-1.8, 2.1, 1.0]},
         {"at": [0.4, 6.4, 1.5], "look": [2.2, 6.9, 1.4]}]


def take_site(**blockout) -> Site:
    stops = [dict(s, pose=p) for s, p in zip(STOPS, POSES)]
    stops[1]["move"] = {"seconds": 5, "path": [{"at": [0.2, 1.0, 1.5], "look": [-1, 3, 1.2]}]}
    stops[2]["move"] = {"seconds": 6}
    return Site.model_validate({"name": "T", "sections": [{"id": "stay", "type": "film", "journey": {
        "world": "a stone house", "stops": stops, "blockout": {"objects": [{"kind": "box", "at": [0, 5, 1], "size": [1, 1, 1], "color": "#888888"}], **blockout}}}]})


def test_a_blockout_makes_one_take_with_a_camera_that_rests_at_every_stop():
    sec = take_site().sections[0]
    assert sec.beats == [] and sec.take is not None
    t = sec.take
    assert t.duration == pytest.approx(3 + 5 + 3 + 6 + 3)                    # holds and moves, in order
    ts = [(k.t, tuple(k.at)) for k in t.camera]
    assert ts[0] == (0.0, (0, -0.4, 1.5)) and ts[1][1] == (0, -0.4, 1.5) and ts[1][0] == 3     # rests on the first stop for its hold
    assert any(abs(k.t - 5.5) < 1e-6 and tuple(k.at) == (0.2, 1.0, 1.5) for k in t.camera)     # the waypoint, halfway through the move
    assert [k.t for k in t.camera] == sorted(k.t for k in t.camera)


def test_a_picture_of_every_stop_is_painted_over_the_blockout():
    t = take_site().sections[0].take
    frames = t.keyframes["frames"]
    assert [f["name"] for f in frames] == ["door", "hearth", "table"]
    assert frames[0]["t"] == 0 and frames[1]["t"] == pytest.approx(3 + 5 + 1.5)               # the middle of the hold
    assert frames[1]["prompt"].startswith("a stone house. The hall")


def test_the_take_is_cut_at_the_middle_of_a_hold_and_long_stretches_are_split():
    t = take_site(segment=6).sections[0].take
    segs = t.ltx["segments"]
    assert segs[0]["range"][0] == 0 and segs[-1]["range"][1] == pytest.approx(t.duration)
    assert all(b["range"][0] == a["range"][1] for a, b in zip(segs, segs[1:]))               # they tile the take
    assert all(s["range"][1] - s["range"][0] <= 6 + 1e-6 for s in segs)
    assert any(abs(s["range"][1] - 9.5) < 1e-6 for s in segs)                                # the middle of the hearth hold
    assert "The hall" in segs[0]["prompt"] and "One continuous" in segs[0]["prompt"]


def test_a_blockout_needs_poses_and_poses_need_a_blockout():
    stops = [dict(s) for s in STOPS]
    with pytest.raises(ValidationError, match="needs a `pose`"):
        Site.model_validate({"name": "T", "sections": [{"id": "s", "type": "film", "journey": {"world": "w", "stops": stops, "blockout": {}}}]})
    with pytest.raises(ValidationError, match="place the camera in a `blockout`"):
        Site.model_validate({"name": "T", "sections": [{"id": "s", "type": "film", "journey": {"world": "w", "stops": [dict(s, pose=POSES[0]) for s in STOPS]}}]})
    with pytest.raises(ValidationError, match="fly through a picture"):
        take_site().model_validate({"name": "T", "sections": [{"id": "s", "type": "film", "journey": {"world": "w", "blockout": {}, "stops": [
            dict(STOPS[0], pose=POSES[0]), dict(STOPS[1], pose=POSES[1], move={"into": [0.1, 0.1, 0.5, 0.5]})]}}]})


def test_the_take_timeline_is_the_plan_stretched_to_the_film():
    sec = take_site().sections[0]
    nominal = [x[3] for x in jy.plan(sec)]
    k = 1.01
    t = jy.timeline(sec, [d * k for d in nominal], [0.0] * (len(nominal) - 1))
    assert t["duration"] == pytest.approx(sum(nominal) * k, abs=1e-2)
    s = {x["id"]: x for x in t["stops"]}
    assert s["door"]["t0"] == 0 and s["hearth"]["t1"] - s["hearth"]["t0"] == pytest.approx(3 * k, abs=1e-2)
