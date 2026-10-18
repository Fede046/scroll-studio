"""The browser half of a match cut, run in Node: `planMatch` (runtime/src/lib/cuts-match.ts) is pure geometry, so the
shapes can be checked without a browser: both sides' shapes land on the same point at the same size, each zoom's pivot
stays inside its picture (so the picture still covers what it covered), and shapes too far apart to meet return null.
Skipped without Node and the repo's node_modules (esbuild comes with vite)."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which("node")
ESBUILD = ROOT / "node_modules" / "esbuild"

pytestmark = pytest.mark.skipif(not NODE or not ESBUILD.exists(), reason="needs node and node_modules (npm install)")

SCRIPT = """
import { build } from "esbuild";
import { pathToFileURL } from "node:url";
const [src, out, cases] = process.argv.slice(1);
await build({ entryPoints: [src], outfile: out, format: "esm", bundle: false, platform: "node", logLevel: "error" });
const m = await import(pathToFileURL(out).href);
const W = 1440, H = 900, view = { x: 0, y: 0, w: W, h: H };
const res = JSON.parse(cases).map(([A, B, zoom]) => {
  const p = m.planMatch(A, B, view, view, zoom);
  if (!p) return null;
  const at = (s, f, c) => [f[0] + s * (c[0] - f[0]), f[1] + s * (c[1] - f[1])];
  const cA = [A.x + A.w / 2, A.y + A.h / 2], cB = [B.x + B.w / 2, B.y + B.h / 2];
  const a = at(p.sA, p.fA, cA), b = at(p.sB, p.fB, cB);
  return { a, b, sizeA: Math.sqrt(A.w * A.h) * p.sA, sizeB: Math.sqrt(B.w * B.h) * p.sB, sA: p.sA, sB: p.sB, fA: p.fA, fB: p.fB };
});
console.log(JSON.stringify(res));
"""


def plan(tmp_path, cases):
    src = ROOT / "runtime" / "src" / "lib" / "cuts-match.ts"
    r = subprocess.run([NODE, "--input-type=module", "-e", SCRIPT, str(src), str(tmp_path / "m.mjs"), json.dumps(cases)],
                       cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout.strip().splitlines()[-1])


def box(x, y, w, h):
    return {"x": x, "y": y, "w": w, "h": h}


def test_the_shapes_meet_at_one_point_and_one_size_and_the_pivots_stay_on_screen(tmp_path):
    cases = [
        [box(500, 300, 400, 400), box(500, 300, 400, 400), 3],        # already agree
        [box(700, 400, 130, 130), box(500, 200, 330, 330), 3],        # small to big: A does the zooming
        [box(400, 150, 500, 500), box(1000, 500, 170, 170), 3],       # big to small: B starts zoomed in
        [box(150, 300, 260, 260), box(650, 350, 260, 260), 3],        # same size, a way apart: a bigger push
    ]
    for r in plan(tmp_path, cases):
        assert r is not None
        assert abs(r["a"][0] - r["b"][0]) < 1e-6 and abs(r["a"][1] - r["b"][1]) < 1e-6
        assert abs(r["sizeA"] - r["sizeB"]) / r["sizeA"] < 1e-6
        assert r["sA"] >= 1.0 and r["sB"] >= 1.0                       # only ever zoom in
        for f in (r["fA"], r["fB"]):
            assert -1e-6 <= f[0] <= 1440 + 1e-6 and -1e-6 <= f[1] <= 900 + 1e-6


def test_too_big_a_ratio_is_capped_and_unreachable_shapes_dissolve(tmp_path):
    ten, apart = plan(tmp_path, [[box(700, 400, 40, 40), box(500, 200, 400, 400), 3],
                                 [box(5, 5, 100, 100), box(1330, 790, 100, 100), 1.0]])
    assert ten is not None and ten["sA"] <= 3 * 2.4 + 1e-6 and ten["sizeA"] < ten["sizeB"]     # capped: the shapes only nearly coincide
    assert apart is None                                                                        # nothing to meet on without showing an edge
