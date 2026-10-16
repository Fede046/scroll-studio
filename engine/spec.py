"""The site spec: one YAML file describes a whole site. The UI, Claude and the CLI all edit this.

A site is a nav, a list of sections and a footer. A section is either a *scene* (a scroll-driven visual
built by a scene module: film, artwork, scene3d, sequence, parallax, type) or a *block* (static content:
intro, features, stats, timeline, quote, cta, gallery).

`Site.model_json_schema()` is the contract for the UI forms and the MCP tools.
"""
from __future__ import annotations

from typing import Annotated, Any, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------- shared pieces

class Link(Model):
    label: str
    href: str = "#"


class Glow(Model):
    """A soft radial light laid over a gradient."""
    x: float = Field(0.5, description="Centre, 0-1 across the image")
    y: float = Field(0.5, description="Centre, 0-1 down the image")
    color: str = Field(..., description="Hex colour")
    radius: float = Field(0.4, description="Softness, as a fraction of the longer side")
    strength: float = Field(0.8, description="0-1: how far the centre goes to the glow's colour")


class Gradient(Model):
    """A backdrop rendered locally with no model at all: a colour sweep, optional glows, stars and film grain.
    For colour cards, dusk skies and night seas behind type."""
    colors: list[str] = Field(..., min_length=2, description="Hex colours along the sweep, first to last")
    angle: float = Field(180, description="Sweep direction in degrees, as in CSS: 180 is top to bottom, 90 left to right")
    glows: list[Glow] = Field(default_factory=list)
    grain: float = Field(0.035, description="Film grain, 0 to 0.2")
    stars: int = Field(0, description="Faint stars scattered over the upper part, for night skies")


# ---------------------------------------------------------------- the product (feature: product integration)

ProductView = Literal["front", "three-quarter", "side", "top", "back", "hero-low", "exploded", "detail"]


class PartMaterial(Model):
    """A material override for the product's parts whose names match. `studio product <project> --parts` lists the
    part, mesh and material names. Rules apply in order, so a later rule wins where two match."""
    match: str = Field("*", description="Glob on the part, mesh or assembly name, case-insensitive: 'Case*', '*knob*', "
                                        "'Housing/*' (an assembly name matches every part inside it)")
    material: Optional[str] = Field(None, description="Only the faces using a material whose name matches this glob "
                                                      "(as listed by --parts), e.g. 'mat_2' or '*Rubber*'")
    color: Optional[str] = Field(None, description="Base colour, hex (sRGB)")
    metallic: Optional[float] = Field(None, ge=0, le=1, description="0 plastic/paint, 1 bare metal")
    roughness: Optional[float] = Field(None, ge=0, le=1, description="0 mirror, 0.3 satin, 0.6 bead-blasted, 0.9 matte")
    emission: Optional[str] = Field(None, description="Glow colour, hex (screens, LEDs)")
    emission_strength: float = Field(1.0, ge=0, description="Glow brightness when `emission` is set")
    transmission: Optional[float] = Field(None, ge=0, le=1, description="See-through amount: 1 glass or clear acrylic")
    texture: Optional[str] = Field(None, description="Base-colour image (project file or URL). Meshes without UVs get a box projection")
    texture_scale: float = Field(0.05, gt=0, description="Box projection: metres per repeat of the texture")
    region: Optional[tuple[float, float, float, float, float, float]] = Field(
        None, description="Only faces whose centre lies in this box, x0 y0 z0 x1 y1 z1 in 0-1 of the product's bounds "
                          "(x left to right seen from the front, y front to back, z bottom to top): paint a screen "
                          "window or a button on a one-piece body")
    facing: Optional[Literal["front", "back", "left", "right", "top", "bottom"]] = Field(
        None, description="Only faces pointing this way (seen from the front view)")


class Product(Model):
    """The product the site is about, declared once. The model is converted, fixed (axes, units), centred on its
    base, given its part materials and cached as one GLB; then takes (`product: {}`), sequences (`model: product`),
    showroom scenes and product stills (`image: {product: three-quarter}`) all use it, and its credit and licence go
    in the footer. One of `model` or `from_photo`."""
    name: str = Field(..., description="Product name, e.g. 'Flipper Zero'")
    maker: Optional[str] = Field(None, description="Who makes it, e.g. 'Flipper Devices'")
    url: Optional[str] = Field(None, description="The maker's page for the product")
    model: Optional[str] = Field(None, description="3D model: GLB/glTF, OBJ, FBX, STL, PLY, STEP/STP (converted locally "
                                                   "with OpenCascade, parts kept with their names) or 3MF; a project "
                                                   "file or an https URL (downloaded once)")
    from_photo: Optional[str] = Field(None, description="A cut-out PNG turned into a 3D model with TRELLIS.2 (see ProductLayer)")
    up: Literal["auto", "z", "y", "x", "-z", "-y", "-x"] = Field(
        "auto", description="Which axis of the file points up. auto: the format's convention (glTF, FBX and OBJ: y; "
                            "STL, PLY, STEP and 3MF: z)")
    units: Literal["auto", "m", "cm", "mm", "in", "ft"] = Field(
        "auto", description="Units the file is in. auto: metres for glTF/FBX/OBJ/PLY, millimetres for STL; STEP and 3MF "
                            "carry their own; anything over 20 m is taken as millimetres")
    rotation: tuple[float, float, float] = Field((0, 0, 0), description="Euler degrees applied after the up fix: turn "
                                                                        "the product so its front faces -y (the front view)")
    parts: list[PartMaterial] = Field(default_factory=list, description="Material overrides by part name")
    exclude: list[str] = Field(default_factory=list, description="Globs on part or assembly names to leave out: "
                                                                 "alternate variants stacked in one CAD file, internal "
                                                                 "parts, packaging")
    tessellation: Literal["draft", "normal", "fine"] = Field(
        "normal", description="STEP: how finely curved surfaces are meshed (fine is smoother and heavier)")
    max_triangles: int = Field(1_500_000, ge=10_000, description="Decimate only above this many triangles")
    licence: Optional[str] = Field(None, description="The model's licence, e.g. 'CC BY 4.0'; shown with the credit")
    credit: Optional[str] = Field(None, description="Attribution for the model, e.g. '3D model by Framework Computer Inc' "
                                                    "(default: '<name> 3D model by <maker>')")
    concept: bool = Field(False, description="Mark the page as a concept: the footer (and the trailer's end card) say "
                                             "'Concept page. Not affiliated with <maker>.'")


class ProductShot(Model):
    """A still of the site's product, rendered by Cycles in a studio light and cached."""
    view: ProductView = Field("three-quarter", description="front, three-quarter, side, top, back, hero-low (a low "
                                                           "camera looking up), exploded (parts pulled apart) or "
                                                           "detail (a close macro view of `part`)")
    part: Optional[str] = Field(None, description="detail: glob on the part/mesh name to frame, e.g. '*port*' "
                                                  "(see studio product --parts); also aims any other view at that part")
    yaw: Optional[float] = Field(None, description="Override the view's turn, degrees (0 front, 90 right side)")
    pitch: Optional[float] = Field(None, description="Override the view's camera height, degrees above the horizon")
    zoom: float = Field(1.0, gt=0, description="1 fits the product in the frame with a margin; 1.3 is closer")
    explode: Optional[float] = Field(None, ge=0, le=1.5, description="How far parts pull apart (exploded view: 1)")
    lens: Optional[float] = Field(None, description="Focal length in mm (default 50; hero-low 32)")
    background: str = Field("auto", description="auto (transparent where the page shows it, such as hero and product "
                                                "blocks, else the theme background), transparent, theme, or a hex colour")
    hdri: str = Field("studio", description="Blender studio light: studio, city, courtyard, forest, interior, night, sunrise, sunset")
    samples: int = Field(128, ge=4, le=4096, description="Cycles samples (denoised)")
    shadow: bool = Field(True, description="A soft contact shadow under the product")
    exposure: float = Field(0.0, ge=-4, le=4, description="Exposure in stops (-0.7 tames a pale metal lid in a bright scene)")
    fstop: Optional[float] = Field(None, gt=0, description="Depth of field, focused on the product (or `part`); "
                                                          "detail views default to f/8, a macro look")
    scene: Optional[str] = Field(None, description="Render the product into a generated scene instead of the studio: "
                                                   "a prompt for the place it stands ('a walnut desk by a window, "
                                                   "morning light'). Z-Image paints the scene to the product's camera "
                                                   "(perspective-matched), the product is lit by it, and a light "
                                                   "Qwen-Image-Edit pass blends it in (needs ComfyUI)")
    harmonise: float = Field(0.3, ge=0, le=1, description="scene: strength of the blending pass (0 skips it); the "
                                                          "product's own pixels are put back if the pass changes them")
    seed: int = Field(7, description="scene: seed for the generated scene")


# ---- freeze (frozen-moment beats): a frame of a beat as an image input ----
class BeatFrame(Model):
    """A frame of a beat of a film: the first or last frame of what that beat renders (after its trim), or the frame
    at a time. Chain beats with it: a beat whose `image` is the last frame of the frozen moment before it starts exactly
    where that moment ends. The beat must come first in the film (or be rendered); `build --only` renders a frozen
    moment on the way, a generated beat that is not rendered yet stands in with its start image."""
    beat: str = Field(..., description="The id of the beat")
    at: Union[Literal["first", "last"], float] = Field("last", description="`first`, `last`, or seconds into the "
                                                                          "beat's clip (after its trim)")
    pick: Literal["last", "sharpest"] = Field("last", description="With at: last, `sharpest` takes the sharpest of the "
                                                                  "last few frames instead of the very last one")
    section: Optional[str] = Field(None, description="The film section holding the beat (found by the beat id when "
                                                     "omitted)")


