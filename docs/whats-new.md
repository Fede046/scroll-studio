# What's new

[← README](../README.md) · [Why Scroll Studio](why.md) · [What's new](whats-new.md) · [Examples](examples.md) · [Guide: make a site](guide.md) · [Styles](styles.md) · [Scenes](scenes.md) · [Licence](licence.md)

### New in 1.4

Coming in 1.5: more customization (your own media everywhere, options for every style), better motion control and faster
rendering. See the [1.5 milestone](https://github.com/Okohedeki/scroll-studio/milestone/1).

- **The one-take page** (`journey:` on a film section): the whole landing page is one camera move through one generated world; every section is a place in it (the door, the rooms, the table, the window, the view), the page's blocks arrive at their stop set as part of the picture, and the camera rests while they are read. ([The one-take page](scenes.md#the-one-take-page-journey))
- **Cinemagraphs** (`cinemagraph:` on any image): a still where only one thing moves (steam, a curtain, smoke, water);
  everything outside the mask is held pixel for pixel and the loop is closed without a seam.
  ([Cinemagraphs](scenes.md#cinemagraphs-one-thing-moves-cinemagraph))
- **Light as the scroll** (`type: light`): one place relit from dawn to night as you scroll. Each time of day is the same
  picture relit with the geometry measured and locked; a WebGL shader carries the light between them (a front of new light,
  windows and lamps coming on one by one, mist, a slow 2.5D drift) and the page's colours follow the sky.
  ([One place, dawn to night](scenes.md#one-place-dawn-to-night-type-light))
- **Inside the product** (`type: inside`): a macro camera flies into the product's own 3D model, stopping at named
  parts, with the parts in the way cut away. ([Inside the product](scenes.md#inside-the-product-type-inside))
- **Miniature worlds** (`type: diorama`): a tilt-shift diorama you orbit and dive into, live in the browser; every
  section lives at a place on it. ([Miniature worlds](scenes.md#miniature-worlds-diorama))
- **Edited like a film** (`transition:` on any section): match cuts, irises, wipes, whips, hard cuts and carried
  headlines between sections instead of fades. ([Edited like a film](scenes.md#edited-like-a-film-transition))
- **Type in the world** (`place: { kind: behind | surface | sky }` on a step): headlines that live inside the scene:
  set behind a pine so the camera passes them, painted on a deck in perspective, written in the haze with fog in front.
  ([Type in the world](scenes.md#type-in-the-world-place))
- **Direction boards** (`studio directions`): how a design studio pitches. One brief in, several complete art directions
  out, side by side on one page, so you pick a direction in minutes before committing to a build. Pick one and it is
  written into `site.yaml`. ([Direction boards](guide.md#direction-boards-pitch-it-before-you-build-it))
- **Six more styles from classic animation:** `stop-motion`, `paper-cut-out`, `scratch-film`, `smears`
  (Spider-Verse timing), `paint-on-glass` and `multiplane`. Thirty-two styles in all.
  ([try them on Halcyon](https://okohedeki.github.io/scroll-studio-showcase/halcyon/looks/))
- **Frozen moments** (`freeze:` on a beat): when time stops, stop generating. One frame, upscaled, with a 2.5D depth
  camera moving through it, rendered offline in seconds, so a crowd stands still while the camera visits a couple's
  hands and feet and every face stays the same face. `image: { beat_frame: ... }` chains the next shot onto its last frame.
  `detail:` builds a pyramid of re-drawn tiles so a 20x push stays sharp; `layers:` cuts people out onto planes over a
  painted-out background so depth jumps have no halos.
- **Camera moves on moving shots** (`camera:` on a beat): keyed camera paths for generated video, so the crowd keeps
  walking while the camera pushes from the wide street to one girl and back out. The camera is flown through the start
  image's depth into a guide video, with the walking people softened so they stay free, and the video model paints the
  shot along it (measured: the view stays within 1% of the keys).
- **Colour that follows the camera** (`reveal:` on a film section): render the film once in full colour; the page shows
  it black and white (or dimmed, blurred, tinted) and brings colour into tracked regions as you scroll.
  ([Colour that follows the camera](scenes.md#colour-that-follows-the-camera-reveal))
- **Face repair** for generated video (`faces: restore`, GFPGAN v1.4).
- **Storyboard first** (`studio storyboard`, `--edit`): sketches, stills and an animatic before any video render, with an
  editor to redo one image at a time. ([Storyboard first](guide.md#storyboard-first))
- **Polish report** (`studio inspect`): every film scored second by second for pops, softness, halos, style drift and
  morphs. ([studio inspect](scenes.md#find-the-polish-problems-before-the-owner-does-studio-inspect))
- **Your product, declared once** (`site.product`, STEP/3MF), **launch trailers** (`studio trailer`) and **Wan 2.2** as a
  second video model.

### New in 1.3

- **Five styles from classic animation.** `zoetrope`: the landing page is one wheel of cards you spin, land on and
  open to read. `pop-up-book`: scenes fold up out of the gutter as the book opens. `flipbook`: one scroll notch, one
  pencil page. `pinscreen`: a lamp-lit wall of pins rolling from picture to picture. `sand`: a backlit sand table swept
  scene to scene. ([try them on Halcyon](https://okohedeki.github.io/scroll-studio-showcase/halcyon/looks/))
- **Story films told in shots** (`film` with `beats:`): every sentence its own generated shot, with end frames, local
  image edits and SeedVR2 clean-up. ([Feel](../examples/feel/site.yaml), the showcase's front door)
- **Fly through a codebase** (`code` scene): live 3D, real text, diffs applied as you scroll.

### New in 1.2

Full history of every version: [CHANGELOG.md](../CHANGELOG.md).


- **One Take** (`film` with `take:`): one unbroken camera move through a generated world. You block the world out
  in rough shapes and camera keys; Blender renders the depth guide, LTX-2.3 paints the world along it in chained
  segments, and your real product is rendered by Cycles from its own 3D model through the identical camera and
  composited onto every frame. The product never warps, because it is never generated.
  ([Stillwater](../examples/one-take/site.yaml))
- **Real places** (`splat`): a phone or drone scan as a Gaussian splat (`.ply` or a gsplat `.pt`), trimmed and
  compressed to SPZ at build time and walked through on scroll. ([Hollis House](../examples/hollis-house/site.yaml))
- **Numbers you can check** (`chart` callouts, `stats` bound to data): headline figures and chart notes are read
  from the source CSV when the site is built, so the copy can't drift from the data. ([Pelorus](../examples/pelorus/site.yaml))
- **Twenty-six styles that change the experience, not just the paint** (`theme: { style: … }`). Each style has its
  own scroll mechanic, layout, transitions and components, built from in-depth research
  ([docs/styles](styles/)): split-flap is a departures board that updates as the clock advances, comic-book is
  read panel by panel, anime-intro cuts like an anime opening, ASCII is a terminal session, blueprint is a drawing
  that drafts itself. `studio looks` builds a site in every style. ([Halcyon](../examples/halcyon/site.yaml))
- **Client work**: `studio copy export` gives the client a Markdown copy deck; `studio copy import` applies their
  edits back into site.yaml (comments kept, invalid edits refused). `studio brand --logo` draws a contrast-checked
  theme from their logo.
