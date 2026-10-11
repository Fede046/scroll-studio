"""Animate a still with LTX-2.3 image-to-video (local ComfyUI): the shared step behind theme.art and film beats."""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from .project import BuildError

FPS = 24
NEGATIVE = ("cuts, camera shake, flicker, morphing, warped body, extra limbs, new objects appearing, neon tubes, light "
            "rings, text, watermark, blur")


def ltx_size(w: int, h: int, mp: float = 0.44) -> tuple[int, int]:
    """About `mp` megapixels at the image's aspect, both sides multiples of 32 (what LTX-2.3 wants)."""
    scale = (mp * 1_000_000 / (w * h)) ** 0.5
    return max(256, round(w * scale / 32) * 32), max(256, round(h * scale / 32) * 32)


def frames_for(seconds: float) -> int:
    return max(9, round(seconds * FPS / 8) * 8 + 1)


def animate(still: Path, prompt: str, motion: str, seconds: float, seed: int, work: Path,
            log: Callable[[str], None] = print, size: Optional[tuple[int, int]] = None,
            negative: str = NEGATIVE, strength: float = 1.0, end_image: Optional[Path] = None) -> list[Path]:
    """Frames (PNG paths, in order) of `still` brought to life by `motion`."""
    from .backends import comfy
    if not comfy.alive():
        raise BuildError(f"Animating needs ComfyUI with LTX-2.3 running at {comfy.COMFY}. Start it (docs/INSTALL.md).")
    from PIL import Image
    w, h = (size[0] // 32 * 32, size[1] // 32 * 32) if size else ltx_size(*Image.open(still).size)
    n = frames_for(seconds)
    log(f"  animating with LTX-2.3 ({w}x{h}, {n} frames): {motion[:80]}")
    comfy.free()
    name = comfy.upload(str(still))
    end_name = comfy.upload(str(end_image)) if end_image else None
    text = f"{prompt or 'The subject of the image'}. {motion}. Smooth natural motion."
    graph = comfy.build_i2v_graph(comfy.LTX, name, n, w, h, FPS, text, negative, seed, prefix=f"studio/anim_{work.name}",
                                  strength=strength, end_image=end_name)
    images = comfy.run(graph, poll=3)
    import shutil
    if (work / "frames").exists():
        shutil.rmtree(work / "frames")
    tmp = Path(comfy.fetch(images, str(work / "frames")))
    comfy.free()
    return sorted(tmp.glob("*.png"))
