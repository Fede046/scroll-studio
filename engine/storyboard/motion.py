"""Stills into moving shots: the storyboard's stand-in films, the animatic and the stand-in clips of `build --only`.

A shot is a `Piece`: a start still (and an end still it dissolves into), a length, and a `Move` (a slow push, pull or
pan: Ken Burns along the shot's own direction, read from its motion text or a take's camera keys). A piece can carry a
video instead (a rendered clip, or the tiny LTX motion preview), which then plays across its length. `render()` lays
pieces end to end with dissolves and encodes them (short GOP, so the page can scrub them).
"""
from __future__ import annotations

import math
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

import numpy as np

from ..config import settings
from ..project import BuildError


@dataclass
class Move:
    """Where the frame looks over the shot: zoom (1 = the whole still) and the focus point (0-1), start to end."""
    z0: float = 1.0
    z1: float = 1.0
    x0: float = 0.5
    x1: float = 0.5
    y0: float = 0.5
    y1: float = 0.5

    def at(self, u: float) -> tuple[float, float, float]:
        e = 0.5 - 0.5 * math.cos(math.pi * min(1.0, max(0.0, u)))
        return self.x0 + (self.x1 - self.x0) * e, self.y0 + (self.y1 - self.y0) * e, self.z0 + (self.z1 - self.z0) * e

    def describe(self) -> str:
        parts = []
        if self.z1 > self.z0 + 0.01:
            parts.append("push in")
        elif self.z0 > self.z1 + 0.01:
            parts.append("pull back")
        if abs(self.x1 - self.x0) > 0.01:
            parts.append("pan right" if self.x1 > self.x0 else "pan left")
        if abs(self.y1 - self.y0) > 0.01:
            parts.append("tilt down" if self.y1 > self.y0 else "tilt up")
        return ", ".join(parts) or "hold"


STILL = Move()

# motion verbs -> a move; the first that matches wins, so specific phrases come before general ones
_VERBS = [
    (r"pull(s|ing)? (back|out|away)|zoom(s|ing)? out|dolly(ing)? out|retreat|reveal(s|ing)? more|widen", Move(1.14, 1.0)),
    (r"orbit|circl|arc(s|ing)? (around|round)|revolv", Move(1.1, 1.12, 0.42, 0.58)),
    (r"pan(s|ning)? left|track(s|ing)? left|move(s)? left|slide(s)? left", Move(1.1, 1.1, 0.58, 0.42)),
    (r"pan(s|ning)? right|track(s|ing)? right|move(s)? right|slide(s)? right", Move(1.1, 1.1, 0.42, 0.58)),
    (r"tilt(s|ing)? up|crane(s|ing)? up|rise(s)?|rising|follow(s|ing)? them up|look(s|ing)? up", Move(1.1, 1.1, 0.5, 0.5, 0.6, 0.4)),
    (r"tilt(s|ing)? down|crane(s|ing)? down|descend|sink(s|ing)?|drop(s|ping)?", Move(1.1, 1.1, 0.5, 0.5, 0.4, 0.6)),
    (r"push(es|ing)? (in|toward|closer)|dolly(ing)? in|zoom(s|ing)? in|move(s|ing)? (steadily )?forward|toward|"
     r"closer|approach|glid", Move(1.0, 1.16)),
    (r"(stays|holds|locked|static|still)\b.*camera|camera (stays|holds) still", Move(1.0, 1.03)),
]


def from_text(motion: Optional[str]) -> Move:
    """A move for a beat's motion text ('the camera pushes in slowly' -> push in); a slow push when it names none."""
    text = (motion or "").lower()
    cam = text[text.find("camera"):] if "camera" in text else text   # the camera's own verbs first
    for src in (cam, text):
        for pat, mv in _VERBS:
            if re.search(pat, src):
                return mv
    return Move(1.0, 1.06)


def _cam(keys: list, t: float) -> tuple[np.ndarray, np.ndarray]:
    ks = sorted(keys, key=lambda k: k["t"])
    if t <= ks[0]["t"]:
        k = ks[0]
        return np.array(k["at"], float), np.array(k["look"], float)
    for a, b in zip(ks, ks[1:]):
        if t <= b["t"]:
            f = (t - a["t"]) / max(b["t"] - a["t"], 1e-6)
            return (np.array(a["at"], float) * (1 - f) + np.array(b["at"], float) * f,
                    np.array(a["look"], float) * (1 - f) + np.array(b["look"], float) * f)
    k = ks[-1]
    return np.array(k["at"], float), np.array(k["look"], float)


