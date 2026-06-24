from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class SectionUpdate(BaseModel):
    display_label: str | None = None
    section_photo_path: str | None = None
    is_visible: bool | None = None
    sort_order: int | None = None
    box_x_pct: float | None = Field(default=None, ge=0, le=100)
    box_y_pct: float | None = Field(default=None, ge=0, le=100)
    box_w_pct: float | None = Field(default=None, ge=0, le=100)
    box_h_pct: float | None = Field(default=None, ge=0, le=100)


class TagConfigUpdate(BaseModel):
    is_visible: bool | None = None
    show_in_history_default: bool | None = None
    sort_order: int | None = None


class RecipeCreate(BaseModel):
    recipe_name: str
    recipe_code: str | None = None
    description: str | None = None


class RecipeUpdate(BaseModel):
    recipe_name: str | None = None
    recipe_code: str | None = None
    description: str | None = None
    is_active: bool | None = None


class RecipeLimitItem(BaseModel):
    tag_id: int
    min_value: float | None = None
    max_value: float | None = None
    is_enabled: bool = True


class RecipeLimitsBulkUpdate(BaseModel):
    limits: list[RecipeLimitItem]


class ActiveRecipeUpdate(BaseModel):
    recipe_id: int | None = None
    selection_mode: Literal["manual", "automatic"] = "manual"


class AlertAcknowledge(BaseModel):
    acknowledged_by: str | None = "dashboard"
    acknowledge_note: str | None = None


class HistoryRequest(BaseModel):
    section_key: str
    start: datetime
    end: datetime
    tag_ids: list[int]
