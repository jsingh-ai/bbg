from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class SectionUpdate(BaseModel):
    display_label: str | None = Field(default=None, max_length=255)
    section_photo_path: str | None = Field(default=None, max_length=500)
    is_visible: bool | None = None
    sort_order: int | None = None
    box_x_pct: float | None = Field(default=None, ge=0, le=100)
    box_y_pct: float | None = Field(default=None, ge=0, le=100)
    box_w_pct: float | None = Field(default=None, ge=0, le=100)
    box_h_pct: float | None = Field(default=None, ge=0, le=100)

    @model_validator(mode="after")
    def box_must_fit_image(self) -> "SectionUpdate":
        if self.box_x_pct is not None and self.box_w_pct is not None and self.box_x_pct + self.box_w_pct > 100:
            raise ValueError("box_x_pct + box_w_pct must be 100 or less")
        if self.box_y_pct is not None and self.box_h_pct is not None and self.box_y_pct + self.box_h_pct > 100:
            raise ValueError("box_y_pct + box_h_pct must be 100 or less")
        return self


class TagConfigUpdate(BaseModel):
    is_visible: bool | None = None
    show_in_history_default: bool | None = None
    sort_order: int | None = None


class RecipeCreate(BaseModel):
    recipe_name: str = Field(min_length=1, max_length=150)
    recipe_code: str | None = Field(default=None, max_length=100)
    description: str | None = Field(default=None, max_length=5000)


class RecipeUpdate(BaseModel):
    recipe_name: str | None = Field(default=None, min_length=1, max_length=150)
    recipe_code: str | None = Field(default=None, max_length=100)
    description: str | None = Field(default=None, max_length=5000)
    is_active: bool | None = None


class RecipeLimitItem(BaseModel):
    tag_id: int = Field(gt=0)
    min_value: float | None = None
    max_value: float | None = None
    is_enabled: bool = True

    @model_validator(mode="after")
    def minimum_must_not_exceed_maximum(self) -> "RecipeLimitItem":
        if self.min_value is not None and self.max_value is not None and self.min_value > self.max_value:
            raise ValueError("min_value must be less than or equal to max_value")
        return self


class RecipeLimitsBulkUpdate(BaseModel):
    limits: list[RecipeLimitItem] = Field(max_length=1000)


class ActiveRecipeUpdate(BaseModel):
    recipe_id: int | None = None
    selection_mode: Literal["manual", "automatic"] = "manual"


class AlertAcknowledge(BaseModel):
    acknowledged_by: str | None = Field(default="dashboard", max_length=100)
    acknowledge_note: str | None = Field(default=None, max_length=500)


class HistoryRequest(BaseModel):
    section_key: str
    start: datetime
    end: datetime
    tag_ids: list[int]


class AssistantChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    time_range: str | None = Field(default=None, max_length=32)
    conversation_id: str | None = Field(default=None, min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.:-]+$")


class AssistantConversationClearRequest(BaseModel):
    conversation_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.:-]+$")
