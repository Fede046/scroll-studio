"""edit.align: an edit the editor re-framed is registered back onto its source, measured outside the subject."""
import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from engine.edit_align import align_edit, register
from engine.spec import EditAlign, ImageEdit


def _scene(w=1280, h=720, seed=3):
    """A textured place (tiles, blobs) with a plain grey 'person' on the left that the edit may change."""
    rng = np.random.default_rng(seed)
    img = np.full((h, w, 3), 60, np.uint8)
    for _ in range(400):
        x, y = int(rng.integers(0, w)), int(rng.integers(0, h))
        r = int(rng.integers(4, 30))
        cv2.circle(img, (x, y), r, tuple(int(c) for c in rng.integers(30, 230, 3)), -1)
    for x in range(0, w, 90):
        cv2.line(img, (x, 0), (x, h), (120, 120, 120), 2)
    for y in range(0, h, 90):
        cv2.line(img, (0, y), (w, y), (120, 120, 120), 2)
    return img


def _move(img, scale, deg, shift):
    h, w = img.shape[:2]
    M = cv2.getRotationMatrix2D((w / 2, h / 2), deg, scale)
    M[:, 2] += shift
    return cv2.warpAffine(img, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT), M


class TestEditAlign(unittest.TestCase):
    def test_register_recovers_a_reframing(self):
        src = _scene()
        edit, M = _move(src, 1.06, 0.8, (34.0, -12.0))
        # the 'person' changed in the edit: paint over the left third so it cannot be matched
        edit[:, :400] = 200
        A, rep = register(src, edit, subject=(0.0, 0.0, 0.32, 1.0))
        self.assertTrue(rep["ok"], rep)
        # A maps the edit back onto the source: composing it with the move gives (about) the identity
        full = np.vstack([M, [0, 0, 1]]) @ np.eye(3)
        back = np.vstack([A, [0, 0, 1]]) @ full
        self.assertTrue(np.allclose(back[:2, :2], np.eye(2), atol=0.01), back)
        self.assertLess(abs(back[0, 2]) + abs(back[1, 2]), 3.0, back)
        self.assertLess(rep["residual_px"], 2.0)

    def test_align_edit_locks_the_place_outside_the_subject(self):
        src = _scene()
        edit, _ = _move(src, 0.97, -0.5, (-20.0, 8.0))
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            Image.fromarray(src).save(d / "src.png")
            Image.fromarray(edit).save(d / "edit.png")
            spec = EditAlign(subject=(0.0, 0.0, 0.3, 1.0), lock=True, feather=16)
            align_edit(d / "src.png", d / "edit.png", spec, d / "out.png", log=lambda *_: None)
            out = np.asarray(Image.open(d / "out.png").convert("RGB")).astype(int)
            self.assertTrue((d / "out.align.json").exists())
        # well outside the subject box and its feather, the place is the source, pixel for pixel
        self.assertEqual(int(np.abs(out[:, 600:] - src[:, 600:].astype(int)).max()), 0)

    def test_spec_accepts_align(self):
        e = ImageEdit.model_validate({"source": {"file": "a.png"}, "instruction": "raise his hands",
                                      "align": {"subject": [0.02, 0, 0.62, 1]}})
        self.assertTrue(e.align.lock)
        self.assertEqual(e.align.subject, (0.02, 0.0, 0.62, 1.0))


if __name__ == "__main__":
    unittest.main()
