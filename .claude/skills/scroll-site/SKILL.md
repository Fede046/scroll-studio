---
name: scroll-site
description: Build a scroll-driven website with the Scroll Studio engine from a brief, images, a 3D model, a film idea or nothing at all. Use when the user asks for a scroll site, landing page with scroll animation, product scroll, "Apple-style" page, artwork reveal, 3D zoom page, photo parallax page, or kinetic type page.
---

# Build a scroll site with Scroll Studio

Everything goes through the engine: write a `site.yaml`, build, look at snapshots, iterate. Never hand-write HTML.
Use the MCP tools (`scroll-studio` server) when available, otherwise the `studio` CLI (`python -m engine.cli ...`).

## 1. Pick the scene types from the subject
| The subject is... | Scene type | Inputs |
|---|---|---|
| a journey, launch, flight, place reveal (cinematic) | `film` | brief + Blender preset/.blend, or an existing video in `video:` |
| a painting, illustration, portrait, building photo, logo | `artwork` | any image (`file:` or `generate:`) |
| science, scale, space, data, networks | `scene3d` | presets: cell-field, cell, nucleus, helix · galaxy, star-system, planet · network, lattice, particles · gltf |
| a physical product with parts | `sequence` | a .glb/.obj/.fbx/.stl (file or https URL) |
| a place: hotel, home, landscape, venue | `parallax` | one photo per step (`file:` or `generate:`) |
| a manifesto, event, agency, statement | `type` | text only |
| a physical product the client owns, in a cinematic world | `film` + `take:` | the product's .glb (or a photo with TRELLIS) + rough world shapes and camera keys |
| a real place: house, venue, shop (scanned) | `splat` | a Gaussian-splat scan (.ply or gsplat .pt) + camera keys |
| a data story with figures that must be right | `chart` + `callouts`, `stats` with `data:` | a CSV (file or URL) |

Mix them: a `film` hero, then `features`/`stats`, then an `artwork` section, then a `cta`.

**Time stops: freeze, don't generate.** A video model cannot hold a crowd still while the camera moves, and an image
editor redraws the faces every time. For "time stops, the camera visits close-ups of the same people", make that beat a
frozen moment in a `film` with `beats:`: `freeze: { from: <beat id> | image: <any image input>, upscale: 2, camera: [{ t,
box: [x0, y0, x1, y1] (0-1 of the frozen frame), hold? }...], parallax: 0.6, ease: inOutSine | flow, grain: 0.012 }`. It
is rendered offline in seconds (one upscaled frame + a depth parallax camera), so the faces never change, and it joins the
film like any beat. `from` takes the sharpest of that beat's last frames (`pick: sharpest`; `pick: last` for the very
last). The next generated beat starts where it ends with `image: { beat_frame: { beat: <freeze id>, at: last } }`. In the
storyboard, a `freeze` card shows flat crops at each camera box (the framing to approve before anything renders). Keep
`parallax` 0.3-0.8 (above 1 stretches behind edges) and boxes near the aspect of `beat_res`. Look at the close-ups after
the SeedVR2 upscale: it redraws detail, and a hand or a logo may come out different from the source.

## 2. Write the spec
- Start from the closest example: `list_projects`, then `create_project(name, example=...)`, then edit with `get_spec`/`set_spec`.
- `spec_schema('<type>')` gives every field with descriptions. Pick a theme preset that fits the domain
  (night, brass, paper, lab, cosmos, studio, dusk, ink, blueprint) and override colours only if the brand needs it.
- An experience in one word: `theme: { style: <name> }` changes how the site scrolls and reads (split-flap board,
  comic pages, terminal session, game level, anime opening, ... the table in README.md). Pick by the brand's
  character, offer two or three, and show them with `studio looks <project> --styles a,b,c`.
- Brand: `studio brand <project> --logo inputs/logo.png` sets contrast-checked colours from the client's logo.
- Copy: short, specific, written for the reader. `<em>…</em>` marks the accent words in a title.
- Steps: the first step can be `intro: true` (the section's opening headline). For `artwork`, `scene3d`, `parallax`,
  each further step drives one stage, level or photo, in order. For `film`/`overlay`, use `at: [from, to]`.
- Quote YAML strings that contain `:` or `,` inside `{ … }` flow mappings.
- No images? Use `image: { generate: "<a photographic prompt>" }`: generated locally (needs ComfyUI running).

## 3. Storyboard, then build
Storyboard before any full render: a film costs an hour or more, a storyboard seconds to minutes, and its frames are
the real first frames (same stages and caches), so approving them is not wasted work.
1. `storyboard(project, level="sketch")` for layout and pacing with no GPU, then `storyboard(project)` (stills).
   Read the returned `sheet` image: does each shot open (and end) on the right frame, does the product sit right in a
   take, are captions and motion verbs right, is anything a placeholder? The summary lists each card's status and the
   full render estimate; open `site` to judge the real page.
2. Fix the spec and storyboard again: only changed shots are redone (`only=[ids]` to limit it). Use
   `level="animatic"` (and `motion=True` with `only` for one shot) to check pacing and motion.
3. Edit shots and images in the loop, not by re-writing the spec: `storyboard_shots(project)` lists every shot's
   fields, images (each a chain of steps, with seeds) and variants. `set_shot_field(project, shot, field, value)` changes
   text, seed, seconds... in place (comments kept, validated). `regenerate_shot_image(project, shot, slot)` renders
   just that image (a new seed; `mode="rerun"` after a text edit; `step=1` for the base of an edit chain) and returns
   its path: read it, then keep it or `pick_shot_variant` an earlier one. The user can do the same in the browser with
   `studio storyboard <project> --edit`. `approve_shot` marks a shot approved (the sheet and `build(plan_only)` list
   the rest). It renders stills only: it never starts a film.
   **Notes first.** The user writes plain-language notes in the editor (a "What should change?" box per shot, a Notes
   tab for the whole page). When asked to handle them, call `storyboard_notes(project)` (or `studio storyboard <project>
   --notes`): each open note comes with its shot's current values and image paths. Decide what it means (a prompt or edit
   instruction reworded, a seed re-rolled, a caption or length changed, copy or order changed in `site.yaml`), do it with
   the tools above, LOOK at any new image before you call it done, then `resolve_note(project, id, reply)` with a short
   plain reply (what you did, or what you did not and why). Do not lecture about prompts; never touch a locked shot; and
   never start a film: only stills render from here. The user plays the result in the editor's Play tab.
