from __future__ import annotations

from fastapi import APIRouter

from ..config import get_settings
from ..services.dashboard_service import get_machine, list_machines, get_sections
from ..services.photo_service import list_photo_files
from ..services.sync_service import sync_machine

router = APIRouter(prefix="/api", tags=["machines"])


@router.get("/config")
def app_config() -> dict:
    settings = get_settings()
    return {
        "app_name": settings.app_name,
        "default_machine_id": settings.default_machine_id,
        "live_refresh_seconds": settings.live_refresh_seconds,
        "default_history_minutes": settings.default_history_minutes,
    }


@router.get("/machines")
def machines() -> list[dict]:
    return list_machines()


@router.get("/machines/{machine_id}")
def machine(machine_id: int) -> dict:
    return get_machine(machine_id)


@router.post("/machines/{machine_id}/sync")
def sync(machine_id: int) -> dict:
    return sync_machine(machine_id)


@router.get("/machines/{machine_id}/sections")
def sections(machine_id: int, include_hidden: bool = True) -> list[dict]:
    return get_sections(machine_id, include_hidden=include_hidden, sync=True)


@router.get("/photos")
def photos() -> list[dict]:
    return list_photo_files()