class ImageInput(Model):
    """An image the engine uses as input: a file in the project's inputs/, one generated locally, a gradient, or a
    still of the site's product."""
    file: Optional[str] = Field(None, description="Path relative to the project folder (inputs/photo.jpg) or an https URL")
    generate: Optional[str] = Field(None, description="Prompt for a local text-to-image model (Z-Image Turbo)")
    gradient: Optional[Gradient] = Field(None, description="Render a gradient backdrop (no model needed) at `size`")
    product: Optional[Union[ProductView, ProductShot]] = Field(
        None, description="A still of `site.product` at `size`: a view name (three-quarter, front, side, top, back, "
                          "hero-low, exploded, detail) or a shot {view, part, yaw, pitch, zoom, explode, background, "
                          "scene ...}")
    scene: Optional[str] = Field(None, description="With `product`: render it into a generated scene described by this "
                                                   "prompt (see ProductShot.scene)")
    size: tuple[int, int] = Field((1920, 1088), description="Generated size (multiples of 16)")
    seed: int = 7
    crop: Optional[tuple[float, float, float, float]] = Field(None, description="Crop [x0, y0, x1, y1] in 0-1 image coordinates")
    edit: Optional["ImageEdit"] = Field(None, description="Make this image by editing another one locally (Qwen-Image-Edit)")
    beat_frame: Optional[BeatFrame] = Field(None, description="A frame of a beat of a film (its first or last frame, "
                                                              "or the frame at a time): chain one beat onto the "
                                                              "end of another")
    credit: Optional[str] = Field(None, description="Attribution shown in the footer")


ImageRef = Union[str, ImageInput]   # a bare string is a file path


class EditRegion(Model):
    """Where an image edit is allowed to change the picture; everywhere else the result is the source, pixel for pixel.

    Name the region (`prompt`, found on the source image by Florence-2 grounding), or point at it (`box`, `points`;
    0-1 picture coordinates). SAM 2.1 then cuts a precise mask around it. A bare string is a prompt:
    `region: "the girl's shoes"`. The editor works on a padded crop around the region (see `scope`), and the result is
    composited back through the feathered mask at the source's own resolution."""
    prompt: Optional[str] = Field(None, description="What the edit may change, as you would say it to a person: \"the girl's "
                                                    "shoes\", \"the shoes of the woman and the man\"")
    points: list[tuple[float, float]] = Field(default_factory=list, description="Points ON the thing, 0-1 across and down the "
                                                                              "source image (with or without a prompt or box)")
    negative_points: list[tuple[float, float]] = Field(default_factory=list, description="Points on what the mask must NOT take")
    box: Optional[tuple[float, float, float, float]] = Field(None, description="x0, y0, x1, y1 around it, 0-1 of the source "
                                                                              "(skips the prompt's search)")
    pick: Union[Literal["all", "first", "largest", "smallest", "left", "right", "top", "bottom", "center"], int] = Field(
        "all", description="When the prompt matches several things: all of them, one by rank (largest, left, center ...) or "
                           "by index (0 is the first the search lists)")
    within: Optional[str] = Field(None, description="Keep only the matches inside the thing this names, e.g. prompt \"hands\" "
                                                    "within \"the girl in the red coat\". A prompt shaped \"the X's Y\" or "
                                                    "\"the Y of the X\" does this by itself")
    grow: int = Field(0, ge=-80, le=200, description="Widen (+) or shrink (-) the mask by this many pixels of the source image "
                                                      "(the edit is free to redraw this much beyond the thing itself)")
    feather: int = Field(8, ge=0, le=100, description="Softness of the mask's edge in pixels of the source image: the edit "
                                                       "fades into the untouched picture over about this distance")
    invert: bool = Field(False, description="Edit everything EXCEPT the region (the region stays the source, pixel for pixel)")
    scope: Literal["crop", "image"] = Field(
        "crop", description="crop: the editor sees only a padded crop around the region, upscaled to its working size, so a "
                            "small region gets full detail; image: the editor sees the whole picture (always used with "
                            "`invert`)")
    context: float = Field(0.6, ge=0, le=4, description="scope crop: how much of the surroundings the editor sees, as a share "
                                                         "of the region's size added on every side")

    @model_validator(mode="before")
    @classmethod
    def _bare_prompt(cls, v):
        return {"prompt": v} if isinstance(v, str) else v

    @model_validator(mode="after")
    def _has_target(self):
        if not (self.prompt or self.points or self.box):
            raise ValueError("an edit region needs a prompt, points or a box")
        return self


class ImageEdit(Model):
    """Derive an image from another with a local image editor (Qwen-Image-Edit): change one thing, keep the rest."""
    source: ImageRef = Field(..., description="The image to edit (a file, or another generated image)")
    instruction: str = Field(..., description="What to change, e.g. 'close the door completely, keep everything else'")
    refs: list[ImageRef] = Field(default_factory=list, description="Up to two more images the instruction can refer to "
                                                                   "('put the second image on the laptop screen')")
    seed: int = 7
    steps: int = Field(30, ge=4, le=60)
    region: Optional[EditRegion] = Field(
        None, description="Edit only inside this region of the source image (or, with `invert`, everywhere but inside it): "
                          "the rest of the result is the source, pixel for pixel, so consecutive versions of a frame "
                          "differ only where the edit is")


ImageInput.model_rebuild()


class Step(Model):
    """One beat of copy that scrolls past the scene."""
    kicker: Optional[str] = None
    title: str = Field(..., description="Headline; <em>…</em> marks the accent words")
    body: Optional[str] = None
    fact: Optional[str] = Field(None, description="Small print under the body (mono)")
    at: Optional[tuple[float, float]] = Field(None, description="overlay layout: visible between these scene progress values (0-1)")
    length: float = Field(1.2, description="split/cards layouts: scroll distance of this step, in screen heights")
    intro: bool = Field(False, description="Render as the section's opening headline (h1)")
    hint: Optional[str] = Field(None, description="Small 'scroll to begin' line under an intro step")
    place: Optional[Literal["left", "right", "center", "top-left", "top-right", "bottom-left", "bottom-right"]] = Field(
        None, description="overlay layout: where this caption sits on the shot (default: left, centred vertically)")
    surface: Optional[Literal["light", "dark"]] = Field(
        None, description="overlay layout: this caption's colours, when the shot under it is lighter or darker than the "
                          "rest of the scene (dark words on a bright sky: light), with a soft glow behind them")
    button: Optional[Link] = Field(None, description="overlay layout: a button under the caption, e.g. the call to "
                                                     "action on a film's last shot")
    image: Optional[ImageRef] = Field(None, description="parallax: this step's photo")
    state: dict[str, Any] = Field(default_factory=dict,
        description="Scene-specific state for this step. chart: {show, focus, x, y, reveal, marks}; map: {center, zoom, pitch, bearing, route, marker}")


class Hud(Model):
    """Overlay instruments tied to scroll progress."""
    kind: Literal["telemetry", "scale", "progress", "legend", "none"] = "none"
    fields: list[dict[str, Any]] = Field(default_factory=list,
        description="telemetry: [{label, unit, from, to, curve, decimals, grouping}] values go from `from` (default 0) to `to` with progress^curve")
    events: list[dict[str, Any]] = Field(default_factory=list, description="telemetry: [{at, label}] lit when progress >= at")
    clock: Optional[dict[str, Any]] = Field(None, description="telemetry: {prefix, start, end, zero} seconds; zero = progress where T=0")
    scales: list[str] = Field(default_factory=list, description="scale: one label per level, e.g. ['100 µm','10 µm']")
    legend: list[dict[str, str]] = Field(default_factory=list, description="legend: [{label, color}]")


class SceneBase(Model):
    id: str
    nav_label: Optional[str] = None
    layout: Literal["overlay", "split", "cards"] = Field(
        "overlay", description="overlay: captions over a full-bleed stage; split: pinned visual beside scrolling "
                               "cards; cards: full-bleed stage with cards scrolling over it")
    side: Literal["left", "right"] = Field("right", description="split/cards: which side the visual sits on")
    length: float = Field(4.0, description="overlay layout: scroll distance in screen heights")
    steps: list[Step] = Field(default_factory=list)
    hud: Hud = Field(default_factory=Hud)
    cue: Optional[str] = Field(None, description="'Scroll to …' hint shown at the start")
    shade: Literal["auto", "none", "strong"] = "auto"
    surface: Optional[Literal["light", "dark", "accent"]] = Field(
        None, description="Colour scheme for the scene's panel in the stack layout (see blocks); sets the text colour over a backdrop")
    backdrop: Optional[ImageRef] = Field(
        None, description="Full-bleed image behind the whole section: a file, URL, generate: or gradient:. In the stack "
                          "layout it is the panel's own backdrop. Pair with `surface` for legible text.")
    locked: bool = Field(False, description="Keep this scene's renders as they are: `studio build` and `studio "
                                            "storyboard` never re-render it, even when its settings change (a log line "
                                            "says so). A locked scene that was never rendered is rendered once. Unlock "
                                            "(or delete the render) to redo it")


# ---------------------------------------------------------------- scene types

class WorldObject(Model):
    """One rough shape in a take's world. Only layout, scale and depth matter: the video model paints the detail."""
    kind: Literal["box", "cylinder", "cone", "blob", "plane", "scatter"]
    name: Optional[str] = None
    at: tuple[float, float, float] = Field((0, 0, 0), description="Centre (x, y, z); z is up")
    size: tuple[float, float, float] = Field((1, 1, 1), description="box/plane: full width, depth, height; blob: radii")
    radius: float = Field(1.0, description="cylinder/cone radius")
    depth: float = Field(1.0, description="cylinder/cone height")
    rotation: tuple[float, float, float] = Field((0, 0, 0), description="Euler degrees")
    color: str = "#9a9a9a"
    soft: bool = Field(False, description="blob: visible in the preview but left out of the depth guide (clouds, haze)")
    count: int = Field(40, description="scatter: how many boxes")
    seed: int = Field(1, description="scatter: random seed")
    area: tuple[float, float, float, float] = Field((-50, -50, 50, 50), description="scatter: x0, y0, x1, y1")
    height: tuple[float, float] = Field((2, 10), description="scatter: min and max box height")
    footprint: tuple[float, float] = Field((3, 6), description="scatter: min and max box width/depth")
    shape: Literal["box", "cone"] = Field("box", description="scatter: box (buildings, rocks) or cone (pines)")
    clear: Optional[tuple[float, float, float]] = Field(None, description="scatter: keep (x, y, radius) empty")


