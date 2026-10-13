"""CAD and print formats to GLB, run in a child process so a huge or broken file can't take the build down.

  python -m engine.backends.cad step  SRC DST <linear mm> <angular rad>   STEP/STP -> GLB (OpenCascade via cascadio)
  python -m engine.backends.cad 3mf   SRC DST                             3MF -> GLB (trimesh); prints {"units": ...}

STEP keeps its assembly tree and part names (one node per part, one primitive per colour) and is written in metres.
3MF is written in the file's own units (the caller applies them) and turned from z-up to glTF's y-up, so both arrive
in Blender with the file's own axes.
"""
from __future__ import annotations

import json
import sys


def step_to_glb(src: str, dst: str, linear: float, angular: float) -> None:
    try:
        import cascadio
    except ImportError:
        raise SystemExit("STEP models need the cascadio package (OpenCascade): pip install cascadio")
    code = cascadio.step_to_glb(src, dst, tol_linear=linear, tol_angular=angular, tol_relative=False,
                                merge_primitives=True, use_parallel=True)
    if code != 0:
        raise SystemExit(f"OpenCascade could not convert {src} (code {code}); is it a valid STEP file?")


def threemf_to_glb(src: str, dst: str) -> dict:
    try:
        import numpy as np
        import trimesh
    except ImportError:
        raise SystemExit("3MF models need trimesh and lxml: pip install trimesh lxml")
    scene = trimesh.load(src, force="scene")
    if not scene.geometry:
        raise SystemExit(f"{src} has no meshes")
    units = (scene.metadata or {}).get("units") or getattr(scene, "units", None) or "millimeter"
    zup_to_yup = np.array([[1, 0, 0, 0], [0, 0, 1, 0], [0, -1, 0, 0], [0, 0, 0, 1]], dtype=float)
    scene.apply_transform(zup_to_yup)
    scene.export(dst, file_type="glb")
    return {"units": str(units)}


if __name__ == "__main__":
    kind, src, dst = sys.argv[1:4]
    if kind == "step":
        step_to_glb(src, dst, float(sys.argv[4]), float(sys.argv[5]))
        print(json.dumps({"units": "m"}))
    elif kind == "3mf":
        print(json.dumps(threemf_to_glb(src, dst)))
    else:
        raise SystemExit(f"unknown kind {kind}")
