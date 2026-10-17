# Scroll Studio engine: design

Scroll Studio is an open-source engine for scroll-driven sites. You clone it, give it inputs (a brief, images,
a 3D model, a CSV, a URL), and it builds a finished static site where scrolling plays the visuals. It runs
locally, with no API keys, and Claude can drive it through the UI's chat, Claude Code, or an MCP server.

Everything in this repo goes through the engine. The current demos (Lodestar Orbital, Atelier Sfumato,
Cellwright Bio, Meridian) become example projects that the engine rebuilds from their spec. One-off scripts
and hand-written pages are not part of the design.

---

## 1. The idea all these sites share

Every site in this realm works the same way: visuals are built ahead of time, and the scroll position plays
them back. That gives the engine two halves:

1. **Build (offline, Python, GPU).** Turn inputs into scroll-ready assets: a film, a frame sequence, image
   layers with reveal masks, a 3D scene, a depth map, a chart dataset.
2. **Play (browser, TypeScript).** One shared runtime maps scroll position to progress per section, and
   a "player" for each scene type renders that progress. Text cards scroll beside the visual.

A site is a list of **sections**. Each section has a **scene type**, its **inputs**, and its **steps** (the
copy cards that scroll past). A site can mix types: a film hero, then an artwork section, then a chart.

---

## 2. Scene types

Each scene type is one engine module: a schema, a builder (inputs → assets), and a runtime player
(assets + progress → pixels). Adding a new kind of site means adding a module, never a one-off page.

| # | Scene type | What the viewer sees | Inputs it accepts | Build | Player |
|---|---|---|---|---|---|
| 1 | `film` | A cinematic shot scrubbed by scroll (rocket launch, fly-over, product reveal) | brief text; optional blockout (`.blend`, `.glb`, or a generated preset rig), reference/brand images, keyframe images | Blender blockout + depth → Z-Image keyframes → LTX-2.3 video (segments) → upscale → short-GOP encode | `video-scrub` (H.264/AV1, seek per frame) or `frame-seq` |
| 2 | `sequence` | Apple-style object turntable / exploded view / assembly | `.glb`/`.obj`/`.step` model, or product photos (→ image-to-3D) | Blender renders a camera path or explode animation to frames (transparent PNG → WebP/AVIF) | `frame-seq` (canvas, preloaded frames) |
| 3 | `artwork` | An image drawn and painted on scroll (sketch → value → underpaint → colour) | any image (painting, illustration, photo, logo), optional focus points | Segmentation + saliency → reveal order; edge trace → SVG strokes; tonal/monochrome layers; brush-front masks | `layers-gl` (WebGL2 compositing) + `svg-draw` |
| 4 | `vector` | A logo or line illustration that draws and fills itself | SVG, or a raster logo (vectorised) | Vectorise, order paths, compute lengths | `svg-draw` |
| 5 | `parallax` | A still photo turned into a 2.5D camera move | one image (or several) | Depth Anything V2 → depth map; optional inpainted background layer | `depth-gl` (displacement / layered parallax) |
| 6 | `morph` | A → B → C transformation (before/after, renovation, product generations) | 2+ images, optional prompt | LTX keyframe interpolation or RIFE/FILM frame interpolation; or masked dissolve | `video-scrub` / `layers-gl` |
| 7 | `scene3d` | Live 3D world: zoom across scales, configurator, space, molecules | `.glb` assets and/or procedural generator presets (cells, helix, particles, terrain, orbit) | glTF optimise (Draco/Meshopt, KTX2), bake preset params, camera path | `three-scene` (three.js + postprocessing) |
| 8 | `splat` | Photoreal fly-through of a real place or object | a phone video or photo set | Gaussian-splat training (gsplat/nerfstudio), compress | `splat` (Spark / gaussian-splats-3d) |
| 9 | `chart` | Data story: charts that build, highlight and re-shape | CSV/JSON + narrative | Clean, aggregate, pre-compute states | `chart` (D3) |
| 10 | `map` | Geographic journey: fly between places, draw routes | places/GeoJSON | Fetch/clip tiles to PMTiles (offline), route geometry | `map` (MapLibre GL) |
| 11 | `type` | Kinetic typography: headlines that assemble, swap, scale with scroll | text only | none | `type` (GSAP) |
| 13 | `showroom` | The site's product, live: scroll turns, explodes and zooms the real model | `site.product` (any model format) or a model file | `engine/product.py` normalised GLB (thinned for the web), Cycles poster | `showroom` (three.js, environment light, shadow) |