# ---------------------------------------------------------------- video model (LTX-2.3 or Wan 2.2)

VideoModel = Literal["ltx", "wan"]
VIDEO_MODEL_DOC = ("Video model: ltx (LTX-2.3, the default) or wan (Wan 2.2 A14B: renders at ~1280x720 and 16 fps, "
                   "retimed to 24; clean, physical motion and first/last-frame control, but no finer detail than LTX "
                   "after restore, and slower). Unset = the site's `video_model`, then studio.toml's, then ltx")


class Wan(Model):
    """Wan 2.2 A14B settings (`video_model: wan`). Two 14B experts sample in turn (high-noise for the first half of
    the steps, low-noise for the rest). Renders at ~1280x720, 16 fps, up to 81 frames (~5 s) per clip; longer shots
    chain clips from the previous last frame; frames are retimed to 24 fps and restored/upscaled as usual."""
    quality: Literal["fast", "full"] = Field("fast", description="fast: the lightx2v 4-step LoRAs, cfg 1 (an 81-frame "
                                             "720p clip samples in ~2.5 min on an RTX 4090, plus loading the two "
                                             "experts). full: no LoRAs, 20 steps at cfg 3.5 (~25 min a clip; uses the "
                                             "negative prompt; in tests no sharper than fast)")
    steps: Optional[int] = Field(None, ge=2, le=60, description="Total steps (default 4 fast, 20 full); the high-noise "
                                                                "expert takes the first half")
    cfg: Optional[float] = Field(None, ge=1, le=10, description="Guidance (default 1 fast, 3.5 full)")
    shift: Optional[float] = Field(None, ge=1, le=20, description="ModelSamplingSD3 shift (default 5 fast, 8 full)")
    res: Optional[tuple[int, int]] = Field(None, description="Render size, multiples of 16 (default 1280x720's "
                                                             "pixel count at the shot's aspect; 720x1280 for portrait)")
    interpolate: Literal["mci", "blend", "dup"] = Field(
        "mci", description="16 -> 24 fps: mci (FFmpeg motion-compensated in-betweens), blend (cross-fades) or dup "
                           "(repeated frames, exact pixels, slight judder)")
    stretch: float = Field(1.35, ge=1, le=2, description="beats/art: a shot up to this many times one clip's length "
                                                     "(81 frames, ~5 s) is one clip played slower instead of two "
                                                     "chained clips (a chained clip restarts the motion)")
    seed: Optional[int] = Field(None, description="takes: seed for Wan (default: the take's ltx.seed)")
    guide_blur: Optional[float] = Field(None, ge=0, le=12, description="takes: blur of the depth guide in pixels "
                                        "(default: ltx.guide_blur). Fun Control follows the guide's shapes closely, so "
                                        "a blockout box tends to stay a box: blur more (3-6) to let it paint a real "
                                        "table or rock, less to hold exact edges")
    negative_prompt: Optional[str] = Field(None, description="Used only when cfg > 1 (quality: full)")


class CameraKey(Model):
    t: float = Field(..., description="Seconds")
    at: tuple[float, float, float] = Field(..., description="Camera position")
    look: tuple[float, float, float] = Field(..., description="Point the camera looks at")


class ProductLayer(Model):
    """The real thing in a take: rendered from its own 3D model through the take's camera and composited over the
    generated world, so it never warps. One of `model` or `from_photo`, or neither (`product: {}`) to use the site's
    `product:` (its normalised model, materials and credit)."""
    model: Optional[str] = Field(None, description="GLB/glTF, OBJ, FBX, STL or PLY: a project file or an https URL. "
                                                   "Omit to use site.product")
    from_photo: Optional[str] = Field(None, description="A cut-out PNG (transparent background) turned into a 3D model "
                                                         "with TRELLIS.2 (needs `trellis_python`/`trellis_script` in studio.toml)")
    credit: Optional[str] = Field(None, description="Attribution shown in the footer")
    at: tuple[float, float, float] = Field((0, 0, 0), description="Where the base centre of the product sits in the world")
    height: Optional[float] = Field(None, description="Height of the product in world units (default: site.product's "
                                                      "real height in metres, else 1)")
    rotation: tuple[float, float, float] = Field((0, 0, 0), description="Euler degrees")
    spin: float = Field(0.0, description="Extra yaw, in degrees, turned evenly over the whole take")
    hdri: Optional[str] = Field(None, description="Light for the product. Default: the plate itself (an environment "
                                                  "built from the generated frames around each moment, so the product "
                                                  "takes the scene's light and reflections). Or a Blender studio light: "
                                                  "studio, forest, city, courtyard, night, interior, sunrise, sunset")
    sun_strength: float = Field(3.0, description="A sun lamp along the take's light direction; 0 to turn it off")
    samples: int = Field(64, description="Cycles samples per frame (denoised)")
    shadow: bool = Field(True, description="Cast the product's shadow onto the generated ground")
    shadow_size: Optional[float] = Field(None, description="Side of the square the shadow falls on, in metres (the table or floor patch); default 3x the height")
    res: Optional[tuple[int, int]] = Field(None, description="Render size of the product pass, which is also the final "
                                                             "film size (default 1920x1080; 2560x1440 when the take "
                                                             "is upscaled)")
    fstop: Optional[float] = Field(2.8, description="Depth of field: focused where the camera looks, at this f-stop "
                                                    "(real scale); none for everything sharp")
    motion_blur: float = Field(0.5, ge=0, le=1, description="Shutter as a fraction of a frame (0: off)")
    grade: bool = Field(True, description="Match the product pass to the plate: black level, white balance, saturation, "
                                          "softness, and a light wrap at the edges")
    grain: Optional[float] = Field(None, ge=0, description="Film grain on the product (0-255 sigma); default: measured "
                                                          "from the plate")


class Take(Model):
    """One continuous camera move through a generated world, with a real product locked to the same camera.

    The world is a rough blockout (shapes + camera keys) rendered by Blender into a depth guide; LTX-2.3 paints the
    world along that guide in chained segments; the product is rendered by Cycles through the identical camera and
    composited over every frame; the result is encoded for scrubbing."""
    duration: float = Field(..., description="Seconds")
    fps: int = 24
    sky: str = "#8fb4d8"
    light: tuple[float, float, float] = Field((0.4, -0.3, 0.85), description="Light direction for the preview and the product's sun")
    ground: Optional[WorldObject] = Field(None, description="A plane under everything (defaults to a 400 x 400 plane at z = 0)")
    objects: list[WorldObject] = Field(default_factory=list)
    camera: list[CameraKey] = Field(..., min_length=2)
    lens: float = Field(32.0, description="Focal length in mm")
    product: Optional[ProductLayer] = None
    product_in_guide: bool = Field(False, description="Put the product's shape in the depth guide. Off by default: the video model then paints its own version of the product, which shows around the edges of the real one. Leave the product out of the prompts too and describe the empty spot ('an empty table').")
    preview_res: tuple[int, int] = Field((1280, 720), description="Blockout render size; same aspect as product.res")
    depth_far: float = Field(400.0, description="Depth guide far plane")
    keyframes: Optional[dict[str, Any]] = Field(None, description="Z-Image stills pinned at times, as in shot.keyframes")
    ltx: dict[str, Any] = Field(..., description="LTX-2.3 settings, as in shot.ltx: res, segments [{id, range, prompt}], "
                                                 "seed, guide_strength ... Render at res [1920, 1088] (multiples of "
                                                 "32) for a detailed world; [1024, 576] is a quick draft")
    upscale: Optional[dict[str, Any]] = Field(None, description="Optional upscale stage, as in shot.upscale")
    restore: Optional[int] = Field(None, ge=360, le=2160, description="Run SeedVR2 over the generated world at this "
                                                                      "height (e.g. 1080) to clean the video model's "
                                                                      "softness and redraw fine detail, before the "
                                                                      "product is composited (the real product is "
                                                                      "never restored); slow")
    video_model: Optional[VideoModel] = Field(None, description=VIDEO_MODEL_DOC + ". With wan the world is painted by "
                                              "Wan 2.2 Fun Control along the same depth guide, from the first "
                                              "keyframe, in the segments and prompts of `ltx:`")
    wan: Optional[Wan] = Field(None, description="Wan settings for this take (over the site's `wan:`)")
    locked: bool = Field(False, description="Keep the take's renders (world, product pass, composite) as they are, even "
                                            "when its settings change: build and storyboard log it and move on")


# ---- freeze (frozen-moment beats) ----
FreezeEase = Literal["linear", "inOutSine", "inOutQuad", "inOutCubic", "inOutQuart", "flow"]


class FreezeKey(Model):
    """One stop of a frozen moment's camera: the framing box the camera has reached at time `t` of the beat."""
    t: float = Field(..., ge=0, le=1, description="When the camera reaches the box, 0-1 of the beat")
    box: tuple[float, float, float, float] = Field(
        ..., description="Framing box [x0, y0, x1, y1] in 0-1 of the frozen frame. The aspect comes from beat_res: a "
                         "box of another shape is widened (never cropped) to it, so everything in the box stays in frame")
    hold: float = Field(0.0, ge=0, le=1, description="The camera rests on the box for this much of the beat after "
                                                     "reaching it (the frozen moment still breathes with the parallax)")


