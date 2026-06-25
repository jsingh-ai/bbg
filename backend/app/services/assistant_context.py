from __future__ import annotations

from collections import OrderedDict, deque
from datetime import datetime, timedelta
from threading import RLock
from typing import Any

from ..config import get_settings
from .assistant_intents import (
    has_around_stop_subject,
    has_change_subject,
    has_compare_modifier,
    has_production_subject,
    has_stop_subject,
    has_time_range,
)
from .assistant_taxonomy import resolve_assistant_taxonomy
from .section_parser import normalize_key


_CONVERSATIONS: OrderedDict[str, deque[dict[str, Any]]] = OrderedDict()
_CONVERSATION_LOCK = RLock()

_FOLLOWUP_PREFIXES = (
    "whatabout",
    "howabout",
    "and",
    "samefor",
    "samethingfor",
    "showthatfor",
    "forthis",
    "foryesterday",
    "forlast",
)


def _settings():
    return get_settings()


def _now_iso() -> str:
    return datetime.utcnow().isoformat()


def _normalize_conversation_id(conversation_id: str | None) -> str | None:
    value = (conversation_id or "").strip()
    return value or None


def _fresh_followup_metadata(conversation_id: str | None, history_turns_available: int) -> dict[str, Any]:
    return {
        "used_context": False,
        "reason": "no_context_applied",
        "conversation_id": conversation_id,
        "history_turns_available": history_turns_available,
        "previous_intent": None,
        "previous_time_range": None,
        "original_intent": None,
        "original_time_range": None,
        "resolved_intent": None,
        "resolved_time_range": None,
        "inherited_intent": None,
        "inherited_time_range": None,
        "changed_intent": False,
        "changed_time_range": False,
        "inherited_resolved_system": None,
        "inherited_section_terms": [],
    }


def _has_explicit_section_only(message: str) -> bool:
    taxonomy = resolve_assistant_taxonomy(message)
    return bool(taxonomy.get("resolved_system"))


def subject_from_intent(route: dict[str, Any]) -> str | None:
    if route.get("explicit_alarm_context") or route.get("resolved_system") == "alarm/system":
        return "alerts"
    if route.get("explicit_state_context"):
        return "state"
    if route.get("explicit_speed_context"):
        return "speed"
    intent = str(route.get("intent") or "")
    if intent == "production_summary":
        return "production"
    if intent == "stop_summary":
        return "stops"
    if intent in {"values_around_last_stop", "most_changed_parameters"}:
        return "process"
    if intent == "section_summary":
        return "section"
    return None


def get_recent_turns(conversation_id: str | None) -> list[dict[str, Any]]:
    normalized_id = _normalize_conversation_id(conversation_id)
    if not normalized_id:
        return []
    with _CONVERSATION_LOCK:
        turns = _CONVERSATIONS.get(normalized_id)
        if turns:
            _CONVERSATIONS.move_to_end(normalized_id)
        return list(turns) if turns else []


def get_last_turn(conversation_id: str | None) -> dict[str, Any] | None:
    turns = get_recent_turns(conversation_id)
    return turns[-1] if turns else None


def clear_conversation(conversation_id: str | None) -> None:
    normalized_id = _normalize_conversation_id(conversation_id)
    if normalized_id:
        with _CONVERSATION_LOCK:
            _CONVERSATIONS.pop(normalized_id, None)


def clear_all_conversations() -> None:
    with _CONVERSATION_LOCK:
        _CONVERSATIONS.clear()


def _evict_excess_conversations(max_conversations: int) -> None:
    bounded_max = max(max_conversations, 1)
    while len(_CONVERSATIONS) > bounded_max:
        _CONVERSATIONS.popitem(last=False)


def get_conversation_memory_stats() -> dict[str, Any]:
    settings = _settings()
    with _CONVERSATION_LOCK:
        conversation_count = len(_CONVERSATIONS)
    return {
        "enabled": bool(settings.assistant_context_enabled),
        "conversation_count": conversation_count,
        "max_conversations": settings.assistant_context_max_conversations,
        "max_turns": settings.assistant_context_max_turns,
        "max_age_minutes": settings.assistant_context_max_age_minutes,
        "message_max_chars": settings.assistant_context_message_max_chars,
        "process_local": True,
    }


def _truncate_message(message: str) -> str:
    max_chars = max(_settings().assistant_context_message_max_chars, 0)
    if max_chars <= 0:
        return ""
    return message[:max_chars]


def _conversation_max_turns() -> int:
    return max(_settings().assistant_context_max_turns, 1)


def _ensure_conversation_capacity() -> None:
    _evict_excess_conversations(_settings().assistant_context_max_conversations)


