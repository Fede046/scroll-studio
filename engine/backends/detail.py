"""Detail passes for deep zoom (engine/zoom.py): the ComfyUI graphs that give a tile fine detail the frame never had.

zimage_img2img   Z-Image Turbo re-diffusion of an image at low denoise: the picture keeps its shapes, colours and
                 composition, and the sampler redraws what is finer than that (stitching, creases, grain of the paper)
                 in the style the prompt names. Fast (a few steps) and run at the tile's full resolution.
qwen_detail      Qwen-Image-Edit asked to add fine detail in the same drawing style (the editor understands what the
                 picture shows, so it can draw laces on a boot; it works at ~1.6 megapixels, then is resized).
"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Callable, Optional

from ..project import BuildError


def build_zimage_img2img_graph(image: str, prompt: str, seed: int, denoise: float, prefix: str, steps: int = 8,
                               cfg: Optional[dict] = None) -> dict:
    """Z-Image Turbo img2img: VAE-encode `image` (an uploaded name), sample from `denoise` of the way up the noise
    schedule, decode. `steps` is the number of steps the whole schedule would take; a low denoise runs a share of them."""
    from .comfy import ZIMAGE
    k = dict(ZIMAGE, **(cfg or {}))
    return {
        "unet": {"class_type": "UNETLoader", "inputs": {"unet_name": k["model"], "weight_dtype": "default"}},
        "shift": {"class_type": "ModelSamplingAuraFlow", "inputs": {"model": ["unet", 0], "shift": k.get("shift", 3.0)}},
        "clip": {"class_type": "CLIPLoader", "inputs": {
            "clip_name": k["text_encoder"], "type": "lumina2", "device": k.get("text_encoder_device", "cpu")}},
        "vae": {"class_type": "VAELoader", "inputs": {"vae_name": k["vae"]}},
        "img": {"class_type": "LoadImage", "inputs": {"image": image}},
        "enc": {"class_type": "VAEEncode", "inputs": {"pixels": ["img", 0], "vae": ["vae", 0]}},
        "pos": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["clip", 0]}},
        "neg": {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["pos", 0]}},
        "ks": {"class_type": "KSampler", "inputs": {
            "model": ["shift", 0], "seed": seed, "steps": steps, "cfg": 1.0,
            "sampler_name": k.get("sampler", "res_multistep"), "scheduler": "simple",
            "positive": ["pos", 0], "negative": ["neg", 0], "latent_image": ["enc", 0], "denoise": denoise}},
        "decode": {"class_type": "VAEDecode", "inputs": {"samples": ["ks", 0], "vae": ["vae", 0]}},
        "save": {"class_type": "SaveImage", "inputs": {"images": ["decode", 0], "filename_prefix": prefix}},
    }


def _run(graph: dict, dst: Path) -> Path:
    from . import comfy
    images = comfy.run(graph, poll=2)
    tmp = Path(comfy.fetch(images[:1], str(dst.parent / f"_{dst.stem}_out")))
    try:
        shutil.move(str(next(tmp.glob("*.png"))), dst)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return dst


def zimage_img2img(src: Path, dst: Path, prompt: str, seed: int, denoise: float, log: Callable = print) -> Path:
    """Re-diffuse `src` (any size, multiples of 16 are best) at `denoise`; writes `dst` at the same size."""
    from PIL import Image
    from . import comfy
    if not comfy.alive():
        raise BuildError(f"Deep zoom needs ComfyUI running at {comfy.COMFY} (docs/INSTALL.md) for its detail pass.")
    w, h = Image.open(src).size
    comfy.free()
    name = comfy.upload(str(src))
    out = _run(build_zimage_img2img_graph(name, prompt, seed, denoise, f"studio/zoom_{src.stem}"[:60]), dst)
    comfy.free()
    im = Image.open(out)
    if im.size != (w, h):
        im.convert("RGB").resize((w, h), Image.LANCZOS).save(out)
    return out


def qwen_detail(src: Path, dst: Path, instruction: str, seed: int, steps: int = 20, megapixels: float = 1.6,
                log: Callable = print) -> Path:
    from PIL import Image
    from . import comfy
    if not comfy.alive():
        raise BuildError(f"Deep zoom needs ComfyUI running at {comfy.COMFY} (docs/INSTALL.md) for its detail pass.")
    w, h = Image.open(src).size
    comfy.free()
    name = comfy.upload(str(src))
    g = comfy.build_qwen_edit_graph([name], instruction, seed, steps, prefix=f"studio/zoom_{src.stem}"[:60], megapixels=megapixels)
    out = _run(g, dst)
    comfy.free()
    im = Image.open(out)
    if im.size != (w, h):
        im.convert("RGB").resize((w, h), Image.LANCZOS).save(out)
    return out
