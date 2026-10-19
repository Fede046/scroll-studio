"""Miniature worlds: the layout half of the `diorama` scene (the drawing half is runtime/src/players/diorama/).

`plan.build(scene, table)` lays a world out from the spec: ground texture, height grid, props, places, camera beats."""
from .plan import build, step_windows

__all__ = ["build", "step_windows"]