class Freeze(Model):
    """A frozen moment: the beat is not generated but rendered from one frame, offline, in seconds. The frame is
    upscaled, given a depth map (Depth Anything V2) and the camera moves through it as a 2.5D parallax move along
    `camera` keys, so a crowd can stand still while the camera visits a couple's hands and feet, and the faces stay
    the faces of the frame. The clip joins the film like any generated beat (trim, crossfade, restore, locked, --only)."""
    from_: Optional[str] = Field(None, alias="from", description="Freeze the last frame of this beat (an earlier beat of "
                                                                 "the film, after its trim); or give `image:`")
    image: Optional[ImageRef] = Field(None, description="Freeze this image instead (a file, or any image input; "
                                                        "`beat_frame:` takes a frame of a beat)")
    pick: Literal["sharpest", "last"] = Field("sharpest", description="With `from`: `sharpest` takes the sharpest of the "
                                                                      "last `pick_window` frames (the very last of a "
                                                                      "moving shot is often motion-blurred, bad for "
                                                                      "close-ups), `last` the very last one. Sharpness is "
                                                                      "measured in the camera's tightest boxes")
    pick_window: int = Field(6, ge=1, le=48, description="How many of the last frames `pick: sharpest` looks at")
    upscale: float = Field(1.0, ge=1, le=4, description="Upscale the frame this many times before moving through it, "
                                                        "so crops stay sharp (a 3x crop of a 1920 frame needs 2). "
                                                        "1 = off")
    upscale_method: Literal["auto", "seedvr2", "lanczos"] = Field(
        "auto", description="seedvr2: SeedVR2 image restoration through ComfyUI (redraws fine detail; the model "
                            "downloads on first use). lanczos: a local detail-preserving resample, no model. auto: "
                            "seedvr2 when its weights are installed, else lanczos")
    camera: list[FreezeKey] = Field(default_factory=list, description="Camera keys over the beat. The camera rests on "
                                                                      "the first box until its t and on the last after "
                                                                      "its t; none: the whole frame, with the parallax")
    parallax: float = Field(0.6, ge=0, le=2, description="Strength of the 2.5D depth effect (0 = flat Ken Burns; the "
                                                         "subject plane stays put while nearer and farther things shift)")
    dolly: Optional[float] = Field(None, ge=0, le=3, description="Extra push-in of near things as the camera closes in "
                                                                 "(default follows `parallax`)")
    ease: FreezeEase = Field("inOutSine", description="How the camera travels between boxes. inOutSine/Quad/Cubic/Quart: "
                                                      "eased, resting at every key. flow: keeps moving through keys "
                                                      "(it rests only at keys with a hold)")
    depth_model: Literal["small", "base", "large"] = Field("small", description="Depth Anything V2 size (small is "
                                                                                  "Apache-2.0; base and large are CC-BY-NC)")
    blur: float = Field(0.0, ge=0, le=1, description="Motion blur: the shutter, as a fraction of a frame (0 = off, 0.5 = "
                                                     "180 degrees). Sub-frames are averaged")
    grain: float = Field(0.0, ge=0, le=0.2, description="Film grain laid over the render (0.01-0.03 is faint) so it "
                                                        "matches generated shots")
    seed: int = 7

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


# ---- reveal + faces (engine/reveal.py, engine/faces.py): kept together so they merge cleanly ----------------------

class RevealAt(Model):
    """The frame a region is first found on (before it is tracked through the whole film): a moment in a beat
    (`beat` + `t`, 0 = its first frame, 1 = its last), or in the whole film (`t` alone, 0-1), or an exact `frame` /
    `seconds` of the joined film. Pick a frame where the thing is plainly in view."""
    beat: Optional[str] = Field(None, description="beats film: the beat's id")
    t: float = Field(0.5, ge=0, le=1, description="0-1 through the beat (or through the film without `beat`)")
    frame: Optional[int] = Field(None, ge=0, description="An exact frame of the film (overrides beat/t)")
    seconds: Optional[float] = Field(None, ge=0, description="An exact time in the film, seconds (overrides beat/t)")


class RevealRegion(Model):
    """One part of the picture that comes into colour. Describe it (`prompt`: found on the `at` frame by Florence-2),
    or point at it (`points` / `box` in 0-1 picture coordinates on the `at` frame); SAM 2.1 then follows it through
    the whole film, forwards and backwards."""
    id: str
    prompt: Optional[str] = Field(None, description="What to colour, as you would say it to a person: \"the woman's hand\", "
                                                    "\"the shoes of the woman and the man\". Every match on the `at` frame "
                                                    "is revealed (see `pick`, `within`)")
    points: list[tuple[float, float]] = Field(default_factory=list, description="Points ON the thing, 0-1 across and down the "
                                                                              "`at` frame (with or without a prompt or box)")
    negative_points: list[tuple[float, float]] = Field(default_factory=list, description="Points on what the mask must NOT take")
    box: Optional[tuple[float, float, float, float]] = Field(None, description="x0, y0, x1, y1 around it, 0-1 on the `at` "
                                                                              "frame (skips the prompt's search)")
    at: Union[RevealAt, list[RevealAt]] = Field(default_factory=RevealAt, description="The frame to find it on. A film of several "
                                                                                       "shots tracks a region only inside a shot it is found in "
                                                                                       "(a cut ends it): give one `at` per shot it must show in")
    pick: Union[Literal["all", "first", "largest", "smallest", "left", "right", "top", "bottom"], int] = Field(
        "all", description="When the prompt matches several things: all of them, one by rank (largest, left, ...) or by "
                           "index (0 is the first the search lists)")
    within: Optional[str] = Field(None, description="Keep only the matches inside the thing this names, e.g. prompt "
                                                    "\"hand\" within \"the woman in the long coat\". A prompt shaped \"the X's Y\" "
                                                    "or \"the Y of the X\" does this by itself")
    grow: int = Field(0, ge=-40, le=80, description="Widen (+) or shrink (-) the finished mask by this many pixels at film size")

    @property
    def seeds(self) -> list[RevealAt]:
        return self.at if isinstance(self.at, list) else [self.at]

    @model_validator(mode="after")
    def _has_target(self):
        if not (self.prompt or self.points or self.box):
            raise ValueError(f"reveal region '{self.id}': give a prompt, points or a box")
        return self


class Reveal(Model):
    """Colour that comes in where the camera looks, driven by scroll. The film is rendered once in full colour; the page
    shows everything in the `base` look, and each region's colour is brought in through a tracked mask, in the browser
    (a WebGL shader draws each frame of the film with its masks from the same frame). Without WebGL the colour film
    plays as it is; with reduced motion each region jumps to colour as its moment arrives."""
    base: str = Field("mono", description="What pixels that are not revealed look like: mono (black and white), dim (darker "
                                          "and muted), blur (soft focus in colour), or a hex colour such as \"#2a4a6a\" "
                                          "(a duotone from black through that colour to white)")
    regions: list[RevealRegion] = Field(..., min_length=1)
    keys: list[dict[str, float]] = Field(default_factory=list, description="Scroll progress of the section -> how revealed "
                                                                          "each region is (0-1), eased between keys: "
                                                                          "[{at: 0.4, her_hand: 0}, {at: 0.48, her_hand: 1}]. A region keeps "
                                                                          "its last value. Default: one region after another")
    cuts: list[float] = Field(default_factory=list, description="Times of the film's cuts, in seconds, when they can't be known "
                                                                "(a beats film knows its own; other films are searched for them)")
    feather: float = Field(6.0, ge=0, le=64, description="Softness of every mask's edge, in pixels at film size")
    ease: Literal["smooth", "linear"] = Field("smooth", description="How a region eases between two keys")
    tracker: Literal["large", "base_plus"] = Field("large", description="SAM 2.1 size: large (sharper, ~450 MB) or base_plus")
    strength: float = Field(1.0, ge=0, le=1, description="1: revealed pixels show the film's own colour; lower mixes the base "
                                                         "look back in")

    @field_validator("base")
    @classmethod
    def _base(cls, v):
        import re
        if v not in ("mono", "dim", "blur") and not re.fullmatch(r"#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})", v):
            raise ValueError("base is mono, dim, blur or a hex colour like #2a4a6a")
        return v

    @model_validator(mode="after")
    def _keys(self):
        ids = [r.id for r in self.regions]
        if len(set(ids)) != len(ids):
            raise ValueError("reveal: region ids must be unique")
        for k in self.keys:
            if "at" not in k:
                raise ValueError("reveal.keys: every key needs `at`")
            for name, v in k.items():
                if name != "at" and name not in ids:
                    raise ValueError(f"reveal.keys: '{name}' is not a region id ({', '.join(ids)})")
                if not 0 <= v <= 1:
                    raise ValueError(f"reveal.keys: {name} must be between 0 and 1")
        return self


class Faces(Model):
    """Face repair for generated video: faces above `min_size` are found in every frame, restored with GFPGAN v1.4, and
    blended back softly (and smoothed over time so nothing flickers)."""
    mode: Literal["restore"] = "restore"
    strength: float = Field(0.7, ge=0, le=1, description="How much of the restored face is blended in")
    min_size: int = Field(96, ge=16, le=2048, description="Faces smaller than this many pixels across are left alone")
    smooth: float = Field(0.6, ge=0, le=0.95, description="Temporal smoothing of the blend (higher: steadier, slower to follow)")


def _faces(v):
    if v in (None, False, "off", "none"):
        return None
    if v is True or v == "restore":
        return {"mode": "restore"}
    return v


# ---------------------------------------------------------------------------------------------------------------


