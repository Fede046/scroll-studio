"""beat.restore (SeedVR2 over one beat) and the `smoother` camera ease."""
from engine.freeze import EASES, CameraPath
from engine.plan import expected
from engine.spec import Beat, FilmScene


def _film(**beat):
    return FilmScene(id="f", type="film", beats=[Beat(id="a", seconds=4, prompt="p", motion="m", **beat), Beat(id="b", seconds=4, prompt="q", motion="m")])


def test_smoother_rests_without_a_jolt():
    e = EASES["smoother"]
    assert e(0) == 0 and e(1) == 1 and abs(e(0.5) - 0.5) < 1e-12
    h = 1e-4
    for u in (0.0 + h, 1.0 - h):          # speed and acceleration both vanish at the stops
        v = (e(u + h) - e(u - h)) / (2 * h)
        a = (e(u + h) - 2 * e(u) + e(u - h)) / (h * h)
        assert abs(v) < 1e-3 and abs(a) < 0.1


def test_smoother_path():
    p = CameraPath([{"t": 0, "box": [0, 0, 1, 1]}, {"t": 1, "box": [0.25, 0.25, 0.75, 0.75]}], "smoother")
    assert abs(p.at(1).w - 0.5) < 1e-9 and abs(p.at(0).w - 1) < 1e-9


def test_restore_stage_only_when_set():
    assert "restore_a" not in expected(_film())
    names = expected(_film(restore=1088))
    assert names.index("beat_a") < names.index("restore_a") < names.index("beats_join")
