"""Camera moves on generated beats in a project: the stage a beat with `camera:` runs instead of a plain animation
(the guide itself, its measurement and the video-model calls are in engine/camera_guide.py).

Folder of the beat (.build/<section>/beats/<id>/), each file with a `.key` beside it holding the digest of what made it,
so changing a key's box re-renders the guide in seconds and never repeats the depth or the people mask:

    still.png    the start image fitted to beat_res (made by the film stage)
    cam_depth.npy   its depth at the generation size       cam_people.png   the moving subjects' mask at that size
    guide.mp4 / guide_rgb.mp4 / guide_static.mp4   the camera flown through the image (see camera_guide)
    frames/      the generated frames (24 fps, PNG, beat_res), what every beat leaves for the clip and `beat_frame`
    camera.json  the measured follow error (studio camera <project> <beat> --check)
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Callable, Optional

import numpy as np

from . import camera_guide as cg
from .animate import FPS
from .freeze_beats import _cached, digest, read_rgb
from .project import BuildError

DEFAULT_BACKEND = "ltx"          # what `backend: auto` picks (decided by measurement: docs/ENGINE.md)


def backend_of(move) -> str:
    return DEFAULT_BACKEND if move.backend == "auto" else move.backend


# ---------------------------------------------------------------- sizes

def gen_size(size: tuple[int, int], backend: str, frames: int) -> tuple[int, int]:
    """The size the video model runs at: `size` when it fits, else the largest at its aspect that does (LTX: multiples of
    64 and <= 22k latent tokens; Wan and Uni3C: ~1280x720 pixels, multiples of 16). The frames are scaled to `size` after."""
    W, H = size
    if backend == "ltx":
        steps = (frames - 1) // 8 + 1
        budget = 21000 / steps * 1024                      # pixels: tokens = pixels / 1024 * steps
        scale = min(1.0, (budget / (W * H)) ** 0.5)
        w = max(256, int(W * scale) // 64 * 64)
        h = max(256, int(round(w * H / W / 64)) * 64)
        while (w // 32) * (h // 32) * steps > 22000 and w > 256:
            w -= 64
            h = max(256, int(round(w * H / W / 64)) * 64)
        return w, h
    scale = min(1.0, (1280 * 720 / (W * H)) ** 0.5)
    return max(256, int(W * scale) // 16 * 16), max(256, int(round(W * scale * H / W / 16)) * 16)


def frames_of(sec_seconds: float, backend: str) -> int:
    return cg.ltx_frames(sec_seconds) if backend == "ltx" else cg.wan_clip_frames(sec_seconds)


def fps_of(backend: str) -> int:
    from .backends import comfy
    return FPS if backend == "ltx" else comfy.WAN_FPS


# ---------------------------------------------------------------- the key

def key_of(sec, i: int) -> dict:
    """The part of the beat's stage key that its camera adds (only present for a beat with `camera`)."""
    b = sec.beats[i]
    chain = cg.chain_of(sec.beats, i)
    k = {"move": b.camera.model_dump(mode="json"), "backend": backend_of(b.camera), "v": cg.VERSION}
    if len(chain) > 1:
        k["chain"] = [[sec.beats[j].id, sec.beats[j].seconds, sec.beats[j].camera.model_dump(mode="json")] for j in chain]
    return k


# ---------------------------------------------------------------- preparing the guide

def prepare(project, sec, i: int, still: Path, bdir: Path, log: Callable = print):
    """(rgb, depth, people, size, frames, fps, plan) for beat i: depth and people mask cached in the beat's folder."""
    from PIL import Image
    b = sec.beats[i]
    move = b.camera
    backend = backend_of(move)
    beat_w, beat_h = sec.beat_res[0] // 32 * 32, sec.beat_res[1] // 32 * 32
    frames = frames_of(b.seconds, backend)
    size = gen_size((beat_w, beat_h), backend, frames)
    img = Image.open(still).convert("RGB").resize(size, Image.LANCZOS)
    rgb = np.asarray(img)
    skey = bdir / "still.png.key"
    base = {"still": skey.read_text() if skey.exists() else digest(str(still), still.stat().st_size, int(still.stat().st_mtime)),
            "size": size}
    dkey = {**base, "model": "small", "v": cg.VERSION}

    def make_depth(tmp):
        from . import freeze as fz
        from .backends import depth as depthmod
        log("  depth: Depth Anything V2 (small)")
        d = depthmod.estimate(img, "small")
        np.save(tmp, fz.prepare_depth(d, rgb, size).astype(np.float16))
    depth = np.load(_cached(bdir / "cam_depth.npy", dkey, make_depth)).astype(np.float32)
    people = None
    if move.subjects.strip():
        pkey = {**base, "subjects": move.subjects, "v": cg.VERSION}

        def make_people(tmp):
            from .region import find
            from .spec import EditRegion
            png = bdir / "_cam_still_gen.png"
            img.save(png)
            try:
                m = find(project, png, EditRegion(prompt=move.subjects, pick="all"), log)
                Image.open(m).convert("L").resize(size, Image.BILINEAR).save(tmp, format="PNG")
            finally:
                png.unlink(missing_ok=True)
        people = np.asarray(Image.open(_cached(bdir / "cam_people.png", pkey, make_people)).convert("L"))
    return rgb, depth, people, size, frames, fps_of(backend), cg.plan_for(sec.beats, i)


