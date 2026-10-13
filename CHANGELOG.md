# Changelog

What changed in each version of Scroll Studio, newest first. Versions follow the project's milestones; each lists the
commits it spans so you can check out any earlier state (`git checkout <commit>`).

Everything so far is version 1. On 2026-10-12 the releases first published as 2.0.0 and 3.0.0 were renumbered
1.1.0 and 1.2.0 (tags `v1.1.0` and `v1.2.0`).

## Unreleased

### Added
- `stage` scene: an opening on a dark stage. A faceless figure stands in the dark; each scroll brings one `lines:` entry
  (set heavier than the last) and a little more light, `platform:` raises a stage under them, and on `name:` (the
  page's <h1>) the view swings round behind them to face a follow-spot that floods the page with light, where `body:`
  and `buttons:` sit. The figure is a drawn outline and never shows a face. Every word is real text; with no scripting
  it is a plain dark panel, and reduced motion keeps the beats as fades.
- `site.product`: the product declared once (name, maker, url, model, licence, credit, `concept`). Models in GLB/glTF,
  OBJ, FBX, STL, PLY, **STEP/STP** (converted locally with OpenCascade through `cascadio`, parts kept as separate meshes
  with their names) and **3MF** (trimesh), from a file or URL. `up`, `units` and `rotation` fix any file; `parts` sets
  materials by part/assembly/mesh glob, material name, a `region` of the bounds and a `facing` (so a one-piece body
  can have a screen window); `exclude` drops alternate variants; `tessellation` and `max_triangles` keep huge CAD
  files in check (only heavy meshes are thinned). Cached as one normalised GLB in `.build/_product/`
  (`engine/product.py`, `backends/blender_scripts/product_prep.py`, `backends/cad.py`).
- Product stills anywhere an image is accepted: `image: {product: <view>}` with views front, three-quarter, side, top,
  back, hero-low, exploded and detail (`part:`, a macro view with shallow depth of field). Framed on the real
  silhouette (about two thirds of the frame), Khronos PBR Neutral colour, soft contact shadow, transparent where the
  page shows it. `scene:` renders the product into a perspective-matched Z-Image backdrop, lit by it, harmonised by a
  light Qwen-Image-Edit pass and checked against the product's own edges.
- `showroom` scene: the product live in the page (three.js, the normalised GLB, environment light, soft shadow);
  scroll keys turn, explode and zoom it; a Cycles poster until it loads.
- `studio product <project> [--parts] [--still <view>]` and MCP tools `product_parts`, `product_still`.
- Footer: the product's credit and licence, and "Concept page. Not affiliated with <maker>." for `concept: true`.
- Takes: plate-matched light by default (environments made from the generated frames, the ground's colour under the
  shadow, sun from `take.light`), depth of field at the camera's look-at, motion blur, and a composite graded to the
  plate (black level, white balance, saturation, softness, grain, light wrap). `product: {}` uses the site's product;
  product passes default to 64 samples at the final film size. `track` stage writes `product/track.json`, the
  product's screen position per frame (for vertical reframing).

### Changed
- Take stage keys are portable: the generated world (blockout, keyframes, LTX) no longer depends on the product (unless
  it is in the depth guide) or on absolute paths, so moving a project or changing the product never re-renders the
  world. Stamps written by the old keys are recognised and migrated.
- Block images keep their transparency (WebP with alpha) instead of being flattened.
- `sequence` scenes take `model: product` (or no model) and the product's own explode offsets.
- ComfyUI client: time spent waiting in a shared ComfyUI's queue no longer counts towards the timeout, and a
  timed-out job is cancelled only if it is ours (it used to interrupt whatever was running).
- URL models stored with Git LFS on GitHub are fetched from media.githubusercontent.com automatically.

## 1.3.0 · 2026-10-11 to 2026-10-12

Commits after `83bfbc7` to the `v1.3.0` tag.

The headline: five styles from classic animation (flipbook, pop-up book, pinscreen, sand and a zoetrope you spin),
story films told in shots, a live 3D codebase flight, and local image edits.

### Added
- Style `zoetrope`: the whole landing page is one wheel of printed cards on a giant strobe zoetrope. Every element
  (hero, each feature, each stat, each step, each question, the call to action) is a card with its own animation.
  Spin it with scroll, swipe, drag or the button; it strobes alive, slows with real friction and lands on a card;
  click a card and it flies out to be read. Research: docs/styles/styles-24-25.md.
- README: why Scroll Studio (local only, 10 to 30 times fewer tokens) with a worked token breakdown.
- Styles `pinscreen` (a dark, lamp-lit board of pins after Alexeieff and Parker: each plate is a pin picture and a wave
  of pins rolls it into the next; the pointer moves the lamp and presses pins) and `sand` (a backlit sand table after
  Caroline Leaf: one scroll sweeps a mound of grains across into the next scene; pictures are poured and cleared in
  sand, the pointer draws furrows). Research: docs/styles/styles-22-23.md.
- `type` scene `mode: weight`: words grow from thin and faint to heavy and solid in reading order, on a variable
  display face (`weights: [200, 800]`). Lines (split with ` / `) are sized at the heaviest weight so the finished
  passage fits the screen and nothing reflows on the way.
- `theme.labels: plain`: kickers, tags, timeline dates and the footer in sentence case in the body face, for brands
  that never set spaced capitals.
- `theme.display_em: heavy`: emphasis as a change of weight (upright, the text's own colour, the heaviest weight).
- `footer.links`: links in the footer to pages hosted elsewhere, such as a privacy policy.
- Styles from classic animation: `flipbook` (a pad of animation paper; one scroll notch lets go of one page, so
  pencil drawings animate; drag the dog-ear to flip) and `pop-up-book` (one book on a table; scroll is the hinge angle,
  scenes rise out of the gutter, pull-tabs raise the stats, a paper wheel turns the timeline). Research:
  docs/styles/styles-24-25.md and styles-26-27.md.
- Image edits: an image input can be an `edit:` of another (Qwen-Image-Edit, local), with up to two reference images.
  Beats take an `end_image:` so a shot lands exactly on a chosen frame, and `beat_restore:` cleans the joined film
  with SeedVR2.
- `film` with `beats:`: a story told in shots. Each beat is a generated still animated by LTX-2.3, cached on its own and
  crossfaded into the next; captions pin to beats (`state: { beat: … }`). Example: Feel.
  Beats take `strength`, `motion_seed` and `trim` for action shots that freeze on their first frame.
- `code` scene: fly through a codebase in live 3D following an agent at work. It opens on the agent's prompt box and
  dives through it; read files line a corridor, edits apply their diffs as you scroll, a run prints its output, a status
  bar ticks off the todo list, and captions pin themselves to files (`state: { file: … }`). Text stays real and readable.
- Copy fields accept `<code>` for inline commands.
- `theme.art`: a prompt (or `file:`) becomes artwork a style draws in its own medium, generated locally with Z-Image
  and, with `motion:`, animated by LTX-2.3 into a seamless loop. `ascii-art` prints it in characters in the hero and
  the render pane; `particles` turns it into a full-screen field of points.
- `theme.art` loops cut where the motion repeats: the build finds the stretch of the clip whose last frame matches its
  first while keeping most of the movement, so fast motion (a dribble) loops without a double exposure.
- `theme.art` tone mapping reads the background from the frame's border and lifts dark subjects, and a light
  background is flipped, so a subject prints as a solid figure. Tip: a dark subject reads best on a plain white
  background, a light one on black.

### Changed
- `type` scene `mode: swap`: on a narrow screen the rolling word shrinks until the longest one fits (it used to run off
  the edge on phones); the fixed words keep their size.
- `code` scene follows the scroll exactly (no trailing flight after you stop), draws lighter frames, and warms up the GPU
  behind the loader.
- `particles`: the hero is a field that fills the whole screen (the art, when there is one) and drifts apart as you
  scroll into the first formation.
- `blueprint`: next, next, next. The pen starts on the next view while the camera is still moving there, construction
  lines take less scroll, and moves between views are short, so no screen is empty paper.

### Fixed
- An animation re-rendered shorter than before no longer keeps the old render's trailing frames.
- `studio looks` refreshes the site's runtime, so rebuilding only the looks never runs a stale one.

## 1.2.0 · 2026-10-10 (first published as 3.0.0)

Commits `34dd0c5` to `83bfbc7`.

The headline: your real product in a generated world, real places, numbers read from the data, twenty-one styles that
change how a site is experienced, tools for client work, and a new licence.

### Licence (breaking)
- Scroll Studio is now **GNU AGPL-3.0** with additional terms ([NOTICE.md](NOTICE.md)): derivatives stay open source
  (including tools offered over a network and code AI agents produce from this repository), the attribution notice is
  kept word for word, modified versions are marked and may not use the name, and the research in `docs/styles` is
  credited wherever it is used. Sites you build are yours under the Scroll Studio Output Exception.
- [AGENTS.md](AGENTS.md) tells AI agents what the licence requires of them.
- Earlier versions were MIT and stay MIT for those copies.

### Added
- **One Take** (`film` with `take:`): one continuous camera move through a generated world. Rough shapes and camera
  keys become a Blender depth guide, LTX-2.3 paints the world in chained segments, and the real product is rendered by
  Cycles from its own 3D model through the same camera and composited, so it never warps. `from_photo:` builds the
  model with TRELLIS. Example: Stillwater (`examples/one-take`).
- **Real places** (`splat` scene): Gaussian-splat scans (`.ply` or gsplat `.pt`) trimmed and compressed to SPZ at build
  time and walked through on scroll with Spark. Example: Hollis House.
- **Numbers you can check**: chart `callouts` resolved from the data at build time, bar and scatter charts, number
  formats, and `stats` items that read their value from a chart. Example: Pelorus (renewables data from Our World in
  Data).
- **Twenty-one styles as experiences** (`theme.style`): particles, liquid-morph, holographic, neon-glow, wireframe-3d,
  glassmorphism, kinetic-type, isometric, clay-3d, ascii-art, gradient-mesh, comic-book, split-flap, retro-vhs, halftone,
  bauhaus, pixel-art, blueprint, art-deco, neo-brutalism and anime-intro. Each has its own scroll mechanic, layout,
  transitions, components and call to action (a departures board, comic pages, a terminal session, a game level, an
  anime opening...), built from research in [docs/styles](docs/styles/). A style is a folder (`engine/styles/<name>/`)
  plus a runtime controller (`runtime/src/styles/<name>.ts`); the contract is in `engine/styles/README.md`.
- `studio looks`: build one site in every style, with a switcher bar and a gallery. Example: Halcyon.
- **Client work**: `studio copy export|import` (a Markdown copy deck for clients, applied back into site.yaml with
  comments kept and invalid edits refused) and `studio brand --logo` (theme colours from a logo, contrast-checked).
- MCP tools: `list_styles`, `looks`, `copy_deck`, `apply_copy_deck`, `brand_from_logo`.
- `theme.mode` override; extra font roles in a style (`--font-<role>` CSS variables).
- An SVG favicon on every page.
- Showcase: the 1.2 examples and a "New in 1.2" section.

### Changed
- One Take product pass renders only the product's screen region (about 9 times faster), its shadow ends at the surface
  it stands on, and the HDRI's own sun is turned to match the scene's light.
- Snapshots and recordings wait for a style's experience to start.
- The Halcyon demo no longer shares one type scene across styles.

### Fixed
- Runtime chunk preloads resolve next to `index.js` (they requested `/chunks/...` from the server root and 404ed on
  GitHub Pages).
- Look pages rebase their own relative links.
- Map styles that name a missing icon no longer log warnings.
- Chart end labels give way to callouts; label halos; a `0%` tick instead of `0.0%`.
- The rolling word in a type `swap` scene is measured after the web fonts load (it was cut off).
- Blockout `scatter` can be cones (pines), so forests no longer read as boxes to the video model.

### Removed
- The first, CSS-only version of the styles and its shared effects layer (`runtime/src/fx`), replaced by the
  per-style experiences.

## 1.1.0 · 2026-10-06 to 2026-10-08 (first published as 2.0.0)

Commits `387962c` to `c566ea5`.

The polish release: rendering fixes found on real hardware, typography and contrast, new layouts and blocks, and
phones that play clips.

### Added
- **Stack layout** (`layout: stack`): every section is a full-screen panel that slides over the last; panel blocks and
  `surface:` (light, dark, accent) recolour one section with contrast-checked tokens. Example: Hushwell.
- **Plain pages** beside a site (privacy, support, press) from Markdown, with fenced code blocks and heading anchors.
- **Backdrops** for any section, including `gradient:` backdrops rendered locally (stops, glows, stars, grain), and
  display-size type.
- **Phones**: a product or hero phone can play a screen recording; poses `rise`, `close`, `lean`, `pair` (two phones that
  swap) and `turn`; big figures under the copy; bold-italic emphasis (`theme.display_em: bold`).
- `scroll.speed` paces the smooth scroll, anchor scrolls and reveals.
- `theme.display_optical_size` pins a variable display face's optical size.
- Self-hosted Google Fonts (no third-party requests for type), with axis specs for more families.
- Casa Alta in the showcase; README GIF and launch copy.

### Changed
- Typography and contrast: secondary text tiers and accent text are derived per theme so small text clears WCAG AA.
- Depth Anything V2 Small (Apache-2.0) is the default depth model; GSAP dropped (unused).
- Clips in phones play only while on screen and pause while the page is hidden.
- `studio publish` rewrites links to every sibling site and warns about missing ones.

### Fixed
- A black rectangle flashing over WebGL scenes (a NaN in the glow shader), and black squares over `scene3d` views.
- Caption text tracks the scroll position, so fast scrolling never leaves text behind.
- GitHub detects the licence file.

## 1.0.0 · 2026-09-28 to 2026-10-05

Commits `51f56a6` to `6353886`.

The first release of the engine: one `site.yaml` in, a static scroll-driven site out.

### Added
- **The engine**: a Pydantic site spec, cached scene builders, a Jinja compiler with themes, and a TypeScript browser
  runtime (Lenis smooth scroll, sticky stages, step cards, HUDs, one lazily loaded player per scene type).
- **Nine scene types**: `film` (Blender blockout, Z-Image keyframes, LTX-2.3 video), `artwork` (any image drawn and
  painted in stages), `scene3d` (three.js zoom journeys), `sequence` (Blender renders of a 3D model), `parallax` (photos
  with estimated depth), `type` (kinetic typography), `vector` (SVG line drawings), `chart` (D3 data stories) and `map`
  (MapLibre camera flights and routes).
- **Content blocks**: hero, intro, features, stats, timeline, quote, cta, gallery, product, strip, orbit, faq.
- **Tools**: the Studio UI and server, a CLI (`build`, `preview`, `snapshot`, `record`, `previews`, `poster`, `publish`,
  `combine`, `doctor`), an MCP server and Claude skill, a model registry, and an install guide.
- URL inputs and locally generated images (`generate:`).
- A loading screen that holds scrolling until every scene's media is ready.
- **Examples**: Lodestar Orbital, Meridian, Atelier Sfumato, Cellwright Bio, Northstar Observatory, Fischer & Vale,
  FORM/26, Wunderkammer, Daybreak Institute, Tidewater Lines, Casa Alta, Hale & Rowe, and the showcase gallery with
  preview videos.
- Licensed MIT.