class Beat(Model):
    """One shot of a story film: a still generated from `prompt` (or taken from `image`), brought to life by `motion`."""
    id: str
    prompt: str = Field("", description="The opening frame, described like a photograph: subject, place, light, lens "
                                        "(not used by a frozen moment)")
    motion: str = Field("", description="What moves and how the camera moves, e.g. 'the door swings open, the camera pushes in'"
                                        " (not used by a frozen moment)")
    seconds: float = Field(4.0, ge=1, le=60, description="Length of the shot (1 to 10 generated; a frozen moment may run longer)")
    seed: int = 7
    image: Optional[ImageRef] = Field(None, description="Start from this image instead of generating it from `prompt`: "
                                                        "a file, or an image input (generate:, edit: ...)")
    end_image: Optional[ImageRef] = Field(None, description="The clip's last frame (same forms as `image`): the motion is "
                                                            "steered to land on it, e.g. a closed door ending open")
    strength: float = Field(1.0, ge=0.3, le=1.0, description="How tightly the clip holds the start image. Lower it "
                                                           "(0.7-0.85) when an action shot freezes on its first frame")
    motion_seed: Optional[int] = Field(None, description="Seed for the motion only, to re-roll a clip and keep its still")
    trim: float = Field(0.0, ge=0, description="Seconds cut from the start of the clip (an action shot that holds its "
                                               "first frame before moving). Re-uses the render: nothing is re-animated")
    video_model: Optional[VideoModel] = Field(None, description=VIDEO_MODEL_DOC + ". `strength` applies to ltx only")
    locked: bool = Field(False, description="Keep this beat's clip (and its storyboard still) as rendered, even when "
                                            "its prompt or motion changes; the rest of the film still builds around it")
    freeze: Optional[Freeze] = Field(None, description="A frozen moment instead of a generated clip: one frame, upscaled, "
                                                       "with a 2.5D camera moving through it, rendered offline in seconds "
                                                       "(see Freeze). prompt, motion, image and end_image are not used")

    @model_validator(mode="after")
    def _generated_or_frozen(self):
        if self.freeze is None:
            if not self.prompt or not self.motion:
                raise ValueError(f"beat '{self.id}': `prompt` and `motion` are required (or make it a frozen moment with `freeze:`)")
            if self.seconds > 10:
                raise ValueError(f"beat '{self.id}': a generated beat is 1 to 10 seconds (a `freeze:` beat may be longer)")
            return self
        f = self.freeze
        if bool(f.from_) == (f.image is not None):
            raise ValueError(f"beat '{self.id}': freeze needs exactly one of `from` (a beat id) and `image`")
        if f.from_ == self.id:
            raise ValueError(f"beat '{self.id}': freeze cannot take its own frame")
        for name in ("image", "end_image", "video_model", "motion_seed"):
            if getattr(self, name) is not None:
                raise ValueError(f"beat '{self.id}': `{name}` does not apply to a frozen moment (use freeze.image / freeze.from)")
        if self.strength != 1.0:
            raise ValueError(f"beat '{self.id}': `strength` does not apply to a frozen moment")
        ks = f.camera
        for i, k in enumerate(ks):
            x0, y0, x1, y1 = k.box
            if not (0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1):
                raise ValueError(f"beat '{self.id}': camera box {i} {list(k.box)} must be [x0, y0, x1, y1] inside 0-1 "
                                 "with x0 < x1 and y0 < y1")
            if i and k.t <= ks[i - 1].t + ks[i - 1].hold - 1e-9:
                raise ValueError(f"beat '{self.id}': camera keys must go forward in time (key {i} at t={k.t} comes before "
                                 f"the previous key's hold ends at {ks[i - 1].t + ks[i - 1].hold:g})")
        if ks and ks[-1].t + ks[-1].hold > 1 + 1e-9:
            raise ValueError(f"beat '{self.id}': the last camera key's hold runs past the end of the beat")
        return self


    # ---- faces
    faces: Optional[Faces] = Field(None, description="`restore`: repair the faces in this beat's clip (GFPGAN), after it is "
                                                     "generated. Off by default; or a mapping with strength, min_size, smooth")

    @field_validator("faces", mode="before")
    @classmethod
    def _faces_in(cls, v):
        return _faces(v)


class FilmScene(SceneBase):
    """AI film scrubbed by scroll. Blender blockout -> Z-Image keyframes -> LTX-2.3 -> encode. Or `beats`: a story told
    in separate shots, each a generated still animated by LTX-2.3, joined with short crossfades; steps can pin
    themselves to a beat with state: {beat: <id>}."""
    type: Literal["film"] = "film"
    video: Optional[str] = Field(None, description="Use an existing film instead of generating one")
    shot: dict[str, Any] = Field(default_factory=dict,
        description="Generation settings: fps, duration, preview_res, blockout {preset|file}, keyframes, ltx, upscale")
    take: Optional[Take] = Field(None, description="A one-take film described in the spec (world, camera, product) instead of `shot`")
    beats: list[Beat] = Field(default_factory=list, description="A story film shot by shot (instead of `shot` / `take`)")
    beat_res: tuple[int, int] = Field((1920, 1088), description="beats: render size (multiples of 32)")
    beat_fade: float = Field(0.4, ge=0, le=2, description="beats: crossfade between shots, in seconds")
    beat_restore: Optional[int] = Field(None, description="beats: run SeedVR2 over the finished film at this height "
                                                          "(e.g. 1088) to clean grain and redraw fine detail; slow")
    gop: int = 6
    # ---- reveal + faces
    reveal: Optional[Reveal] = Field(None, description="Scroll-driven colour: the film is full colour, the page shows the "
                                                       "`base` look and brings colour into tracked regions as you scroll")
    faces: Optional[Faces] = Field(None, description="`restore`: repair the faces in the whole film (GFPGAN) before it is "
                                                     "encoded; beats can set it per beat. Off by default")

    @field_validator("faces", mode="before")
    @classmethod
    def _faces_in(cls, v):
        return _faces(v)


class ArtworkScene(SceneBase):
    """Any image, drawn and painted in stages as you scroll."""
    type: Literal["artwork"] = "artwork"
    layout: Literal["overlay", "split", "cards"] = "split"
    image: ImageRef
    focus: Union[Literal["auto"], list[tuple[float, float]]] = Field(
        "auto", description="Where drawing starts: 'auto' (faces, then saliency) or [(x, y)] in 0-1 image coords")
    stages: list[Literal["guides", "lines", "value", "underpaint", "colour"]] = Field(
        default_factory=lambda: ["guides", "lines", "value", "underpaint", "colour"],
        description="One stage per step after the intro step, in order")
    width: int = Field(1800, description="Working width of the layers in pixels")
    line_density: float = Field(1.0, description="More (>1) or fewer (<1) contour strokes")
    underpaint: str = Field("#5a3a22", description="Monochrome underpainting colour")
    paper: str = Field("#efe8da", description="Paper colour")
    caption: Optional[str] = Field(None, description="Label under the canvas")


class Level(Model):
    preset: str = Field(..., description="Level generator, see engine/scenes/scene3d.py PRESETS")
    params: dict[str, Any] = Field(default_factory=dict)


class Scene3DScene(SceneBase):
    """Live 3D: a zoom journey through nested levels built from generator presets (or glTF models)."""
    type: Literal["scene3d"] = "scene3d"
    layout: Literal["overlay", "split", "cards"] = "cards"
    style: Literal["glow", "solid"] = Field("glow", description="glow: additive fluorescence; solid: lit PBR")
    levels: list[Level]
    zoom: float = Field(14.0, description="Scale factor between levels")
    background: Optional[str] = None
    bloom: tuple[float, float, float] = (0.5, 0.45, 0.12)
    final: Optional[str] = Field(None, description="Extra beat on the last level, e.g. 'dock' for molecule docking")
    dust: str = Field("#8fb8d8", description="Colour of the background dust particles")
    seed: int = Field(7, description="Seed for the procedural presets")


class SequenceScene(SceneBase):
    """A 3D model rendered to an image sequence (turntable, explode, assemble) and scrubbed by scroll."""
    type: Literal["sequence"] = "sequence"
    model: Optional[str] = Field(None, description="glTF/GLB, OBJ, FBX or STL: a project file or an https URL (downloaded "
                                                   "once). Omit, or write 'product', to use site.product")
    credit: Optional[str] = Field(None, description="Attribution shown in the footer (e.g. for CC-BY models)")
    frames: int = 120
    size: tuple[int, int] = (1920, 1080)
    samples: int = 96
    keys: list[dict[str, Any]] = Field(default_factory=lambda: [
        {"t": 0, "yaw": -35, "pitch": 18, "explode": 0, "zoom": 1.0},
        {"t": 0.5, "yaw": 60, "pitch": 28, "explode": 1, "zoom": 1.1},
        {"t": 1, "yaw": 160, "pitch": 14, "explode": 0, "zoom": 0.95}],
        description="Camera/explode keys over progress: yaw/pitch degrees, explode 0-1, zoom")
    background: Optional[str] = Field(None, description="Backdrop colour (defaults to the theme background)")
    hdri: str = Field("studio", description="Blender studio light: studio, forest, city, courtyard, night, interior, sunrise, sunset")


class ShowroomScene(SceneBase):
    """The real product, live in the page: three.js renders the product's normalised GLB with studio environment
    lighting and a soft shadow; scroll turns, explodes and zooms it along `keys`, and the pointer nudges the view."""
    type: Literal["showroom"] = "showroom"
    layout: Literal["overlay", "split", "cards"] = "cards"
    model: str = Field("product", description="'product' (site.product) or a model file/URL in any product format")
    keys: list[dict[str, Any]] = Field(default_factory=lambda: [
        {"t": 0, "yaw": -35, "pitch": 18, "explode": 0, "zoom": 1.0},
        {"t": 0.5, "yaw": 50, "pitch": 26, "explode": 1, "zoom": 0.9},
        {"t": 1, "yaw": 160, "pitch": 12, "explode": 0, "zoom": 1.05}],
        description="Over scene progress: yaw/pitch degrees (yaw 0 is the front), explode 0-1, zoom")
    background: Optional[str] = Field(None, description="Colour behind the product (default: the theme background); "
                                                        "'transparent' shows the section's backdrop")
    lighting: Literal["studio", "soft", "contrast"] = Field(
        "studio", description="studio: environment light plus a key; soft: even, low-contrast; contrast: a hard key and rim")
    exposure: float = Field(1.0, gt=0, description="Tone-mapping exposure")
    shadow: bool = Field(True, description="Soft shadow on an invisible floor")
    spin: float = Field(0.0, description="Idle turn in degrees per second on top of the keys (0: scroll only)")
    poster: bool = Field(True, description="Render a Cycles still shown until the live model has loaded (and without WebGL)")


