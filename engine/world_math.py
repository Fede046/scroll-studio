"""world_math: the geometry of type in the world, as plain functions (no models, no ComfyUI), shared by the builder and the tests.

Coordinates. Everything is measured in pixels of the *working frame* (960x540, the film cropped to 16:9). A text lives on a
*plane* whose unit is the plane's width (y down): for `behind` and `sky` the plane is the anchor frame itself
(x / 960, y / 960), for `surface` it is the surface rectified from its quad (a unit wide, 1/aspect tall). Per frame the
builder gives the runtime a 3x3 matrix that takes a pixel of the *current* frame (as 0-1 across and down) to the plane, so
the shader needs one matrix multiply and a division per pixel to find which letter it is on.
"""
from __future__ import annotations

import cv2
import numpy as np

W, H = 960, 540


# ---------------------------------------------------------------- surfaces

def order_quad(pts: np.ndarray) -> np.ndarray:
    """Four points -> top-left, top-right, bottom-right, bottom-left."""
    p = np.asarray(pts, dtype=np.float64).reshape(4, 2)
    c = p.mean(axis=0)
    ang = np.arctan2(p[:, 1] - c[1], p[:, 0] - c[0])
    p = p[np.argsort(ang)]                          # clockwise from the right-hand side, y down
    s = p.sum(axis=1)
    tl = int(np.argmin(s))
    return np.roll(p, -tl, axis=0)


def surface_quad(mask: np.ndarray, inset: float = 0.03) -> np.ndarray:
    """The four corners (TL, TR, BR, BL; pixels) of a surface mask: its largest part's convex hull reduced to a quadrilateral
    (the polygon fit is loosened until four corners are left; a hull that never gets there falls back to the minimum-area
    rectangle), pulled in towards the middle by `inset` so the type stays on the surface."""
    m = (np.asarray(mask) > 127).astype(np.uint8)
    cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cnts:
        raise ValueError("the surface mask is empty")
    big = max(cnts, key=cv2.contourArea)
    hull = cv2.convexHull(big)
    per = cv2.arcLength(hull, True)
    quad = None
    for eps in np.linspace(0.005, 0.15, 30):
        ap = cv2.approxPolyDP(hull, eps * per, True)
        if len(ap) == 4:
            quad = ap.reshape(4, 2).astype(np.float64)
            break
        if len(ap) < 4:
            break
    if quad is None:
        quad = cv2.boxPoints(cv2.minAreaRect(hull)).astype(np.float64)
    quad = order_quad(quad)
    c = quad.mean(axis=0)
    return c + (quad - c) * (1 - inset)


def plane_aspect(quad: np.ndarray, size: tuple[int, int] = (W, H)) -> float:
    """Width / height of the rectangle that a quadrilateral seen in perspective really is (Zhang and He's whiteboard
    method: the focal length and the aspect fall out of the quad when the pixels are square and the principal point is the
    centre). Falls back to the mean edge lengths when the quad is nearly fronto-parallel (the formula divides by zero)."""
    q = np.asarray(quad, dtype=np.float64).reshape(4, 2)
    tl, tr, br, bl = q
    edge = 0.5 * (np.linalg.norm(tr - tl) + np.linalg.norm(br - bl)) / max(0.5 * (np.linalg.norm(bl - tl) + np.linalg.norm(br - tr)), 1e-6)
    u0, v0 = size[0] / 2, size[1] / 2
    m1, m2, m3, m4 = [np.array([p[0] - u0, p[1] - v0, 1.0]) for p in (tl, tr, bl, br)]
    try:
        k2 = np.dot(np.cross(m1, m4), m3) / np.dot(np.cross(m2, m4), m3)
        k3 = np.dot(np.cross(m1, m4), m2) / np.dot(np.cross(m3, m4), m2)
        n2, n3 = k2 * m2 - m1, k3 * m3 - m1
        den = n2[2] * n3[2]
        f2 = -((n2[0] * n3[0]) + (n2[1] * n3[1])) / den if abs(den) > 1e-9 else -1.0
        if f2 <= 0 or not np.isfinite(f2):
            return float(np.clip(edge, 0.25, 6.0))
        f = np.sqrt(f2)
        Ai = np.linalg.inv(np.array([[f, 0, 0], [0, f, 0], [0, 0, 1.0]]))
        Q = Ai.T @ Ai
        a = np.sqrt(abs(n2 @ Q @ n2) / max(abs(n3 @ Q @ n3), 1e-12))
        if not np.isfinite(a):
            return float(np.clip(edge, 0.25, 6.0))
        # trust the projective estimate only when it is not wildly away from what the edges say
        if not (0.5 < a / edge < 2.0):
            a = edge
        return float(np.clip(a, 0.25, 6.0))
    except (ZeroDivisionError, FloatingPointError, np.linalg.LinAlgError):
        return float(np.clip(edge, 0.25, 6.0))