def guide_for(project, sec, i: int, still: Path, bdir: Path, log: Callable = print):
    """The guide videos (cached by what they are made from) plus the things measuring needs."""
    b = sec.beats[i]
    move = b.camera
    rgb, depth, people, size, frames, fps, plan = prepare(project, sec, i, still, bdir, log)
    gkey = {"depth": (bdir / "cam_depth.npy.key").read_text(), "people": (bdir / "cam_people.png.key").read_text()
            if people is not None else None, "move": move.model_dump(mode="json", include={"parallax", "dolly", "soften"}),
            "plan": [plan.lo, plan.hi, [[k.t, list(k.box), k.hold, move.ease] for k in move.keys]],
            "chain": key_of(sec, i).get("chain"), "frames": frames, "fps": fps, "size": size, "v": cg.VERSION}
    stamp = bdir / "guide.json"
    paths = [bdir / "guide.mp4", bdir / "guide_rgb.mp4", bdir / "guide_static.mp4"]
    if not (stamp.exists() and stamp.read_text() == digest(gkey) and all(p.exists() for p in paths)):
        t0 = time.time()
        cg.write_guide(bdir, rgb, depth, people, move, plan, size=size, n_frames=frames, fps=fps,
                       soften=move.soften * size[0], seed=b.seed)
        stamp.write_text(digest(gkey))
        log(f"  guide: {frames} frames at {size[0]}x{size[1]} in {time.time() - t0:.1f}s")
    else:
        log("  guide: up to date")
    return cg.Guide(*paths, frames, fps), dict(rgb=rgb, depth=depth, people=people, size=size, plan=plan, backend=backend_of(move))


# ---------------------------------------------------------------- generating

