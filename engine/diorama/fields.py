"""Small numpy helpers for painting a diorama's ground: noise, signed distances, masks, soft edges."""
from __future__ import annotations

import math

import numpy as np


def smoothstep(a: float, b: float, x):
    t = np.clip((x - a) / (b - a if b != a else 1e-9), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def value_noise(rng: np.random.Generator, n: int, cells: int, octaves: int = 3, persistence: float = 0.5) -> np.ndarray:
    """Smooth value noise on an n x n grid, 0..1, `cells` across at the first octave."""
    import cv2
    out = np.zeros((n, n), np.float32)
    amp, total = 1.0, 0.0
    for o in range(octaves):
        c = max(2, cells * 2 ** o)
        g = rng.random((c + 1, c + 1)).astype(np.float32)
        out += amp * cv2.resize(g, (n, n), interpolation=cv2.INTER_CUBIC)
        total += amp
        amp *= persistence
    out /= total
    lo, hi = float(out.min()), float(out.max())
    return (out - lo) / max(hi - lo, 1e-6)


def ellipse_sdf(X, Z, cx, cz, a, b, rot_deg=0.0):
    """Approximate signed distance (negative inside) to an ellipse with radii a (along its x) and b."""
    t = math.radians(rot_deg)
    dx, dz = X - cx, Z - cz
    u = dx * math.cos(t) + dz * math.sin(t)
    v = -dx * math.sin(t) + dz * math.cos(t)
    k = np.sqrt((u / a) ** 2 + (v / b) ** 2)
    return (k - 1.0) * min(a, b)


def segment_sdf(X, Z, p0, p1, radius):
    """Signed distance to a capsule from p0 to p1."""
    px, pz = X - p0[0], Z - p0[1]
    dx, dz = p1[0] - p0[0], p1[1] - p0[1]
    L2 = dx * dx + dz * dz or 1e-9
    t = np.clip((px * dx + pz * dz) / L2, 0, 1)
    return np.hypot(px - t * dx, pz - t * dz) - radius


def box_sdf(X, Z, cx, cz, hx, hz, rot_deg=0.0):
    t = math.radians(rot_deg)
    dx, dz = X - cx, Z - cz
    u = dx * math.cos(t) + dz * math.sin(t)
    v = -dx * math.sin(t) + dz * math.cos(t)
    qx, qz = np.abs(u) - hx, np.abs(v) - hz
    return np.hypot(np.maximum(qx, 0), np.maximum(qz, 0)) + np.minimum(np.maximum(qx, qz), 0)


def hex_rgb(h: str) -> np.ndarray:
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return np.array([int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)], np.float32)


def to_hex(c) -> str:
    c = np.clip(np.asarray(c, np.float32), 0, 1)
    return "#%02x%02x%02x" % tuple(int(round(v * 255)) for v in c)


def mix(a, b, t):
    return a + (b - a) * t