def rectify(quad: np.ndarray, aspect: float) -> np.ndarray:
    """Homography from frame pixels to the surface's plane (a unit wide, 1/aspect tall), taking the quad to its corners."""
    dst = np.float32([[0, 0], [1, 0], [1, 1 / aspect], [0, 1 / aspect]])
    return cv2.getPerspectiveTransform(np.float32(quad), dst).astype(np.float64)


def frame_plane() -> np.ndarray:
    """The plane of `behind` and `sky` type: the anchor frame itself, a unit wide."""
    return np.diag([1 / W, 1 / W, 1.0])


# ---------------------------------------------------------------- the per-frame matrix the player reads

def screen_matrix(R: np.ndarray, Ht: np.ndarray, angle_about: tuple[float, float, float] | None = None) -> np.ndarray:
    """Pixel (0-1 across and down) of frame t -> plane. R takes anchor-frame pixels to the plane; Ht takes anchor-frame pixels
    to frame t's. `angle_about` (cx, cy, degrees): turn the type on the plane about its centre."""
    S = np.diag([float(W), float(H), 1.0])
    M = R @ np.linalg.inv(Ht) @ S
    if angle_about and angle_about[2]:
        cx, cy, deg = angle_about
        a = np.deg2rad(-deg)
        c, s = np.cos(a), np.sin(a)
        T = np.array([[1, 0, -cx], [0, 1, -cy], [0, 0, 1.0]])
        Rot = np.array([[c, -s, 0], [s, c, 0], [0, 0, 1.0]])
        M = np.linalg.inv(T) @ Rot @ T @ M
    return M


def pack_matrix(M: np.ndarray, center: tuple[float, float] = (0.0, 0.0)) -> list[float]:
    """3x3 -> the nine numbers the player stores (row major, six significant digits). A homography is only defined up to a
    scale, and its sign matters: the player drops pixels whose w is not positive (the other side of a floor's horizon, where
    the plane's coordinates run through infinity), so the sign is chosen to make w positive at the plane point `center` (the
    middle of the type), and the scale to make the matrix of order one."""
    M = np.asarray(M, dtype=np.float64)
    z = (np.linalg.inv(M) @ np.array([center[0], center[1], 1.0]))[2]
    if z < 0:
        M = -M
    M = M / np.linalg.norm(M)
    return [float(f"{v:.6g}") for v in M.ravel()]


def unpack_matrix(v) -> np.ndarray:
    return np.asarray(v, dtype=np.float64).reshape(3, 3)


def apply(M: np.ndarray, u: float, v: float) -> tuple[float, float] | None:
    """The shader's lookup: pixel (u, v in 0-1 of the frame) -> plane coordinates (None where w is not positive)."""
    p = M @ np.array([u, v, 1.0])
    if p[2] <= 0:
        return None
    return float(p[0] / p[2]), float(p[1] / p[2])


# ---------------------------------------------------------------- text boxes

def estimate_lines(chars: int, lines: int | None, plane_h: float, size: float, hmax: float = 0.3) -> tuple[int, float]:
    """(lines, block height in plane widths) a title of `chars` letters will have at `size` (a fraction of the plane's width).
    The player sets the type the same way with the real font measured (lib/worldText.ts `layout`: more lines make larger
    type for the same width, so the most lines whose block is no taller than `hmax` of the plane's height); this uses an
    average face, enough to know roughly where the type is."""
    adv, lead = 0.52, 1.08

    def block(n: int) -> float:
        return size / (adv * max(1.0, chars / n)) * lead * n

    if lines:
        return lines, min(block(lines), hmax * plane_h)
    n = 1
    for k in range(2, 6):
        if block(k) <= hmax * plane_h:
            n = k
        else:
            break
    return n, min(block(n), hmax * plane_h)


