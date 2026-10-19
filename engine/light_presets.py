"""Named times of day for the `light` scene: pure data (no imports from the spec, which reads it for validation).

Each preset says three things:
  prompt   how the editor (Qwen-Image-Edit) is told to relight the place: the sky, the sun or moon, the direction,
           colour and length of the shadows, what the light does on water and walls, which lamps are lit
  clock    the hour the page shows beside the picture (and the sun's place on its arc)
  haze     mist lying in the distance, 0-1 (the browser draws it with the depth map, so it drifts)
  lit      artificial light is on (lamps, windows): the build looks for what turned on between this time and its neighbour
  sun      where the light comes from: "left", "right", "high", "behind", or "none"; the page's light front spreads from there

The wording keeps the structure exactly: only light changes. `FRAME` wraps every preset.
"""
from __future__ import annotations

FRAME = ("Relight this exact photograph as {when}. Keep the scene identical: every building, wall, roof, window, door, boat, "
         "lamp post, rock, tree, wave and the camera framing stay exactly where they are, pixel for pixel. Change only the "
         "light: the colour of the sky, where the sun or moon is, the direction, colour and length of the shadows, the "
         "reflections on the water, the colour of the light on every surface and which lamps and windows are lit. "
         "Do not add or remove any object. No people.")

PRESETS: dict[str, dict] = {
    "dawn": {
        "label": "Dawn", "clock": "05:50", "hours": 5.8, "haze": 0.55, "lit": True, "sun": "left",
        "prompt": "first light before sunrise: a pale peach and lilac sky glowing just above the horizon, the rest of the "
                  "sky soft blue-grey, cool dim blue light on the buildings, soft mist lying low on the water, very faint "
                  "long shadows, the street lamps still lit with a small warm glow and a few warm windows",
    },
    "sunrise": {
        "label": "Sunrise", "clock": "06:40", "hours": 6.7, "haze": 0.3, "lit": False, "sun": "left",
        "prompt": "sunrise: the sun just clearing the horizon on the left, low pink and orange light raking across the "
                  "facades from the left, long soft shadows falling to the right, a gentle rosy sky, thin mist over the "
                  "water, the lamps switched off",
    },
    "morning": {
        "label": "Morning", "clock": "08:30", "hours": 8.5, "haze": 0.1, "lit": False, "sun": "left",
        "prompt": "early morning: low clean sun on the left, warm golden light skimming across the facades, long soft "
                  "shadows falling to the right, a fresh pale blue sky, the water bright and calm, the lamps off",
    },
    "noon": {
        "label": "Noon", "clock": "12:30", "hours": 12.5, "haze": 0.0, "lit": False, "sun": "high",
        "prompt": "high noon: the sun nearly overhead, bright neutral white light, short hard shadows directly under "
                  "things, a deep clear blue sky, saturated colours, the lamps off",
    },
    "afternoon": {
        "label": "Afternoon", "clock": "15:30", "hours": 15.5, "haze": 0.05, "lit": False, "sun": "right",
        "prompt": "mid afternoon: the sun on the right, warm bright light, medium shadows falling to the left, a clear blue "
                  "sky a little warmer near the horizon, the lamps off",
    },
    "golden-hour": {
        "label": "Golden hour", "clock": "18:30", "hours": 18.4, "haze": 0.12, "lit": False, "sun": "right",
        "prompt": "golden hour: the sun low on the right, rich amber light across every facade, long warm shadows falling "
                  "to the left across the quay, a glowing amber and apricot sky with a few thin clouds, the water "
                  "reflecting the gold, the lamps still off",
    },
    "sunset": {
        "label": "Sunset", "clock": "19:20", "hours": 19.3, "haze": 0.2, "lit": False, "sun": "right",
        "prompt": "sunset: the sun at the horizon on the right, a blazing orange and magenta sky, deep red-orange light on "
                  "the nearest facades and long shadows, the rest in cool shade, the water mirroring the sky",
    },
    "blue-hour": {
        "label": "Blue hour", "clock": "20:10", "hours": 20.1, "haze": 0.15, "lit": True, "sun": "none",
        "prompt": "blue hour just after sunset: a deep blue sky with a last thin orange band on the horizon, the buildings "
                  "in soft cool blue shade, every street lamp and many windows have just come on and glow warm yellow, "
                  "pools of lamplight on the stones, warm reflections of the lights on the blue water",
    },
    "night": {
        "label": "Night", "clock": "22:30", "hours": 22.5, "haze": 0.0, "lit": True, "sun": "none",
        "prompt": "night: a dark navy sky full of stars and a bright moon, cool blue moonlight on the roofs, every street "
                  "lamp lit with a warm glow and halo, most windows lit warm yellow, shop awnings and boats' cabin lights "
                  "on, long bright warm reflections of the lamps and windows on the dark water",
    },
    "overcast": {
        "label": "Overcast", "clock": "11:00", "hours": 11.0, "haze": 0.2, "lit": False, "sun": "none",
        "prompt": "a heavy overcast day: a flat pale grey sky, soft shadowless light, muted colours, the water slate grey, "
                  "the lamps off",
    },
    "storm": {
        "label": "Storm", "clock": "16:45", "hours": 16.7, "haze": 0.35, "lit": True, "sun": "none",
        "prompt": "an approaching storm: a dark green-grey sky with heavy clouds, a thin shaft of low sunlight breaking "
                  "through on the horizon, dark moody light on the buildings, the water dark and choppy, the street lamps "
                  "and some windows lit warm against the gloom",
    },
}

# the time-of-day sequence a bare `times: dawn` style list reads in; `day` is the usual six
SEQUENCES: dict[str, list[str]] = {
    "day": ["dawn", "morning", "noon", "golden-hour", "blue-hour", "night"],
}


def preset(name: str) -> dict:
    key = name.strip().lower().replace(" ", "-").replace("_", "-")
    if key not in PRESETS:
        raise KeyError(f"unknown time of day '{name}' (known: {', '.join(PRESETS)})")
    return PRESETS[key]


def instruction(preset_name: str | None, prompt: str | None) -> str:
    """The relight instruction for a time: its preset's wording, then any free text of the spec's (which wins where
    they disagree because it comes last)."""
    parts = []
    if preset_name:
        parts.append(preset(preset_name)["prompt"])
    if prompt:
        parts.append(prompt.strip().rstrip("."))
    return FRAME.format(when=", ".join(parts))