**The product, declared once.** `site.product` names the model once; `engine/product.py` converts it (STEP via
OpenCascade, 3MF via trimesh), normalises it in Blender (axes, units, base at the origin, part materials, explode
offsets as node extras) into one cached GLB, and renders stills (`image: {product: <view>}`, optionally into a
generated `scene:`). Takes (`product: {}`), sequences (`model: product`) and showroom scenes all use that GLB; takes
light it from the plate (environments built from the generated frames) and grade it to the plate.

Mapping the current demos: Lodestar Orbital and Meridian = `film`; Atelier Sfumato = `artwork`;
Cellwright Bio = `scene3d` with generator presets (cells, chromatin, helix, molecule).

**Proposed v1:** `film`, `artwork`, `scene3d`, `sequence`, `parallax`, `type`, because they cover the existing
demos plus the two most-requested looks (product turntable, photo parallax). **v2:** `morph`, `vector`, `chart`,
`splat`, `map`. All dependencies for v1 and v2 are declared now (section 6) so nothing is missing later.

---

## 3. The site spec

One file describes a site. The UI edits it, Claude edits it, the CLI builds it.

```yaml
# projects/lodestar/site.yaml
site:
  name: Lodestar Orbital
  theme: { preset: night-mission, accent: "#e8742c", fonts: { display: "Sora", body: "Inter", mono: "IBM Plex Mono" } }
  brand: { logo: inputs/logo.svg, capture_url: null }    # or a URL to pull colours, fonts, logo
  nav: { links: [Mission, Services, Record], cta: "Talk to mission ops" }

sections:
  - id: launch
    type: film
    length: 9 screens                    # scroll distance
    inputs:
      brief: "A slender white two-stage rocket launches at dawn, climbs through clouds, separates, deploys a satellite."
      subject: "slender white two-stage rocket, plain white body, two thin black bands ..."
      blockout: { preset: rocket-launch }          # or file: inputs/scene.blend / inputs/scene.glb
      keyframes: auto                              # or a list of images/prompts at times
    render: { res: 1920x1088, seconds: 18, segments: 3s, upscale: none }
    hud: { kind: telemetry, fields: [altitude, velocity], events: [Lift-off, Max-Q, Stage separation] }
    steps:
      - { at: 0.00, kicker: Lodestar Orbital, title: "Every mission starts on the ground." }
      - { at: 0.30, title: "Through the weather. Past the noise." }
      - { at: 0.80, title: "Your satellite, exactly where it belongs." }

  - id: studio
    type: artwork
    inputs: { image: inputs/mona_lisa.jpg, focus: auto }          # auto = face/saliency detection
    stages: [guides, lines, value, underpaint, colour]
    steps: [...]
```

The schema is defined once (Pydantic) and exported as JSON Schema, which drives the UI forms, validation, and
the MCP tools.

---

## 4. Architecture

```
inputs ─► ingest ─► builders (per scene type) ─► asset cache ─► site compiler ─► dist/ (static site)
                         │                                        ▲
                         └─ backends: ComfyUI · Blender · ML models · FFmpeg
UI (React) ◄─► engine server (FastAPI + job queue + websocket events) ◄─► MCP server / CLI / Claude Code
```

- **Ingest** normalises inputs: images (EXIF, colour space, size), video (probe, proxy), 3D (glTF convert),
  URL capture (Playwright: brand colours, fonts, logo, copy), CSV, brief text.
- **Builders** are stage graphs with a content-addressed cache (inputs + params hash → outputs), so changing
  one step only reruns what depends on it. Long GPU stages are resumable and report progress.
- **Backends**: ComfyUI workflows are stored as JSON templates, never built in ad-hoc code. Blender runs
  headless with a library of rigs and presets. ML models load through one model registry.
