"""Variants: every image the edit workspace renders is kept, per image, under
`<project>/storyboard/variants/<shot>/<slot>[~depth]/` with an index.json that records, for each, the recipe that drew it
(prompt or instruction, seed, steps ...) and the cache entry it lives in. Picking one writes its recipe back into
site.yaml, so the full build finds that very image in its cache.

Which variant is *current* is never stored: it is the one whose cache entry is the image the spec describes now.
`history` only remembers the order variants were made current from here, for Revert.
"""
from __future__ import annotations

import json
import os
import shutil
import threading
import time
from pathlib import Path
from typing import Optional

from ...project import BuildError, Project

_LOCKS: dict[str, threading.RLock] = {}
LOCK_STALE_S = 3 * 3600


def _lock(project: Project) -> threading.RLock:
    return _LOCKS.setdefault(str(project.root), threading.RLock())


def root(project: Project) -> Path:
    return project.root / "storyboard" / "variants"


def folder(project: Project, key: str) -> Path:
    return root(project) / key


def load(project: Project, key: str) -> dict:
    p = folder(project, key) / "index.json"
    try:
        data = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except (OSError, ValueError):
        data = {}
    data.setdefault("key", key)
    data.setdefault("variants", [])
    data.setdefault("history", [])
    return data


def _save(project: Project, key: str, data: dict) -> None:
    d = folder(project, key)
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / "index.json.tmp"
    tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
    os.replace(tmp, d / "index.json")


def find(data: dict, cache: str) -> Optional[dict]:
    return next((v for v in reversed(data["variants"]) if v.get("cache") == cache), None)


def get(data: dict, n: int) -> Optional[dict]:
    return next((v for v in data["variants"] if v["n"] == n), None)


def register(project: Project, key: str, src: Path, cache: str, recipe: dict, origin: str,
             seed: Optional[int] = None, make_current: bool = False) -> dict:
    """Keep a copy of `src` as a variant of `key` (once per cache entry); returns its index entry."""
    with _lock(project):
        data = load(project, key)
        hit = find(data, cache)
        if hit is not None:
            if make_current and (not data["history"] or data["history"][-1] != hit["n"]):
                data["history"].append(hit["n"])
                _save(project, key, data)
            return hit
        n = max([v["n"] for v in data["variants"]] + [0]) + 1
        suffix = Path(src).suffix or ".png"
        name = f"v{n:03d}" + (f"_s{seed}" if seed is not None else "") + suffix
        d = folder(project, key)
        d.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, d / name)
        v = {"n": n, "cache": cache, "file": name, "seed": seed, "recipe": recipe, "origin": origin,
             "time": time.strftime("%Y-%m-%d %H:%M:%S")}
        data["variants"].append(v)
        if make_current:
            data["history"].append(n)
        _save(project, key, data)
        return v


def file_of(project: Project, key: str, v: dict) -> Path:
    return folder(project, key) / v["file"]


def push_history(project: Project, key: str, n: int) -> None:
    with _lock(project):
        data = load(project, key)
        if not data["history"] or data["history"][-1] != n:
            data["history"].append(n)
            _save(project, key, data)


def revert_target(project: Project, key: str) -> Optional[dict]:
    """The variant that was current before the latest one made current from here, if any (does not change anything)."""
    data = load(project, key)
    h = [n for n in data["history"] if get(data, n)]
    if len(h) < 2:
        return None
    return get(data, h[-2])


def pop_history(project: Project, key: str) -> None:
    with _lock(project):
        data = load(project, key)
        if data["history"]:
            data["history"].pop()
            _save(project, key, data)


def used_seeds(project: Project, key: str) -> set[int]:
    return {v["seed"] for v in load(project, key)["variants"] if v.get("seed") is not None}


# ---------------------------------------------------------------- one job per image

class Busy(BuildError):
    pass


def _pid_alive(pid: int) -> bool:
    if pid == os.getpid():
        return True
    try:
        if os.name == "nt":
            import ctypes
            k32 = ctypes.windll.kernel32
            h = k32.OpenProcess(0x1000, False, pid)     # PROCESS_QUERY_LIMITED_INFORMATION
            if not h:
                return False
            code = ctypes.c_ulong()
            ok = k32.GetExitCodeProcess(h, ctypes.byref(code))
            k32.CloseHandle(h)
            return bool(ok) and code.value == 259       # STILL_ACTIVE
        os.kill(pid, 0)
        return True
    except (OSError, ValueError, AttributeError):
        return False


def _holder_alive(text: str) -> bool:
    import re
    m = re.search(r"pid (\d+)", text or "")
    return bool(m) and _pid_alive(int(m.group(1)))


def claim(project: Project, key: str, who: str) -> Path:
    """Take the image's lock (a file, so another process on the same project sees it too). Raises Busy."""
    d = folder(project, key)
    d.mkdir(parents=True, exist_ok=True)
    lock = d / ".busy"
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        try:
            age = time.time() - lock.stat().st_mtime
            holder = lock.read_text(encoding="utf-8")
        except OSError:
            age, holder = 0, ""
        if age < LOCK_STALE_S and _holder_alive(holder):
            raise Busy(f"{key} is already being rendered ({holder or 'another job'})")
        lock.unlink(missing_ok=True)
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(f"{who} pid {os.getpid()}")
    return lock


def release(lock: Path) -> None:
    lock.unlink(missing_ok=True)


def busy(project: Project, key: str) -> bool:
    lock = folder(project, key) / ".busy"
    try:
        return lock.exists() and time.time() - lock.stat().st_mtime < LOCK_STALE_S and _holder_alive(lock.read_text(encoding="utf-8"))
    except OSError:
        return False
