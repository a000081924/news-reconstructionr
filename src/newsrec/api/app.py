import asyncio
import json
import os
from contextlib import asynccontextmanager
from dataclasses import asdict
from functools import partial
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, File, Header, Query, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from newsrec.domain.engines import ENGINES
from newsrec.services.ingestion import MAX_BYTES
from newsrec.services.recognition import PaddleEngine
from newsrec.services.workspace import Workspace
from newsrec.workers.queue import GPUQueue
from newsrec.api.limits import BodyLimit
from newsrec.api.schemas import PageResponse


class RecognitionRequest(BaseModel):
    engine: str = "structure"


class Correction(BaseModel):
    block_id: int
    line_index: int = Field(ge=-1)
    text: str = Field(max_length=100_000)


class CorrectionRequest(BaseModel):
    engine: str = "structure"
    corrections: list[Correction] = Field(max_length=10_000)


def create_app(root=None, engine_factories=None, resident=None):
    root = root or os.getenv("NEWSREC_DATA", ".runtime")
    # Every interactive engine can be chosen; NEWSREC_ENGINE only decides which one is
    # loaded at startup, since the card holds one at a time and the rest swap on demand.
    resident = resident or os.getenv("NEWSREC_ENGINE", "structure")
    if engine_factories is None:
        engine_factories = {} if resident == "none" else {
            spec.id: partial(PaddleEngine, spec.id) for spec in ENGINES.values() if spec.interactive
        }

    @asynccontextmanager
    async def lifespan(app):
        app.state.workspace = Workspace(root)
        app.state.worker = GPUQueue(app.state.workspace, engine_factories, resident)
        await app.state.worker.start()
        try:
            yield
        finally:
            await app.state.worker.stop()

    app = FastAPI(title="Newspaper reconstruction", lifespan=lifespan)
    app.add_middleware(BodyLimit)

    @app.exception_handler(KeyError)
    async def missing(request, exc):
        return JSONResponse({"detail": "Not found"}, status_code=404)

    @app.exception_handler(ValueError)
    async def invalid(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=400)

    @app.get("/api/engines")
    def engines():
        return [{**asdict(spec), "enabled": spec.id in app.state.worker.factories,
                 "loaded": spec.id in app.state.worker.engines} for spec in ENGINES.values()]

    @app.post("/api/documents", status_code=201)
    async def upload(file: UploadFile = File(...)):
        try:
            content = await file.read(MAX_BYTES + 1)
            if len(content) > MAX_BYTES:
                return JSONResponse({"detail": "upload exceeds 50 MiB"}, status_code=413)
            return await asyncio.to_thread(app.state.workspace.upload, file.filename or "Untitled scan", content)
        finally:
            await file.close()

    @app.get("/api/documents")
    def documents():
        return app.state.workspace.documents()

    @app.get("/api/documents/{document_id}")
    def document(document_id: str):
        return app.state.workspace.document(document_id)

    @app.delete("/api/documents/{document_id}", status_code=204)
    async def delete_document(document_id: str):
        app.state.workspace.delete_document(document_id)

    @app.post("/api/pages/{page_id}/recognize", status_code=202)
    async def recognize(page_id: str, body: RecognitionRequest):
        return {"job_id": app.state.worker.enqueue(page_id, body.engine)}

    @app.get("/api/jobs/{job_id}")
    def job(job_id: str):
        return app.state.workspace.job(job_id)

    @app.get("/api/jobs/{job_id}/events")
    async def events(job_id: str, request: Request, last_event_id: str | None = Header(None), after: int = Query(0, ge=0)):
        app.state.workspace.job(job_id)
        try:
            cursor = int(last_event_id) if last_event_id else after
            if cursor < 0:
                raise ValueError()
        except ValueError:
            return JSONResponse({"detail": "invalid event cursor"}, status_code=400)
        async def stream():
            nonlocal cursor
            bus = app.state.worker.bus
            signal = bus.subscribe(job_id)
            try:
                while not await request.is_disconnected():
                    signal.clear()
                    snapshot = app.state.workspace.job(job_id)
                    for event in snapshot["events"]:
                        if event["id"] > cursor:
                            cursor = event["id"]
                            yield f'id: {cursor}\nevent: stage\ndata: {json.dumps(event, ensure_ascii=False)}\n\n'
                    if snapshot["status"] in ("done", "error"):
                        return
                    try:
                        await asyncio.wait_for(signal.wait(), 15)
                    except TimeoutError:
                        yield ": heartbeat\n\n"
            finally:
                bus.unsubscribe(job_id, signal)
        return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.get("/api/pages/{page_id}", response_model=PageResponse)
    def page(page_id: str, engine: str = "structure"):
        return app.state.workspace.page(page_id, engine)

    @app.get("/api/pages/{page_id}/image")
    def image(page_id: str):
        return FileResponse(app.state.workspace.image(page_id), media_type="image/png")

    @app.get("/api/pages/{page_id}/thumbnail")
    def thumbnail(page_id: str):
        return FileResponse(app.state.workspace.image(page_id, True), media_type="image/png")

    @app.get("/api/pages/{page_id}/corrections")
    def edits(page_id: str, engine: str = "structure"):
        return app.state.workspace.edits(page_id, engine)

    @app.put("/api/pages/{page_id}/corrections", response_model=PageResponse)
    async def save_edits(page_id: str, body: CorrectionRequest):
        return app.state.workspace.save_edits(page_id, body.engine, [e.model_dump() for e in body.corrections])

    @app.delete("/api/pages/{page_id}/corrections", response_model=PageResponse)
    async def undo(page_id: str, engine: str = "structure"):
        return app.state.workspace.save_edits(page_id, engine, [])

    @app.get("/api/pages/{page_id}/export")
    def export(page_id: str, format: Literal["html", "alto", "page-xml"] = "html", engine: str = "structure"):
        content, media_type = app.state.workspace.export(page_id, engine, format)
        suffix = "html" if format == "html" else "xml"
        return Response(content, media_type=media_type, headers={"Content-Disposition": f'attachment; filename="{format}.{suffix}"'})

    frontend = Path(__file__).resolve().parents[3] / "frontend" / "dist"
    if frontend.exists():
        app.mount("/", StaticFiles(directory=frontend, html=True), name="frontend")
    return app


app = create_app()
