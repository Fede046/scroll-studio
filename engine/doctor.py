"""`studio doctor`: check every external tool and say which scene types are ready."""
from __future__ import annotations

import importlib.util
import shutil
import subprocess
from pathlib import Path

from .config import STATIC, settings


def _ver(cmd: list[str]) -> str | None:
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return (out.stdout or out.stderr).strip().splitlines()[0] if out.returncode == 0 else None
    except Exception:
        return None


def checks() -> list[dict]:
    s = settings()
    res = []
    def add(name, ok, detail, needed_by):
        res.append({"name": name, "ok": bool(ok), "detail": detail or "missing", "needed_by": needed_by})

    add("Node.js", _ver(["node", "--version"]), _ver(["node", "--version"]), "building the runtime and UI")
    add("Runtime bundle", (STATIC / "runtime" / "index.js").exists(), "engine/compile/static/runtime", "every site (npm run build)")
    ff = _ver([s["ffmpeg"], "-version"])
    add("FFmpeg", ff, ff and ff[:40], "film, sequence, recordings")
    bl = _ver([s["blender"], "--version"])
    add("Blender", bl, bl or s["blender"], "film (blockout), sequence")
    try:
        import torch
        gpu = torch.cuda.is_available()
        detail = f"{torch.cuda.get_device_name(0)}, {torch.cuda.get_device_properties(0).total_memory / 2**30:.0f} GB" if gpu else "no CUDA GPU"
        add("PyTorch + CUDA", gpu, detail, "parallax (depth), film")
    except Exception:
        add("PyTorch + CUDA", False, "torch not installed", "parallax (depth), film")
    for mod, need in (("transformers", "parallax (depth)"), ("cv2", "artwork"), ("websocket", "recordings"), ("playwright", "recordings, URL capture"),
                      ("cascadio", "product models in STEP/STP (OpenCascade)"), ("trimesh", "product models in 3MF"),
                      ("lxml", "product models in 3MF")):
        add(mod, importlib.util.find_spec(mod), "installed" if importlib.util.find_spec(mod) else None, need)
    try:
        from .backends import comfy
        add("ComfyUI", comfy.alive(), s["comfy_url"] if comfy.alive() else f"not running at {s['comfy_url']}",
            "film, generated images (`generate:`)")
    except Exception as e:
        add("ComfyUI", False, str(e), "film, generated images")
    res.extend(wan_checks())
    add("Chrome", shutil.which("chrome") or Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe").exists() or s["chrome"],
        "found", "recordings")
    return res


def wan_checks() -> list[dict]:
    """Every Wan 2.2 file (engine/models.yaml entries with `wan:`), looked up in ComfyUI's own model lists, so a
    file in a subfolder, on another drive behind a junction, or renamed in studio.toml [wan] is found where ComfyUI
    loads it from. Without ComfyUI running, the check can't see them and says so."""
    import yaml
    from .backends import comfy
    entries = [m for m in yaml.safe_load((Path(__file__).parent / "models.yaml").read_text(encoding="utf-8"))["comfyui"]
               if m.get("wan")]
    names = comfy.wan_model_names()
    lists, out = {}, []
    for m in entries:
        key = m["wan"]
        folder = comfy.WAN_FOLDERS[key]
        if folder not in lists:
            lists[folder] = comfy.listed(folder)
        have, want = lists[folder], names[key]
        base = want.replace("\\", "/").rsplit("/", 1)[-1]
        if have is None:
            ok, detail = False, f"{want}: ComfyUI not running, can't check"
        else:
            hit = want if want in have else next((h for h in have if h.replace("\\", "/").rsplit("/", 1)[-1] == base), None)
            ok = hit is not None
            detail = f"{folder}/{hit}" if ok else f"missing {folder}/{want} ({m['size_gb']} GB): {m['source']}"
        out.append({"name": m["name"], "ok": ok, "detail": detail, "needed_by": ", ".join(m.get("used_by", []))})
    return out


def report() -> None:
    from rich.console import Console
    from rich.table import Table
    t = Table(title="Scroll Studio doctor")
    for c in ("", "Check", "Detail", "Needed by"):
        t.add_column(c)
    for c in checks():
        t.add_row("[green]✓[/]" if c["ok"] else "[red]✗[/]", c["name"], str(c["detail"]), c["needed_by"])
    Console().print(t)