4. Lock approved shots (`locked: true` on a beat, take or scene, or `set_shot_field(..., "locked", true)`) so later
   edits never re-render them.
5. `build(project, plan_only=True)` shows what will render and how long; tell the user before a long render.

### Colour that follows the camera, and faces

- A film that should come into colour where the camera looks (a black-and-white crowd with one couple in colour, a product
  that colours in as you scroll): render the film in **full colour**, then add `reveal:` (`base: mono`, `regions` with a
  `prompt` and an `at: {beat, t}` frame where the thing is plainly in view, `keys` mapping the section's scroll progress to
  0-1 per region). Never ask the video model to colour only part of the picture: it colours the rest and moves things.
- A region shows only in shots where it has an `at` (a cut ends its track): one `at` per shot it must be seen in.
- A prompt matching several things (both hands) reveals all of them: narrow it with `pick: left`, `within: "the woman"`, an
  "X's Y" prompt, or `points: [[x, y]]` (0-1 on the `at` frame). Look at `.build/<section>/reveal/<id>/ground.jpg`.
- Edit `keys`, `feather` and `base` freely: they re-pack in seconds and re-track nothing. `studio storyboard` shows each shot
  with the reveal applied (base look; real colour once a build made the masks).
- `faces: restore` (a beat or the film) repairs faces in generated video; off by default, ~0.7 s per 1080p frame. Needs
  `studio setup-comfy` once (and a ComfyUI restart); `studio doctor` checks it.

### Edits that change only a region

- Versions of one frame that dissolve into each other (a frozen moment that gets richer as the camera visits shoes, then
  hands) must not shimmer: a plain Qwen edit nudges everything. Give the edit a `region`:
  `image: { edit: { source: ..., instruction: "Redraw her shoes in rich detail and colour ...", region: { prompt: "the
  girl's shoes", pick: largest, grow: 12, feather: 8 }, seed: 3 } }` (or `region: "the girl's shoes"`; or `box` /
  `points`, 0-1 of the source). Everything outside the mask is the source, pixel for pixel; chain the edits (shoes, then
  hands on the shoes' result, then the whole girl).
- The editor sees a padded crop around the region (`context`), so small regions get real detail; the instruction should
  say the colour, material and light you want (the seam is matched by the edit, the feather only hides the join).
  `scope: image` for a region that is most of the picture; `invert: true` to edit everything except the region.
- Look at the result with the outline on: `edit_<digest>.outline.png` / `.mask.png` beside the edit in
  `.build/_generated/`, the card in `studio storyboard`, or the **region** button in `--edit`. A wrong mask is fixed with
  `pick`, `within`, `points` / `negative_points`, `grow` (the boxes found are in `region_<digest>.boxes.jpg`), not by
  rewording the instruction.

## 4. Build, look, fix
1. `build(project, draft=True)` (or `only=[ids]` for a few shots) then `wait_for_job`. Read the log on failure: it names the stage and the cause.
2. `snapshot(project)`, then read the sheet image. Check: text legible over the visual, the subject framed
   (not hidden behind the copy), nothing cut off, colours on brand, every stage actually visible.
3. Fix the spec (or the engine, if it's an engine limitation) and repeat. Finish with a full `build`.
4. `record(project)` for an MP4 scroll-through when the user wants something to share. For a launch film, add
   `trailer: {}` to the spec and run `trailer(project)` (16:9 + 9:16 in dist/trailer/); check the cut with
   `trailer(project, plan_only=True)` and look at frames of the result before handing it over.
5. Client revisions: `studio copy export <project>` -> send copy.md -> `studio copy import <project> copy.md` -> build.

## 5. Hand over
Tell the user where the site is (`dist/index.html`, preview with `studio preview <name>` or in `studio ui`), what
each section shows, and anything you couldn't do (e.g. ComfyUI not running, so generated images were skipped).
