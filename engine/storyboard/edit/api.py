"""HTTP side of the edit workspace: one router, used by `studio storyboard <project> --edit` (its own small server) and
mounted in `studio ui`'s server too.

  GET  /sb/{name}                         the page
  GET  /api/sb/{name}/state | poll        everything shown / what changed since (spec revision, running jobs)
  POST /api/sb/{name}/save                field edits -> site.yaml (422 {errors} when invalid, 409 {conflict} when the
                                          file moved on under the fields being saved)
  POST /api/sb/{name}/lock | approve | undo | sheet
  POST /api/sb/{name}/image               {key, mode: regenerate|rerun}   one image job (409 if it is already running)
  POST /api/sb/{name}/pick | revert       make a kept variant current
  GET  /api/sb/{name}/img?p=&w=           an image of the project, as a thumbnail (w) or whole
  GET  /sb/{name}/files/...               the storyboard folder (sheet, stand-in page)
"""
from __future__ import annotations

import socket
import threading
import webbrowser
from pathlib import Path
from typing import Callable, Optional

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel

from ...project import BuildError, Project
from ...server.jobs import JobQueue
from . import images, specdoc, variants
from .workspace import Workspace

PAGE = Path(__file__).with_name("page.html")
PORTS = range(8971, 8980)
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp"}


class Edit(BaseModel):
    path: str
    value: object = None
    old: object = None
    has_old: bool = True


class SaveReq(BaseModel):
    edits: list[dict]
    rev: Optional[str] = None


class LockReq(BaseModel):
    shot: str
    locked: bool


class ApproveReq(BaseModel):
    shot: str
    approved: bool


class ImageReq(BaseModel):
    key: str
    mode: str = "regenerate"
    seed: Optional[int] = None


class PickReq(BaseModel):
    key: str
    n: int


class KeyReq(BaseModel):
    key: str


def make_router(resolve: Callable[[str], Project], jobs: JobQueue) -> APIRouter:
    r = APIRouter()
    spaces: dict[str, Workspace] = {}

    def ws(name: str) -> Workspace:
        project = resolve(name)
        key = str(project.root)
        if key not in spaces:
            spaces[key] = Workspace(project, jobs)
        return spaces[key]

    def guarded(fn):
        try:
            return fn()
        except specdoc.SpecError as e:
            return JSONResponse({"ok": False, "errors": e.errors}, 422)
        except specdoc.Conflict as e:
            return JSONResponse({"ok": False, "conflict": e.paths,
                                 "error": "site.yaml changed on disk under these fields; they were reloaded"}, 409)
        except variants.Busy as e:
            return JSONResponse({"ok": False, "error": str(e)}, 409)
        except BuildError as e:
            return JSONResponse({"ok": False, "error": str(e)}, 400)

    @r.get("/sb/{name}", response_class=HTMLResponse)
    def page(name: str):
        ws(name)
        return HTMLResponse(PAGE.read_text(encoding="utf-8").replace("__NAME__", name),
                            headers={"Cache-Control": "no-store"})

    @r.get("/api/sb/{name}/state")
    def state(name: str):
        return guarded(lambda: ws(name).state())

    @r.get("/api/sb/{name}/poll")
    def poll(name: str):
        return ws(name).poll()

    @r.post("/api/sb/{name}/save")
    def save(name: str, req: SaveReq):
        return guarded(lambda: ws(name).save(req.edits, req.rev))

    @r.post("/api/sb/{name}/lock")
    def lock(name: str, req: LockReq):
        return guarded(lambda: ws(name).set_lock(req.shot, req.locked))

    @r.post("/api/sb/{name}/approve")
    def approve(name: str, req: ApproveReq):
        return guarded(lambda: {"ok": True, "approval": ws(name).approve(req.shot, req.approved)})

    @r.post("/api/sb/{name}/undo")
    def undo(name: str):
        return guarded(lambda: {"ok": True, **ws(name).undo()})

    @r.post("/api/sb/{name}/image")
    def image(name: str, req: ImageReq):
        return guarded(lambda: {"ok": True, "job": ws(name).start(req.key, req.mode, req.seed).public(tail=3)})

    @r.post("/api/sb/{name}/pick")
    def pick(name: str, req: PickReq):
        return guarded(lambda: {"ok": True, **ws(name).pick(req.key, req.n)})

    @r.post("/api/sb/{name}/revert")
    def revert(name: str, req: KeyReq):
        return guarded(lambda: {"ok": True, **ws(name).revert(req.key)})

    @r.post("/api/sb/{name}/sheet")
    def sheet(name: str):
        return guarded(lambda: {"ok": True, "job": ws(name).sheet().public(tail=3)})

    @r.get("/api/sb/{name}/img")
    def img(name: str, p: str, w: int = 0):
        project = resolve(name)
        f = (project.root / p).resolve()
        if project.root not in f.parents or f.suffix.lower() not in IMAGE_EXT or not f.is_file():
            raise HTTPException(404)
        if w and w < 2000:
            t = images.thumb(project, f, w)
            if t is not None:
                f = t
        return FileResponse(f, headers={"Cache-Control": "private, max-age=86400"})

    @r.get("/sb/{name}/files/{path:path}")
    def files(name: str, path: str):
        project = resolve(name)
        base = (project.root / "storyboard").resolve()
        f = (base / (path or "storyboard.html")).resolve()
        if base not in f.parents and f != base:
            raise HTTPException(403)
        if f.is_dir():
            f = f / "index.html"
        if not f.is_file():
            raise HTTPException(404, "not made yet: use Update sheet")
        return FileResponse(f, headers={"Cache-Control": "no-store"})

    return r


def free_port(preferred: Optional[int] = None) -> int:
    def free(p: int) -> bool:
        with socket.socket() as s:
            return s.connect_ex(("127.0.0.1", p)) != 0
    if preferred:
        if not free(preferred):
            raise BuildError(f"port {preferred} is in use")
        return preferred
    for p in PORTS:
        if free(p):
            return p
    raise BuildError("ports 8971-8979 are all in use; pass --port")


def make_app(project: Project) -> FastAPI:
    app = FastAPI(title="Scroll Studio: storyboard editor")
    jobs = JobQueue()

    def resolve(name: str) -> Project:
        if name != project.name:
            raise HTTPException(404, f"this editor serves '{project.name}'")
        return project
    app.include_router(make_router(resolve, jobs))

    @app.get("/")
    def home():
        return RedirectResponse(f"/sb/{project.name}")
    return app


def serve(project: Project, port: Optional[int] = None, open_browser: bool = True, log: Callable[[str], None] = print) -> None:
    """Serve the edit workspace for one project (blocks until Ctrl-C)."""
    import uvicorn
    port = free_port(port)
    url = f"http://127.0.0.1:{port}/sb/{project.name}"
    app = make_app(project)
    log(f"storyboard editor for {project.name}: {url}  (Ctrl-C to stop)")
    if open_browser:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
