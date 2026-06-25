from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import FRONTEND_DIST, STATIC_ROOT, get_settings
from .routes import alerts, assistant, dashboard, machines, recipes

settings = get_settings()

app = FastAPI(title=settings.app_name, version="1.0.0")

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
        if requested.is_file() and str(requested).startswith(str(FRONTEND_DIST.resolve())):
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
