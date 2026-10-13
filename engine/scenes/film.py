"""film: an AI film generated locally and scrubbed by scroll.

Stages (each cached by its own settings):
  blockout   Blender preset or the user's .blend -> beauty frames + log-depth pass
  keyframes  Z-Image Turbo + depth ControlNet -> detailed stills at chosen times
  generate   LTX-2.3 guided by the depth video + keyframes, in segments -> gen/gen.mp4; or, with
             video_model: wan, Wan 2.2 Fun Control along the same depth video -> wan/gen/gen.mp4
  upscale    optional (shot.upscale.method: ltx | seedvr2)
  restore    take.restore: SeedVR2 over the generated world, before the product composite
  encode     short-GOP H.264 for scrubbing (desktop + mobile), poster and end frames

`video:` skips generation and encodes an existing film instead (remove it to regenerate from `shot:`).
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Optional

from ..project import BuildContext, BuildError, ffmpeg, file_key, probe
from ..spec import FilmScene


def _args(ctx: BuildContext, **kw):
    o = ctx.options
    return SimpleNamespace(dry_run=False, variants=int(o.get("variants", 1)), res=o.get("res"), sampler=None,
                           seconds=None, upscale=None, only=None, segment=o.get("segment"), force=ctx.force,
                           source=None, **kw)


def _restore_args(ctx: BuildContext, source: Path):
    a = _args(ctx)
    a.source = str(source)
    return a


def _legacy_path(path: Path) -> str:
    """How take.json named the product file before keys were made portable (absolute path); tests patch this."""
    return str(path)


def take_product(sec: FilmScene, ctx: BuildContext) -> tuple[Path, Optional[Path], dict]:
    """The take product's model file (site.product's normalised GLB when the layer names no model), the raw source
    file (for keys written before site.product existed), and the layer as take.py reads it (height and res resolved)."""
    from ..inputs import resolve_path
    layer = sec.take.product
    p = layer.model_dump(mode="json")
    site_product = ctx.project.load().product
    raw = None
    if layer.model:
        path = raw = resolve_path(ctx.project, layer.model, ctx.log)
    elif layer.from_photo:
        from ..backends.trellis import image_to_mesh
        photo = resolve_path(ctx.project, layer.from_photo, ctx.log)
        path = image_to_mesh(photo, ctx.work / "trellis", ctx.log)
    elif site_product is not None:
        from ..product import normalised_glb
        path = normalised_glb(ctx.project, log=ctx.log)
        if site_product.model:
            raw = resolve_path(ctx.project, site_product.model, ctx.log)
    else:
        raise BuildError(f"film section '{sec.id}': take.product needs `model` or `from_photo`, or a site `product:`")
    from ..product import take_height
    p["height"] = take_height(ctx.project, layer)
    if not p.get("res"):
        p["res"] = [2560, 1440] if sec.take.upscale else [1920, 1080]
    return path, raw, p


def take_shot(sec: FilmScene, ctx: BuildContext) -> dict:
    """Turn a spec `take` into the `shot` mapping the film stages run on, writing take.json for Blender.

    Keys are portable: the world (blockout, keyframes, LTX) is keyed without the product unless the product is in
    the depth guide, and never by an absolute path, so a moved project or a new product keeps its generated world.
    `legacy_world_key` is the key of the older formula, so stamps written by it still count."""
    import json
    t = sec.take.model_dump(mode="json", exclude={"locked"})   # locking never changes what is rendered
    legacy = None
    if sec.take.product:
        path, raw, p = take_product(sec, ctx)
        t["product"] = p
        t["product_file"] = str(path)
        pw, ph = p["res"]
        bw, bh = t["preview_res"]
        if abs(pw / ph - bw / bh) > 0.01:
            raise BuildError(f"take.product.res {pw}x{ph} and take.preview_res {bw}x{bh} must have the same aspect ratio")
        layer = sec.take.product
        old = {k: v for k, v in layer.model_dump(mode="json").items()
               if k in ("model", "from_photo", "credit", "at", "height", "rotation", "spin", "hdri", "sun_strength",
                        "samples", "shadow", "shadow_size", "res")}
        site_product = ctx.project.load().product
        if not old["model"] and not old["from_photo"] and site_product is not None:
            old["model"] = site_product.model
            old["credit"] = old["credit"] or site_product.credit
        old["height"] = old["height"] if old["height"] is not None else 1.0
        old["hdri"] = old["hdri"] or "sunrise"
        old["samples"] = old["samples"] if "samples" in layer.model_fields_set else 32
        old["res"] = old["res"] or [1920, 1080]
        src = raw or path
        lw = {**{k: v for k, v in t.items() if k not in ("ltx", "keyframes", "upscale", "product", "product_file", "restore", "video_model", "wan")},
              "product": old, "product_file": _legacy_path(src)}
        legacy = {"world_key": lw, "model": file_key(src)}
    ctx.work.mkdir(parents=True, exist_ok=True)
    (ctx.work / "take.json").write_text(json.dumps(t, indent=1), encoding="utf-8")
    world = {k: v for k, v in t.items() if k not in ("ltx", "keyframes", "upscale", "product", "product_file", "restore", "video_model", "wan")}
    if sec.take.product and sec.take.product_in_guide:
        world["product"] = {k: t["product"][k] for k in ("at", "height", "rotation", "spin")}
        world["product_model"] = file_key(Path(t["product_file"]))
    shot = {"fps": t["fps"], "duration": t["duration"], "preview_res": t["preview_res"], "ltx": t["ltx"],
            "blockout": {"world": str(ctx.work / "take.json")}, "world_key": world, "legacy_world_key": legacy}
    if t.get("video_model"):
        shot["video_model"] = t["video_model"]
    if sec.take.wan:   # only what the take sets, so the site's `wan:` fills the rest
        shot["wan"] = sec.take.wan.model_dump(mode="json", exclude_unset=True)
    if t.get("keyframes"):
        shot["keyframes"] = t["keyframes"]
    if t.get("upscale"):
        shot["upscale"] = t["upscale"]
    return shot


def world(sec: FilmScene, ctx: BuildContext, keyframes_too: bool = True) -> tuple[dict, dict, Optional[dict]]:
    """The world stages of a take or shot, as the full build runs them: `blockout` (Blender: the grey world, the
    camera and its depth guide) and `keyframes` (Z-Image stills on that depth). Returns (shot, blockout key, legacy
    key). The storyboard calls this too, so an approved keyframe is the one the film is generated from."""
    from . import film_build as fb
    shot, bkey, legacy = blockout_key(sec, ctx)
    bdir = ctx.work / "blockout"
    ctx.stage("blockout", bkey, [bdir / "depth.mp4", bdir / "first.png"], lambda: fb.stage_blockout(shot, str(ctx.work)),
              legacy=legacy)
    if keyframes_too and shot.get("keyframes", {}).get("frames"):
        keyframes(shot, bkey, legacy, ctx)
    return shot, bkey, legacy


def blockout_key(sec: FilmScene, ctx: BuildContext) -> tuple[dict, dict, Optional[dict]]:
    """(shot, blockout key, legacy key) without running anything (the storyboard's sketch reads the cache with it)."""
    shot = dict(take_shot(sec, ctx) if sec.take else sec.shot, id=sec.id)
    for k in ("fps", "duration", "preview_res", "ltx"):
        if k not in shot:
            raise BuildError(f"film section '{sec.id}': shot.{k} is required to generate a film (or set `video:`)")
    bl = dict(shot.get("blockout", {}))
    if bl.get("file"):
        bl["file"] = str(ctx.project.path(bl["file"]))
        shot["blockout"] = bl
    legacy = None
    if sec.take:
        bkey = {"take": shot["world_key"], "fps": shot["fps"], "duration": shot["duration"], "res": shot["preview_res"]}
        lw = shot.get("legacy_world_key")
        legacy = {"blockout": {"world_key": (lw or {}).get("world_key", shot["world_key"])}, "fps": shot["fps"],
                  "duration": shot["duration"], "res": shot["preview_res"], "file": None,
                  "model": lw["model"] if lw else None}
    else:
        bkey = {"blockout": {k: v for k, v in bl.items() if k != "world"}, "fps": shot["fps"], "duration": shot["duration"],
                "res": shot["preview_res"], "file": file_key(Path(bl["file"])) if bl.get("file") else None, "model": None}
    return shot, bkey, legacy


def generate(sec: FilmScene, ctx: BuildContext) -> Path:
    from . import film_build as fb
    shot, bkey, legacy = world(sec, ctx)
    out = str(ctx.work)
    gkey = {"b": bkey, "k": shot.get("keyframes"), "ltx": shot["ltx"], "subject": shot.get("subject")}
    glegacy = legacy and {"b": legacy, "k": shot.get("keyframes"), "ltx": shot["ltx"], "subject": shot.get("subject")}
    from ..animate import video_model, wan_settings
    model = video_model(shot.get("video_model"), ctx.options.get("site_video_model"))
    # Wan's renders live under wan/ with their own stage names, so switching models back and forth never
    # throws away the other model's cached film (and LTX keys are unchanged).
    sfx, mout = ("", out) if model == "ltx" else ("_wan", str(ctx.work / "wan"))
    gdir = Path(mout) / "gen"
    if model == "wan":
        shot["wan"] = wan_settings(ctx.options.get("site_wan"), shot.get("wan"))
        gkey = dict(gkey, video_model=model, wan=shot["wan"])
        ctx.stage("generate_wan", gkey, [gdir / "gen.mp4"],
                  lambda: fb.stage_generate_wan(shot, out, mout, _args(ctx), ctx.log))
    else:
        ctx.stage("generate", gkey, [gdir / "gen.mp4"], lambda: fb.stage_generate(shot, out, _args(ctx)),
                  legacy=glegacy)
    film = gdir / "gen.mp4"
    up = shot.get("upscale")
    if up and up.get("method") in ("ltx", "seedvr2"):
        dst = gdir / ("gen_sr.mp4" if up["method"] == "seedvr2" else "gen_up.mp4")
        ctx.stage("upscale" + sfx, {"g": gkey, "u": up}, [dst], lambda: fb.stage_upscale(shot, mout, _args(ctx)),
                  legacy=(glegacy and not sfx) and {"g": glegacy, "u": up})
        film = dst
    if sec.take and sec.take.restore:
        film = restore_take(sec, ctx, shot, film, up)
    if sec.take and sec.take.product:
        film = product_layer(sec, ctx, shot, film)
    return film


def keyframe_digests(shot: dict, bkey: dict, variants: int = 1) -> dict[str, str]:
    """One digest per keyframe: the world it is painted over, the shared settings (model, res, seed...) and its own
    entry. The stage key covers every keyframe; these let a re-run redo only the keyframes that changed."""
    import hashlib
    import json
    common = {k: v for k, v in shot["keyframes"].items() if k != "frames"}
    return {f["name"]: hashlib.sha1(json.dumps({"b": bkey, "c": common, "f": f, "v": variants}, sort_keys=True,
                                               default=str).encode()).hexdigest()[:16]
            for f in shot["keyframes"]["frames"]}


def keyframes(shot: dict, bkey: dict, legacy: Optional[dict], ctx: BuildContext) -> list[Path]:
    """Stage `keyframes`: Z-Image stills locked to the blockout's depth. When it re-runs, keyframes whose own digest
    (keyframe_digests) is unchanged and whose PNG exists are kept, so editing one keyframe's prompt repaints only it."""
    import json
    from . import film_build as fb
    kdir = ctx.work / "keyframes"
    names = [f["name"] for f in shot["keyframes"]["frames"]]
    outs = [kdir / f"{n}.png" for n in names]
    args = _args(ctx)
    digests = keyframe_digests(shot, bkey, args.variants)
    record = kdir / "_frames.json"

    def run():
        old = json.loads(record.read_text()) if record.exists() and not ctx.force else {}
        keep = {n for n in names if old.get(n) == digests[n] and (kdir / f"{n}.png").exists()}
        if keep:
            ctx.log(f"  keyframes: kept {', '.join(sorted(keep))} (unchanged)")
        a = _args(ctx, skip=keep)
        fb.stage_keyframes(shot, str(ctx.work), a)
        record.write_text(json.dumps(digests, indent=1))
    key, lkey = {"b": bkey, "k": shot["keyframes"]}, legacy and {"b": legacy, "k": shot["keyframes"]}
    state = ctx.status("keyframes", key, outs, lkey)
    ctx.stage("keyframes", key, outs, run, legacy=lkey)
    if state in ("fresh", "migrated") and not record.exists() and ctx.options.get("plan") is None:
        record.write_text(json.dumps(digests, indent=1))   # a cache from before per-keyframe digests: adopt it
    return outs


def restore_take(sec: FilmScene, ctx: BuildContext, shot: dict, film: Path, up: Optional[dict]) -> Path:
    """take.restore: SeedVR2 over the generated world (as beat_restore does for beats), before the product composite,
    so the real product is never touched by restoration. Skipped when the take already upscales with SeedVR2."""
    from . import film_build as fb
    if up and up.get("method") == "seedvr2":
        ctx.log("  restore: skipped, take.upscale already runs SeedVR2")
        return film
    restored = ctx.work / "gen" / "gen_sr.mp4"
    rshot = {"id": sec.id, "fps": shot["fps"], "duration": shot["duration"], "ltx": {},
             "upscale": {"method": "seedvr2", "resolution": int(sec.take.restore), **ctx.options.get("restore", {})}}
    ctx.stage("restore", {"src": file_key(film), "res": sec.take.restore}, [restored],
              lambda: fb.stage_upscale(rshot, str(ctx.work), _restore_args(ctx, film)))
    return restored


def _take_json(ctx: BuildContext) -> dict:
    import json
    return json.loads((ctx.work / "take.json").read_text(encoding="utf-8"))


def json_product_file(ctx: BuildContext) -> str:
    return _take_json(ctx)["product_file"]


def _model_key(path: Path) -> dict:
    """The product model in a cache key: a normalised GLB is named by the digest of what made it, so its name and size
    identify it on any machine (no mtime, which would re-render a product pass after a fresh checkout or copy)."""
    if path.parent.name == "_product":
        return {"glb": path.name, "size": path.stat().st_size}
    return file_key(path)


def _product_keys(ctx: BuildContext) -> dict:
    """What the product pass depends on: the camera and world timing, the product layer and model, and take.py."""
    from ..product import _sha
    from . import film_build as fb
    t = _take_json(ctx)
    return {"camera": {k: t.get(k) for k in ("camera", "lens", "fps", "duration", "light")},
            "product": t["product"], "model": _model_key(Path(t["product_file"])),
            "script": _sha(Path(fb.SCRIPTS) / "take.py")}


def track(sec: FilmScene, ctx: BuildContext) -> Path:
    """product/track.json: per frame, the camera and where the product is on screen (stage `track`, seconds)."""
    from . import film_build as fb
    out = ctx.work / "product" / "track.json"
    ctx.stage("track", {"p": _product_keys(ctx)}, [out],
              lambda: fb.stage_track(str(ctx.work), _take_json(ctx)["product"]["res"]))
    return out


def product_layer(sec: FilmScene, ctx: BuildContext, shot: dict, film: Path) -> Path:
    """The real product, rendered through the identical camera, lit by the plate and graded to it, over the world."""
    from . import film_build as fb
    p = _take_json(ctx)["product"]
    pdir = ctx.work / "product"
    n = int(round(shot["fps"] * shot["duration"]))
    base = _product_keys(ctx)
    trk = track(sec, ctx)
    env = None
    if not p.get("hdri"):        # plate-matched light: environments built from the generated frames themselves
        env = pdir / "env" / "env.json"
        ctx.stage("plate_env", {"p": base, "film": file_key(film), "v": fb.PLATE_ENV_VERSION}, [env],
                  lambda: fb.stage_plate_env(film, trk, env, shot["fps"], ctx.log))
    pkey = {"p": base, "env": file_key(env) if env else None}
    ctx.stage("product", pkey, [pdir / "frames" / f"{n:04d}.png"],
              lambda: fb.stage_product(shot, str(ctx.work), p["res"], p["samples"], ctx, env=env))
    comp = ctx.work / "gen" / "take.mp4"
    ckey = {"film": file_key(film), "p": pkey, "grade": p.get("grade", True), "grain": p.get("grain"),
            "v": fb.COMPOSITE_VERSION}
    ctx.stage("composite", ckey, [comp], lambda: fb.stage_composite(film, pdir, comp, shot["fps"], p["res"],
                                                                     grade=p.get("grade", True), grain=p.get("grain"),
                                                                     track=trk, log=ctx.log))
    return comp


def encode(src: Path, ctx: BuildContext, gop: int) -> dict:
    web = ctx.web
    common = ["-an", "-c:v", "libx264", "-preset", "slow", "-pix_fmt", "yuv420p", "-g", str(gop), "-keyint_min", str(gop),
              "-sc_threshold", "0", "-movflags", "+faststart"]
    crop169 = "crop='min(iw,ih*16/9)':'min(ih,iw*9/16)',"

    def run():
        h = int(probe(src).get("height") or 0)
        desk_w, crf = (2560, 19) if h >= 1440 else (1920, 20)
        mob_w = 1280 if h >= 1080 else 960
        ffmpeg("-i", src, "-vf", f"{crop169}scale={desk_w}:-2:flags=lanczos", *common, "-crf", str(crf), web / "film.mp4", log=ctx.log)
        ffmpeg("-i", src, "-vf", f"{crop169}scale={mob_w}:-2:flags=lanczos", *common, "-crf", "24", web / "film-mobile.mp4", log=ctx.log)
        ffmpeg("-i", src, "-vf", f"{crop169}scale={desk_w}:-2", "-frames:v", "1", "-q:v", "2", web / "poster.jpg")
        ffmpeg("-sseof", "-0.1", "-i", src, "-vf", f"{crop169}scale={desk_w}:-2", "-frames:v", "1", "-q:v", "2", "-update", "1", web / "end.jpg")
    outs = [web / n for n in ("film.mp4", "film-mobile.mp4", "poster.jpg", "end.jpg")]
    ctx.stage("encode", {"src": file_key(src), "gop": gop}, outs, run)
    return {"video": ctx.url(outs[0]), "videoMobile": ctx.url(outs[1]), "poster": ctx.url(outs[2]), "end": ctx.url(outs[3])}


def beats_film(sec: FilmScene, ctx: BuildContext) -> Path:
    """A story in shots: each beat's still (generated, or a file) animated by the video model (LTX-2.3 or Wan 2.2,
    `video_model`), cached per beat, then joined with crossfades. Steps pinned with state: {beat: <id>} are timed to their beat."""
    import shutil
    from PIL import Image, ImageOps
    from ..animate import FPS, animate, video_model, wan_settings
    from ..inputs import resolve_image
    from ..spec import ImageInput
    W, H = sec.beat_res[0] // 32 * 32, sec.beat_res[1] // 32 * 32
    clips, standing = [], []
    only = ctx.options.get("only_beats")      # build --only: the beats to render (None: all)
    for b in sec.beats:
        bdir = ctx.work / "beats" / b.id
        clip = bdir / "clip.mp4"

        def run(b=b, bdir=bdir, clip=clip):
            bdir.mkdir(parents=True, exist_ok=True)
            ref = b.image if b.image else ImageInput(generate=b.prompt, size=(W, H), seed=b.seed)
            src = resolve_image(ctx.project, ref, ctx.log)
            still = bdir / "still.png"
            ImageOps.fit(Image.open(src).convert("RGB"), (W, H), Image.LANCZOS).save(still)
            end = None
            if b.end_image:
                end = bdir / "end.png"
                ImageOps.fit(Image.open(resolve_image(ctx.project, b.end_image, ctx.log)).convert("RGB"), (W, H),
                             Image.LANCZOS).save(end)
            import json
            akey = json.dumps({k: v for k, v in key.items() if k != "trim"}, sort_keys=True)
            stamp = bdir / "anim.json"
            frames = sorted((bdir / "frames").glob("*.png"))
            if not (frames and stamp.exists() and stamp.read_text() == akey):
                frames = animate(still, b.prompt, b.motion, b.seconds, b.seed if b.motion_seed is None else b.motion_seed,
                                 bdir, ctx.log, size=(W, H), strength=b.strength, end_image=end, model=model, wan=wan)
                stamp.write_text(akey)
            frames = frames[round(b.trim * FPS):]
            seq = bdir / "seq"
            if seq.exists():
                shutil.rmtree(seq)
            seq.mkdir()
            for i, f in enumerate(frames):
                shutil.copy(f, seq / f"{i:04d}.png")
            ffmpeg("-framerate", str(FPS), "-i", seq / "%04d.png", "-c:v", "libx264", "-crf", "13", "-preset", "slow",
                   "-pix_fmt", "yuv420p", clip, log=ctx.log)
        def ref_key(r):
            if r is None or (isinstance(r, str) and r.startswith("http")):
                return r
            if isinstance(r, str):
                return file_key(ctx.project.path(r))
            from ..inputs import stable_dump
            return stable_dump(r)
        key = {"prompt": b.prompt, "motion": b.motion, "seconds": b.seconds, "seed": b.seed, "res": [W, H],
               "image": ref_key(b.image)}
        model = video_model(b.video_model, ctx.options.get("site_video_model"))
        wan = wan_settings(ctx.options.get("site_wan")) if model == "wan" else None
        if model != "ltx":   # only when not the default, so LTX beats rendered before video_model existed stay cached
            key["video_model"] = model
            key["wan"] = {k: v for k, v in wan.items() if k != "seed"}
        if b.end_image:
            key["end_image"] = ref_key(b.end_image)
        # only when set, so beats rendered before these existed stay cached
        if b.strength != 1.0:
            key["strength"] = b.strength
        if b.motion_seed is not None:
            key["motion_seed"] = b.motion_seed
        if b.trim:
            key["trim"] = b.trim
        ctx.log(f"  beat {b.id}")
        lock = b.locked or ctx.locked
        if only is not None and b.id not in only and ctx.status(f"beat_{b.id}", key, [clip], locked=lock) == "stale":
            # not selected and not rendered yet: its storyboard still stands in (never stamped as the beat)
            from ..fidelity import would_render
            would_render("stand-in", f"beat {b.id} (its storyboard still, until it is rendered)")
            from ..storyboard.standin import beat_clip
            ctx.log(f"  beat_{b.id}: not in --only and not rendered: its storyboard still stands in")
            clips.append(beat_clip(ctx.project, sec, b, bdir / "standin.mp4", (W, H), ctx.log))
            standing.append(b.id)
            continue
        ctx.stage(f"beat_{b.id}", key, [clip], run, locked=lock)
        clips.append(clip)

    # join: each clip crossfades into the next
    durs = [float(probe(c)["duration"]) for c in clips]
    fade = min(sec.beat_fade, *(d / 3 for d in durs)) if len(clips) > 1 else 0
    out = ctx.work / "gen" / "beats.mp4"

    def join():
        out.parent.mkdir(parents=True, exist_ok=True)
        if len(clips) == 1:
            shutil.copy(clips[0], out)
            return
        args, graph, last, t = [], [], "[0:v]", 0.0
        for c in clips:
            args += ["-i", c]
        for i in range(1, len(clips)):
            t += durs[i - 1] - fade
            tag = f"[v{i}]"
            graph.append(f"{last}[{i}:v]xfade=transition=fade:duration={fade:.3f}:offset={t:.3f}{tag}")
            last = tag
        ffmpeg(*args, "-filter_complex", ";".join(graph), "-map", last, "-c:v", "libx264", "-crf", "14", "-preset", "slow",
               "-pix_fmt", "yuv420p", "-r", str(FPS), out, log=ctx.log)
    ctx.stage("beats_join", {"clips": [file_key(c) for c in clips], "fade": fade}, [out], join)
    if sec.beat_restore and standing:
        ctx.log(f"  beats_restore: skipped while {', '.join(standing)} stand in; a full build restores the film")
    elif sec.beat_restore:
        from . import film_build as fb
        shot = {"id": sec.id, "fps": FPS, "duration": float(probe(out)["duration"]), "ltx": {},
                "upscale": {"method": "seedvr2", "resolution": int(sec.beat_restore)}}
        restored = ctx.work / "gen" / "gen_sr.mp4"
        ctx.stage("beats_restore", {"src": file_key(out), "res": sec.beat_restore}, [restored],
                  lambda: fb.stage_upscale(shot, str(ctx.work), _restore_args(ctx, out)))
        out = restored

    pin_steps(sec, durs, fade)
    return out


def pin_steps(sec: FilmScene, durs: list[float], fade: float) -> None:
    """Time steps pinned with state: {beat: id} to their beat's span over the joined film (sets step.at)."""
    total = sum(durs) - fade * (len(durs) - 1)
    spans, t = {}, 0.0
    for b, d in zip(sec.beats, durs):
        spans[b.id] = (t / total, (t + d) / total)
        t += d - fade
    for st in sec.steps:
        pin = (st.state or {}).get("beat")
        if pin is None or st.at is not None:
            continue
        if pin not in spans:
            raise BuildError(f"film section '{sec.id}': step '{st.title}' is pinned to beat {pin}, which is not in beats")
        a, b2 = spans[pin]
        part = (st.state or {}).get("part")
        if part:
            a, b2 = a + (b2 - a) * float(part[0]), a + (b2 - a) * float(part[1])
        pad = (b2 - a) * 0.1
        st.at = (round(a + pad, 4), round(b2 - pad * 0.6, 4))


def build(sec: FilmScene, ctx: BuildContext, theme: dict) -> dict:
    src = ctx.project.path(sec.video) if sec.video else beats_film(sec, ctx) if sec.beats else generate(sec, ctx)
    if not src.exists():
        raise BuildError(f"film source not found: {src}")
    cfg = encode(src, ctx, sec.gop)
    if sec.take and sec.take.product and sec.take.product.credit:   # site.product's own credit is added site-wide
        cfg["credits"] = [sec.take.product.credit]
    return cfg