def from_camera(keys: list, t0: float, t1: float) -> Move:
    """A move that follows a take's camera between two moments: towards what it looks at is a push, sideways a pan,
    up or down a tilt (the still is one frame; the move suggests the rest of the path)."""
    p0, l0 = _cam(keys, t0)
    p1, _ = _cam(keys, t1)
    v = l0 - p0
    dist = float(np.linalg.norm(v)) or 1.0
    f = v / dist
    up = np.array([0.0, 0.0, 1.0])
    r = np.cross(f, up)
    r = r / (np.linalg.norm(r) or 1.0)
    u = np.cross(r, f)
    d = p1 - p0
    fwd = float(np.dot(d, f)) / dist
    lat = float(np.dot(d, r)) / dist
    vert = float(np.dot(d, u)) / dist
    push = max(-0.16, min(0.2, 0.25 * fwd))
    x = max(-0.08, min(0.08, 0.12 * lat))
    y = max(-0.08, min(0.08, -0.12 * vert))
    base = 1.0 + (0.1 if abs(x) > 0.005 or abs(y) > 0.005 else 0.0)
    z0, z1 = (base, base + push) if push >= 0 else (base - push, base)
    return Move(z0, z1, 0.5 - x, 0.5 + x, 0.5 - y, 0.5 + y)


@dataclass
class Piece:
    seconds: float
    start: Optional[Path] = None
    end: Optional[Path] = None           # dissolve into this over the second half
    move: Move = field(default_factory=Move)
    video: Optional[Path] = None         # play this across the piece instead of the stills
    label: str = ""

    def key(self) -> dict:
        from ..project import file_key
        fk = lambda p: file_key(p) | {"dir": p.parent.name} if p else None
        return {"s": round(self.seconds, 3), "a": fk(self.start), "b": fk(self.end), "v": fk(self.video),
                "m": [round(x, 4) for x in (self.move.z0, self.move.z1, self.move.x0, self.move.x1, self.move.y0, self.move.y1)]}


class _Video:
    """Frames of a clip read in order (an FFmpeg pipe at the output size), addressed by position 0-1."""
    def __init__(self, path: Path, W: int, H: int):
        from ..project import probe
        info = probe(path)
        num, _, den = str(info.get("r_frame_rate", "24/1")).partition("/")
        fps = float(num) / float(den or 1)
        self.n = max(1, int(round(float(info.get("duration") or 1) * fps)))
        self.W, self.H, self.i, self.last = W, H, -1, None
        vf = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}"
        self.p = subprocess.Popen([settings()["ffmpeg"], "-hide_banner", "-loglevel", "error", "-i", str(path), "-vf", vf,
                                   "-f", "rawvideo", "-pix_fmt", "bgr24", "-"], stdout=subprocess.PIPE,
                                  stderr=subprocess.DEVNULL)

    def at(self, u: float) -> np.ndarray:
        want = min(self.n - 1, int(round(u * (self.n - 1))))
        size = self.W * self.H * 3
        while self.i < want:
            buf = self.p.stdout.read(size)
            if len(buf) < size:
                self.n = max(1, self.i + 1)
                break
            self.last = np.frombuffer(buf, np.uint8).reshape(self.H, self.W, 3)
            self.i += 1
        return self.last if self.last is not None else np.zeros((self.H, self.W, 3), np.uint8)

    def close(self):
        if self.p.poll() is None:
            self.p.kill()


def _load(path: Path, cache: dict, W: int, H: int) -> np.ndarray:
    import cv2
    k = str(path)
    if k not in cache:
        if len(cache) > 12:
            cache.pop(next(iter(cache)))
        im = cv2.imread(k, cv2.IMREAD_UNCHANGED)
        if im is None:
            raise BuildError(f"storyboard: cannot read {path}")
        if im.ndim == 2:
            im = cv2.cvtColor(im, cv2.COLOR_GRAY2BGR)
        elif im.shape[2] == 4:   # a transparent still (a product cut-out) sits on dark grey
            a = im[:, :, 3:4].astype(np.float32) / 255
            im = (im[:, :, :3].astype(np.float32) * a + 30 * (1 - a)).astype(np.uint8)
        # cover the frame once at a little over output size, so warps stay cheap
        h, w = im.shape[:2]
        s = max(W / w, H / h) * 1.25
        if s < 1:
            im = cv2.resize(im, (max(W, round(w * s)), max(H, round(h * s))), interpolation=cv2.INTER_AREA)
        cache[k] = im
    return cache[k]