def _replace_deque_if_needed(conversation_id: str, turns: deque[dict[str, Any]]) -> deque[dict[str, Any]]:
    max_turns = _conversation_max_turns()
    if turns.maxlen == max_turns:
        return turns
    replacement = deque(list(turns)[-max_turns:], maxlen=max_turns)
    _CONVERSATIONS[conversation_id] = replacement
    return replacement


def cleanup_old_conversations(max_age_minutes: int = 120) -> None:
    cutoff = datetime.utcnow() - timedelta(minutes=max(max_age_minutes, 1))
    with _CONVERSATION_LOCK:
        expired: list[str] = []
        for conversation_id, turns in _CONVERSATIONS.items():
            if not turns:
                expired.append(conversation_id)
                continue
            created_at = turns[-1].get("created_at")
            if not created_at:
                continue
            try:
                created_dt = datetime.fromisoformat(str(created_at))
            except ValueError:
                continue
            if created_dt < cutoff:
                expired.append(conversation_id)
        for conversation_id in expired:
            _CONVERSATIONS.pop(conversation_id, None)
        _ensure_conversation_capacity()


def remember_turn(conversation_id: str | None, message: str, route: dict[str, Any], raw: dict[str, Any] | None = None) -> None:
    normalized_id = _normalize_conversation_id(conversation_id)
    if not normalized_id or not _settings().assistant_context_enabled:
        return
    cleanup_old_conversations(_settings().assistant_context_max_age_minutes)
    with _CONVERSATION_LOCK:
        turns = _CONVERSATIONS.setdefault(normalized_id, deque(maxlen=_conversation_max_turns()))
        turns = _replace_deque_if_needed(normalized_id, turns)
        turns.append(
            {
                "message": _truncate_message(message),
                "intent": route.get("intent"),
                "time_range": route.get("time_range"),
                "compare_to": route.get("compare_to"),
                "resolved_system": route.get("resolved_system"),
                "section_terms": list(route.get("section_terms") or []),
                "matched_alias": route.get("matched_alias"),
                "subject": subject_from_intent(route),
                "stop_time": (raw or {}).get("stop_time"),
                "created_at": _now_iso(),
            }
        )
        _CONVERSATIONS.move_to_end(normalized_id)
        _ensure_conversation_capacity()


def is_followup_message(message: str) -> bool:
    normalized = normalize_key(message)
    if not normalized:
        return False
    if any(normalized.startswith(prefix) for prefix in _FOLLOWUP_PREFIXES):
        return True
    if len(normalized) <= 24 and has_time_range(message):
        return True
    return any(
        phrase in normalized
        for phrase in (
            "whatabout",
            "howabout",
            "samefor",
            "samethingfor",
            "showthatfor",
            "andbags",
            "andstops",
            "whataboutbags",
            "whataboutstops",
            "whataboutunwinder",
            "whataboutdancer",
        )
    )


def _is_clear_current_route(message: str, route: dict[str, Any]) -> bool:
    if has_compare_modifier(message):
        return True
    explicit_time = has_time_range(message)
    explicit_production = has_production_subject(message)
    explicit_stop = has_stop_subject(message)
    explicit_process = has_change_subject(message) or has_around_stop_subject(message)
    explicit_section = _has_explicit_section_only(message)
    if explicit_time and (explicit_production or explicit_stop or explicit_process):
        return True
    if explicit_time and explicit_section and route.get("intent") == "section_summary":
        return True
    return False


def _find_previous_turn(recent_turns: list[dict[str, Any]], predicate) -> dict[str, Any] | None:
    for turn in reversed(recent_turns[-5:]):
        if not turn.get("intent"):
            continue
        if predicate(turn):
            return turn
    return None


