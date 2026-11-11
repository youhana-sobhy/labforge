"""HTTP API and web UI server."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import socket
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__, catalog
from .engine import EngineError
from .kinds import KINDS, VENDOR_ROADMAP
from .manager import LabError, LabManager
from .settings import settings

log = logging.getLogger("labforge.api")
WEB = Path(__file__).parent / "web"


class LaunchRequest(BaseModel):
    template: str
    name: str = ""
    owner: str = "anonymous"
    ttl_minutes: int | None = Field(None, ge=5)


class ExtendRequest(BaseModel):
    minutes: int = Field(60, ge=5, le=480)


class ConfigRequest(BaseModel):
    text: str
    by: str = ""


class LinkRequest(BaseModel):
    up: bool
    by: str = ""


class ExecRequest(BaseModel):
    command: str


class TemplateRequest(BaseModel):
    yaml: str


def create_app(manager: LabManager | None = None, start_background: bool = True) -> FastAPI:
    mgr = manager or LabManager()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if start_background:
            await asyncio.to_thread(mgr.start)
        yield
        mgr.stop()

    app = FastAPI(title="LabForge", version=__version__, lifespan=lifespan)
    app.state.manager = mgr

    @app.exception_handler(LabError)
    async def lab_error(_: Request, e: LabError):
        return JSONResponse({"detail": str(e)}, status_code=e.status)

    @app.exception_handler(EngineError)
    async def engine_error(_: Request, e: EngineError):
        return JSONResponse({"detail": str(e)}, status_code=502)

    # ---- platform -------------------------------------------------------------------------------------------
    @app.get("/api/health")
    def health():
        return {"ok": True, "version": __version__, "docker": mgr.engine.ping(),
                "max_active_labs": settings.max_active_labs, "max_ttl_minutes": settings.max_ttl_minutes}

    @app.get("/api/kinds")
    def kinds():
        out = []
        for k in KINDS.values():
            d = k.to_dict()
            ready = next((i for i in k.images if mgr.engine.image_present(i)), None)
            d["image_ready"] = ready is not None
            d["ready_image"] = ready
            out.append(d)
        return {"kinds": out, "roadmap": VENDOR_ROADMAP}

    @app.get("/api/stats")
    def stats():
        return mgr.store.stats()

    # ---- catalog ------------------------------------------------------------------------------------------
    @app.get("/api/catalog")
    def list_catalog():
        items = [catalog.summary(t, src) for t, src in catalog.load_all().values()]
        order = {"Beginner": 0, "Intermediate": 1, "Advanced": 2}
        return sorted(items, key=lambda i: (i["source"] != "built-in", order[i["difficulty"]], i["name"]))

    @app.get("/api/catalog/{template_id}")
    def get_template(template_id: str):
        all_ = catalog.load_all()
        if template_id not in all_:
            raise HTTPException(404, "template not found")
        return catalog.summary(*all_[template_id])

    @app.get("/api/catalog/{template_id}/yaml", response_class=PlainTextResponse)
    def template_yaml(template_id: str):
        for d in (catalog.BUILTIN, settings.user_catalog):
            f = d / f"{template_id}.yaml"
            if f.exists():
                return f.read_text()
        raise HTTPException(404, "template not found")

    @app.post("/api/catalog", status_code=201)
    def add_template(req: TemplateRequest):
        try:
            topo = catalog.save_custom(req.yaml)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(422, f"invalid template: {e}") from e
        mgr.store.log(None, f"Template '{topo.name}' added to the catalog")
        return catalog.summary(topo, "custom")

    # ---- labs ---------------------------------------------------------------------------------------------
    @app.get("/api/labs")
    def list_labs(active: bool = False):
        return mgr.list(active_only=active)

    @app.post("/api/labs", status_code=201)
    def launch(req: LaunchRequest):
        return mgr.create(req.template, name=req.name, owner=req.owner, ttl_minutes=req.ttl_minutes)

    @app.get("/api/labs/{lab_id}")
    def get_lab(lab_id: str):
        return mgr.get(lab_id)

    @app.delete("/api/labs/{lab_id}")
    def destroy(lab_id: str, by: str = ""):
        return mgr.destroy(lab_id, by=by)

    @app.post("/api/labs/{lab_id}/extend")
    def extend(lab_id: str, req: ExtendRequest):
        return mgr.extend(lab_id, req.minutes)

    @app.post("/api/labs/{lab_id}/links/{index}")
    def set_link(lab_id: str, index: int, req: LinkRequest):
        return mgr.set_link(lab_id, index, req.up, by=req.by)

    @app.post("/api/labs/{lab_id}/checks")
    def run_checks(lab_id: str):
        return mgr.run_checks(lab_id)

    @app.get("/api/labs/{lab_id}/events")
    def lab_events(lab_id: str, after: int = 0):
        return mgr.store.events(lab_id, after=after)

    @app.get("/api/events")
    def all_events(after: int = 0, limit: int = 100):
        return mgr.store.events(None, after=after, limit=limit)

    @app.get("/api/labs/{lab_id}/nodes/{node}/config")
    def show_config(lab_id: str, node: str):
        return mgr.show_config(lab_id, node)

    @app.post("/api/labs/{lab_id}/nodes/{node}/config")
    def apply_config(lab_id: str, node: str, req: ConfigRequest):
        return mgr.apply_config(lab_id, node, req.text, by=req.by)

    @app.post("/api/labs/{lab_id}/nodes/{node}/exec")
    def exec_cmd(lab_id: str, node: str, req: ExecRequest):
        return mgr.exec(lab_id, node, req.command)

    @app.websocket("/api/labs/{lab_id}/nodes/{node}/console")
    async def console(ws: WebSocket, lab_id: str, node: str):
        await ws.accept()
        lab = mgr.store.get_lab(lab_id)
        if not lab or lab["status"] != "running" or node not in lab["topology"]["nodes"]:
            await ws.send_text("\r\n\x1b[31mThis device is not running.\x1b[0m\r\n")
            await ws.close()
            return
        kind = KINDS[lab["topology"]["nodes"][node]["kind"]]
        try:
            exec_id, sock = await asyncio.to_thread(mgr.engine.open_shell, lab_id, node, kind.console)
        except Exception as e:  # noqa: BLE001
            await ws.send_text(f"\r\n\x1b[31mCould not open console: {e}\x1b[0m\r\n")
            await ws.close()
            return
        loop = asyncio.get_running_loop()

        async def pump_out():
            while True:
                data = await loop.run_in_executor(None, _recv, sock)
                if not data:
                    break
                await ws.send_bytes(data)
            with contextlib.suppress(Exception):
                await ws.send_text("\r\n\x1b[2m[session closed]\x1b[0m\r\n")
                await ws.close()

        out_task = asyncio.create_task(pump_out())
        try:
            while True:
                msg = await ws.receive_text()
                try:
                    m = json.loads(msg)
                except json.JSONDecodeError:
                    m = {"type": "input", "data": msg}
                if m.get("type") == "resize":
                    await asyncio.to_thread(mgr.engine.resize_shell, exec_id, int(m["rows"]), int(m["cols"]))
                elif m.get("type") == "input":
                    await asyncio.to_thread(sock.sendall, m["data"].encode())
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            out_task.cancel()
            with contextlib.suppress(Exception):
                sock.sendall(b"\x04")
                sock.close()

    # ---- web UI -------------------------------------------------------------------------------------------
    app.mount("/static", StaticFiles(directory=WEB), name="static")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(WEB / "index.html", headers={"Cache-Control": "no-cache"})

    return app


def _recv(sock: socket.socket) -> bytes:
    try:
        return sock.recv(65536)
    except OSError:
        return b""
