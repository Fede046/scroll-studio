# Scroll Studio

**Scroll-driven websites from one YAML file. Runs on your own machine with no API keys, and Claude can drive it
through MCP.**

[![Lodestar Orbital: a rocket launch that plays as you scroll](docs/media/lodestar.gif)](https://okohedeki.github.io/scroll-studio-showcase/)

**[See every example site live →](https://okohedeki.github.io/scroll-studio-showcase/)** ·
**[One page, twenty-six experiences →](https://okohedeki.github.io/scroll-studio-showcase/halcyon/looks/)**

Give it a brief, a photo, a painting, a 3D model, a CSV or a film idea. It builds a static site where scrolling
plays the visuals: generated video, a painting drawn stroke by stroke, a live 3D zoom, a data story, a map flight.
The output is plain HTML, CSS and JS you can host anywhere.

**What you need:** 7 of the 10 scene types (`scene3d`, `chart`, `map`, `type`, `vector`, `splat`, and `artwork` from your own
images) need no GPU at all, just Python and a browser. `parallax` and `sequence` run on the CPU but are much
faster on a GPU. `film` generates video locally with LTX-2.3 and needs Blender, ComfyUI and a 24 GB card (RTX
4090 class). Details in [docs/INSTALL.md](docs/INSTALL.md).

```
site.yaml ──► studio build ──► dist/  (plain static files: host anywhere)
   ▲               │
   │               ├─ film      Blender blockout → Z-Image keyframes → LTX-2.3 video → scrub-ready encode
 Studio UI         ├─ artwork   any image → guides, contour strokes, graphite, underpainting, colour layers
 Claude (MCP)      ├─ scene3d   live three.js zoom journeys built from presets or your glTF models
 CLI               ├─ sequence  Blender (Cycles) renders a 3D model: turntable, explode, reassemble
                   ├─ parallax  photos + estimated depth (Depth Anything V2) → 2.5D camera moves
                   ├─ type      kinetic typography: reveal, stack, swap, scale, weight
                   ├─ vector    SVG or vectorised artwork drawing itself stroke by stroke
                   ├─ chart     CSV data stories with D3: series, zooms, callouts read from the data
                   ├─ map       live vector maps (MapLibre): camera flights and routes per step
                   └─ splat     a Gaussian-splat scan of a real place, walked through on scroll (Spark)
```

## Why Scroll Studio

- **Local only. Nothing to pay per site.** Every image and video is generated on your own GPU with open models
  (Z-Image, Qwen-Image-Edit, LTX-2.3, SeedVR2). No API keys, no credits, no cloud account, no per-clip bill. Your
  brief, your brand and your footage never leave your machine, and a site costs the electricity to render it.
- **10 to 30 times fewer tokens.** When an AI agent builds the site, it writes a short spec, not the code. The
  engine already holds the markup, the stylesheets, the scroll physics and the players, so the agent only writes
  the words and the choices. An agent coding the same page by hand has to write and debug all of it, for every
  site and every revision.
- **An engine, not one effect.** Twenty-six styles and eleven scene types from the same spec. Switching a whole site
  from a pop-up book to a pinscreen is one word, not a rebuild.
- **Plain output.** Static HTML, CSS and JS that drops into any host or framework.

### Token savings, worked example: Halcyon as a zoetrope

[Halcyon](examples/halcyon/site.yaml) with `theme: { style: zoetrope }` is a landing page that is one spinning wheel
of cards: 19 cards, each with its own animation, prize-wheel physics, cards that fly out to be read. What an agent
writes for it:

| | Tokens the agent writes |
|---|---:|
| **With Scroll Studio:** `site.yaml` (content, order, `style: zoetrope`) | **1,241** |
| **By hand,** the same page: | |
| &nbsp;&nbsp;Page markup and copy | 15,934 |
| &nbsp;&nbsp;Stylesheets | 16,821 |
| &nbsp;&nbsp;Wheel, physics, strobe, open and close | 15,321 |
| &nbsp;&nbsp;The 45 card animations | 29,882 |
| &nbsp;&nbsp;Scrolling, loader and art helpers | 6,574 |
| &nbsp;&nbsp;**Total** | **84,532** |

That is about **68 times fewer** for a full experience like this one, before counting the debugging rounds a
hand-built page needs. A simpler hand-built scroll page lands at 10 to 30 times. Every later change is a line in the
spec rather than a rewrite, and the agent reads the skill once per session (about 1,100 tokens). Counted with
tiktoken (`cl100k_base`) on the files in this repo; other tokenizers differ by roughly 10 to 20%.

### New in 1.3

- **Light as the scroll** (`type: light`): one place relit from dawn to night as you scroll. Each time of day is the same
  picture relit with the geometry measured and locked; a WebGL shader carries the light between them (a front of new light,
  windows and lamps coming on one by one, mist, a slow 2.5D drift) and the page's colours follow the sky.
  ([One place, dawn to night](#one-place-dawn-to-night-type-light))
- **Direction boards** (`studio directions`): how a design studio pitches. One brief in, several complete art directions
  out, side by side on one page, so you pick a direction in minutes before committing to a build. Pick one and it is
  written into `site.yaml`. ([Direction boards](#direction-boards-pitch-it-before-you-build-it))
- **Colour that follows the camera** (`reveal:` on a film section): render the film once in full colour; the page shows
  it black and white (or dimmed, blurred, tinted) and brings colour into tracked regions as you scroll.
  ([Colour that follows the camera](#colour-that-follows-the-camera-reveal))
- **Face repair** for generated video (`faces: restore`, GFPGAN v1.4).
- **Five styles from classic animation.** `zoetrope`: the landing page is one wheel of cards you spin, land on and
  open to read. `pop-up-book`: scenes fold up out of the gutter as the book opens. `flipbook`: one scroll notch, one
  pencil page. `pinscreen`: a lamp-lit wall of pins rolling from picture to picture. `sand`: a backlit sand table swept
  scene to scene. ([try them on Halcyon](https://okohedeki.github.io/scroll-studio-showcase/halcyon/looks/))
- **Story films told in shots** (`film` with `beats:`): every sentence its own generated shot, with end frames, local
  image edits and SeedVR2 clean-up. ([Feel](examples/feel/site.yaml), the showcase's front door)
- **Frozen moments** (`freeze:` on a beat): when time stops, stop generating. One frame, upscaled, with a 2.5D depth
  camera moving through it, rendered offline in seconds, so a crowd stands still while the camera visits a couple's
  hands and feet and every face stays the same face. `image: { beat_frame: ... }` chains the next shot onto its last frame.
  `detail:` builds a pyramid of re-drawn tiles so a 20x push stays sharp; `layers:` cuts people out onto planes over a
  painted-out background so depth jumps have no halos.
- **Camera moves on moving shots** (`camera:` on a beat): keyed camera paths for generated video, so the crowd keeps
  walking while the camera pushes from the wide street to one girl and back out. The camera is flown through the start
  image's depth into a guide video, with the walking people softened so they stay free, and the video model paints the
  shot along it (measured: the view stays within 1% of the keys).
- **Fly through a codebase** (`code` scene): live 3D, real text, diffs applied as you scroll.

### New in 1.2

Full history of every version: [CHANGELOG.md](CHANGELOG.md).


- **One Take** (`film` with `take:`): one unbroken camera move through a generated world. You block the world out
  in rough shapes and camera keys; Blender renders the depth guide, LTX-2.3 paints the world along it in chained
  segments, and your real product is rendered by Cycles from its own 3D model through the identical camera and
  composited onto every frame. The product never warps, because it is never generated.
  ([Stillwater](examples/one-take/site.yaml))
- **Real places** (`splat`): a phone or drone scan as a Gaussian splat (`.ply` or a gsplat `.pt`), trimmed and
  compressed to SPZ at build time and walked through on scroll. ([Hollis House](examples/hollis-house/site.yaml))
- **Numbers you can check** (`chart` callouts, `stats` bound to data): headline figures and chart notes are read
  from the source CSV when the site is built, so the copy can't drift from the data. ([Pelorus](examples/pelorus/site.yaml))
- **Twenty-six styles that change the experience, not just the paint** (`theme: { style: … }`). Each style has its
  own scroll mechanic, layout, transitions and components, built from in-depth research
  ([docs/styles](docs/styles/)): split-flap is a departures board that updates as the clock advances, comic-book is
  read panel by panel, anime-intro cuts like an anime opening, ASCII is a terminal session, blueprint is a drawing
  that drafts itself. `studio looks` builds a site in every style. ([Halcyon](examples/halcyon/site.yaml))
- **Client work**: `studio copy export` gives the client a Markdown copy deck; `studio copy import` applies their
  edits back into site.yaml (comments kept, invalid edits refused). `studio brand --logo` draws a contrast-checked
  theme from their logo.

## Examples

**Live samples: https://okohedeki.github.io/scroll-studio-showcase/**

Make previews for any project with
`studio previews <project> ... --out <folder>` (a video and a poster each), or a single poster at a chosen
moment with `studio poster <project> --at <scene>:<progress> --out poster.jpg`. Previews stay out of git. To put several built sites online together (GitHub Pages or any static host):
`studio publish <project> ... --out <folder> --home showcase`.

The [showcase site](examples/showcase/site.yaml) puts every example on one page with its preview.

Every example is a `site.yaml` in [`examples/`](examples/) and rebuilds with `studio build examples/<name>`.

| Example | Domain | Scene type | What scrolling does |
|---|---|---|---|
| [Lodestar Orbital](examples/lodestar-orbital/site.yaml) | Aerospace | `film` | A rocket launch to orbit, generated locally with LTX-2.3, with live telemetry |
| [Meridian](examples/meridian/site.yaml) | Private aviation | `film` | A jet descends through cloud over London; the altimeter counts down |
| [Atelier Sfumato](examples/atelier-sfumato/site.yaml) | Art education | `artwork` | The Mona Lisa is drawn and painted in five lessons |
| [Cellwright Bio](examples/cellwright-bio/site.yaml) | Biotech | `scene3d` | A zoom from tissue to a molecule docking on DNA |
| [Northstar Observatory](examples/northstar-observatory/site.yaml) | Astronomy | `scene3d` | A fall from the whole galaxy to one living planet |
| [Fischer & Vale](examples/fischer-vale/site.yaml) | Luxury goods | `sequence` | A glass chess set lifts off its board and settles back |
| [FORM/26](examples/form-conference/site.yaml) | Events | `type` | A conference site told in kinetic type |
| [Wunderkammer](examples/wunderkammer/site.yaml) | Museum | `vector` | Dürer's *Rhinoceros* (1515) re-cut line by line |
| [Daybreak Institute](examples/daybreak-institute/site.yaml) | Research | `chart` | Real solar data (IRENA) told as a scrolling data story |
| [Tidewater Lines](examples/tidewater-lines/site.yaml) | Logistics | `map` | Shanghai to Rotterdam, port by port, on a live map |
| [Casa Alta](examples/casa-alta/site.yaml) | Hospitality | `parallax` | Generated photos of a cliff hotel in 2.5D (needs ComfyUI to build) |
| [Hushwell](examples/hushwell/site.yaml) | Healthcare | `stack` layout | Panels slide over each other: hero, product with phone, photo strip, orbit, FAQ |
| [Hale & Rowe](examples/hale-rowe/site.yaml) | Architecture | `artwork` | A house drawn from construction lines to finished photo (needs ComfyUI) |
| [Stillwater](examples/one-take/site.yaml) | Consumer product | `film` + `take` | One take from a mountain ridge down to a bottle on a lakeside table; the bottle is the real 3D model |
| [Hollis House](examples/hollis-house/site.yaml) | Real estate | `splat` | A walk through a scanned house, room by room |
| [Pelorus](examples/pelorus/site.yaml) | Research | `chart` (bar) | The renewables share of electricity, every figure read from Our World in Data |
| [Halcyon](examples/halcyon/site.yaml) | Software | blocks | One product page as twenty-one experiences (`studio looks`) |
| [Quay House](examples/harbour-light/site.yaml) | Hospitality | `light` | One harbour from dawn to night; windows and lamps come on (needs ComfyUI to build) |

## Quick start

```bash
git clone https://github.com/Okohedeki/scroll-studio && cd scroll-studio
pip install -e .
studio doctor                         # what this machine can build
studio build examples/cellwright-bio  # live 3D: needs nothing but Python
studio preview cellwright-bio         # http://localhost:5173
studio ui                             # the Studio app: http://localhost:5180
```

Full setup (GPU, Blender, ComfyUI and models) is in [docs/INSTALL.md](docs/INSTALL.md).

## Make your own

```bash
studio new harbour-hotel --example atelier-sfumato   # or start blank: studio new harbour-hotel
# edit projects/harbour-hotel/site.yaml (or use studio ui), drop files in inputs/
studio storyboard harbour-hotel                      # every shot's real first frame, before any film renders
studio build harbour-hotel --draft
studio snapshot harbour-hotel --at top --at studio:0.5   # screenshots + contact sheet
studio build harbour-hotel && studio record harbour-hotel   # final build + an MP4 scroll-through
```

A spec is a theme, a nav and a list of sections. Scenes are the scroll-driven visuals; blocks (`hero`, `intro`,
`product`, `features`, `stats`, `timeline`, `strip`, `orbit`, `quote`, `faq`, `cta`, `gallery`) are the content between them.
Set `layout: stack` and every section becomes a full-screen panel that slides up over the one before it (see
[Hushwell](examples/hushwell/site.yaml)); `surface: dark | light | accent` recolours a single section:

```yaml
name: Harbour Hotel
theme: { preset: dusk }                  # night, brass, paper, lab, cosmos, studio, dusk, ink, blueprint
sections:
  - id: rooms
    type: parallax
    steps:
      - { intro: true, title: "A room above <em>the water.</em>" }
      - { title: Morning, image: { generate: "Hotel terrace above a harbour at sunrise, photoreal" } }
      - { title: Evening, image: inputs/terrace-dusk.jpg }
  - type: cta
    title: Stay <em>a while.</em>
    button: { label: Book, href: "https://example.com" }
```

`studio schema` prints every field. Inputs can be project files or https URLs; images can be generated locally
from a prompt (`generate:`). Builds are cached per stage, so editing copy never re-renders a film. A theme can
pin the display face's optical size (`display_optical_size: 40`): variable serifs like Fraunces grow more
expressive at huge sizes, and a pinned size keeps headlines calm.

A site can carry plain pages beside the scroll page, for the privacy policy, support or press: Markdown files set
in the site's theme, served at `/<slug>/` and linked from the footer (`nav: true` adds them to the nav too).

```yaml
pages:
  - { slug: privacy, title: Privacy, source: pages/privacy.md }
  - { slug: support, title: Support, source: pages/support.md, nav: true }
```

A `product` block's phone can play a screen recording instead of showing a screenshot: `device: { video: inputs/clips/write.mp4, image: inputs/write.jpg }` (muted, looping; the image is the poster). `pose:` picks the composition so a run of product panels doesn't repeat one: `beside` (default), `rise` (centred under centred copy, cut off by the panel's bottom edge), `close` (larger, cut off below), `lean` (tilted out of the lower corner), `pair` (with a second phone, `behind: { video: …, image: … }`, the two swapping places on a loop), `turn` (turned in perspective towards the copy). `stats: [{value, label}]` shows big figures under the body instead of tags. A `hero` takes a `device:` too, rising from the bottom edge under the copy. `theme.display_em: bold` sets `<em>` words as bold italics in the text's own colour instead of the accent colour. `scroll: { speed: 1.2 }` paces the smooth scroll, anchor scrolls and scroll-driven reveals (1 is the default; 1.2 is a fifth faster).

Any section can sit on a full-bleed `backdrop:` (in the stack layout, the panel's own), with `surface:` picking the
text colour. A backdrop can be a file, a URL, a `generate:` prompt, or a `gradient:` rendered on the spot with no
model: colour stops, glows, stars and grain, enough for colour cards, dusk skies and night seas behind type.

```yaml
  - type: hero
    surface: dark
    backdrop:
      gradient:
        colors: ["#2A1B2E", "#8A4B5A", "#D98C7A"]
        glows: [{ x: 0.5, y: 0.95, color: "#F2B48C", radius: 0.5, strength: 0.6 }]
        stars: 120
    title: Your words stay <em>on your phone.</em>
```

## Direction boards: pitch it before you build it

A studio does not start with the build. It shows the client three or six different ideas of what the site could be, side
by side, and the client points at one. `studio directions` does that from the site's own spec:

```bash
studio directions my-site                      # six directions: board.html + board.png in my-site/directions/
studio directions my-site --n 4 --seed 7       # another seed, another set
studio directions my-site --brief "calmer, more editorial, for people who travel slowly"
studio directions my-site --serve              # the boards in the browser, a Pick button on each
studio directions my-site --pick c             # write direction C into site.yaml (a minimal diff; backup kept)
studio directions my-site --undo               # put the file back as it was before the last pick
studio directions my-site --reroll d           # another idea in place of one direction
studio storyboard my-site                      # now every image redraws in the picked direction's imagery
```

Each **direction** is a complete art direction, not a colourway: a **concept** line; a **palette**; a **type pairing**
(Google Fonts the engine loads and self-hosts); one of the engine's **styles** (the experience: what scrolling does, how
sections hand over; or the default editorial layout); an **imagery treatment**, which is how every generated image and film
prompt is phrased (medium, light, lens, mood, colour in words) so the whole page looks like one shoot; **motion notes**
(page, camera, type) and the pace; and the **voice** that suits it. Its board shows the hero and two or three key sections
as storyboard stills (Z-Image Turbo, the same generator and seeds in every direction, so what differs is the direction),
set in that direction's palette and type, with the palette, faces, style and imagery written out under them. The page is
`directions/board.html` (open it, or `--serve` it like the storyboard editor), and `directions/board.png` is the same page
as one contact sheet.

**They differ in kind.** The set is built from schools of design (a naturalist's plate book, the Swiss grid, golden-hour
film photography, neon noir, drafting-table blueprint, a risograph zine, a picture book, soft clay, silver noir, art deco,
cut paper, a travel poster, a Dutch still life, Y2K chrome, an arcade, a terminal, a quiet product studio, reportage,
wabi-sabi, an old atlas, cel animation, Memphis pop), picked greedily so each next one fits the subject and is far from
those already chosen. A distance measure (kind of picture, experience, colour, type, what the pictures are made of) then
checks every pair; a pair closer than 0.5 is one idea twice, and the weaker of the two is replaced. The board header shows
the closest pair, how many kinds and experiences the set spans, and what was regenerated. Directions are listed from closest
to today's site to a different site.

**There is no text model, so the writer is deterministic.** The engine has no local language model (ComfyUI's `models/LLM`
holds Florence-2, a captioner, and Gemma is only LTX's text encoder), so ideas are not generated: they are composed from a
curated, combinable vocabulary (`engine/directions/vocab.py`: schools, palettes, type pairings, imagery treatments,
photographers' lighting such as Rembrandt, Vermeer window light or Penn's north light, and which engine styles give each
school the right experience), chosen to fit the subject and mood words found in the site's copy and the brief, and combined
by a seed. The same brief and seed give the same boards. Add a school by adding data; tests check every palette's contrast,
that every font loads and every style exists. Nothing is sent anywhere and there are no API keys.

The optional **`directions:`** block in the spec is the brief and the constraints:

```yaml
directions:
  brief: "Quiet and handmade, never precious; a working studio, not a gallery."
  count: 6
  seed: 4
  moods: [handmade, warm, calm]            # also read from the brief: calm, warm, bold, playful, technical, raw, nostalgic ...
  keep: [colors]                           # parts of today's look every direction keeps: style, colors, fonts, imagery
  styles:   { avoid: [pixel-art, ascii-art] }              # or only: [none, halftone, sand]; none = the default layout
  fonts:    { avoid: [Press Start 2P] }                    # or only: [Fraunces, Karla ...]
  palettes: { avoid: [pink], brand: ["#c2612a"] }          # brand colours become every direction's accent
  stills: 4                                # stills per board: the hero, then key sections
```

**A pick** writes the direction into `site.yaml` and nothing else: `theme` (style, mode, colours, fonts, display weight and
emphasis, radius), `imagery` and `scroll.speed`. Only what differs from what the site already resolves to is written, comments
and layout stay, the old file is kept in `directions/backups/`, and an edit that would make the spec invalid is refused.
**Copy is never touched** (a direction has a voice note, but the writer cannot write copy, so there is nothing to apply).

`imagery:` is a spec field on its own, so you can write it by hand:

```yaml
imagery:
  medium: 35mm film photograph, Kodak Portra 400, fine grain
  light: low golden-hour sun, long soft shadows
  lens: 35mm, eye level, shallow depth of field
  mood: unhurried, sun-warmed, quietly luxurious
  palette: honey, terracotta and sea blue
```

It is added to every prompt the engine sends to the image and video models (a `generate:` image, a beat's frame and clip, a
take's keyframes and segments), and with `restyle` on (the default) the phrases it replaces in the original prompts
(`photorealistic`, `shot on a medium format camera`, `golden hour`) are dropped first. Unset, nothing is added and no cache
key changes. Example: [Kiln & Kettle](examples/kiln-and-kettle/site.yaml). MCP tools: `directions`, `direction_reroll`,
`direction_pick`, `direction_undo`.

## Storyboard first

A film costs an hour or more to render (LTX-2.3 or Wan 2.2, SeedVR2, a Cycles product pass over every frame), so
look at it before you pay for it. `studio storyboard` shows every shot of the page at a fraction of the cost, through
the same stages and caches the full build uses:

```bash
studio storyboard my-site --level sketch     # seconds, no ComfyUI: a take's grey world, cached stills, prompt cards
studio storyboard my-site                    # stills (default): the real first (and end) frame of every shot
studio storyboard my-site --level animatic   # the stills in motion, timed cuts and captions -> animatic.mp4
studio storyboard my-site --level animatic --motion --only door   # plus a tiny LTX preview of one shot's motion
studio build my-site --plan                  # what a build would render, and about how long it takes here
studio build my-site --only door,enter       # render just those beats (or sections); the rest keep their cache
studio storyboard my-site --edit             # edit every shot in the browser, regenerate one image at a time
```

It writes `<project>/storyboard/` (not committed, like `dist/`):

- `site/`: the real page, built with the storyboard's frames standing in for every film that isn't rendered yet
  (stills that dissolve into one another as you scroll; with a slow camera move at `animatic`), with the real copy,
  layout and style, and a corner badge so it is never mistaken for the finished site.
- `sheet.jpg` (one image an agent can read) and `storyboard.html`: a card per shot (a beat, a take, a product still,
  a block's image) with its frames, prompt, motion, caption, length, the fidelity of its frames (final, stills,
  sketch, placeholder), its status (new, changed since the last storyboard, unchanged, locked, rendered) and the full
  render estimate on this machine, calibrated from the seconds every stage records; the total is at the top.
- `animatic.mp4` at `animatic`: a rough cut with the page's captions in its own fonts and the trailer's end card.

Nothing is thrown away. A beat's still is the very image the beat is animated from (same input, same cache); a
take's frames are its `blockout` and `keyframes` stages, painted over the depth of the blockout the film is
generated along. So an approved frame is the film's first frame and the full build only adds motion. What only the
storyboard makes (a take's sketch, low-sample product stills and the product over its keyframes, motion previews,
placeholder cards) is cached apart, keyed by its samples, and never read by a full build.

Edit one beat and storyboard again: only that shot is redone, in seconds, and the sheet marks it. Editing one of a
take's keyframe prompts repaints only that keyframe. When a shot is right, lock it:

```yaml
beats:
  - id: door
    locked: true      # never re-rendered by storyboard or build, even if its prompt or settings change
```

`locked: true` works on a beat, a take and any scene section; the build logs `locked, kept the existing render` for
each stage it keeps (a locked shot that was never rendered is rendered once). `studio build` prints its plan and
estimate before any heavy GPU work; with `confirm_over = 30` in studio.toml it asks first when a build would run
longer than that many minutes (`--yes` skips the question; without a terminal it stops instead of waiting).

### Edit it, one image at a time

`studio storyboard my-site --edit [--port 8971]` opens the storyboard as an editing workspace (a local server; the same
page is `/sb/<project>` in `studio ui`). Three tabs: **Shots**, **Notes** and **Play**. A card shows what you judge by:
the image or images with their variants, the caption, a *What should change?* box, Regenerate / Re-run / Revert and
Lock / Approve. The exact prompts, edit instructions, motion, seeds and strengths are behind **Advanced** on each card
(and the shared steps behind their own fold), closed until you open them; each browser remembers what it opened.

- **Say what should change.** Type a note in plain words on a card ("warmer light", "she should look older", "less
  grain"), or on the **Notes** tab for the whole storyboard (pacing, tone, copy, order, anything). Notes are an inbox
  in `<project>/storyboard/notes.json`; the page only collects them and shows each one's status (waiting for Claude,
  Claude is on it, done), Claude's reply, and what it led to (the fields edited, the variants added). An agent does the
  interpreting: the MCP tool `storyboard_notes` lists the open notes with each shot's current values and image paths
  (`studio storyboard my-site --notes` prints the same for an agent without MCP); it acts with `set_shot_field`,
  `regenerate_shot_image`, `pick_shot_variant` or by editing `site.yaml`, looks at the result, and calls `resolve_note`
  with a short reply. The page refreshes by itself when the spec, a variant or a note changes, wherever the change came
  from, and **Not quite** sends a note back with a follow-up.
- **Edit any field** (under Advanced). Caption, prompt, motion, seconds, seed, trim, strength, a take's keyframe prompts and motion
  segments, an edit's instruction, a product still's scene and view. Save writes the change into `site.yaml` *in
  place*: only the edited text changes, so comments, column alignment, quoting and line endings stay as you wrote them
  (a change a text splice cannot make, such as switching a source, falls back to ruamel's round-trip dump with the
  file's own indentation). The spec is validated first: an invalid value is shown on the card and nothing is written.
  The previous text of every save is kept in `<project>/storyboard/history/` (the last 30; **Undo last save**
  restores it).
- **Regenerate, Re-run, Revert, per image.** *Regenerate* renders one more variant of just that image with a new seed;
  *Re-run* renders it with the same seed after you edited its text; *Revert* goes back to the image that was in use
  before. Only that image's stage runs (a beat's start or end image, an edit, a take keyframe, a product still), through
  the code and cache digests the full build uses, as a background job with its progress on the card. Videos, restores and
  product passes are never started from here. Locked shots refuse, and one job runs per image at a time; jobs share
  ComfyUI with whatever else is queued on it.
- **Variants.** Every render is kept under `<project>/storyboard/variants/<shot>/<image>/` and shown as a strip of
  thumbnails on the card. Click one to make it current: its seed (and text) are written into `site.yaml`, and it is put
  back in the build's cache if that was cleaned, so `studio build` reproduces exactly that image.
- **Shared steps.** A chain of edits (a generated base image, a relight edit, a crop edit per shot) is shown the readable
  way: each card holds only what is its own, with the full chain behind an expander, and the steps several shots share
  are listed once at the top, where one edit reaches every shot that uses them ("Re-run its shots" redraws them).
- **Lock and Approve.** *Lock* sets `locked: true` in the spec. *Approve* is storyboard-only state in
  `<project>/storyboard/state.json`: a badge on the card, listed as "not approved" on the sheet and by
  `studio build --plan`, and read as "changed since approval" once the shot is edited again.
- **Safe beside other editors.** If `site.yaml` changes on disk while the page is open (you, an agent, git), the page
  notices, reloads the values and says which; a save whose fields changed under it is refused instead of overwriting.

- **Play the whole thing.** The **Play** tab plays `animatic.mp4` (every shot at its length, with the page's captions)
  with a timeline of shot markers: click one to jump to that shot; the shot on screen is named and its card is
  highlighted. *Rebuild animatic* cuts it again as a background job from the stills and clips that exist now (it
  renders nothing new: no ComfyUI, no Blender; an image not drawn yet is a placeholder card) and the player says when
  the cut is out of date and which shots changed since. The stand-in page (stills scrolling like the real one) and, once
  `studio build` has run, the real built page play in a frame with an auto-scroll that runs top to bottom (speed, pause,
  scrub; it waits out the page's loader).

Agents drive the same loop through the MCP tools `storyboard_notes`, `resolve_note`, `storyboard_shots`,
`set_shot_field`, `regenerate_shot_image` (returns the new image's path), `pick_shot_variant` and `approve_shot`. *Update sheet* in the page rebuilds `sheet.jpg` and the stand-in
page from the edited spec and what is rendered so far (a sketch-level storyboard: no ComfyUI, images not drawn yet show as
cards); `studio storyboard my-site` does the same at stills or animatic level.

## Styles

`theme: { style: <name> }` changes how a site is experienced: what scrolling does, how content is laid out and
arrives, how sections hand over, what the pointer does and what the call to action is. The same `site.yaml` reads
as a departures board, a comic, a terminal session, a game level or an anime opening. `theme.colors` and
`theme.fonts` still win, so a brand's palette can wear any style.

| Style | What scrolling is |
|---|---|
| `particles` | One swarm of points re-forming into each section's subject |
| `liquid-morph` | One body that morphs; nothing cuts, everything becomes |
| `holographic` | Rotating holographic plates; the information is in the angle |
| `neon-glow` | A night street where signs ignite as you arrive |
| `wireframe-3d` | Flying a camera through a world drawn in lines |
| `glassmorphism` | Windows over a living world moving behind them |
| `kinetic-type` | An instrument made of letters, played by scroll speed |
| `isometric` | A fixed-angle drone over a model world that builds itself |
| `clay-3d` | Soft toys on a table: mass, squash and wobble |
| `ascii-art` | A terminal session that types and prints |
| `gradient-mesh` | Weather: one breathing colour field that shifts with each chapter |
| `comic-book` | Reading a comic page panel by panel |
| `split-flap` | A departures board updating as the clock advances |
| `retro-vhs` | Operating a VCR: play, search, rewind |
| `halftone` | Reading a freshly printed newspaper |
| `bauhaus` | Composing a poster from shapes that persist and change role |
| `pixel-art` | Playing a side-scrolling game |
| `blueprint` | A technical drawing that drafts itself |
| `art-deco` | An opening night: doors, sunbursts, marquees |
| `neo-brutalism` | A desk you fill up and can mess with |
| `anime-intro` | Scrubbing the playhead of an anime opening, cut by cut |
| `flipbook` | Thumbing a pad of pencil drawings, one page per notch |
| `pop-up-book` | Opening a pop-up book: scenes fold up out of the gutter, tabs pull |
| `pinscreen` | A lamp-lit wall of pins; each picture rolls into the next in a wave |
| `sand` | A backlit sand table; a hand sweeps the grains into each scene |
| `zoetrope` | The page is one wheel of cards: spin it, land on one, open it to read |
| `stop-motion` | Scroll fires the shutter: felt and clay sets step on twos, dead still between exposures |
| `paper-cut-out` | Paper sheets swing off brass brads; hinged pieces sway, a jointed paper arm points |

```bash
studio looks examples/halcyon            # dist/looks/<style>/ for every style, plus a gallery at dist/looks/
studio looks my-site --styles split-flap,comic-book,anime-intro
```

### Art in the style's own medium

`theme.art` gives a style a picture to draw in its own medium. Describe it and it is generated locally (Z-Image); add
`motion:` and LTX-2.3 animates it into a seamless loop. `ascii-art` prints it in characters in the hero and plays it
in the render pane; `particles` fills the whole first screen with it as a field of points that drifts apart as you
scroll.

```yaml
theme:
  style: ascii-art
  art:
    prompt: "a basketball player dribbling on an empty court, side view, black background, strong rim light"
    motion: "he dribbles the ball low and steady, the camera stays still"
    label: "dribbling, frame by frame"
    seconds: 3          # 1-8 seconds of motion
    frames: 36          # frames kept for the loop
    width: 220          # detail of the sheet the runtime draws from
```

Use `file:` instead of `prompt:` to start from your own image. Plain, high-contrast subjects on a dark or light
background read best. Animation needs ComfyUI running (docs/INSTALL.md); a still needs only the image model.

A style is a folder (`engine/styles/<name>/`: tokens, stylesheet, its own block markup and page chrome) plus a
runtime module (`runtime/src/styles/<name>.ts`) with its scroll controller; the contract is in
[engine/styles/README.md](engine/styles/README.md) and the research behind each one in [docs/styles](docs/styles/).

## Your product, declared once

Declare the product a site is about once, at the top of `site.yaml`, and every part of the site uses the real thing:

```yaml
product:
  name: Flipper Zero
  maker: Flipper Devices
  url: https://flipperzero.one
  model: https://example.com/flipper-zero-body-3d.stp   # GLB/glTF, OBJ, FBX, STL, PLY, STEP/STP or 3MF; file or URL
  licence: GPL-3.0
  concept: true                  # footer: "Concept page. Not affiliated with Flipper Devices."
  rotation: [0, 90, 0]           # up / units / rotation fix any file's axes and scale
  parts:                         # materials by part name (globs), material name, or a region of a one-piece body
    - { match: "*", color: "#e9e7e0", roughness: 0.55 }
    - { match: "*", region: [0.235, 0, 0.28, 0.62, 0.35, 0.85], facing: front, color: "#111214", roughness: 0.05 }
sections:
  - type: hero
    title: A pocket multi-tool for hardware.
    image: { product: three-quarter, size: [1920, 1080] }          # a Cycles still, cached
  - type: product
    title: Every port where you need it.
    image: { product: { view: detail, part: "*usb*" } }            # a macro view of one part
  - type: product
    title: On your desk.
    image: { product: hero-low, scene: "a walnut desk by a window, morning light" }
  - id: live
    type: showroom                 # the real model live in the page: scroll turns, explodes and zooms it
```

The engine converts the model (STEP through OpenCascade, keeping every part and its name; 3MF through trimesh),
fixes its axes and units, centres it on its base, applies the part materials, decimates only an absurdly heavy file
and caches one GLB. `studio product <project> --parts` lists the part, assembly and material names to target;
`studio product <project> --still exploded` renders a still. Views: `front`, `three-quarter`, `side`, `top`, `back`,
`hero-low`, `exploded` (when the model has parts) and `detail` (with `part:`). A still is transparent where the page
can show it (hero and product blocks) and on the theme background elsewhere; `scene:` paints a place around it with
Z-Image to the still's own camera, lights the product with that place, and blends it in with a light Qwen-Image-Edit
pass (checked: if the edit changed the product, the rendered product is put back through its matte).

A take's `product: {}` and a sequence's `model: product` use the same model, materials and credit; the credit and
licence go in the footer automatically.

## One Take, places and data

A `film` scene with a `take:` is one continuous shot. `objects` are rough shapes (`box`, `cylinder`, `cone`, `blob`,
`plane`, `scatter` for forests or towns), `camera` is a list of `{t, at, look}` keys, and `product` is your 3D model
(`model: inputs/bottle.glb`, `from_photo:` with TRELLIS configured, or `product: {}` for the site's product) standing
at a point in that world. The world is generated; the product is rendered through the same camera and lit by the plate
itself (environments built from the generated frames, the sun along the take's light, its shadow and occlusion on a
ground of the plate's colour), with depth of field and motion blur, then graded to the plate (black level, white
balance, saturation, softness, grain, a light wrap). `hdri:` picks a studio light instead:

```yaml
  - id: take
    type: film
    take:
      duration: 15
      objects:
        - { kind: box, name: Table, at: [0, -5, 0.75], size: [1.6, 0.9, 0.06], color: "#9a7b56" }
        - { kind: scatter, count: 60, area: [-120, 40, -30, 140], height: [6, 14], shape: cone, color: "#3f5538" }
      camera:
        - { t: 0, at: [-70, 190, 70], look: [0, 40, 6] }
        - { t: 15, at: [1.6, -3.4, 1.3], look: [0, -5, 0.95] }
      product: { model: inputs/bottle.glb, at: [0, -5, 0.78], height: 0.27 }
```

For detail, render the world at `ltx: { res: [1920, 1088] }` (multiples of 32; 1024x576 is a quick draft) and add
`restore: 1080`: SeedVR2 cleans and redraws the generated world before the product is composited, so the real
product is never touched by restoration.

A `splat` scene takes a scan (`source: inputs/house.ply` or a gsplat checkpoint) and camera `keys` with `{t, at,
look}`; the build trims faint and oversized splats, keeps the `max_splats` most visible and writes SPZ.

A `chart` can carry `callouts` resolved from the data (`{series: Denmark, at: last, label: "Denmark {y} in {x}"}`;
`at` is `max`, `min`, `first`, `last` or an x value), and a `stats` item can take its number from a chart:
`{ unit: "%", label: World share, data: { section: share, series: World, at: last } }`.

### A story in shots

A `film` with `beats:` tells a story shot by shot. Each beat is a still generated from its `prompt` (or your own
`image`), brought to life by its `motion` with LTX-2.3, and the shots are joined with short crossfades. Every beat is
cached on its own, so changing one shot re-renders only that shot. Steps pin themselves to a beat with
`state: { beat: <id> }`:

```yaml
  - id: story
    type: film
    length: 26
    beats:
      - id: door
        seconds: 5
        prompt: A weathered wooden door standing alone in an endless desert at dusk, warm light through the gap, photoreal
        motion: the door swings open, golden light and dust pour out, the camera pushes in
      - id: clash
        prompt: Two hoplite shield walls colliding on a dusty plain, bronze and red cloaks, low angle, photoreal
        motion: the shield walls crash together, dust bursts outward, slow motion
    steps:
      - { title: A landing page is the door <em>to a world.</em>, intro: true, state: { beat: door } }
```

`beat_res` sets the render size (default 1920x1088; about seven minutes a five-second beat on an RTX 4090). LTX animates
slow, camera-led motion best; for an action shot that holds its first frame, lower `strength` (0.7-0.85), re-roll the
motion alone with `motion_seed`, and cut the hold with `trim` (seconds, re-uses the render).
Example: [Feel](examples/feel/site.yaml).

### A frozen moment

When time stops, stop generating. A video model cannot hold a crowd still while the camera moves (the people melt and
drift), and redrawing close-ups with an image editor gives every close-up different faces. A beat with `freeze:` is
not generated at all: it takes one frame, upscales it, estimates its depth (Depth Anything V2) and flies a 2.5D camera
through it, offline, in seconds. Every pixel of the clip is a pixel of that one frame, so a woman's face is the same
face in the wide shot and in the close-up of her hand. The clip joins the film like any generated beat: same stage,
cache, `trim`, crossfade, `beat_restore`, `locked`, `build --only`, storyboard card and editor fields.

```yaml
    beats:
      - id: walk
        seconds: 5
        prompt: A crowd walks toward the camera across a plaza, a woman and a man side by side in the centre
        motion: the crowd walks steadily toward the camera, the camera tracks backward in front of them
        image: inputs/crowd.png
      - id: freeze
        seconds: 12
        freeze:
          from: walk              # the last frame of a beat (its sharpest of the last 6), or `image:` (any image input)
          upscale: 2              # SeedVR2 image restoration through ComfyUI, so crops stay sharp
          camera:                 # keyframes over the beat (0-1): a framing box [x0, y0, x1, y1] in the frozen frame
            - { t: 0,    box: [0, 0, 1, 1] }
            - { t: 0.3,  box: [0.25, 0.2, 0.75, 0.68] }
            - { t: 0.55, box: [0.26, 0.42, 0.58, 0.753], hold: 0.1 }      # rest on the hands for 10% of the beat
            - { t: 0.8,  box: [0.34, 0.732, 0.6, 1.0] }
            - { t: 1,    box: [0.25, 0.2, 0.75, 0.68] }
          parallax: 0.6           # the 2.5D depth effect (0 = flat Ken Burns); the subject plane stays put
          ease: inOutSine         # or flow: keep moving through keys instead of resting at each
          grain: 0.012            # a faint film grain so it matches the generated shots
      - id: walkon                # starts exactly where the frozen moment ends
        prompt: They walk on, the camera pulls back
        motion: time starts again, the two of them walk toward the camera, the camera pulls back
        image: { beat_frame: { beat: freeze, at: last } }
```

- **The frame.** `from: <beat id>` freezes that beat's last frame after its `trim`. A moving shot's very last frame is
  often motion-blurred, bad for close-ups, so `pick: sharpest` (the default) takes the sharpest of the last
  `pick_window` frames (6), measured inside the boxes the camera will look at; `pick: last` takes the very last.
  `image:` freezes any image input instead (a file, `generate:`, `edit:`, a crop, a `beat_frame`).
- **The camera.** Boxes are in 0-1 of the frozen frame; the aspect comes from `beat_res`, so a box of another shape is
  widened (never cropped) and everything inside it stays in frame. The camera arrives at each box at its `t`, rests for
  its `hold`, and travels to the next one along an eased path with no jerk at the keys (`ease`: inOutSine, inOutQuad,
  inOutCubic, inOutQuart, linear, or `flow`, one smooth curve that keeps its speed through keys and rests only at holds
  and at both ends). A full-frame box at `t: 0` makes the first frame the frozen frame itself, so the cut from the
  shot it froze is invisible.
- **The depth effect.** The camera sways a little and pushes near things in as it closes up (`parallax`, `dolly`),
  against a focus plane that follows the middle of the view, so the subject holds still while the crowd around them
  shifts. The sway fades out where the view is too near the frame's edge to move. `parallax` 0.3-0.8 is clean; above 1
  you see stretching behind foreground edges (it is one photograph: nothing behind a person was ever drawn).
- **Sharp crops.** `upscale: 2` (1-4) enlarges the frame before the camera crops into it. `upscale_method: auto` uses
  SeedVR2 (the 7B sharp model, through ComfyUI, about two minutes for a 1920x1088 frame at 2x) when ComfyUI lists its
  weights, else a local Lanczos + sharpen that is honest but soft; `seedvr2` and `lanczos` force one. SeedVR2 redraws
  fine detail (wool, stitching, fingernails), so look at the close-ups.
- **Cheap to iterate.** The frame, the upscale and the depth are cached apart from the camera: changing a box, the
  parallax or the ease re-renders in seconds (about 20 s for 12 s of film at 1920x1088 on an RTX 4090) and never
  repeats the upscale. `blur` (0-1, the shutter) adds motion blur by averaging sub-frames.
- **Chaining.** `image: { beat_frame: { beat: <id>, at: first | last | <seconds>, pick: last | sharpest } }` is the
  frame of any beat, so a generated beat can start exactly where a frozen moment (or another generated beat) ends. A
  beat that uses it re-renders when that beat's clip does. Under `build --only`, a beat that is not rendered stands in
  with its storyboard still instead of failing.

The render is an inverse parallax warp in torch (a ray marched through the depth map per pixel, so the nearest surface
wins at an edge), on the GPU when there is one and the CPU otherwise; it needs no Blender session. The storyboard shows
the camera's boxes as flat crops of the source before anything renders, and `build --plan` prices a frozen beat apart
from a generated one.

### Deep zoom and layered depth (`freeze.detail`, `freeze.layers`)

A frozen frame has only so many pixels: at a box a twentieth of the frame wide, 1920 px is a thumbnail enlarged twenty
times (the 2x upscale buys one factor of two), and one depth map warped over one picture smears at every depth jump.
Two fields on a frozen beat fix those.

```yaml
      - id: push
        seconds: 14
        freeze:
          image: inputs/street.png
          upscale: 2
          camera:
            - { t: 0.0,  box: [0, 0, 1, 1] }
            - { t: 0.4,  box: [0.455, 0.80, 0.555, 0.96], hold: 0.05 }     # her boots
            - { t: 0.55, box: [0.485, 0.845, 0.53, 0.89] }                 # a 22x close-up of the boot's top
            - { t: 1.0,  box: [0, 0, 1, 1] }
          detail: { prompt: "hand-drawn ink, clean outlines, fine hatching" }   # deep zoom ({} for the defaults)
          layers: auto                                                          # layered depth (or a list of subjects)
```

- **Deep zoom** (`detail`). The frame is built into a pyramid of tiles instead of being enlarged: from the camera's keys the
  engine finds which regions it visits at which scale (`studio freeze <project> <beat> --plan` prints them), as many levels
  as the tightest box needs (`levels: auto` stops when a tile pixel falls on every output pixel; each level adds at most
  `ratio` x the detail of the one above, default 2), and for each tile (a crop of its parent): SeedVR2 enlarges it, Z-Image
  Turbo re-draws it at low `strength` (0.3 by default: fine detail in the picture's own style, nothing moved), it is aligned to
  its parent (ECC), and then it is **given the parent's low frequencies exactly** (`lock`): colours, tone and shapes are the
  parent's at every level, and only what is finer than a parent pixel is new. Its depth is the parent's, snapped to the
  tile's own edges with the guided filter. The render takes every pixel from the finest tile that covers it and fades each
  level in by screen-space pixel density (a mip chain turned inside out), with feathered tile borders: detail arrives as
  the camera does and nothing swaps or pops. Every tile is its own cached stage, keyed by its box and its parent's key:
  moving the deepest box rebuilds only the tiles that moved. Measured on a 14 s push from a 1920 street to a 22x close-up
  (17 tiles, 4 levels): the sharpest edges take 5.6 output pixels at 20x against 11.3 for one upscaled frame (1.4 px at
  1x, 1.8 at 2x), and the sharpness curve along the whole move is smooth: no level swaps. Needs ComfyUI (SeedVR2, Z-Image Turbo); without SeedVR2 the
  enlarge falls back to Lanczos. The Qwen-Image-Edit re-draw (`method: qwen`) understands the picture (it draws laces on
  a boot) but also moves and reshapes things by several percent, which a tile cannot be made to agree with (ghosting), so it is
  experimental. The pyramid sharpens and adds texture; it cannot invent an object the frame does not already contain
  (laces on a black silhouette): for that, give the freeze an `image:` that already has it.
- **Layered depth** (`layers`). The frame is cut into planes, back to front: a **background plate** (the frame with the
  subjects painted out: Qwen-Image-Edit through the subjects' mask, pixel-exact outside the hole) and **subject planes**
  (`subjects: auto` finds every person with Florence-2 and cuts each out with SAM 2.1, or list `{prompt}` / `{box}` / `{points}`
  subjects; subjects at a similar depth share a plane, at most `planes`). Each plane has its own smooth depth and a soft alpha
  edge, and its colour has the plate's share removed at the edge, so it carries no fringe of the old background. The render
  marches and samples the planes one after the other and composites them: at rest the result is the frame, and when the camera
  moves a person slides over the background instead of smearing, with real background revealed where they stood. The planes
  are cut from the same picture, and with `detail` from the same tiles (each tile carries its planes' alphas, refined at its
  resolution, and continues the plate), so a layered deep zoom costs one attribute per plane per tile, not a pyramid per
  plane, and every level agrees by construction. `planes.jpg` in the beat's `layers/` folder shows what was found.
  Limits: an occluded part of one person behind another is not drawn (the plate shows through instead); a plate fill
  leaves a faint pale ghost of the removed shape where the fog is uniform; and SAM cuts a person who is nearly the colour of
  the fog out only in part (look at `planes.jpg`): the part left behind stays in the background plane and tears off the
  person when the camera sways. Name such a subject with `points:` on its body, or keep `parallax` low.
- **Measuring it.** `studio freeze <project> <beat> --report [--against <other beat>]` renders and measures the clip: how
  many output pixels the sharpest edges take at each zoom the camera reaches (a crisp edge is 1-2 px), a frame-to-frame
  difference plot with its spike ratio (a pop stands out of the curve), and a frame strip, written beside the clip.
### A camera move on a moving shot (`camera:`)

A video model takes camera direction only as words, and mostly ignores them, so "the crowd keeps walking while the camera
pushes in to the girl" used to be a clip, then a cut to a still. A beat with `camera:` keys gets the camera it asks for
by construction. The keys have the shape of a frozen moment's (`{t, box, hold}` and an `ease`), but the beat is still
generated, so people walk, traffic moves and fog drifts:

```yaml
      - id: push
        seconds: 5
        prompt: A hand-drawn faceless crowd walking toward the viewer, one girl in the centre
        motion: everyone in the crowd walks steadily toward the viewer down the foggy street
        image: inputs/street.png
        camera:
          keys:
            - { t: 0.0, box: [0, 0, 1, 1] }                  # the wide street
            - { t: 0.5, box: [0.40, 0.38, 0.62, 0.97] }      # the camera has reached the girl
            - { t: 1.0, box: [0, 0, 1, 1] }                  # and is back out again
          subjects: the people                               # who is free to move (default)
```

What happens, each step cached by its own digest in the beat's folder:

1. **Depth and people.** The beat's start image gets a depth map (Depth Anything V2) and the moving subjects (`subjects`)
   are found by Florence-2 and cut out by SAM 2.1, the way `edit.region` does.
2. **The guide.** The camera path is flown through that depth with the same renderer a frozen moment uses (parallax and
   all), as a depth video. The subjects' depth is blurred into soft blobs (`soften`), so the guide fixes the camera and
   the static world (street, buildings, lamps) and only hints where the people are. Two more videos come with it:
   `guide_rgb.mp4`, the picture itself flown along the keys (a pure-camera preview you can look at before a minute of GPU
   is spent: `studio camera <project> <beat> --guide`), and `guide_static.mp4`, where the static world is.
3. **The shot.** LTX-2.3 (the IC-LoRA depth control a take uses) paints the beat along the guide from the start image,
   with frames of the pure-camera render pinned along the way (`anchor`: once a second and at the end, which keeps the
   subjects' looks and sharpens close-ups). It runs at about 1024x576 (`camera.res`; at 1536x896 the girl's black coat
   turned white in a test) and is scaled to `beat_res`: add `beat_restore: 1088` to the film for the fine detail. `backend: wan` runs Wan 2.2 Fun Control on
   the same guide; `backend: uni3c` is Wan's camera controlnet (needs a file that is not installed by default, see
   docs/INSTALL.md; the engine fails with its name, URL and folder when it is missing).
4. **The measurement.** `studio camera <project> <beat> --check` registers every generated frame against the first on the
   static world and reports how far the camera is from the keyed view (zoom error in %, shift in view widths), how far the
   people walked, and what a perfect camera scores on the same measurement; it writes `camera.json` and a contact sheet.

Beats that **continue** one another share one camera. `camera.continues: true` makes the beat start where the previous
camera beat ended, at the speed it ended at (a chain flows as one smooth path and rests only at its ends and on holds, so
there is no ease to a stop at the cut), start on that beat's last frame (`beat_frame`, exactly, unless it names an
`image`), and fly its guide through the chain's base plate (the first beat's start image: the world every beat of the
chain looks at, so a camera that pulls back out of a close-up has the wide street to fly through). Its frames are graded
back toward the plate's tone and grain (`match`, 0.7 when continuing), which stops a clip-to-clip drift in contrast, haze
and grain from showing at the cut.

```yaml
      - id: in                      # pushes in and is still moving when the beat ends
        seconds: 3
        image: inputs/street.png
        prompt: ...
        motion: ...
        camera: { keys: [{ t: 0, box: [0, 0, 1, 1] }, { t: 1, box: [0.18, 0.10, 0.82, 0.80] }] }
      - id: out                     # carries on to the girl and back out, starting on the last frame of `in`
        seconds: 3
        prompt: ...
        motion: ...
        camera:
          continues: true
          keys: [{ t: 0.5, box: [0.40, 0.38, 0.62, 0.97] }, { t: 1, box: [0, 0, 1, 1] }]
```

`trim` and `end_image` do not combine with `camera` (the keys are timed over the whole clip; the path decides the last
frame). Cost: the depth and the people mask once per start image (about a minute, mostly model loading), the guide in
seconds, the shot as long as any LTX beat of that length (about 10 minutes for 5 s on a 4090). Changing a box re-renders the guide and the shot, not the depth.

### Edit only inside a region (`edit.region`)

A plain image edit (Qwen-Image-Edit) redraws a little of everything: ask for richer shoes and the crowd around them
shifts too, so two versions of the same frame shimmer when one dissolves into the other. With `region` the edit may
change **only** part of the picture; everywhere else the result is the source image, pixel for pixel. A landing page
can freeze a frame of a crowd, let the camera visit one person's shoes and then their hands, and have each come into
more detail and colour while the rest of the frame stays exactly as it was:

```yaml
image:
  edit:
    source: { beat_frame: { beat: walk, at: last } }
    instruction: "Redraw her shoes in rich detail: worn leather, laces, stitching, deep brown. Keep the drawing style."
    region: { prompt: "the girl's shoes", pick: largest, grow: 12, feather: 8 }    # or  region: "the girl's shoes"
    seed: 3
```

Chain edits like any others, each region found on the previous result: shoes, then `region: "her hands"` with the shoes
edit as its `source`, then the whole girl. Outside each region the pixels equal that step's own source.

How it works. (1) **Find**: Florence-2 turns `prompt` into boxes on the source (`pick`, `within` and the "X's Y" owner
test work as in `reveal`; or give `box` / `points` in 0-1 picture coordinates, `negative_points` for what to leave out),
and SAM 2.1 cuts a precise mask at the source's resolution. (2) **Shape**: `grow` widens the mask (pixels of the source;
the edit may redraw that much beyond the thing itself, which helps it blend), `feather` softens its edge, `invert: true`
edits everything except the region. (3) **Edit**: by default the editor is shown a padded **crop** around the region
(`context`: how much surrounding, as a share of the region's size, 0.6 by default) rather than the whole picture. The
editor works at a fixed size (about 1.6 megapixels), so a small region in a big picture gets several times the pixels a
whole-image pass would give it, and that is where real detail comes from; the surroundings in the crop keep its colour
and style consistent. `scope: image` shows it the whole picture (always used with `invert`). (4) **Composite**: the
result is blended back through the feathered mask with integer arithmetic at the source's own size, so where the mask
is 0 the output pixel *is* the source pixel. Colour and tone at the seam are the edit's job (say what colour and light
you want in `instruction`); the feather only hides the join.

The mask is kept beside the image: `.build/_generated/edit_<digest>.mask.png` (the exact compositing weight), plus an
`.outline.png` overlay for review and `region_<digest>.boxes.jpg` (the boxes Florence-2 found, drawn on the source).
`studio storyboard` draws the outline on a card whose image is a region edit, and the edit workspace (`--edit`) shows it
over the image (a **region** button switches it off) with the region's prompt, `pick`, `grow` and `feather` as fields;
a region given as a bare string becomes a mapping when you edit its other fields. Cache: the region is part of the
edit's digest only when set, so nothing already rendered is redrawn. The region is found on each source once (it is
cached by the source's content and what names the region), so changing only `seed`, `instruction`, `feather` or `grow`
reuses it. `ComfyUI` needs the same nodes as `reveal` (`studio setup-comfy`).

### Colour that follows the camera (`reveal:`)

Say you want a black-and-white crowd with a couple in it, and colour that comes into exactly the part the camera looks
at: her hand, then their shoes, then the two of them, while the crowd stays grey. Asking a video model to colour only
the hands colours the crowd, reframes and changes faces. So the film is rendered **once, in full colour**, and the
page reveals the colour region by region from tracked masks, in the browser, driven by scroll. Any film section can do
it (beats, a take, or your own `video:`), and any site can "bring the product into colour" as you scroll:

```yaml
    reveal:
      base: mono              # what un-revealed pixels look like: mono, dim, blur, or a tint colour such as "#2a4a6a"
      regions:
        - { id: her_hand, prompt: "the woman's hand", pick: left, at: { beat: hands, t: 0.5 } }
        - { id: shoes,    prompt: "the shoes of the woman and the man", at: { beat: feet, t: 0.5 } }
        - { id: couple,   prompt: "the woman in the long coat and the man in the jacket", at: { beat: walk, t: 0 } }
      keys:                   # scroll progress of the section (0-1) -> how revealed each region is (0-1), eased
        - { at: 0.40, her_hand: 0 }
        - { at: 0.48, her_hand: 1 }
        - { at: 0.55, shoes: 0 }
        - { at: 0.62, shoes: 1 }
        - { at: 0.70, couple: 0 }
        - { at: 0.80, couple: 1 }
      feather: 6              # mask edge softness, px at film size
```

How it works: each region is described (`prompt`, found on its `at` frame by Florence-2) or pointed at (`points`,
`box`, in 0-1 picture coordinates), then followed through the film by SAM 2.1's video predictor, forwards and
backwards from that frame, **inside its shot** (a cut ends a track: tracking never runs across one, so a region
shows only in shots where it has an `at`; give it one `at` per shot it must show in: `at: [{beat: walk, t: 0}, {beat:
seen, t: 0.5}]`; a non-beats film's cuts are found by scene detection, or listed in `reveal.cuts`). The masks are packed
(up to four per video) into grayscale videos with the film's own frame rate, frame count and keyframe interval, and the
page draws each frame of the film through a small WebGL2 shader: the base look everywhere, colour where mask x reveal
amount, a film frame and its mask frames always from the same frame number (a seek goes to both videos and the canvas is
drawn only when both have landed). Without WebGL2 the colour film plays as it is; with reduced motion each region jumps
to colour as its moment arrives; phones get half-size masks and a 1280-wide canvas.

A prompt that matches several things (both hands) reveals all of them unless you narrow it: `pick:` (`first`,
`largest`, `smallest`, `left`, `right`, `top`, `bottom`, or an index), `within: "the woman in the long coat"`, or a
prompt shaped "the X's Y" / "the Y of the X", which does that by itself; for the awkward cases give `points`. Each
region leaves `ground.jpg` (the boxes it found) beside its masks in `.build/<section>/reveal/<id>/`. `grow:` widens or
shrinks a finished mask in pixels; `tracker: base_plus` uses the smaller SAM 2.1.

Everything is cached per region: the film, the prompt, its frame and the model are its key, so editing `keys:`,
`feather` or `base` re-packs in seconds and re-tracks nothing. The storyboard draws every shot the way the page will
show it (base look; with masks from a full build, the colour at that moment), and the animatic is cut from those frames.
It runs on ComfyUI with `studio setup-comfy` (below) and about 2 GB of models.

### One place, dawn to night (`type: light`)

A section that is one place and a whole day. The scene takes a single picture of the place (a photo, a generated image,
or another scene's still) and relights it into each time of day with the geometry locked; scroll then moves
*continuously* through the day instead of cross-fading a slideshow. Each step of the section sits at a time of day, and the
section's own colours (ink, accent, the shade behind the text) follow the sky.

```yaml
- id: day
  type: light
  world:
    generate: "wide photograph of a small stone harbour town around a calm bay ..., even daylight, no people"
  world_time: noon                       # the world picture IS noon: used as it is, the anchor everything is measured against
  times: [dawn, morning, noon, golden-hour, blue-hour, night]     # presets, or free text ("low green storm light")
  lamps: [{ prompt: the street lamps and the lit windows }]       # what switches on: cut out with Florence-2 + SAM 2.1
  steps:                                 # the sections of the day, in order (or pin one: state: { time: night })
    - { kicker: "Quay House", title: "The harbour <em>wakes first.</em>", intro: true }
    - { kicker: "Morning",    title: "Coffee on the quay, <em>before anyone.</em>" }
    - ...
```

**Build** (one cached stage per time: `world`, `depth`, `sky`, `time_<id>`, `maps`, `web`; an unchanged spec rebuilds nothing,
and changing one time's words redoes that time only). Each time is the world relit by Qwen-Image-Edit with an instruction that
changes only the light (`engine/light_presets.py`: dawn, sunrise, morning, noon, afternoon, golden-hour, sunset, blue-hour, night,
overcast, storm; a time can also be free text, or `image:` a picture of your own). The geometry lock has three parts, because an
editor left to itself redraws the place (measured here: 11 to 16 px of drift at 1024 across, windows and houses reshaped):
1. **Start from the world.** The edit samples from the picture's own latent (`structure.strength`, the denoise strength, 0.88
   by default), so the layout is held: 0.75 moves things about 1 px, 0.88 a few, 1.0 (from noise) 11 to 16 px.
2. **Measure, undo the global move, retry.** Structure is compared in a light-invariant way (band-passed log luminance,
   locally normalised); dense optical flow gives the displacement, and `drift` is how far things are from where they were, in px at
   1024 across. What the editor does to a place is mostly a global zoom and shift; a robust affine fit undoes it and bends nothing
   (`structure.align: affine`; `flow` also pulls local structure in, which matches edges better but makes lines wobble; `none`
   measures only). A relight still over `structure.max_drift` is redone with another seed (`retries`) and the best kept.
   `structure.chain` relights each time from its neighbour nearer the world's time instead of the world, so neighbours agree more.
   On the Quay House example (six times, seed 7 base): the editor moved the place 5 to 24 px (mean, at 1024 across) and left
   0.0 to 4.4 px after its global move was undone; edge agreement went from 0.40-0.69 to 0.70-0.86 (what stays under 1.0 is the
   light itself changing which edges exist at night). Night needed `strength: 0.96` to get dark; at 0.88 it stays a moonlit dusk.
3. **Glide over what is left.** Between neighbouring times the build writes a flow texture of the structure that still differs;
   the page glides along it as the light changes, so edges slide into place instead of cross-fading doubled.

Between neighbouring times the build also writes the low-frequency light-change field (edge-aware, log-encoded) and a map of the
lights that turn on or off (small bright features that the change of ambient light cannot explain, each with its own delay and a
halo; `lamps:` confines them to regions named with Florence-2 and SAM 2.1). `studio light <project>` reports drift, edge
agreement and glide per time and pair.

**Play** (`runtime/src/players/light.ts`, WebGL2): scroll maps to a time of day with a hold at each step (`hold`) so a headline
reads in its own light and the change passes between headlines. Between two times the shader carries the light's low-frequency
change across both pictures (so nothing dips to grey half-way), switches the rest (shadows, lit and unlit surfaces) with a front
of new light that spreads from where it arrives, reaching the sky first and the near ground last, brings windows and lamps on one
by one with a halo, draws the times' `haze` as mist that thickens with distance and drifts, and breathes the place with a slow
2.5D drift through the world's depth map (`drift`). Optionally a sun and moon glow travels over the sky (`sun`). A clock and sun arc
in the corner show the hour. Phones get a smaller picture set and a `focus` crop; prefers-reduced-motion gets one still per step
(no drift, no blending); without WebGL the stills are plain images, one per step. Scrolling is never captured: it is the
page's own scroll.

`studio light <project> [--section day]` builds the section and writes `light/<id>/`: `sheet.jpg` (every time with its measured
drift), `strip_*.jpg` (the built page across each transition, at the scroll positions a viewer passes through) and `light.json`.
`studio light --presets` lists the named times. Example: [Quay House](examples/harbour-light/site.yaml).

### Faces, repaired (`faces: restore`)

Generated video bends faces. `faces: restore` on a film or on a beat repairs them after generation: faces above
`min_size` pixels are found in every frame (RetinaFace), restored with GFPGAN v1.4 (Apache-2.0; CodeFormer is left out,
its licence is non-commercial), blended back through a soft face mask, and the change is smoothed over time in the
face's own aligned space so it never flickers. Off by default, cached by the clip and the settings:

```yaml
    beats:
      - { id: walk, prompt: ..., motion: ..., faces: restore }                              # this beat
    faces: { strength: 0.7, min_size: 96, smooth: 0.6 }                                    # or the whole film
```

About 0.7 s per frame of 1080p on an RTX 4090 with two faces in view. `studio setup-comfy` installs the nodes and
weights.

### Find the polish problems before the owner does (`studio inspect`)

```bash
studio inspect my-site [--section story] [--json] [--embed] [--video recording.mp4]
```

A finished film (beats, a take or any `video:`) is scored second by second and beat by beat, on the CPU, for the five
things people see without being able to say why, each measured so it can be said in a sentence:

| | what it measures | how it reads |
|---|---|---|
| **Pops** | a frame change that motion cannot explain, over a large part of the picture; a one-frame flicker; judder (motion updating under 12 times a second); and the dissolve between two beats that are meant to be one scene but do not line up (a double image, a colour change) | "Crossfade shoes to hands: at mid-fade 90% of the edges differ, so a double image shows" |
| **Softness** | how much fine detail the busiest parts of the frame hold (a frequency-domain index, so a soft-focus photograph is not mistaken for an upscale), with the edge width in pixels beside it | "only 2% of the fine detail of this film's sharpest frames is left here (edges 3.1 px wide), as if enlarged" |
| **Halos** | the share of clean edges with a bright rim or seam beside them, against the film's own usual share | "19% of the clean edges have a bright rim, 6.2x this film's usual 3%" |
| **Style drift** | how far the look moves from the scene's first second: the share of the picture's structure that is weak hatching or pencil texture (drawn styles), grain, and, within a still shot, tone, line density and saturation; `--embed` adds a CLIP image-embedding distance (local OpenCLIP weights only, nothing is downloaded) | "66% of the structure is soft hatching, against 37% at the start of the scene (sketchier)" |
| **Morphs** | the share of the change between frames that optical flow cannot explain: things appearing, dissolving or rearranging instead of moving | "93% of the change is things rebuilding themselves rather than travelling" |

Beats that join like one scene (the two frames that meet look alike) are judged as a continuation; a join between frames
that look nothing alike is a scene change, a dissolve on purpose, and is never flagged. It writes
`.build/inspect/<section>.json` (the contract: per-beat scores 0-100, issues with a level, time span, reason and what to
try, a per-second timeline) and `<section>.html`: a timeline strip of every metric by second, the worst moments as
pictures (before and after, the dissolve's three frames, a 1:1 crop with the rim pixels marked) each with one line saying
what is wrong, and a score table per beat. Reports are cached by the film's content (a copy of a build is the same key;
an unchanged film answers at once), a rebuilt beat re-measures. The storyboard editor (`studio storyboard --edit`) shows a
badge on every beat card with its worst problem, linking to the report, and a **Polish check** button; MCP: `inspect_film`.
`--video` judges any video file as one shot, e.g. a `studio record` scroll-through.

### Two video models: LTX-2.3 and Wan 2.2

Beats, takes and `theme.art` animate with LTX-2.3 by default. `video_model: wan` switches to Wan 2.2 A14B, a second
local model: a pair of 14B experts (one lays out the motion, the other paints the detail) that renders at its native
~1280x720 and 16 fps, retimed to 24 fps with FFmpeg's motion-compensated interpolation and restored to 1080p by the
SeedVR2 stage (`beat_restore`, `take.upscale`). Choose it for the whole site, or per beat, take or art:

```yaml
video_model: wan            # site default (else studio.toml's video_model, else ltx)
wan: { quality: fast }      # fast: 4-step lightx2v LoRAs, cfg 1 · full: ~20 steps, cfg 3.5, no LoRAs (slower)
sections:
  - id: story
    type: film
    beats:
      - id: door
        video_model: wan    # per beat; `image` is the first frame and `end_image` the last (first-last-frame)
        ...
  - id: take
    type: film
    take:
      video_model: wan      # Wan 2.2 Fun Control paints the world along the Blender depth guide
      wan: { quality: fast }
      ltx: { segments: [...] }   # the same segments and prompts drive either model
```

A Wan clip is at most 81 frames (~5 s). A beat a little longer than that (up to `wan.stretch`, 1.35x) is one clip
played slower; a longer one chains clips, each starting on the last frame of the one before, with the end image on
the last. In a take, every segment is cut into clips of at most 81 frames along the depth guide; the first clip starts
on the keyframe at its start time and each clip takes the keyframe inside its range as a reference still. The product
pass is unchanged, so the real product stays locked to the same camera. Both models' renders are cached side by side
(a take's Wan render lives in `.build/<section>/wan/`), so switching back and forth costs nothing, and LTX caches made
before `video_model` existed stay valid. `studio doctor` lists every Wan file ComfyUI can see; file names that differ
from the defaults go in `studio.toml` under `[wan]`.

Which to use: on the Feel door beat (start and end image given) the two land the same motion and, after SeedVR2, LTX
still shows the finer texture (it renders beats at 1920x1088; Wan at 1280x720), so LTX stays the default. Wan earns its
place in takes, where Fun Control at 1280x720 paints a crisper world than LTX at the example's 1024x576 and follows the
guide's shapes closely (blur the guide, `wan.guide_blur`, when a blockout box should become something better than a
box). On an RTX 4090 an 81-frame Wan clip samples in about 2.5 minutes (fast) or 25 (full), plus about 4 minutes to
load each 14B expert from a hard disk when they aren't already in RAM.

### Flying through code

A `code` scene follows an AI agent through a codebase in live 3D, with real, readable text. It opens on the agent's
prompt box (`terminal`), the task types itself, and the camera dives through the screen into the project. Files the
agent `read`s line a corridor, each `edit` is a stop where the diff applies itself as you scroll (removed lines light up
and fold away, new ones type in), and a `run` prints its output line by line. A status bar ticks off each file's `todo`.
Steps pin themselves to the route with `state: { file: <path> }` (or `terminal` / `outro`), so captions never need
progress numbers:

```yaml
  - id: session
    type: code
    length: 20
    terminal: { logo: "open|code", prompt: "add a field that validates signups are 18+", model: Claude Opus 4.5 }
    files:
      - { path: config/fortify.php, file: inputs/fortify.php }            # read
      - path: app/Models/User.php
        kind: edit
        todo: "User model: fillable + cast"
        code: |2
           protected $fillable = [
               'name',
          +    'date_of_birth',
           ];
      - { path: php artisan test, kind: run, file: inputs/test-output.txt }
    steps:
      - { title: Every change, <em>a diff you can follow.</em>, state: { file: app/Models/User.php } }
```

For an edit, start each line with `+`, `-` or a space, like a diff (use `|2` so YAML keeps the leading markers).
`tree` lists more paths to scatter around the route so it reads as a whole project.

## Launch trailers

`studio trailer my-site` cuts a launch film from what the site already rendered, in 16:9 and 9:16, with no extra
generation: `dist/trailer/trailer-16x9.mp4`, `trailer-9x16.mp4` and a poster beside each (H.264, yuv420p, CRF 18,
faststart; ready for X, TikTok, Reels and Shorts). `trailer: {}` derives the cut: a hook shot, the middle of the
story, the product reveal, feature callouts and an end card, each captioned with the site's own headlines.

```yaml
trailer:
  bpm: 100                       # every cut lands on the beat grid
  music: inputs/track.mp3        # optional, local; trimmed, faded and loudness-normalised (-14 LUFS)
  url: stillwater.example        # end card: name, tagline, call to action, address, disclaimer
  embed: true                    # a "Watch the launch film" button on the opening section
  shots:                         # optional; leave out for the derived cut
    - { section: take, step: 0 }                            # the footage under a step, captioned with it
    - { beat: laugh }                                       # a beat of a story film
    - { card: "One take. <em>No cuts.</em>", beats: 4 }     # type on the theme background
    - { section: order, beats: 6 }                          # any other section, recorded scrolling
    - { product: three-quarter, callouts: [750 ml, 24 h cold] }   # a product still (needs site.product)
```

The 9:16 cut is reframed, never letterboxed: in a take the crop follows the product through the take's own camera
(`take.py --pass track`), cuts the reveal where the product is biggest in frame and pushes in on it as far as the
source resolution allows; other footage follows a saliency-guided crop; recorded sections are recorded at phone size.
Captions, callouts and the end card are set in the theme's own fonts and colours (HTML in headless Chrome, so `<em>`
reads as it does on the site), animate on the beat, and keep inside the TikTok/Reels safe areas. Every stage is
cached, so a re-run costs nothing until something changes; `studio trailer my-site --plan` prints the cut.

## Client work

```bash
studio copy export my-site                 # my-site/copy.md: every visible line of text, ready to send
studio copy import my-site copy.md         # apply the client's edits (prints a diff; --dry-run to preview)
studio brand my-site --logo inputs/logo.png --mode light   # theme colours from the logo, contrast-checked
```

The copy deck is plain Markdown: one `###` key per field, the text under it. Imports keep site.yaml's comments and
layout and refuse anything that would make the spec invalid. A rebuild after an import re-renders only what the
text touches.

## With Claude

Open the repo in Claude Code and ask for a site. The `scroll-studio` MCP server (`.mcp.json`) gives Claude tools
to create projects, edit specs, build, take snapshots and look at them, record videos and cut launch trailers; the `scroll-site` skill
gives it the workflow. Any MCP client can use `python -m engine.mcp_server`.

## How it's built

- `engine/`: Python. Spec (`spec.py`), scene builders (`scenes/`), compiler and themes (`compile/`), backends for
  ComfyUI, Blender and depth (`backends/`), CLI, server, MCP server, snapshot and record tools.
- `runtime/`: TypeScript. The scroll core (Lenis, sticky stages, step cards, HUDs) plus one lazily loaded player per
  scene type. Built into `engine/compile/static/runtime` and copied into every site.
- `ui/`: React. The Studio app.
- Every model, with its size and licence, is listed in [`engine/models.yaml`](engine/models.yaml).

## Licence

Scroll Studio is free software under the **GNU AGPL-3.0** ([LICENSE](LICENSE)) with additional terms under its
section 7 ([NOTICE.md](NOTICE.md)):

- **Derivatives stay open source.** A modified version, a port, or a tool built from Scroll Studio (including one
  offered over a network, and including code an AI agent produced from this repository) must be released under the
  AGPL with its complete source.
- **Attribution, word for word.** Derivatives keep the notice
  `Based on Scroll Studio by Edeki Okoh: https://github.com/Okohedeki/scroll-studio (GNU AGPL-3.0)` in their README,
  notice file and About / `--version` / footer, and work that uses the research in `docs/styles` credits it as
  `Style research from Scroll Studio by Edeki Okoh: https://github.com/Okohedeki/scroll-studio`.
- **No misrepresentation.** Modified versions are marked as modified, may not claim to be the original or be named
  "Scroll Studio", and nobody may present the code or the research as their own.
- **Your sites are yours.** Sites you build with Scroll Studio are covered by the Scroll Studio Output Exception: license
  them however you like, keeping the notice comment in the runtime files.

AI agents: see [AGENTS.md](AGENTS.md). Versions published before this change were MIT and stay MIT for those copies.

Model weights keep their own licences (see `engine/models.yaml`). Two are non-commercial: Depth Anything V2 Base/Large
(CC-BY-NC-4.0; the default Small model is Apache-2.0) and the optional MusicGen. LTX-2.3 and Gemma ship under their own
community terms. Check them before commercial use.