- **Model manager**: one registry of every model (name, size, VRAM, licence, source). It downloads to a
  configurable model directory, verifies checksums, and checks the GPU before a job starts.
- **Site compiler** renders templates + the runtime bundle + assets into `dist/`: plain static files that
  deploy to any host (GitHub Pages, Netlify, S3). It emits poster images, mobile encodes, and reduced-motion
  fallbacks for every section.
- **Runtime** (`@scroll-studio/runtime`, TypeScript): scroll controller (Lenis + per-section progress),
  sticky stage + scrolling step cards, the players, shared HUD/caption/progress components, theme tokens,
  asset preloading by priority, and mobile and `prefers-reduced-motion` behaviour.
- **`doctor`** checks the whole stack: Python, Node, FFmpeg, Blender, CUDA/VRAM, ComfyUI, disk space, models.
- **Frozen moments** (`engine/freeze.py`, `engine/freeze_beats.py`, `engine/backends/upscale.py`). A `film` beat with
  `freeze:` is not generated: the beat stage renders one frame offline. Steps, each cached by its own digest in the
  beat's folder: the source frame (a beat's sharpest-of-last-N frame, or an image input, fitted to `beat_res`), the
  upscale (SeedVR2 on one image through ComfyUI, or Lanczos + unsharp), the depth (Depth Anything V2 through
  `backends/depth.py`, then a guided filter that snaps it to the picture and a near-edge dilation, as `parallax.py` does),
  and the render. The render is an inverse parallax warp in torch: per pixel a ray is marched through the depth map from
  near to far (the nearest surface that lands there wins, so disocclusions show the background that was there instead of
  a smear), the colour is sampled bicubic from a mip chain of the upscaled frame, the camera path is `CameraPath` (boxes
  with hold, per-leg eases or one C1 curve for `flow`) and `Timeline` adds the sway, the dolly and the focus plane that
  keeps the subject still, with the sway scaled to the room the view has. Blender was not used: a mesh displacement opens
  the same holes behind foreground edges at seconds a frame, and the warp needs no session and is deterministic. The
  stage key holds the source clip's `file_key` (so a re-rendered `walk` re-freezes) and only freeze beats have the new key
  shape. `image: {beat_frame: ...}` resolves through `resolve_image` to a frame written to `.build/_generated/bf_*.png`
  (a frozen beat is rendered first when it is not; its first and last frames are kept lossless); beats that use it carry
  the source clip in their key. Storyboard: a `freeze` card of flat crops at the camera's boxes and a flat preview clip;
  editor: `_freeze_shot` (fields per box number); plan: `film:freeze` / `film:freeze_up` units.
- **Camera moves on moving beats** (`engine/camera_guide.py`, `engine/camera_beats.py`). A generated `film` beat with
  `camera:` keys (the keys of a frozen moment's camera) gets its camera from a guide instead of from prompt words. In the
  beat's folder, each step keyed by its own digest: the start image's depth (`freeze.prepare_depth` over Depth Anything V2)
  and the moving subjects' mask (`region.find`: Florence-2 + SAM 2.1); then the guide: the camera path flown through the
  depth with `freeze.render_frames` (the public API, three times over one geometry: the depth video, the picture itself as a
  pure-camera render, and the static-world mask), the subjects' depth softened into blobs (`soften_subjects`) so the guide
  constrains the camera and the static world and leaves the people free. The shot is then generated along the guide:
  `ltx` reuses the take's machinery (`comfy.build_graph`: LTX-2.3 IC-LoRA union control, the guide as the depth video, the
  start image as the pinned first frame; the shot is generated at the largest size that fits ~22k latent tokens and scaled
  to `beat_res`), `wan` is Wan 2.2 Fun Control (`build_wan_graph` with the guide as `control_video`), `uni3c` is the Wan i2v
  graph with `WanUni3CControlnetApply` on both experts and the pure-camera render as its render video (it fails first with
  the file name, URL, folder and licence when `Wan21_Uni3C_controlnet_fp16.safetensors` is not in `model_patches`). A path is
  a `CameraPlan` (`path`, slice): alone a beat covers its own `CameraPath`; beats that `continue` one another share one
  `flow` path over the chain (rests only at its ends and holds) and each takes its slice, so position and speed carry across
  the cut, and the guide of every beat in a chain is flown through the chain's base plate (the first beat's still), not
  through the previous beat's last frame (a close-up cannot zoom out). Plans reach the renderer as one key per frame under
  linear easing, which keeps `freeze.py` untouched. Afterwards `tone_match` pulls the frames toward the plate (per-channel
  gain and offset measured on the static world against the pure-camera render, smoothed in time, plus grain to the plate's
  noise level). Measuring (`studio camera --check`, MCP `camera_check`): `track_views` registers every frame against the
  first on the static world (SIFT + RANSAC similarity), `follow_error` compares the implied view with the keyed one,
  `people_displacement` takes the camera out and reads how far the people have walked, and the same numbers for the
  pure-camera render are the measurement's floor. Measured on the Presence street (3 s, 768x448, the keys push from the
  wide frame to the girl and back): `ltx` follows the keys within 0.7-0.9% rms of view width (the floor is 0.15-0.2%),
  `wan` (Fun Control, start image pinned) lags and never completes the pull-out (22.6% rms, 43% at worst), so `auto` is
  `ltx`; `uni3c` could not be measured (its file is not installed). Stage key: a beat gets a `camera` entry only when it has `camera:`
  (every other beat keeps its cache), including the chain it belongs to. Plan: `film:camera` units.