class ParallaxScene(SceneBase):
    """Photos turned into 2.5D camera moves with an estimated depth map; one photo per step."""
    type: Literal["parallax"] = "parallax"
    layout: Literal["overlay", "split", "cards"] = "cards"
    move: Literal["dolly", "pan", "orbit", "rise"] = Field("dolly", description="Default camera move for each photo")
    moves: list[Literal["dolly", "pan", "orbit", "rise"]] = Field(default_factory=list, description="Per-photo moves, in step order")
    strength: float = Field(1.0, description="Depth effect amount")
    depth_model: Literal["small", "base", "large"] = Field(
        "small", description="Depth Anything V2 size. small is Apache-2.0; base/large are sharper but CC-BY-NC (non-commercial)")
    width: int = Field(2560, description="Max photo width served to desktop browsers")


class VectorScene(SceneBase):
    """A logo or line drawing whose strokes draw themselves, then fill. From an SVG, or a raster image vectorised
    with vtracer (engravings, illustrations, logos)."""
    type: Literal["vector"] = "vector"
    layout: Literal["overlay", "split", "cards"] = "split"
    svg: Optional[str] = Field(None, description="SVG file (project path or https URL)")
    image: Optional[ImageRef] = Field(None, description="Raster image to vectorise when there is no SVG")
    order: Literal["center", "left", "top", "document"] = Field("center", description="Which strokes draw first")
    colors: Literal["original", "ink", "accent"] = Field("original", description="Fill colours: as traced, theme ink, or theme accent")
    detail: float = Field(1.0, description="Vectorising detail: higher keeps smaller specks (more paths, heavier page)")
    threshold: int = Field(140, description="Raster images: grey level below which a pixel counts as ink (0-255)")
    max_width: int = Field(2000, description="Raster images are traced at this width")
    background: Optional[str] = Field(None, description="Canvas colour behind the drawing (defaults to the theme)")


class ChartScene(SceneBase):
    """A data story: a chart that draws, zooms, highlights and annotates itself as the steps scroll past.
    Each step's `state` says what to show: {show: [series], focus: [series], x: [x0, x1], y: [y0, y1],
    reveal: true (draw the lines across this step), marks: [{series, x, label}]}."""
    type: Literal["chart"] = "chart"
    layout: Literal["overlay", "split", "cards"] = "split"
    data: str = Field(..., description="CSV file (project path or https URL), long format: one row per (series, x, y)")
    x: str = Field(..., description="Column for the x axis (numbers or years)")
    y: str = Field(..., description="Column for the y axis")
    series: Optional[str] = Field(None, description="Column that names each line")
    include: list[str] = Field(default_factory=list, description="Series to load (empty = all, capped at 12)")
    kind: Literal["line", "area", "bar", "scatter"] = Field("line", description="bar: grouped bars per x; scatter: dots")
    y_scale: Literal["linear", "log"] = "linear"
    y_label: Optional[str] = None
    unit: str = Field("", description="Unit after values, e.g. ' GW' or '%'")
    format: Literal["auto", "compact", "percent", "integer"] = Field(
        "auto", description="Number style: compact (1.2k, 3.4M), percent (adds %), integer, or auto")
    source: Optional[str] = Field(None, description="Data credit shown under the chart and in the footer")
    colors: list[str] = Field(default_factory=list, description="Series colours in `include` order (defaults to the theme)")
    callouts: list[dict[str, Any]] = Field(default_factory=list,
        description="Marks computed from the data at build time, so numbers in the story are the data's: "
                    "[{series, at: max | min | first | last | <x value>, label: 'text with {y} and {x}', step: <index>}]. "
                    "Each becomes a mark on that step (default: the last step).")


class Route(Model):
    id: str
    points: list[tuple[float, float]] = Field(..., description="[lng, lat] waypoints")
    color: Optional[str] = None
    geodesic: bool = Field(False, description="Bend each leg along the great circle (flights)")


class Marker(Model):
    lng: float
    lat: float
    label: str


class MapScene(SceneBase):
    """A geographic journey on a live vector map. Each step's `state` moves the camera and draws routes:
    {center: [lng, lat], zoom, pitch, bearing, routes: {route_id: 0-1}}. Tiles come from OpenFreeMap (no key)."""
    type: Literal["map"] = "map"
    layout: Literal["overlay", "split", "cards"] = "cards"
    style: str = Field("https://tiles.openfreemap.org/styles/liberty", description="MapLibre style URL")
    dark: bool = Field(False, description="Darken and desaturate the base map to sit under a dark theme")
    routes: list[Route] = Field(default_factory=list)
    markers: list[Marker] = Field(default_factory=list)


class SplatKey(Model):
    t: float = Field(..., description="Scene progress 0-1")
    at: tuple[float, float, float] = Field(..., description="Camera position, in the scan's own coordinates")
    look: tuple[float, float, float] = Field(..., description="Point the camera looks at")


class SplatScene(SceneBase):
    """A real place, scanned: a Gaussian splat the camera flies through as you scroll. Bring a scan from any
    phone app or trainer as .ply (3D Gaussian Splatting layout), .spz, or a gsplat .pt checkpoint; the build trims
    it and writes a small .spz the page streams. `studio build` logs the scan's bounds to place the camera keys."""
    type: Literal["splat"] = "splat"
    source: str = Field(..., description="Scan file: project path or https URL (.ply, .spz, .pt)")
    credit: Optional[str] = Field(None, description="Attribution shown in the footer")
    max_splats: int = Field(600_000, description="Keep the N most opaque splats (page weight ~16 bytes each)")
    min_opacity: float = Field(0.04, description="Drop splats fainter than this")
    max_scale: float = Field(0.0, description="Drop splats longer than this (scene units) on any axis: the smears scans leave in the air; 0 keeps all")
    crop: Optional[tuple[float, float, float, float, float, float]] = Field(None, description="Keep only x0 y0 z0 x1 y1 z1")
    sh: int = Field(1, ge=0, le=3, description="Spherical-harmonic degree to keep (view-dependent colour); 0 is smallest")
    up: tuple[float, float, float] = Field((0, 0, 1), description="Which way is up in the scan")
    fov: float = Field(60.0, description="Vertical field of view in degrees")
    keys: list[SplatKey] = Field(..., min_length=2, description="Camera path over scene progress")
    background: Optional[str] = Field(None, description="Colour behind the splats (defaults to the theme background)")


class TypeScene(SceneBase):
    """Kinetic typography driven by scroll."""
    type: Literal["type"] = "type"
    mode: Literal["reveal", "stack", "swap", "scale", "weight"] = Field(
        "reveal", description="reveal: words light up in reading order; stack: lines slam in; swap: one word rolls "
                              "through `words`; scale: one phrase settles then bursts; weight: words grow from thin and "
                              "faint to heavy and solid in reading order (a variable display face; ' / ' breaks lines)")
    text: str = Field("", description="reveal/scale/weight: the passage; swap: the fixed part")
    words: list[str] = Field(default_factory=list, description="swap: the words that cycle")
    weights: list[int] = Field(default_factory=lambda: [200, 800], min_length=2, max_length=2,
                               description="weight: the display face's weight at the start and at the end")
    length: float = 3.0
    size: Literal["passage", "display"] = Field(
        "passage", description="passage: reading size, left-aligned. display: a headline, bigger and centred")



class CodeFile(Model):
    """One file on the route through the codebase."""
    path: str = Field(..., description="Shown as the file's title, e.g. app/Models/User.php")
    code: Optional[str] = Field(None, description="The source. For kind: edit, start each line with '+' (added), "
                                                  "'-' (removed) or ' ' (unchanged), like a diff")
    file: Optional[str] = Field(None, description="Read the source from this project file instead of `code`")
    kind: Literal["read", "edit", "run"] = Field(
        "read", description="read: flies past as the agent reads it; edit: a stop where the diff applies itself as you "
                            "scroll; run: a terminal stop whose output prints line by line")
    label: Optional[str] = Field(None, description="Tag over the file (default: Read / Edit / the command for run)")
    lang: Optional[str] = Field(None, description="Highlighting: php, ts, tsx, js, py, go, rust, sh... (default: from the extension)")
    weight: float = Field(1.0, description="Share of the scroll this file gets, relative to the others of its kind")
    todo: Optional[str] = Field(None, description="An item on the agent's todo list, ticked when this file is done")


class CodeTerminal(Model):
    """The agent's prompt box the scene opens on; the camera dives through it into the code."""
    logo: str = Field("", description="Wordmark over the prompt, e.g. 'opencode'; split as dim|bright with '|', e.g. 'open|code'")
    prompt: str
    agent: str = "Build"
    model: str = ""
    provider: str = ""
    hints: list[str] = Field(default_factory=lambda: ["tab switch agent", "ctrl+p commands"])


class CodeScene(SceneBase):
    """Fly through a codebase in live 3D, following an agent at work: the scene opens on its prompt, dives into the
    files it reads, stops at each edit while the diff applies itself, and ends on the test run. Steps can pin
    themselves to the route with state: {file: <path>} (or 'terminal' / 'outro') instead of `at`."""
    type: Literal["code"] = "code"
    terminal: Optional[CodeTerminal] = None
    files: list[CodeFile] = Field(..., min_length=1, description="The route, in order")
    tree: list[str] = Field(default_factory=list, description="More paths in the project, drawn around the route so "
                                                              "it reads as a whole codebase")
    length: float = 14.0