def apply_followup_context(message: str, route: dict[str, Any], recent_turns: list[dict[str, Any]]) -> dict[str, Any]:
    updated = dict(route)
    followup = _fresh_followup_metadata(None, len(recent_turns))
    original_intent = route.get("intent")
    original_time_range = route.get("time_range")
    followup["original_intent"] = original_intent
    followup["original_time_range"] = original_time_range
    updated["followup"] = followup
    if not recent_turns:
        followup["reason"] = "no_recent_turns"
        followup["resolved_intent"] = updated.get("intent")
        followup["resolved_time_range"] = updated.get("time_range")
        return updated
    if _is_clear_current_route(message, route):
        previous = recent_turns[-1]
        followup["reason"] = "current_message_explicit"
        followup["previous_intent"] = previous.get("intent")
        followup["previous_time_range"] = previous.get("time_range")
        followup["resolved_intent"] = updated.get("intent")
        followup["resolved_time_range"] = updated.get("time_range")
        return updated

    explicit_time = has_time_range(message)
    explicit_compare = has_compare_modifier(message)
    explicit_production = has_production_subject(message)
    explicit_stop = has_stop_subject(message)
    explicit_process = has_change_subject(message) or has_around_stop_subject(message)
    explicit_section = _has_explicit_section_only(message)
    followup_candidate = is_followup_message(message)

    if not followup_candidate and not (explicit_time or explicit_section):
        followup["reason"] = "message_not_followup_like"
        followup["resolved_intent"] = updated.get("intent")
        followup["resolved_time_range"] = updated.get("time_range")
        return updated

    previous: dict[str, Any] | None = None
    reason_parts: list[str] = []
    inherited_intent = None
    inherited_time_range = None
    inherited_resolved_system = None
    inherited_section_terms: list[str] = []

    if explicit_time and route.get("intent") == "fallback":
        previous = _find_previous_turn(recent_turns, lambda turn: turn.get("subject") in {"production", "section"})
        if previous:
            inherited_intent = str(previous.get("intent") or "") or None
            if inherited_intent:
                updated["intent"] = inherited_intent
                updated["matched_rule"] = "followup_inherited_intent"
                reason_parts.append("inherited_intent")
            if previous.get("subject") == "section":
                inherited_resolved_system = previous.get("resolved_system")
                inherited_section_terms = list(previous.get("section_terms") or [])
                updated["resolved_system"] = inherited_resolved_system
                updated["section_terms"] = inherited_section_terms
                updated["matched_rule"] = "followup_inherited_section"
                reason_parts.append("inherited_section")
    elif explicit_production:
        previous = _find_previous_turn(recent_turns, lambda turn: turn.get("subject") in {"stops", "production"})
        if previous and previous.get("time_range") and not explicit_time:
            updated["intent"] = "production_summary"
            inherited_time_range = str(previous["time_range"])
            updated["time_range"] = inherited_time_range
            updated["matched_rule"] = "followup_resolved_subject_and_inherited_time"
            reason_parts.extend(["resolved_production_subject", "inherited_time_range"])
    elif explicit_stop:
        previous = _find_previous_turn(recent_turns, lambda turn: turn.get("subject") in {"production", "stops"})
        if previous and previous.get("time_range") and not explicit_time:
            updated["intent"] = "stop_summary"
            inherited_time_range = str(previous["time_range"])
            updated["time_range"] = inherited_time_range
            updated["matched_rule"] = "followup_resolved_subject_and_inherited_time"
            reason_parts.extend(["resolved_stop_subject", "inherited_time_range"])
    elif explicit_section:
        previous = _find_previous_turn(recent_turns, lambda turn: turn.get("subject") in {"process", "section"})
        if previous and previous.get("subject") == "process":
            inherited_intent = str(previous.get("intent") or "") or None
            if inherited_intent:
                updated["intent"] = inherited_intent
                updated["matched_rule"] = "followup_inherited_section"
                reason_parts.append("preserved_process_intent")
            if previous.get("time_range") and not explicit_time:
                inherited_time_range = str(previous["time_range"])
                updated["time_range"] = inherited_time_range
                reason_parts.append("inherited_time_range")
        elif previous and previous.get("subject") == "section" and previous.get("time_range") and not explicit_time:
            inherited_time_range = str(previous["time_range"])
            updated["time_range"] = inherited_time_range
            updated["matched_rule"] = "followup_inherited_time_range"
            reason_parts.append("inherited_time_range")
    elif explicit_process:
        previous = _find_previous_turn(recent_turns, lambda turn: turn.get("subject") in {"process", "section"})
        if previous and previous.get("time_range") and not explicit_time:
            inherited_time_range = str(previous["time_range"])
            updated["time_range"] = inherited_time_range
            updated["matched_rule"] = "followup_inherited_time_range"
            reason_parts.append("inherited_time_range")

    if not previous:
        followup["reason"] = "no_compatible_turn"
        followup["resolved_intent"] = updated.get("intent")
        followup["resolved_time_range"] = updated.get("time_range")
        return updated

    followup["previous_intent"] = previous.get("intent")
    followup["previous_time_range"] = previous.get("time_range")

    if explicit_compare:
        updated["compare_to"] = route.get("compare_to")
    else:
        updated["compare_to"] = None

    if not reason_parts:
        followup["reason"] = "no_inheritance_needed"
        followup["resolved_intent"] = updated.get("intent")
        followup["resolved_time_range"] = updated.get("time_range")
        return updated

    followup.update(
        {
            "used_context": True,
            "reason": ", ".join(reason_parts),
            "resolved_intent": updated.get("intent"),
            "resolved_time_range": updated.get("time_range"),
            "inherited_intent": inherited_intent,
            "inherited_time_range": inherited_time_range,
            "changed_intent": original_intent != updated.get("intent"),
            "changed_time_range": original_time_range != updated.get("time_range"),
            "inherited_resolved_system": inherited_resolved_system,
            "inherited_section_terms": inherited_section_terms,
        }
    )
    return updated
