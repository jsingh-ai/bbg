from __future__ import annotations

from fastapi import APIRouter

from ..schemas import RecipeCreate, RecipeUpdate, RecipeLimitsBulkUpdate
from ..services.recipe_service import (
    bulk_update_limits,
    create_recipe,
    get_recipe,
    get_recipe_limits_for_section,
    list_recipes,
    update_recipe,
)

router = APIRouter(prefix="/api", tags=["recipes"])


@router.get("/machines/{machine_id}/recipes")
def recipes(machine_id: int) -> list[dict]:
    return list_recipes(machine_id)


@router.post("/machines/{machine_id}/recipes")
def create(machine_id: int, payload: RecipeCreate) -> dict:
    return create_recipe(machine_id, payload.model_dump())


@router.get("/recipes/{recipe_id}")
def recipe(recipe_id: int) -> dict:
    return get_recipe(recipe_id)


@router.patch("/recipes/{recipe_id}")
def patch_recipe(recipe_id: int, payload: RecipeUpdate) -> dict:
    return update_recipe(recipe_id, payload.model_dump(exclude_unset=True))


@router.get("/recipes/{recipe_id}/limits")
def limits(recipe_id: int, section_key: str) -> dict:
    return get_recipe_limits_for_section(recipe_id, section_key)


@router.put("/recipes/{recipe_id}/limits")
def put_limits(recipe_id: int, payload: RecipeLimitsBulkUpdate) -> dict:
    return bulk_update_limits(recipe_id, [item.model_dump() for item in payload.limits])