# ---------------------------------------------------------------- content blocks

class BlockBase(Model):
    id: Optional[str] = None
    nav_label: Optional[str] = None
    band: bool = Field(False, description="Alternate background band")
    surface: Optional[Literal["light", "dark", "accent"]] = Field(
        None, description="Colour scheme for this section: dark inverts the theme, accent uses its soft accent colour. "
                          "In the stack layout each section is a panel, so this sets the panel's colour.")
    backdrop: Optional[ImageRef] = Field(
        None, description="Full-bleed image behind the whole section: a file, URL, generate: or gradient:. In the stack "
                          "layout it is the panel's own backdrop. Pair with `surface` for legible text.")


class IntroBlock(BlockBase):
    type: Literal["intro"] = "intro"
    kicker: Optional[str] = None
    title: str
    body: Optional[str] = None
    button: Optional[Link] = None


class Feature(Model):
    tag: Optional[str] = None
    title: str
    body: Optional[str] = None
    meter: Optional[float] = Field(None, description="0-1 progress bar under the card")


class FeaturesBlock(BlockBase):
    type: Literal["features"] = "features"
    kicker: Optional[str] = None
    title: Optional[str] = None
    items: list[Feature]


class StatData(Model):
    section: str = Field(..., description="id of a chart section on this page")
    series: str
    at: Union[Literal["max", "min", "first", "last"], float] = "last"
    decimals: int = 0
    scale: float = Field(1.0, description="Multiply the value (e.g. 0.001 to show thousands)")


class Stat(Model):
    value: str = Field("", description="Shown as-is; a plain number counts up. Leave empty when `data` fills it")
    unit: Optional[str] = None
    label: str
    data: Optional[StatData] = Field(None, description="Read the value from a chart's data at build time, so headline "
                                                       "numbers can never drift from the source")


class StatsBlock(BlockBase):
    type: Literal["stats"] = "stats"
    items: list[Stat]


class TimelineItem(Model):
    when: str
    title: str
    body: Optional[str] = None


class TimelineBlock(BlockBase):
    type: Literal["timeline"] = "timeline"
    kicker: Optional[str] = None
    title: Optional[str] = None
    items: list[TimelineItem]


class QuoteBlock(BlockBase):
    type: Literal["quote"] = "quote"
    text: str
    who: Optional[str] = None


class CtaBlock(BlockBase):
    type: Literal["cta"] = "cta"
    kicker: Optional[str] = None
    title: str
    button: Optional[Link] = None
    background: Optional[str] = Field(None, description="'scene:<id>' uses that scene's last frame, or an image path")


class GalleryItem(Model):
    title: str
    href: str
    kicker: Optional[str] = None
    body: Optional[str] = None
    image: Optional[str] = None
    video: Optional[str] = None


class GalleryBlock(BlockBase):
    type: Literal["gallery"] = "gallery"
    kicker: Optional[str] = None
    title: Optional[str] = None
    items: list[GalleryItem]


class HeroBlock(BlockBase):
    """A full-screen opening: headline over a photo or looping video, with an optional badge and buttons."""
    type: Literal["hero"] = "hero"
    badge: Optional[str] = Field(None, description="Small pill above the headline (e.g. 'Now open in Lisbon')")
    title: str
    body: Optional[str] = None
    buttons: list[Link] = Field(default_factory=list, description="The first is the primary button")
    image: Optional[ImageRef] = Field(None, description="Background photo (file, URL or generate:)")
    video: Optional[str] = Field(None, description="Background video file (muted, looping); image is its poster")
    align: Literal["center", "left"] = "center"
    device: Optional["Device"] = Field(None, description="A phone rising from the bottom edge under the copy")


class DeviceOption(Model):
    title: str
    body: Optional[str] = None
    selected: bool = Field(False, description="Shown as the chosen option")


class Device(Model):
    """A phone showing a simple app screen, drawn in HTML so the text stays sharp at any size."""
    app: Optional[str] = Field(None, description="App name in the screen's header")
    title: Optional[str] = Field(None, description="Screen title")
    label: Optional[str] = Field(None, description="Small label above the options")
    note: Optional[str] = Field(None, description="Paragraph under the label")
    options: list[DeviceOption] = Field(default_factory=list)
    button: Optional[str] = Field(None, description="Button at the bottom of the screen")
    image: Optional[ImageRef] = Field(None, description="Use a screenshot instead of the drawn screen")
    video: Optional[str] = Field(None, description="Play a screen recording (a project file or URL; muted, looping) "
                                                  "instead of the drawn screen; `image` is then its poster")
    time: str = "9:41"


class ProductBlock(BlockBase):
    """Product or service panel: a large image and/or a phone on one side, copy, tags and buttons on the other."""
    type: Literal["product"] = "product"
    kicker: Optional[str] = None
    title: str
    body: Optional[str] = None
    tags: list[str] = Field(default_factory=list, description="Small pills under the body")
    buttons: list[Link] = Field(default_factory=list, description="The first is the primary button")
    note: Optional[str] = Field(None, description="Small print under the buttons (e.g. a price)")
    image: Optional[ImageRef] = Field(None, description="Product shot. On light surfaces a white background disappears "
                                                        "(multiply blend), so generate it 'on a plain white background'")
    knockout: bool = Field(True, description="Whiten the shot's light studio background (sampled from its edges) so "
                                             "the product floats on the panel instead of sitting in a grey box")
    device: Optional[Device] = None
    side: Literal["left", "right"] = Field("left", description="Which side the image goes on")
    pose: Literal["beside", "rise", "close", "lean", "pair", "turn"] = Field("beside", description=(
        "How the phone sits, so a run of product panels doesn't repeat one composition. beside: next to the copy. "
        "rise: centred under centred copy, cut off by the panel's bottom edge. close: larger, top-aligned beside the "
        "copy and cut off below. lean: tilted out of the lower corner on `side`, running off the edges. "
        "pair: with a second phone (`behind`), the two swapping places on a loop. turn: turned in perspective "
        "towards the copy"))
    behind: Optional[Device] = Field(None, description="pair: the second phone (its own image or video)")
    stats: list[Stat] = Field(default_factory=list, description="Big figures under the body, shown instead of the tags")


class StripItem(Model):
    image: ImageRef
    caption: Optional[str] = None


class StripBlock(BlockBase):
    """A row of photos that slides sideways as you scroll."""
    type: Literal["strip"] = "strip"
    kicker: Optional[str] = None
    title: Optional[str] = None
    body: Optional[str] = None
    items: list[StripItem]


class OrbitItem(Model):
    label: str
    status: Optional[str] = Field(None, description="e.g. Live, Developing, Roadmap; the first status used is highlighted")


class OrbitBlock(BlockBase):
    """Services arranged around a centre on rings that turn as you scroll, each with a status."""
    type: Literal["orbit"] = "orbit"
    kicker: Optional[str] = None
    title: str
    body: Optional[str] = None
    center: str = Field(..., description="Label in the middle (usually the brand)")
    items: list[OrbitItem]


class FaqItem(Model):
    q: str
    a: str


class FaqBlock(BlockBase):
    """Questions and answers as an accordion (works without JavaScript)."""
    type: Literal["faq"] = "faq"
    kicker: Optional[str] = None
    title: str = "Questions"
    items: list[FaqItem]


Section = Annotated[Union[
    FilmScene, ArtworkScene, Scene3DScene, SequenceScene, ParallaxScene, TypeScene, VectorScene, ChartScene, MapScene,
    SplatScene, CodeScene, ShowroomScene,
    IntroBlock, FeaturesBlock, StatsBlock, TimelineBlock, QuoteBlock, CtaBlock, GalleryBlock,
    HeroBlock, ProductBlock, StripBlock, OrbitBlock, FaqBlock,
], Field(discriminator="type")]

SCENE_TYPES = ("film", "artwork", "scene3d", "sequence", "parallax", "type", "vector", "chart", "map", "splat", "code",
               "showroom")


# ---------------------------------------------------------------- site

class Art(Model):
    """Artwork a style renders in its own medium: ascii-art prints it in characters, particles fills the screen with
    it in points. Generated locally from a prompt (or taken from a file), optionally animated into a short loop."""
    prompt: Optional[str] = Field(None, description="Generate the image locally (Z-Image), e.g. 'a basketball player "
                                                    "dribbling, black background'. Plain backgrounds and strong "
                                                    "silhouettes read best in characters and points")
    file: Optional[str] = Field(None, description="Use this image (project file or URL) instead of a prompt")
    motion: Optional[str] = Field(None, description="Animate it with the video model (needs ComfyUI), e.g. 'dribbles the "
                                                    "ball between his legs'. Omit for a still")
    seconds: float = Field(3.0, ge=1, le=8, description="Length of the animated loop")
    size: tuple[int, int] = Field((1024, 768), description="Generated image size (the loop keeps its aspect)")
    seed: int = 7
    frames: int = Field(36, ge=1, le=96, description="Frames shipped to the page (sampled evenly from the loop)")
    width: int = Field(220, ge=40, le=480, description="Sampling width in pixels of the shipped frames: characters "
                                                       "and points are drawn from these")
    label: Optional[str] = Field(None, description="Short name shown with the art (defaults to the prompt)")
    video_model: Optional[VideoModel] = Field(None, description=VIDEO_MODEL_DOC)