def _smooth(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


def timings(pieces: list[Piece], fade: float) -> tuple[list[float], float, float]:
    """Start time of each piece, the total length and the dissolve actually used (never over a third of a piece)."""
    if not pieces:
        return [], 0.0, 0.0
    fade = min([fade] + [p.seconds / 3 for p in pieces]) if len(pieces) > 1 else 0.0
    starts, t = [], 0.0
    for p in pieces:
        starts.append(t)
        t += p.seconds - fade
    return starts, t + fade, fade


def render(pieces: list[Piece], out: Path, size: tuple[int, int] = (1280, 720), fps: int = 24, fade: float = 0.5,
           gop: Optional[int] = 6, crf: int = 22, moves: bool = True, overlay: Optional[Callable[[int], Optional[np.ndarray]]] = None,
           log: Callable[[str], None] = print, progress: Callable[[float, str], None] = lambda f, m="": None) -> float:
    """Encode the pieces end to end (dissolves of `fade` seconds) to `out`; returns the length in seconds.
    moves=False holds each still (the stills storyboard); overlay(frame) -> RGBA over the frame (captions)."""
    import cv2
    from ..trailer.frame import warp
    W, H = size
    starts, total, fade = timings(pieces, fade)
    n = max(1, int(round(total * fps)))
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp.mp4")
    args = [settings()["ffmpeg"], "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24",
            "-s", f"{W}x{H}", "-r", str(fps), "-i", "-", "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", str(crf),
            "-pix_fmt", "yuv420p", "-movflags", "+faststart"]
    if gop:
        args += ["-g", str(gop), "-keyint_min", str(gop), "-sc_threshold", "0"]
    enc = subprocess.Popen(args + [str(tmp)], stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    stills: dict = {}
    videos: dict[int, _Video] = {}

    def frame_of(k: int, t: float) -> np.ndarray:
        p = pieces[k]
        u = (t - starts[k]) / max(p.seconds, 1e-6)
        if p.video is not None:
            if k not in videos:
                videos[k] = _Video(p.video, W, H)
            return videos[k].at(u)
        fx, fy, z = p.move.at(u) if moves else (0.5, 0.5, 1.0)
        img = warp(_load(p.start, stills, W, H), W, H, fx, fy, z)
        if p.end is not None and u > 0.45:
            b = warp(_load(p.end, stills, W, H), W, H, fx, fy, z)
            img = cv2.addWeighted(img, 1 - _smooth((u - 0.45) / 0.45), b, _smooth((u - 0.45) / 0.45), 0)
        return img

    try:
        for i in range(n):
            t = i / fps
            k = max(0, min(len(pieces) - 1, next((j for j in range(len(pieces) - 1, -1, -1) if starts[j] <= t), 0)))
            img = frame_of(k, t)
            if k > 0 and fade > 0 and t < starts[k] + fade:   # dissolve from the piece before
                prev = frame_of(k - 1, t)
                a = _smooth((t - starts[k]) / fade)
                img = cv2.addWeighted(prev, 1 - a, img, a, 0)
            for j in [j for j in videos if j < k - 1]:
                videos.pop(j).close()
            if overlay is not None:
                over = overlay(i)
                if over is not None:
                    al = over[:, :, 3:4].astype(np.float32) * (1 / 255)
                    img = (img.astype(np.float32) * (1 - al) + over[:, :, :3].astype(np.float32) * al).astype(np.uint8)
            enc.stdin.write(np.ascontiguousarray(img).tobytes())
            if i % 48 == 0:
                progress(i / n, f"frame {i}/{n}")
        enc.stdin.close()
        if enc.wait() != 0:
            raise BuildError("storyboard encode failed: " + enc.stderr.read().decode(errors="replace")[-800:])
    finally:
        for v in videos.values():
            v.close()
        if enc.poll() is None:
            enc.kill()
    tmp.replace(out)
    return total