- **Plans and storyboards.** `engine/plan.py` runs every builder in a dry run (`engine/fidelity.py` `planning()`):
  `BuildContext.stage` reports instead of running, a stage that would run marks its outputs dirty so stages keyed on
  them count too, and code that renders outside a stage (image inputs, product stills, model conversion) raises
  `WouldRender`. Estimates are seconds per unit of work per stage kind (frames, seconds of film, keyframes, beats),
  the median of the `seconds` every stamp records on this machine, with RTX 4090 defaults. `studio build` prints the
  plan first (`--plan` stops there; studio.toml `confirm_over` asks above a threshold, `--yes` doesn't); `--only`
  renders chosen sections and beats while the rest keep their cache or show their storyboard stand-in.
  `engine/storyboard/` makes a card per shot from the same stages and caches (`film.world` runs the take's `blockout`
  and `keyframes` stages; beat stills are the beats' own image inputs), previewing what only the full build needs at
  full quality (`fidelity.previewing`: product stills at a few samples, keyed apart; at `sketch` no ComfyUI and
  placeholder cards), builds the real page into `storyboard/site/` with stand-in films (`standin.py`: stills scrubbed
  by scroll, Ken Burns moves from the motion text or the take's camera at `animatic`), draws the sheet (`sheet.py`)
  and cuts `animatic.mp4` with the trailer's type layer. `locked: true` (beats, takes, scenes) makes a stage keep
  existing outputs whatever its key; the `keyframes` stage repaints only keyframes whose own digest changed.
- **The storyboard editor.** `engine/storyboard/edit/` is `studio storyboard --edit`, `/sb/<project>` in the Studio server
  and the MCP tools `storyboard_shots`, `set_shot_field`, `regenerate_shot_image`, `pick_shot_variant`, `approve_shot`.
  The spec stays the single source of truth: `shots.py` reads site.yaml into shots, image slots and their chains of
  generators (`generate`, `edit` over another image, product still, gradient, file, take keyframe), each field carrying
  the YAML path it is written to; identical steps in several chains are shared and written in every place.
  `specdoc.py` writes edits as text splices located with ruamel's composer (comments, alignment, quoting, CRLF kept;
  anchors and aliases followed), falling back to ruamel's round trip with the file's indentation and wrap width; the
  result must load back as the old data plus the edit and validate against `Site`, else nothing is written, and each
  write keeps the old text in `storyboard/history/`. `render.py` renders one image: `inputs.resolve_image` on the
  image input (so the file lands under the digest the build looks up: `inputs.generated_path` / `edit_path`) or the
  take's `keyframes` stage (a keyframe may set its own `seed`); never a video, restore or product-pass stage.
  `variants.py` keeps every render with the recipe that drew it (which is current is derived from the cache entry
  the spec describes, never stored), and picking one writes the recipe back and restores the cache entry (a
  keyframe's file and `_frames.json` digest, then `BuildContext.adopt`). `workspace.py` runs image jobs on the server's
  `JobQueue` (one per image: a lock file in the variants folder) and shares ComfyUI with other sessions without ever
  stopping or interrupting it. Approvals live in `storyboard/state.json`, outside the spec. `notes.py` is the inbox of
  plain-language notes (`storyboard/notes.json`); the page only collects them, an agent interprets them through the MCP
  tools `storyboard_notes` / `resolve_note` (or `--notes`), and `render.py` / `workspace.py` attach the edits and variants
  made while a note is `working` to it. The poll endpoint carries a `vrev` (variants, notes, approvals) next to the spec's
  revision, so a page follows changes made by another process, and shows renders another process holds a lock for. The
  Play tab serves `storyboard/animatic.mp4` (with its `animatic.timeline.json`: shot spans, the shots' signatures and
  the spec revision at the cut, which is what "stale" compares), the stand-in page and `dist/`; `Workspace.animatic()` is
  `storyboard(level="animatic", generate=False)`, where `Maker(generate=False)` shows cached images and placeholder
  cards and renders nothing.
- **Reveal and faces.** `engine/reveal.py` and `engine/faces.py` are post stages over a film's finished file, run in
  ComfyUI through custom nodes (`engine/backends/comfy_nodes/scroll_studio_nodes/`, installed by `studio setup-comfy`
  next to kijai's ComfyUI-segment-anything-2 and ComfyUI-Florence2). A `reveal` region is found on one frame (Florence-2
  phrase grounding; `choose_boxes` applies `pick`/`within` and the "X's Y" owner test; or the spec's own box/points) and
  tracked by SAM 2.1's video predictor inside its shot (`shots_of`: a beats film's beats, `reveal.cuts`, or ffmpeg scene
  detection), forwards and backwards from the seed, over a 960x540 working copy cropped like the encode; the masks are
  cached per region as `.npz`. `pack` feathers and grows them and encodes up to four per grayscale atlas video (2x2
  tiles of 960x544) with the film's fps, frame count and GOP, plus a half-size phone copy, and draws the poster and end
  frame with the reveal applied. The runtime (`players/reveal.ts`, chosen by `video.ts` when the film's config has
  `reveal`) seeks the film and the mask video to the middle of the same frame and draws only when both have landed;
  `lib/revealKeys.ts` eases the keys, and `engine/reveal.py` `amounts_at` / `composite` are its CPU twins (a test runs
  both on the same keys). The storyboard (`storyboard/reveal.py`) draws every card frame, stand-in and animatic piece
  with the same compositor. `faces` cuts a clip into overlapping chunks of frames, restores each in ComfyUI and joins
  them; the smoothing lives in `scroll_studio_nodes/faces.py`.
- **Region edits.** `engine/region.py` is what `inputs._edit` calls when an `edit:` has a `region`. `find` locates the
  region on the source: Florence-2 boxes through `reveal.find_boxes` (`pick`, `within`, the owner rule) or the spec's
  box/points, then SAM 2.1 in image mode, which is the video predictor over a one-frame batch (`SSRevealTrack` with
  `frame_index: 0`; the stock node is points-only and the custom node already takes boxes, and not needing a new node
  means a running ComfyUI never has to be restarted for it); the soft mask is cached as `region_<digest>.png` by the
  source's content and `find_spec` (everything that names the region, nothing that shapes it). `shape` thresholds,
  dilates (`grow`), blurs (`feather`, sigma = feather / 2) and inverts it to the 8-bit weight that is also saved as
  `edit_<digest>.mask.png`. `crop_box` picks the editor's input (the mask's extent plus `context` of its size on each
  side, at least `MIN_CROP` across, no more than `MAX_CROP_ASPECT` long, inside the picture): Qwen's graph rescales its
  first image to a fixed ~1.6 MP (`ImageScaleToTotalPixels`), so a crop is drawn at several times the scale of a
  whole-image pass; the result is resized back to the crop and `composite` blends it in with integer arithmetic
  (`(src * (255 - m) + edit * m + 127) // 255`, and the source itself where `m == 0`), at the source's size, which is
  why pixels outside the region are exact. `edit_path` adds `region.edit_key` to its digest only when a region is set,
  and `inputs.LATE_FIELDS` keeps an unset `region` out of `image_key`, so no existing key moves (the dry-run plan of
  `examples/feel` is the check). The editor shows the outline (`region.outline_of`: `edit_<digest>.outline.png` beside the
  image, carried with variants by `copy_sidecars`) on cards (`sheet.thumbs`) and in the workspace (`node_json` `image.region`).
- **Launch trailers** (`engine/trailer/`, `studio trailer`): a second output from the same spec and the same cache.
  `plan.py` cuts shots from what the builders already rendered (takes, beats, scroll recordings, product stills) onto
  a beat grid; `frame.py` reframes each for 16:9 and 9:16 (the take's product projected through its camera by
  `take.py --pass track`, else a saliency crop) and limits push-ins to what the source resolution allows; `type.py`
  sets captions, callouts and the end card in the theme's fonts with headless Chrome (`type.html`, drawn by
  `seek(t)`, captured as transparent frames); the result is encoded once per format and the music muxed in.

### Repository layout

```
scroll-studio/
  engine/                      Python package
    spec/                      Pydantic schema → JSON Schema
    ingest/                    images, video, 3D, URL capture, data
    scenes/<type>/             schema.py · builder.py · presets/   (one folder per scene type)
    backends/comfy/            client + workflows/*.json
    backends/blender/          headless runner, blockout_lib, rigs/
    backends/models/           registry.yaml, downloader, VRAM checks
    compile/                   site compiler, templates/, themes/
    plan.py                    dry-run build plans, estimates calibrated from stage stamps
    region.py                  `edit.region`: find a region on an image (Florence-2 + SAM 2.1), edit a crop, composite exactly
    storyboard/                cards per shot, stand-in films, sheet.jpg/storyboard.html, animatic
    storyboard/edit/           the edit workspace: specdoc (site.yaml edits), shots (fields and image chains), variants,
                               render (one image's stage), approvals, workspace + api (server, page.html)
    fidelity.py                plan and storyboard preview modes, placeholder cards
    jobs/                      stage graph, cache, events
    server/                    FastAPI app (REST + websocket) used by the UI and MCP
    cli.py                     `studio new | storyboard | build | preview | export | doctor | models`
  runtime/                     TypeScript runtime (Vite) → runtime.js
    core/ players/ components/
  ui/                          React + Vite app: the Studio
  mcp/                         MCP server so Claude can create projects, edit specs, run builds, read previews
  .claude/skills/              Claude Code skills: new-site, add-section, render, publish
  examples/                    lodestar-orbital/, meridian/, atelier-sfumato/, cellwright-bio/ (spec + inputs)
  docs/
  requirements.txt  pyproject.toml  package.json  install.ps1 / install.sh
```

---

## 5. The UI (Studio)

A local web app (`studio ui` → http://localhost:5180):

1. **Projects**: create from a template or an example, or from a URL (brand capture).
2. **Site editor**: section list (add, reorder, delete), each section's inputs (upload/drag-drop), copy steps,
   theme. Forms are generated from the JSON Schema.
3. **Build panel**: per-section stages with status, progress, logs, ETA, VRAM, cancel/resume.
4. **Review**: contact sheets for keyframes and variants (pick one), frame scrubber for films, before/after
   for upscales, the 100% crop check.
5. **Live preview**: the real site in an iframe at desktop and phone width, with a scroll-position slider.
6. **Export**: static `dist/` zip, a scroll-through recording (MP4/GIF for README or social), deploy guide.
7. **Claude panel**: chat that edits the spec and triggers builds through the same API the UI uses.

---

## 6. Required technology (declared now)

### System
| Tool | Version | Used by |
|---|---|---|
| Python | 3.11 | engine |
| Node.js | 20 LTS+ | runtime, UI, site build |
| FFmpeg | 6+ (with libx264, libsvtav1, libvpx) | encodes, probes, frame extraction |
| Blender | 4.2 LTS+ (headless) | blockouts, depth passes, turntables |
| Git + Git LFS | any | examples' inputs |
| NVIDIA GPU + driver | CUDA 12.4+; 24 GB VRAM for full-quality film, 12 GB for the lighter profile | ComfyUI, ML models |
| ComfyUI | pinned commit + custom nodes (ComfyUI-LTXVideo, KJNodes, VideoHelperSuite) | film, morph, keyframes |
| Chrome / Playwright Chromium | current | URL capture, previews, scroll recordings |
| COLMAP | 3.9+ (only for `splat`) | camera poses for splat training |

### Python (`requirements.txt`)
`torch` (CUDA build), `numpy`, `opencv-python`, `scikit-image`, `scipy`, `pillow`, `pillow-avif-plugin`,
`imageio`, `av` (PyAV), `pydantic`, `pyyaml`, `jinja2`, `fastapi`, `uvicorn`, `websockets`, `httpx`,
`huggingface_hub`, `transformers`, `accelerate`, `safetensors`, `onnxruntime-gpu`, `rembg`, `vtracer`,
`trimesh`, `pygltflib`, `cascadio` (STEP via OpenCascade), `lxml` (3MF), `playwright`, `pandas`, `soundfile`, `rich`,
`typer`, `mcp`, `pytest`.
Optional extras: `[splat]` gsplat, nerfstudio; `[audio]` audiocraft or transformers MusicGen.

### Node (`package.json`)
Runtime: `lenis`, `gsap` (ScrollTrigger), `three`, `postprocessing`, `@sparkjsdev/spark` (splats), `d3`,
`maplibre-gl`, `pmtiles`. Build/UI: `vite`, `typescript`, `react`, `react-dom`, `@gltf-transform/cli`,
`sharp`, `zod` (schema mirror), `playwright`.

### Models (downloaded by the model manager)
| Model | For | Size | Licence (check before commercial use) |
|---|---|---|---|
| LTX-2.3 22B distilled fp8 + Gemma 3 12B text encoder + IC-LoRA Union Control + spatial upscaler | `film`, `morph` | ~35 GB | LTX-2 Community Licence |
| Z-Image Turbo + Fun ControlNet Union 2.1 + Qwen3 4B encoder | keyframes, stills | ~20 GB | Apache 2.0 |
| Depth Anything V2 (Large) | `parallax`, depth from photos | 1.3 GB | CC-BY-NC (Large) / Apache (Small) |
| BiRefNet or SAM 2 | segmentation for `artwork`, `sequence`, cutouts | 0.2–0.9 GB | MIT / Apache 2.0 |
| SAM 2.1 Hiera Large + Florence-2 large | `film` `reveal`: a region's prompt -> a box -> a mask tracked through the film | 0.45 GB + 1.5 GB | Apache 2.0 / MIT |
| GFPGAN v1.4 (+ facexlib RetinaFace and ParseNet) | `faces: restore` | 0.35 GB + 0.2 GB | Apache 2.0 / MIT |
| RIFE 4.x | `morph`, frame interpolation | <0.1 GB | MIT |
| Hunyuan3D-2 or TRELLIS | image → 3D for `sequence` from photos | 5–10 GB | Tencent community (region limits) / MIT |
| Real-ESRGAN (or LTX upscaler) | stills and frame upscaling | <0.1 GB | BSD-3 |
| MusicGen (optional) | music beds for recordings | 3–13 GB | CC-BY-NC |

The open-source project itself is MIT or Apache 2.0; model licences are listed in the model registry and shown
in the UI when a model is first downloaded.

---

## 7. Build order

1. **Engine skeleton**: spec schema, job graph and cache, CLI, `doctor`, model registry.
2. **Runtime**: scroll core, step cards, `video-scrub`, `frame-seq`, `layers-gl`, `svg-draw`, `three-scene`.
3. **Port the demos into scene modules** and rebuild them from `examples/` as the acceptance test:
   `film` (from run.py + ltx_comfy.py + blockout_lib), `artwork` (from build_mona.py, with auto focus
   instead of hard-coded landmarks), `scene3d` (from bio.html, split into generator presets).
4. **UI + server**, then the **MCP server and Claude skills**.
5. New scene types: `sequence`, `parallax`, `type`, then v2.
6. Installers, docs, CI (build every example at low resolution on each change).
