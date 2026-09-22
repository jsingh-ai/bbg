from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import FRONTEND_DIST, STATIC_ROOT, get_settings
from .db import pool
from .routes import alerts, assistant, dashboard, machines, recipes
from .services.alert_service import evaluate_alerts

settings = get_settings()
logger = logging.getLogger(__name__)


async def _alert_evaluator_loop() -> None:
    interval = max(settings.alert_evaluation_seconds, 10)
    while True:
        try:
            machine_rows = await asyncio.to_thread(
                pool.fetch_all,
                "SELECT machine_id FROM opc_machines WHERE is_active = 1 ORDER BY machine_id",
            )
            for row in machine_rows:
                machine_id = int(row["machine_id"])
                try:
                    await asyncio.to_thread(evaluate_alerts, machine_id)
                except Exception:
                    logger.exception("Background alert evaluation failed for machine %s", machine_id)
        except Exception:
            logger.exception("Background alert evaluator could not load active machines")
        await asyncio.sleep(interval)


@asynccontextmanager
async def lifespan(_: FastAPI):
    evaluator_task: asyncio.Task | None = None
    if settings.alert_evaluation_seconds > 0:
        evaluator_task = asyncio.create_task(_alert_evaluator_loop())
    try:
        yield
    finally:
        if evaluator_task:
            evaluator_task.cancel()
            with suppress(asyncio.CancelledError):
                await evaluator_task


app = FastAPI(title=settings.app_name, version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_ROOT.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_ROOT)), name="static")

app.include_router(machines.router)
app.include_router(dashboard.router)
app.include_router(recipes.router)
app.include_router(alerts.router)
app.include_router(assistant.router)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "app": settings.app_name}


if FRONTEND_DIST.exists():
    assets_dir = FRONTEND_DIST / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    @app.get("/{full_path:path}")
    def serve_frontend(full_path: str) -> FileResponse:
        requested = (FRONTEND_DIST / full_path).resolve()
        if requested.is_file() and requested.is_relative_to(FRONTEND_DIST.resolve()):
            return FileResponse(str(requested))
        return FileResponse(str(FRONTEND_DIST / "index.html"))
else:
    @app.get("/")
    def frontend_missing() -> JSONResponse:
        return JSONResponse(
            {
                "message": "Frontend build not found. Run scripts\\build_frontend.bat, then restart the backend.",
                "api_health": "/api/health",
            }
        )
