"""film: an AI film generated locally and scrubbed by scroll.

Stages (each cached by its own settings):
  blockout   Blender preset or the user's .blend -> beauty frames + log-depth pass
  keyframes  Z-Image Turbo + depth ControlNet -> detailed stills at chosen times
  generate   LTX-2.3 guided by the depth video + keyframes, in segments -> gen/gen.mp4
  upscale    optional (shot.upscale.method: ltx | seedvr2)
  encode     short-GOP H.264 for scrubbing (desktop + mobile), poster and end frames

`video:` skips generation and encodes an existing film instead (remove it to regenerate from `shot:`).
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from ..project import BuildContext, BuildError, ffmpeg, file_key, probe
from ..spec import FilmScene


def _args(ctx: BuildContext, **kw):
    o = ctx.options
    return SimpleNamespace(dry_run=False, variants=int(o.get("variants", 1)), res=o.get("res"), sampler=None,
                           seconds=None, upscale=None, only=None, segment=o.get("segment"), force=ctx.force,
                           source=None, **kw)


def take_shot(sec: FilmScene, ctx: BuildContext) -> dict:
    """Turn a spec `take` into the `shot` mapping the film stages run on, writing take.json for Blender."""
    import json
    from ..inputs import resolve_path
    t = sec.take.model_dump(mode="json")
    p = t.get("product")
    if p:
        if p.get("model"):
            t["product_file"] = str(resolve_path(ctx.project, p["model"], ctx.log))
        elif p.get("from_photo"):
            from ..backends.trellis import image_to_mesh
            photo = resolve_path(ctx.project, p["from_photo"], ctx.log)
            t["product_file"] = str(image_to_mesh(photo, ctx.work / "trellis", ctx.log))
        else:
            raise BuildError(f"film section '{sec.id}': take.product needs `model` or `from_photo`")
        pw, ph = p["res"]
        bw, bh = t["preview_res"]
        if abs(pw / ph - bw / bh) > 0.01:
            raise BuildError(f"take.product.res {pw}x{ph} and take.preview_res {bw}x{bh} must have the same aspect ratio")
    ctx.work.mkdir(parents=True, exist_ok=True)
    (ctx.work / "take.json").write_text(json.dumps(t, indent=1), encoding="utf-8")
    shot = {"fps": t["fps"], "duration": t["duration"], "preview_res": t["preview_res"], "ltx": t["ltx"],
            "blockout": {"world": str(ctx.work / "take.json"), "world_key": {k: v for k, v in t.items() if k not in ("ltx", "keyframes", "upscale")}}}
    if t.get("keyframes"):
        shot["keyframes"] = t["keyframes"]
    if t.get("upscale"):
        shot["upscale"] = t["upscale"]
    return shot


def generate(sec: FilmScene, ctx: BuildContext) -> Path:
    from . import film_build as fb
    shot = dict(take_shot(sec, ctx) if sec.take else sec.shot, id=sec.id)
    for k in ("fps", "duration", "preview_res", "ltx"):
        if k not in shot:
            raise BuildError(f"film section '{sec.id}': shot.{k} is required to generate a film (or set `video:`)")
    out = str(ctx.work)
    bl = dict(shot.get("blockout", {}))
    if bl.get("file"):
        bl["file"] = str(ctx.project.path(bl["file"]))
        shot["blockout"] = bl
    bdir, gdir = ctx.work / "blockout", ctx.work / "gen"
    bkey = {"blockout": {k: v for k, v in bl.items() if k != "world"}, "fps": shot["fps"], "duration": shot["duration"],
            "res": shot["preview_res"], "file": file_key(Path(bl["file"])) if bl.get("file") else None,
            "model": file_key(Path(json_product_file(ctx))) if bl.get("world") and sec.take.product else None}
    ctx.stage("blockout", bkey, [bdir / "depth.mp4", bdir / "first.png"], lambda: fb.stage_blockout(shot, out))
    if shot.get("keyframes", {}).get("frames"):
        names = [f["name"] for f in shot["keyframes"]["frames"]]
        ctx.stage("keyframes", {"b": bkey, "k": shot["keyframes"]}, [ctx.work / "keyframes" / f"{n}.png" for n in names],
                  lambda: fb.stage_keyframes(shot, out, _args(ctx)))
    gkey = {"b": bkey, "k": shot.get("keyframes"), "ltx": shot["ltx"], "subject": shot.get("subject")}
    ctx.stage("generate", gkey, [gdir / "gen.mp4"], lambda: fb.stage_generate(shot, out, _args(ctx)))
    film = gdir / "gen.mp4"
    up = shot.get("upscale")
    if up and up.get("method") in ("ltx", "seedvr2"):
        dst = gdir / ("gen_sr.mp4" if up["method"] == "seedvr2" else "gen_up.mp4")
        ctx.stage("upscale", {"g": gkey, "u": up}, [dst], lambda: fb.stage_upscale(shot, out, _args(ctx)))
        film = dst
    if sec.take and sec.take.product:
        # The real product, rendered through the identical camera, over the generated world.
        p = sec.take.product
        pdir = ctx.work / "product"
        n = int(round(shot["fps"] * shot["duration"]))
        # world_key carries the camera, duration, fps and product placement; the model file adds its content
        pkey = {"world": shot["blockout"]["world_key"], "model": file_key(Path(json_product_file(ctx)))}
        ctx.stage("product", pkey, [pdir / "frames" / f"{n:04d}.png"], lambda: fb.stage_product(shot, out, p.res, p.samples, ctx))
        comp = gdir / "take.mp4"
        ctx.stage("composite", {"film": file_key(film), "p": pkey}, [comp], lambda: fb.stage_composite(film, pdir, comp, shot["fps"], p.res))
        film = comp
    return film


def json_product_file(ctx: BuildContext) -> str:
    import json
    return json.loads((ctx.work / "take.json").read_text(encoding="utf-8"))["product_file"]


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
    """A story in shots: each beat's still (generated, or a file) animated by LTX-2.3, cached per beat, then joined
    with crossfades. Steps pinned with state: {beat: <id>} are timed to their beat."""
    import shutil
    from PIL import Image, ImageOps
    from ..animate import FPS, animate
    from ..inputs import resolve_image
    from ..spec import ImageInput
    W, H = sec.beat_res[0] // 32 * 32, sec.beat_res[1] // 32 * 32
    clips = []
    for b in sec.beats:
        bdir = ctx.work / "beats" / b.id
        clip = bdir / "clip.mp4"

        def run(b=b, bdir=bdir, clip=clip):
            bdir.mkdir(parents=True, exist_ok=True)
            ref = b.image if b.image else ImageInput(generate=b.prompt, size=(W, H), seed=b.seed)
            src = resolve_image(ctx.project, ref, ctx.log)
            still = bdir / "still.png"
            ImageOps.fit(Image.open(src).convert("RGB"), (W, H), Image.LANCZOS).save(still)
            frames = animate(still, b.prompt, b.motion, b.seconds, b.seed, bdir, ctx.log, size=(W, H))
            seq = bdir / "seq"
            if seq.exists():
                shutil.rmtree(seq)
            seq.mkdir()
            for i, f in enumerate(frames):
                shutil.copy(f, seq / f"{i:04d}.png")
            ffmpeg("-framerate", str(FPS), "-i", seq / "%04d.png", "-c:v", "libx264", "-crf", "13", "-preset", "slow",
                   "-pix_fmt", "yuv420p", clip, log=ctx.log)
        key = {"prompt": b.prompt, "motion": b.motion, "seconds": b.seconds, "seed": b.seed, "res": [W, H],
               "image": file_key(ctx.project.path(b.image)) if b.image and not b.image.startswith("http") else b.image}
        ctx.log(f"  beat {b.id}")
        ctx.stage(f"beat_{b.id}", key, [clip], run)
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

    # beat spans over the film, for steps pinned with state: {beat: id}
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
        pad = (b2 - a) * 0.1
        st.at = (round(a + pad, 4), round(b2 - pad * 0.6, 4))
    return out


def build(sec: FilmScene, ctx: BuildContext, theme: dict) -> dict:
    src = ctx.project.path(sec.video) if sec.video else beats_film(sec, ctx) if sec.beats else generate(sec, ctx)
    if not src.exists():
        raise BuildError(f"film source not found: {src}")
    return encode(src, ctx, sec.gop)
