"""Polish report: `studio inspect`. Scores a built film section (beats or take) second by second and beat by beat for
pops, softness, halos, style drift and morphs, so problems are flagged before the owner sees them.

    from engine.polish import inspect_section
    report = inspect_section(project, "story")          # cached by the film's content; writes .build/inspect/story.json + .html

See run.py for the report's shape and analyze.py / metrics.py for the measurements.
"""
from .api import (inspect_project, inspect_section, inspect_video, report_path, load_report, beat_badges,  # noqa: F401
                  Nothing, METRICS)
