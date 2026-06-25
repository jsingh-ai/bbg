from __future__ import annotations

from fastapi import APIRouter

from ..schemas import AssistantChatRequest
from ..services.assistant_service import (
    get_assistant_diagnostics_response,
    get_production_candidates_response,
    get_production_debug_response,
    handle_assistant_chat,
)

router = APIRouter(prefix="/api/assistant", tags=["assistant"])


@router.post("/chat")
def assistant_chat(payload: AssistantChatRequest) -> dict:
    return handle_assistant_chat(payload.message, payload.time_range, payload.conversation_id)


@router.get("/diagnostics")
def assistant_diagnostics() -> dict:
    return get_assistant_diagnostics_response()


@router.get("/production-debug")
def assistant_production_debug(time_range: str = "today") -> dict:
    return get_production_debug_response(time_range)


@router.get("/production-candidates")
def assistant_production_candidates(time_range: str = "today", limit: int = 50) -> dict:
    return get_production_candidates_response(time_range, limit)