def make_frames(project, sec, i: int, still: Path, bdir: Path, text: str, negative: str, seed: int, wan_cfg: Optional[dict],
                log: Callable = print) -> list[Path]:
    """The beat's frames (PNG paths in bdir/frames, 24 fps, beat_res): the guide, then the video model along it."""
    import shutil
    from PIL import Image
    from .animate import retime
    b = sec.beats[i]
    move = b.camera
    guide, info = guide_for(project, sec, i, still, bdir, log)
    backend, size = info["backend"], info["size"]
    beat_size = (sec.beat_res[0] // 32 * 32, sec.beat_res[1] // 32 * 32)
    gstill = bdir / "_cam_gen_still.png"
    Image.open(still).convert("RGB").resize(size, Image.LANCZOS).save(gstill)
    if backend == "ltx":
        pngs = cg.generate_ltx(gstill, guide.depth, text, negative, size, guide.frames, seed, bdir, move.guide_strength, log)
        src_fps = FPS
    elif backend == "wan":
        pngs = cg.generate_wan(gstill, guide.depth, text, negative, size, guide.frames, seed, bdir, wan_cfg, log)
        src_fps = guide.fps
    elif backend == "uni3c":
        pngs = cg.generate_uni3c(gstill, guide.rgb, text, negative, size, guide.frames, seed, bdir, wan_cfg, move.guide_strength, log)
        src_fps = guide.fps
    else:
        raise BuildError(f"camera backend '{backend}': use ltx, wan or uni3c")
    gstill.unlink(missing_ok=True)
    frames = bdir / "frames"
    if frames.exists():
        shutil.rmtree(frames)
    frames.mkdir(parents=True)
    if src_fps != FPS:
        raw = bdir / "_frames_src"
        if raw.exists():
            shutil.rmtree(raw)
        raw.mkdir()
        for n, p in enumerate(pngs, 1):
            shutil.copy(p, raw / f"{n:04d}.png")
        out = retime(raw, frames, src_fps, FPS, tuple(beat_size), (wan_cfg or {}).get("interpolate", "mci"), log)
        shutil.rmtree(raw, ignore_errors=True)
    else:
        out = []
        for n, p in enumerate(pngs, 1):
            dst = frames / f"{n:04d}.png"
            if tuple(Image.open(p).size) != tuple(beat_size):
                Image.open(p).convert("RGB").resize(beat_size, Image.LANCZOS).save(dst)
            else:
                shutil.copy(p, dst)
            out.append(dst)
    return out


# ---------------------------------------------------------------- the commands: guide only, and the check

def _beat(project, beat_id: str, section: Optional[str] = None):
    from .freeze_beats import find_beat
    sec, b = find_beat(project, beat_id, section)
    if b.camera is None:
        raise BuildError(f"beat '{beat_id}' has no `camera:` keys")
    return sec, sec.beats.index(b), b


def guide_only(project, beat_id: str, section: Optional[str] = None, log: Callable = print) -> dict:
    """Make the beat's guide (depth, people mask, the three guide videos) without generating anything: seconds once the
    depth and the mask are cached, and `guide_rgb.mp4` is a pure-camera preview of the move (the picture flown along the
    keys, no video model): look at it before spending minutes on the beat. Needs the start image (the beat's `still.png`,
    made by a build or a storyboard; otherwise it is resolved here)."""
    from PIL import Image, ImageOps
    from .inputs import resolve_image
    from .scenes.film import beats_film  # noqa: F401  (import check only)
    sec, i, b = _beat(project, beat_id, section)
    bdir = project.build / sec.id / "beats" / b.id
    bdir.mkdir(parents=True, exist_ok=True)
    still = bdir / "still.png"
    if not still.exists():
        from .spec import ImageInput
        W, H = sec.beat_res[0] // 32 * 32, sec.beat_res[1] // 32 * 32
        if b.image:
            ref = b.image
        elif b.camera.continues and i > 0:
            from .spec import BeatFrame
            ref = ImageInput(beat_frame=BeatFrame(beat=sec.beats[i - 1].id, at="last"))
        else:
            ref = ImageInput(generate=b.prompt, size=(W, H), seed=b.seed)
        ImageOps.fit(Image.open(resolve_image(project, ref, log)).convert("RGB"), (W, H), Image.LANCZOS).save(still)
    guide, info = guide_for(project, sec, i, still, bdir, log)
    return {"beat": b.id, "dir": str(bdir), "guide": str(guide.depth), "preview": str(guide.rgb), "static": str(guide.static),
            "frames": guide.frames, "fps": guide.fps, "size": list(info["size"]), "backend": info["backend"]}


def check(project, beat_id: str, section: Optional[str] = None, log: Callable = print, width: int = 768) -> dict:
    """Does the camera follow the keys, and do the people still move? Measured on the beat's generated frames and written to
    camera.json beside them: the zoom and shift error against the keyed view (camera_guide.follow_error), the people's motion
    after the camera is taken out (people_motion), and the same two numbers for the pure-camera render (the measurement's own
    floor: what a perfect camera scores)."""
    from PIL import Image
    sec, i, b = _beat(project, beat_id, section)
    bdir = project.build / sec.id / "beats" / b.id
    pngs = sorted((bdir / "frames").glob("*.png"))
    if not pngs:
        raise BuildError(f"beat '{b.id}' has no generated frames yet: build it first")
    H0 = Image.open(pngs[0]).size
    size = (width, int(round(width * H0[1] / H0[0])))
    frames = [np.asarray(Image.open(p).convert("RGB").resize(size, Image.LANCZOS)) for p in pngs]
    static_v = [m[..., 0] for m in cg.read_video(bdir / "guide_static.mp4", size)]
    ref_v = cg.read_video(bdir / "guide_rgb.mp4", size)
    people = np.asarray(Image.open(bdir / "cam_people.png").convert("L").resize(size, Image.BILINEAR)) \
        if (bdir / "cam_people.png").exists() else None
    plan = cg.plan_for(sec.beats, i)
    n = len(frames)
    static = [static_v[round(k / max(n - 1, 1) * (len(static_v) - 1))] for k in range(n)]
    out = {"beat": b.id, "backend": backend_of(b.camera), "frames": n, "size": list(size)}
    fe = cg.follow_error(frames, plan, static)
    out["camera"] = {k: v for k, v in fe.items() if k != "per_frame"}
    out["per_frame"] = [{k: (round(x, 4) if isinstance(x, float) else x) for k, x in r.items()} for r in fe["per_frame"][::max(1, n // 24)]]
    floor = cg.follow_error(ref_v, plan, static_v)
    out["floor"] = {k: v for k, v in floor.items() if k != "per_frame"}
    if people is not None:
        out["people"] = cg.people_motion(frames, people, static)
        out["people_floor"] = cg.people_motion(ref_v, people, static_v)
    (bdir / "camera.json").write_text(json.dumps(out, indent=1))
    return out