# ---------------------------------------------------------------- occlusion (the shader's twin)

def smoothstep(a: float, b: float, x):
    t = np.clip((np.asarray(x, dtype=np.float64) - a) / max(b - a, 1e-9), 0, 1)
    return t * t * (3 - 2 * t)


def visibility(scene_depth, text_depth: float, soft: float):
    """How much of a type pixel shows (0-1) where the scene's depth is `scene_depth` (0 far .. 1 near): all of it where the
    scene is farther than the type, none where it is nearer, a soft step of width 2*soft in between."""
    return 1.0 - smoothstep(text_depth - soft, text_depth + soft, scene_depth)


# ---------------------------------------------------------------- a surface's orientation from the depth map

FOCAL = 0.85            # the focal length as a fraction of the picture's width: an ordinary lens, about 62 degrees across.
                        # Generated footage has no calibration; this is the guess


def fit_disparity_plane(D: np.ndarray, mask: np.ndarray, size: tuple[int, int] = (W, H), iters: int = 4) -> np.ndarray | None:
    """Fit d = a*x + b*y + c to the depth map `D` (0 far .. 1 near, Depth Anything's relative disparity) over the mask's
    pixels, in calibrated image coordinates x = (px - cx) / f. A plane's disparity is linear in the image, and zero on its
    vanishing line (the horizon, for a floor), so (a, b, c) is the plane's normal (in camera coordinates, up to scale) when
    the map's zero is the far distance, which the per-shot normalisation makes it. `D`, `mask` and `size` are at one
    resolution. Returns (a, b, c) or None."""
    w, h = size
    f = FOCAL * w
    ys, xs = np.nonzero(np.asarray(mask) > 127)
    if len(xs) < 200:
        return None
    if len(xs) > 30000:
        idx = np.random.default_rng(3).choice(len(xs), 30000, replace=False)
        xs, ys = xs[idx], ys[idx]
    x = (xs - w / 2) / f
    y = (ys - h / 2) / f
    d = D[ys, xs].astype(np.float64)
    A = np.stack([x, y, np.ones_like(x)], axis=1)
    wt = np.ones(len(x))
    sol = None
    for _ in range(iters):
        sol, *_ = np.linalg.lstsq(A * wt[:, None], d * wt, rcond=None)
        r = np.abs(A @ sol - d)
        wt = 1.0 / (1.0 + (r / 0.03) ** 2)
    return sol


def plane_frame(n: np.ndarray, center_px: tuple[float, float], size: tuple[int, int] = (W, H)) -> np.ndarray:
    """Homography from a surface's plane to frame pixels (a 3x3 `P`; its inverse is the rectifying map), for a plane with
    normal `n` (camera coordinates) through the ray of `center_px`. The plane's unit is the width of the frame at the
    centre; its (0, 0) is the centre; u runs along the surface's horizontal (the camera's x axis laid in it), v runs down
    the picture. A plane facing the camera gives (nearly) the identity."""
    w, h = size
    f = FOCAL * w
    n = np.asarray(n, dtype=np.float64)
    n = n / max(np.linalg.norm(n), 1e-9)
    if n[2] < 0:
        n = -n
    cx, cy = center_px
    X0 = np.array([(cx - w / 2) / f, (cy - h / 2) / f, 1.0])
    ex = np.array([1.0, 0.0, 0.0])
    ex = ex - n * (ex @ n)
    if np.linalg.norm(ex) < 1e-3:                        # a plane edge-on along x: use the y axis
        ex = np.array([0.0, 1.0, 0.0]) - n * n[1]
    ex /= np.linalg.norm(ex)
    ey = np.cross(n, ex)
    ey /= np.linalg.norm(ey)
    K = np.array([[f, 0, w / 2], [0, f, h / 2], [0, 0, 1.0]])

    def img(v):
        p = K @ v
        return p[:2] / p[2]

    if (img(X0 + 0.01 * ey) - img(X0))[1] < 0:           # v runs down the picture
        ey = -ey
    # the unit: s plane-units-in-camera-space per plane unit, so one unit spans the frame's width at the centre
    span = np.linalg.norm(img(X0 + 0.005 * ex) - img(X0 - 0.005 * ex)) / 0.01
    s = w / max(span, 1e-6)
    P = K @ np.stack([ex * s, ey * s, X0], axis=1)
    return P / P[2, 2]
