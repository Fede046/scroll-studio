"""The layout safety net for 1.5 (docs/design/1.5-make-it-yours.md, step 0): every example compiles to the same placement
before and after the layout model is replaced.

Each examples/<name>/site.yaml has a snapshot in tests/snapshots/layout/<name>.json (engine/compile/layout_snapshot.py:
the spec's validators, the real templates with a stand-in config, the placement facts read from the markup). A change
that moves anything fails with a diff naming the section, the element and old -> new. When the move is the point of the
change, review the diff and rewrite the snapshots:

    UPDATE_LAYOUT_SNAPSHOTS=1 python -m pytest tests/test_layout_snapshots.py

No GPU, no rendering, no network."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path

import pytest
import yaml

from engine.compile.layout_snapshot import diff_layout, layout_snapshot

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = sorted((ROOT / "examples").glob("*/site.yaml"), key=lambda p: p.parent.name)
SNAPSHOTS = Path(__file__).resolve().parent / "snapshots" / "layout"
UPDATE = os.environ.get("UPDATE_LAYOUT_SNAPSHOTS") == "1"


def dumps(snap: dict) -> str:
    return json.dumps(snap, indent=1, ensure_ascii=False) + "\n"


def write(path: Path, snap: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(dumps(snap))


@pytest.mark.parametrize("site_yaml", EXAMPLES, ids=lambda p: p.parent.name)
def test_example_keeps_its_layout(site_yaml: Path):
    snap = layout_snapshot(site_yaml)
    file = SNAPSHOTS / f"{site_yaml.parent.name}.json"
    if UPDATE:
        write(file, snap)
        return
    assert file.exists(), f"no snapshot for {site_yaml.parent.name}: run UPDATE_LAYOUT_SNAPSHOTS=1 python -m pytest tests/test_layout_snapshots.py"
    old = json.loads(file.read_text(encoding="utf-8"))
    lines = diff_layout(old, snap)
    assert not lines, (f"{site_yaml.parent.name}: the layout changed ({len(lines)} differences). If this is intended, review and run "
                       "UPDATE_LAYOUT_SNAPSHOTS=1 python -m pytest tests/test_layout_snapshots.py\n  " + "\n  ".join(lines[:60])
                       + ("\n  ..." if len(lines) > 60 else ""))
    assert old == snap      # nothing the diff does not name


def test_every_example_has_a_snapshot_and_no_snapshot_outlives_its_example():
    if UPDATE:
        for stale in set(SNAPSHOTS.glob("*.json")) - {SNAPSHOTS / f"{p.parent.name}.json" for p in EXAMPLES}:
            stale.unlink()
        return
    have = {p.stem for p in SNAPSHOTS.glob("*.json")}
    want = {p.parent.name for p in EXAMPLES}
    assert len(want) >= 28
    assert have == want, f"missing: {sorted(want - have)}, stale: {sorted(have - want)}"


def test_snapshot_files_are_lf_and_what_the_writer_writes():
    for f in SNAPSHOTS.glob("*.json"):
        raw = f.read_bytes()
        assert b"\r" not in raw, f"{f.name} has CR line endings"
        assert raw.decode("utf-8") == dumps(json.loads(raw)), f"{f.name} is not in the writer's format"


def test_a_snapshot_is_deterministic_and_plain_json():
    a, b = layout_snapshot(EXAMPLES[0]), layout_snapshot(EXAMPLES[0])
    assert a == b and json.loads(json.dumps(a)) == a


def test_partial_coverage_is_written_down_never_skipped():
    """What a render decides (the inside scene's schedule, a journey's measured side) is said in a `note`."""
    snap = json.loads((SNAPSHOTS / "inside-board.json").read_text(encoding="utf-8"))
    assert "note" in snap and any("note" in s for s in snap["sections"])
    assert "match-cut anchors" in json.loads((SNAPSHOTS / "film-cuts.json").read_text(encoding="utf-8"))["note"]


# ---------------------------------------------------------------- the snapshot notices what moves

def edited(tmp_path: Path, example: str, change) -> dict:
    """The snapshot of an example whose spec `change(raw)` has edited (the folder is copied: only site.yaml is read)."""
    raw = yaml.safe_load((ROOT / "examples" / example / "site.yaml").read_text(encoding="utf-8"))
    change(raw)
    d = tmp_path / example
    d.mkdir()
    (d / "site.yaml").write_text(yaml.safe_dump(raw, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return layout_snapshot(d / "site.yaml")


def baseline(example: str) -> dict:
    return layout_snapshot(ROOT / "examples" / example / "site.yaml")


def section(raw: dict, type_: str) -> dict:
    return next(s for s in raw["sections"] if s["type"] == type_)


def test_a_step_place_moves_the_snapshot(tmp_path):
    def move(raw):
        section(raw, "film")["steps"][0]["place"] = "top-right"
    old, new = baseline("meridian"), edited(tmp_path, "meridian", move)
    lines = diff_layout(old, new)
    assert old != new and lines
    assert any("ss-captions--top-right" in l for l in lines)             # the caption sits in its own container now
    assert any(l.startswith("[descent]") for l in lines)                 # and the diff names the section
    assert any("sdata" in l and "top-right" in l for l in lines)         # the embedded section data changed too


def test_a_scene_layout_moves_the_snapshot(tmp_path):
    def cards(raw):
        section(raw, "film")["layout"] = "cards"
    old, new = baseline("meridian"), edited(tmp_path, "meridian", cards)
    lines = diff_layout(old, new)
    assert old != new
    assert any("ss-overlay" in l and "ss-cards" in l for l in lines)     # the section's layout class
    assert any("ss-captions" in l and "removed" in l for l in lines)     # the overlay's caption container is gone
    assert any("ss-steps--over" in l for l in lines)                     # replaced by the cards' scrolling steps


def test_a_product_side_moves_the_snapshot(tmp_path):
    def flip(raw):
        p = section(raw, "product")
        p["side"] = "left" if p.get("side", "right") == "right" else "right"
    old, new = baseline("tern-house"), edited(tmp_path, "tern-house", flip)
    lines = diff_layout(old, new)
    assert old != new
    assert any("ss-product--left" in l and "ss-product--right" in l for l in lines)


def test_a_step_window_and_the_site_layout_move_the_snapshot(tmp_path):
    def window(raw):
        section(raw, "film")["steps"][1]["at"] = [0.4, 0.5]
    lines = diff_layout(baseline("meridian"), edited(tmp_path, "meridian", window))
    assert any("data-from" in l and "0.4" in l for l in lines)

    def stack(raw):
        raw["layout"] = "stack"
    lines = diff_layout(baseline("kiln-and-kettle"), edited(tmp_path, "kiln-and-kettle", stack))
    assert any(l.startswith("root classes") and "layout-stack" in l for l in lines)
    assert any("ss-panel" in l for l in lines)


def test_an_unedited_spec_has_no_diff(tmp_path):
    assert diff_layout(baseline("meridian"), edited(tmp_path, "meridian", lambda raw: None)) == []
    old = baseline("meridian")
    assert diff_layout(old, copy.deepcopy(old)) == []
