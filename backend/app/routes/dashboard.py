from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query

from ..schemas import SectionUpdate, TagConfigUpdate, ActiveRecipeUpdate
from ..services.dashboard_service import (
    default_history_range,
    get_active_recipe,
    get_history,
    get_machine,
    get_section_live_values,
    get_sections,
    set_active_recipe,
    update_section,
    update_tag_config,
)
from ..services.alert_service import evaluate_alerts, list_alerts

router = APIRouter(prefix="/api", tags=["dashboard"])


@router.get("/machines/{machine_id}/dashboard")
def dashboard_state(machine_id: int) -> dict:
    active_recipe = get_active_recipe(machine_id)
    return {
        "machine": get_machine(machine_id),
        "active_recipe": active_recipe,
        "sections": get_sections(machine_id, include_hidden=True, sync=False, active_recipe=active_recipe),
        "alerts": list_alerts(machine_id, active_only=True),
    }


@router.get("/machines/{machine_id}/sections/{section_key}/live")
def section_live(machine_id: int, section_key: str, include_hidden: bool = True) -> dict:
    return get_section_live_values(machine_id, section_key, include_hidden=include_hidden)


@router.patch("/sections/{section_id}")
def patch_section(section_id: int, payload: SectionUpdate) -> dict:
    return update_section(section_id, payload.model_dump(exclude_unset=True))


@router.patch("/machines/{machine_id}/tags/{tag_id}/config")
def patch_tag_config(machine_id: int, tag_id: int, payload: TagConfigUpdate) -> dict:
    return update_tag_config(machine_id, tag_id, payload.model_dump(exclude_unset=True))


@router.get("/machines/{machine_id}/history")
def history(
    machine_id: int,
    section_key: str | None = None,
    tag_ids: Annotated[list[int] | None, Query()] = None,
    start: datetime | None = None,
    end: datetime | None = None,
) -> dict:
    default_start, default_end = default_history_range()
    return get_history(machine_id, section_key, start or default_start, end or default_end, tag_ids or [])


@router.get("/machines/{machine_id}/active-recipe")
def active_recipe(machine_id: int) -> dict | None:
    return get_active_recipe(machine_id)


@router.put("/machines/{machine_id}/active-recipe")
def put_active_recipe(machine_id: int, payload: ActiveRecipeUpdate) -> dict | None:
    return set_active_recipe(machine_id, payload.recipe_id, payload.selection_mode)


@router.post("/machines/{machine_id}/evaluate-alerts")
def evaluate(machine_id: int) -> dict:
    return evaluate_alerts(machine_id)
