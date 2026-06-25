from __future__ import annotations

from fastapi import APIRouter

from ..schemas import AssistantChatRequest
from ..services.assistant_service import get_assistant_diagnostics_response, handle_assistant_chat

router = APIRouter(prefix="/api/assistant", tags=["assistant"])


@router.post("/chat")
def assistant_chat(payload: AssistantChatRequest) -> dict:
    return handle_assistant_chat(payload.message, payload.time_range, payload.conversation_id)


@router.get("/diagnostics")
def assistant_diagnostics() -> dict:
    return get_assistant_diagnostics_response()