class Theme(Model):
    preset: str = Field("night", description="night, brass, paper, lab, cosmos, studio, dusk, ink, blueprint, clinic (see engine/themes.yaml)")
    style: Optional[str] = Field(
        None, description="An experience in one word: its own scroll mechanic, layout, transitions and look. particles, "
                          "liquid-morph, holographic, neon-glow, wireframe-3d, glassmorphism, kinetic-type, isometric, clay-3d, "
                          "ascii-art, gradient-mesh, comic-book, split-flap, retro-vhs, halftone, bauhaus, pixel-art, blueprint, "
                          "art-deco, neo-brutalism, anime-intro, flipbook, pop-up-book, pinscreen, sand, zoetrope (see engine/styles/). Colours/fonts set here still win")
    mode: Optional[Literal["light", "dark"]] = Field(None, description="Override the preset's light/dark mode (set it when colors flip it)")
    colors: dict[str, str] = Field(default_factory=dict, description="Override tokens: bg, bg2, ink, accent, accent2")
    fonts: dict[str, str] = Field(default_factory=dict, description="Google Fonts families: display, body, mono")
    display_weight: Optional[int] = None
    display_italic_em: Optional[bool] = Field(None, description="Render <em> accent words in italic")
    display_em: Optional[Literal["accent", "bold", "heavy"]] = Field(
        None, description="How <em> words are set: accent (the accent colour, italic when display_italic_em), "
                          "bold (bold italics in the text's own colour, so a headline reads as one face) or heavy "
                          "(upright, the text's own colour, at the face's heaviest weight: pair with a light "
                          "display_weight so emphasis is a change of weight)")
    labels: Optional[Literal["caps", "plain"]] = Field(
        None, description="Small labels (kickers, tags, timeline dates): caps (spaced capitals in the mono face, the "
                          "default) or plain (sentence case in the body face, for brands that never set all-caps)")
    display_optical_size: Optional[int] = Field(
        None, description="Pin the display face's optical size (variable fonts such as Fraunces or Newsreader grow "
                          "more expressive at large sizes; 36-48 keeps headlines calm)")
    radius: Optional[str] = None
    art: Optional[Art] = Field(None, description="Artwork the style renders in its own medium (ascii-art: characters, "
                                                  "particles: points). A prompt or a file, optionally animated")


class Nav(Model):
    logo: Optional[str] = Field(None, description="Inline SVG path data (24x24) or an image file")
    links: list[Link] = Field(default_factory=list, description="Empty = generated from sections with nav_label")
    cta: Optional[Link] = None


class Loader(Model):
    """Loading screen: scrolling stays locked until every scene's media has loaded (videos fully downloaded,
    frames decoded, map tiles drawn), with a progress bar."""
    enabled: bool = True
    label: Optional[str] = Field(None, description="Text under the bar (defaults to the site name)")
    max_wait: float = Field(45.0, description="Seconds after which the site opens anyway")
    min_time: float = Field(0.6, description="Minimum seconds on screen, so it never flashes")


class Footer(Model):
    left: Optional[str] = None
    right: Optional[str] = None
    links: list[Link] = Field(default_factory=list, description="Links shown before `right`, e.g. a privacy policy "
                                                                 "or terms hosted elsewhere (`pages:` adds its own)")


class Scroll(Model):
    speed: float = Field(1.0, description="Pace of the smooth scroll, anchor scrolls and scroll-driven reveals: "
                                          "1.2 is a fifth faster, 0.8 a fifth slower")


class Page(Model):
    """A plain page beside the site (privacy policy, support, press): Markdown set in the site's theme, served
    at /<slug>/ and linked from the footer."""
    slug: str = Field(..., description="URL path: 'privacy' is served at /privacy/")
    title: str
    source: str = Field(..., description="Markdown file relative to the project folder (pages/privacy.md)")
    summary: Optional[str] = Field(None, description="Meta description for the page")
    nav: bool = Field(False, description="Also link it from the nav, after the section links")


# ---------------------------------------------------------------- launch trailer (`studio trailer`, engine/trailer/)

class TrailerShot(Model):
    """One shot of the launch trailer, cut from something the site already rendered. Give one source: `section`
    (with `step` or `range`), `beat`, `product` or `card`."""
    section: Optional[str] = Field(None, description="id of a section. A film plays its own footage (take, beats or "
                                                      "video); any other section is recorded scrolling through the "
                                                      "built site (at phone size for 9:16)")
    step: Optional[int] = Field(None, description="film: the footage under this step (its index in the section's "
                                                  "steps), captioned with its headline")
    beat: Optional[str] = Field(None, description="id of a beat of a beats film (the section is found for you)")
    range: Optional[tuple[float, float]] = Field(None, description="Part of the source: seconds of a film, or 0-1 "
                                                                   "scroll progress of a recorded section")
    product: Optional[str] = Field(None, description="A still of `site.product` from this view (front, three-quarter, "
                                                     "side, top, back, hero-low, exploded) with a slow push-in. Needs "
                                                     "the product feature; skipped with a note when it is missing")
    card: Optional[str] = Field(None, description="A type card on the theme background with this headline "
                                                  "(<em>…</em> marks accent words)")
    caption: Optional[str] = Field(None, description="Headline over the shot (<em>…</em> marks accent words). "
                                                     "Default: the matching step or section headline; '' for none")
    kicker: Optional[str] = Field(None, description="Small label above the caption")
    callouts: list[str] = Field(default_factory=list, description="Short feature lines ('24 h cold') set big, one "
                                                                  "after another on the beat, over this shot")
    beats: Optional[int] = Field(None, ge=1, le=64, description="Length on the trailer's beat grid (default: long "
                                                                "enough to read the caption, at least a bar)")
    speed: float = Field(1.0, ge=0.25, le=4.0, description="Playback speed of the footage")
    hold: bool = Field(False, description="Freeze the first frame of `range` instead of playing it")
    zoom: Optional[tuple[float, float]] = Field(None, description="Push-in: scale at the start and the end of the "
                                                                  "shot (1 = the whole frame). Default: a slow push on "
                                                                  "the product reveal and on stills")
    focus: Optional[tuple[float, float]] = Field(None, description="Point (0-1 x, y of the source) that the 9:16 crop "
                                                                   "and the push-in keep in frame. Default: the "
                                                                   "product in a take, else the most salient area")


class Trailer(Model):
    """A launch film cut by the engine from the site's own renders (`studio trailer`): dist/trailer/trailer-16x9.mp4,
    trailer-9x16.mp4 (reframed, never letterboxed) and their posters. Cuts land on a beat grid; captions and the end
    card are set in the theme's fonts and colours. `trailer: {}` derives the cut: a hook shot, the middle of the
    story, the product reveal, 2-4 feature callouts and an end card."""
    shots: list[TrailerShot] = Field(default_factory=list, description="The cut, in order. Empty: derived from the site")
    formats: list[Literal["16x9", "9x16"]] = Field(default_factory=lambda: ["16x9", "9x16"],
                                                   description="16x9: 1920x1080; 9x16: 1080x1920 for TikTok/Reels/Shorts")
    seconds: float = Field(24.0, ge=8, le=90, description="Target length of a derived cut (15-30 s suits social)")
    bpm: float = Field(100.0, ge=40, le=220, description="Tempo of the beat grid the cuts land on")
    music: Optional[str] = Field(None, description="A local audio file (project path); none is generated. Without "
                                                   "it the trailer is silent and the captions carry it")
    music_start: float = Field(0.0, ge=0, description="Seconds into the music where the first cut lands (a downbeat)")
    loudness: float = Field(-14.0, ge=-30, le=-8, description="Music loudness target, integrated LUFS")
    fps: Literal[24, 30] = 24
    captions: bool = Field(True, description="Set captions over the shots")
    title: Optional[str] = Field(None, description="End card name (default: the site name)")
    tagline: Optional[str] = Field(None, description="End card line (default: the site description)")
    cta: Optional[str] = Field(None, description="End card call to action (default: the nav button's label)")
    url: Optional[str] = Field(None, description="End card address, e.g. stillwater.example (default: the nav "
                                                 "button's link when it is a full URL)")
    disclaimer: Optional[str] = Field(None, description="Small print on the end card (default: the product's concept "
                                                        "line, 'Concept page. Not affiliated with <maker>.')")
    end_beats: int = Field(8, ge=2, le=32, description="Length of the end card on the beat grid")
    end_background: Literal["blur", "theme"] = Field("blur", description="blur: the last shot, blurred under the "
                                                                         "theme colour; theme: the plain background")
    embed: bool = Field(False, description="Add a 'Watch the launch film' button to the first section that opens the "
                                           "trailer in a modal (built by `studio trailer`, picked up by the next build)")
    embed_label: str = Field("Watch the launch film", description="Label of the embed button")


class Site(Model):
    name: str
    description: str = ""
    lang: str = "en"
    theme: Theme = Field(default_factory=Theme)
    layout: Literal["flow", "stack"] = Field(
        "flow", description="flow: sections follow one another. stack: every section is a full-screen panel with "
                            "rounded top corners that slides up over the one before it.")
    nav: Nav = Field(default_factory=Nav)
    loader: Loader = Field(default_factory=Loader)
    scroll: Scroll = Field(default_factory=Scroll)
    sections: list[Section]
    footer: Footer = Field(default_factory=Footer)
    pages: list[Page] = Field(default_factory=list, description="Plain Markdown pages beside the site (privacy, support)")
    product: Optional[Product] = Field(None, description="The product the site is about, declared once: takes, sequences, "
                                                         "showroom scenes and `image: {product: <view>}` stills use it")
    # launch trailer
    trailer: Optional[Trailer] = Field(None, description="A launch film built from the site's renders by "
                                                         "`studio trailer` (16:9 and 9:16); `{}` derives the cut")
    video_model: Optional[VideoModel] = Field(None, description="Default video model for film beats, takes and "
                                              "theme.art: ltx (LTX-2.3) or wan (Wan 2.2). Unset = studio.toml's, then ltx")
    wan: Wan = Field(default_factory=Wan, description="Wan 2.2 settings used wherever video_model is wan")


def is_scene(section) -> bool:
    return getattr(section, "type", None) in SCENE_TYPES
