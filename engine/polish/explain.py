"""Plain-words explanations for the polish report: the label of each metric, what is wrong in one line, and what to try."""
from __future__ import annotations

LABELS = {"pops": "Pops", "softness": "Softness", "halos": "Halos", "drift": "Style drift", "morphs": "Morphs"}
SHORT = {"pops": "pop", "softness": "soft", "halos": "halo", "drift": "drift", "morphs": "morph"}

WHAT = {
    "pops": "A pop is a change the eye catches because nothing led up to it: the picture jumps between two frames "
            "(more than motion can explain), brightness flickers, motion judders, or a crossfade dissolves two "
            "pictures that do not line up so a double image shows.",
    "softness": "Softness is lost detail. The sharp edges of a frame are measured in pixels (at 1920 across): clean "
                "linework or photo is about 1.5 to 2.5 px, a picture stretched from fewer pixels is 3 px and more.",
    "halos": "Halos are bright rims and seams along clean edges: what a depth warp or a cut-out leaves at a "
             "boundary. Measured as the share of clean edges with a bright rim beside them.",
    "drift": "Style drift is the look moving away from where the section started: more hatching or pencil texture, "
             "different grain, a different tonal balance. Compared with the section's first second, and within a "
             "beat with where the beat started.",
    "morphs": "A morph is things appearing, dissolving or rearranging instead of moving. Optical flow explains "
              "motion; what it cannot explain is the share of the change that is a rebuild.",
}

HINTS = {
    "dissolve": "Start the next beat on the previous beat's last frame (image: { beat_frame: { beat: <previous>, at: last } }) "
                "so the dissolve is between matching pictures, or shorten beat_fade.",
    "cut": "Start the next beat on the previous beat's last frame (image: { beat_frame }), or add a short beat_fade.",
    "jump": "Look at these frames: usually a clip glitching at a seam. Try trim: on the beat, or a new motion_seed.",
    "flash": "A brightness flicker inside a clip: try a new motion_seed, or trim: past it.",
    "stutter": "The clip updates in bursts or at a low frame rate: re-roll motion_seed, or ask for less motion in `motion`.",
    "softness": "The picture runs out of pixels at this zoom. Give the camera a source with real detail at this scale (an "
                "edit.region redraw), raise freeze.upscale, or open the framing box.",
    "halos": "Lower freeze.parallax and dolly for this beat, give the edit region less grow/feather, or end the move "
             "where there is less depth jump along the edges.",
    "drift": "Start the beat from the previous beat's last frame (image: { beat_frame }) and keep strength near 1.0, or "
             "describe the same style in the end_image.",
    "morphs": "The video model rebuilt the picture between its start and end images. Shorten the beat, make end_image "
              "closer to image, or cut instead of morphing.",
}


def level_of(sev: float) -> str:
    return "clean" if sev < 0.25 else "slight" if sev < 0.5 else "visible" if sev < 0.75 else "bad"


def _pct(x: float) -> str:
    return f"{100 * x:.0f}%"


def reason(metric: str, r: dict, span, ctx: dict) -> tuple[str, str]:
    """One line saying what is wrong at the worst moment of a stretch (`r` is that moment's measurements), and a hint."""
    if metric == "pops":
        k = r.get("kind")
        if k in ("dissolve", "cut"):
            s = (f"{'Crossfade' if k == 'dissolve' else 'Hard cut'} {r['from']} to {r['to']}: at "
                 f"{'mid-fade' if k == 'dissolve' else 'the cut'} {_pct(r['edges'])} of the edges differ between the two shots"
                 f"{', so a double image shows' if k == 'dissolve' else ''}")
            if r.get("chroma", 0) >= 1.5:
                s += f", and the colour changes (by {r['chroma']:.1f} levels)"
            elif r.get("luma", 0) >= 18:
                s += f", and the brightness changes (by {r['luma']:.0f} levels)"
            return s + ".", HINTS[k]
        if k == "jump":
            return (f"The change between two frames jumps to {r['ratio']:.1f}x what its neighbours show, more than motion "
                    f"explains (a pop)."), HINTS["jump"]
        if k == "flash":
            return f"One frame is {r['step']:.1f} brightness levels off from the frames either side of it and then it is back (a flicker).", HINTS["flash"]
        if k == "stutter":
            return (f"While things move the picture updates only {r['rate']:.0f} times a second, in visible steps (judder)."), HINTS["stutter"]
    if metric == "softness":
        d, ref = r["detail"], r.get("ref")
        w, wref = r.get("width"), r.get("width_ref")
        soft_style = r.get("hatch") is not None and r["hatch"] == r["hatch"] and r["hatch"] >= 0.55
        s = "Looks soft"
        if ref and d < ref:
            s += f": only {100 * d / ref:.0f}% of the fine detail of this film's sharpest frames is left here"
        if w:
            s += f" (edges {w:.1f} px wide" + (f", {wref:.1f} at the sharpest" if wref and w / wref >= 1.3 else "") + ")"
        s += ", the strokes are soft (pencil-like texture, see Style drift)" if soft_style else ", as if enlarged from fewer pixels"
        if r.get("aniso") and (r["aniso"] > 1.5 or r["aniso"] < 0.67):
            s += ", and the blur runs mostly one way"
        if span.kind == "freeze" and span.zoom:
            s += f". The camera's tightest framing is {_pct(span.zoom)} of the frame, {1 / span.zoom:.0f}x the source"
        return s + ".", HINTS["softness"]
    if metric == "halos":
        return (f"{_pct(r['rim'])} of the clean edges here have a bright rim or seam beside them, {r['rim'] / r['base']:.1f}x "
                f"this film's usual {_pct(r['base'])} (halos and double edges)."), HINTS["halos"]
    if metric == "drift":
        what = r["what"]
        if what == "hatch":
            v, ref = r["value"], r["ref"]
            if v > ref:
                return (f"The look has moved: {_pct(v)} of the picture's structure is soft hatching or pencil texture, "
                        f"against {_pct(ref)} at the start of the scene (it looks sketchier)."), HINTS["drift"]
            return (f"The look has moved: only {_pct(v)} of the picture's structure is texture, against {_pct(ref)} at the "
                    f"start of the scene (it looks cleaner and flatter)."), HINTS["drift"]
        if what == "grain":
            return (f"The grain is {r['value']:.1f} levels here against {r['ref']:.1f} at the start of the section "
                    f"({r['value'] / r['ref']:.1f}x)."), HINTS["drift"]
        if what == "tone":
            return "The tonal balance (how the picture's darks and lights are spread) has moved away from where this beat started.", HINTS["drift"]
        if what == "line":
            return (f"Line density is {r['value'] / r['ref']:.1f}x what it was when this beat started (linework thicker or "
                    f"thinner)."), HINTS["drift"]
        if what == "sat":
            return f"Saturation has moved from {r['ref']:.2f} to {r['value']:.2f} since this beat started.", HINTS["drift"]
        if what == "embed":
            return "A CLIP image embedding of this frame has moved far from the scene's first second (the look changed).", HINTS["drift"]
    if metric == "morphs":
        return (f"{_pct(r['unexplained'])} of the change between frames is things appearing, dissolving or rearranging, "
                f"not moving: shapes are rebuilding themselves rather than travelling."), HINTS["morphs"]
    return metric, ""
