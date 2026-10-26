"""A storyboard sketch of a take: a few moments of its world, rendered by take.py's own world pass.

  SS_STILLS=0,5,15 blender -b --factory-startup -P take_stills.py -- --take take.json --pass world --out DIR --res 1280x720

take.py runs unchanged (the same world, camera and Workbench look as the blockout stage); blockout_lib.render is told
to render only these seconds, as stills/tSS.SS.png (with their depth), instead of every frame. take.py itself is not
edited, because its content is part of the product pass's cache key.
"""
import os
import runpy
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import blockout_lib  # noqa: E402

STILLS = [float(x) for x in os.environ.get("SS_STILLS", "0").split(",") if x.strip()]
_render = blockout_lib.render


def render(args, cam, target, depth_far=400.0):
    args.stills = STILLS
    return _render(args, cam, target, depth_far)


blockout_lib.render = render
runpy.run_path(os.path.join(HERE, "take.py"), run_name="__main__")
