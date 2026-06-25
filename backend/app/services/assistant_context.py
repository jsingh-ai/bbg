from __future__ import annotations

from collections import deque
from datetime import datetime, timedelta
from typing import Any

from ..config import get_settings
from .assistant_taxonomy import resolve_assistant_taxonomy
from .section_parser import normalize_key


_CONVERSATIONS: dict[str, deque[dict[str, Any]]] = {}

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
_TIME_RANGE_TERMS = (
    "today",
    "yesterday",
    "thisweek",
    "lastweek",
    "week",
    "lasthour",
    "hour",
    "24hours",
    "last24hours",
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
        "inherited_intent": None,
        "inherited_time_range": None,
        "inherited_resolved_system": None,
        "inherited_section_terms": [],
    }


def _has_any(normalized: str, phrases: tuple[str, ...]) -> bool:
    return any(phrase in normalized for phrase in phrases)


def _has_explicit_compare(message: str) -> bool:
    normalized = normalize_key(message)
    return any(
        term in normalized
        for term in (
            "compare",
            "versus",
            "vs",
            "betterthan",
            "worsethan",
            "yesterdaycomparison",
        )
    )


def _has_explicit_time_range(message: str) -> bool:
    normalized = normalize_key(message)
    return _has_any(normalized, _TIME_RANGE_TERMS)


def _has_explicit_production_intent(message: str) -> bool:
    normalized = normalize_key(message)
    return any(
        term in normalized
        for term in (
            "production",
            "goodbags",
            "badbags",
            "bags",
            "scrap",
            "reject",
            "rejects",
            "quality",
            "shiftproduction",
        )
    )


def _has_explicit_stop_intent(message: str) -> bool:
    normalized = normalize_key(message)
    return any(term in normalized for term in ("stops", "stop", "downtime", "longeststop", "stopcount"))


def _has_explicit_process_intent(message: str) -> bool:
    normalized = normalize_key(message)
    return any(
        term in normalized
        for term in (
            "changedthemost",
            "changesthemost",
            "mostchanged",
            "unstable",
            "variation",
            "uncertainty",
            "movingthemost",
            "bouncing",
            "aroundthelaststop",
            "changedaround",
            "changedbefore",
            "whatchanged",
        )
    )


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
    turns = _CONVERSATIONS.get(normalized_id)
    return list(turns) if turns else []


def get_last_turn(conversation_id: str | None) -> dict[str, Any] | None:
    turns = get_recent_turns(conversation_id)
    return turns[-1] if turns else None


def clear_conversation(conversation_id: str | None) -> None:
    normalized_id = _normalize_conversation_id(conversation_id)
    if normalized_id:
        _CONVERSATIONS.pop(normalized_id, None)


def cleanup_old_conversations(max_age_minutes: int = 120) -> None:
    cutoff = datetime.utcnow() - timedelta(minutes=max(max_age_minutes, 1))
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


def remember_turn(conversation_id: str | None, message: str, route: dict[str, Any], raw: dict[str, Any] | None = None) -> None:
    normalized_id = _normalize_conversation_id(conversation_id)
    if not normalized_id or not _settings().assistant_context_enabled:
        return
    cleanup_old_conversations(_settings().assistant_context_max_age_minutes)
    turns = _CONVERSATIONS.setdefault(normalized_id, deque(maxlen=max(_settings().assistant_context_max_turns, 1)))
    turns.append(
        {
            "message": message,
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


def is_followup_message(message: str) -> bool:
    normalized = normalize_key(message)
    if not normalized:
        return False
    if any(normalized.startswith(prefix) for prefix in _FOLLOWUP_PREFIXES):
        return True
    if len(normalized) <= 24 and _has_any(normalized, _TIME_RANGE_TERMS):
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
    if _has_explicit_compare(message):
        return True
    explicit_time = _has_explicit_time_range(message)
    explicit_production = _has_explicit_production_intent(message)
    explicit_stop = _has_explicit_stop_intent(message)
    explicit_process = _has_explicit_process_intent(message)
    explicit_section = _has_explicit_section_only(message)
    if explicit_time and (explicit_production or explicit_stop or explicit_process):
        return True
    if explicit_time and explicit_section and route.get("intent") == "section_summary":
        return True
    return False


def _compatible_previous_turn(current_route: dict[str, Any], recent_turns: list[dict[str, Any]]) -> dict[str, Any] | None:
    desired_subject = subject_from_intent(current_route)
    for turn in reversed(recent_turns[-5:]):
        if not turn.get("intent"):
            continue
        if desired_subject is None:
            return turn
        previous_subject = turn.get("subject")
        if previous_subject == desired_subject:
            return turn
        if desired_subject == "section" and previous_subject in {"process", "section", "speed", "state", "alerts"}:
            return turn
        if desired_subject == "process" and previous_subject in {"process", "section", "speed", "state"}:
            return turn
        if desired_subject == "production" and previous_subject == "production":
            return turn
        if desired_subject == "stops" and previous_subject == "stops":
            return turn
    return recent_turns[-1] if recent_turns else None


def apply_followup_context(message: str, route: dict[str, Any], recent_turns: list[dict[str, Any]]) -> dict[str, Any]:
    updated = dict(route)
    followup = _fresh_followup_metadata(None, len(recent_turns))
    updated["followup"] = followup
    if not recent_turns:
        followup["reason"] = "no_recent_turns"
        return updated
    if _is_clear_current_route(message, route):
        previous = recent_turns[-1]
        followup["reason"] = "current_message_explicit"
        followup["previous_intent"] = previous.get("intent")
        followup["previous_time_range"] = previous.get("time_range")
        return updated

    explicit_time = _has_explicit_time_range(message)
    explicit_compare = _has_explicit_compare(message)
    explicit_production = _has_explicit_production_intent(message)
    explicit_stop = _has_explicit_stop_intent(message)
    explicit_process = _has_explicit_process_intent(message)
    explicit_section = _has_explicit_section_only(message)
    followup_candidate = is_followup_message(message)

    if not followup_candidate and not (explicit_time or explicit_section):
        followup["reason"] = "message_not_followup_like"
        return updated

    previous = _compatible_previous_turn(updated, recent_turns)
    if not previous:
        followup["reason"] = "no_compatible_turn"
        return updated

    followup["previous_intent"] = previous.get("intent")
    followup["previous_time_range"] = previous.get("time_range")

    inherited_intent = None
    inherited_time_range = None
    inherited_resolved_system = None
    inherited_section_terms: list[str] = []
    reason_parts: list[str] = []

    if explicit_compare:
        updated["compare_to"] = route.get("compare_to")
    else:
        updated["compare_to"] = None

    if explicit_time and route.get("intent") == "fallback":
        inherited_intent = str(previous.get("intent") or "") or None
        if inherited_intent:
            updated["intent"] = inherited_intent
            reason_parts.append("inherited_intent_from_previous_turn")
    elif explicit_section and route.get("intent") == "section_summary" and previous.get("intent") in {
        "values_around_last_stop",
        "most_changed_parameters",
    }:
        inherited_intent = str(previous.get("intent") or "") or None
        if inherited_intent:
            updated["intent"] = inherited_intent
            reason_parts.append("preserved_previous_process_intent_for_section_followup")

    if not explicit_time and previous.get("time_range"):
        inherited_time_range = str(previous["time_range"])
        updated["time_range"] = inherited_time_range
        reason_parts.append("inherited_time_range")

    if explicit_section and previous.get("resolved_system") and not updated.get("resolved_system"):
        inherited_resolved_system = str(previous["resolved_system"])
        updated["resolved_system"] = inherited_resolved_system
        inherited_section_terms = list(previous.get("section_terms") or [])
        updated["section_terms"] = inherited_section_terms
        reason_parts.append("inherited_section")

    if not explicit_section and updated.get("intent") == "section_summary" and previous.get("resolved_system") and not updated.get("resolved_system"):
        inherited_resolved_system = str(previous["resolved_system"])
        updated["resolved_system"] = inherited_resolved_system
        inherited_section_terms = list(previous.get("section_terms") or [])
        updated["section_terms"] = inherited_section_terms
        reason_parts.append("inherited_section")

    if explicit_production and previous.get("time_range") and not explicit_time:
        updated["intent"] = "production_summary"
    if explicit_stop and previous.get("time_range") and not explicit_time:
        updated["intent"] = "stop_summary"
    if explicit_process and previous.get("time_range") and not explicit_time:
        updated["intent"] = route.get("intent")

    if not reason_parts:
        followup["reason"] = "no_inheritance_needed"
        return updated

    followup.update(
        {
            "used_context": True,
            "reason": ", ".join(reason_parts),
            "inherited_intent": inherited_intent,
            "inherited_time_range": inherited_time_range,
            "inherited_resolved_system": inherited_resolved_system,
            "inherited_section_terms": inherited_section_terms,
        }
    )
    return updated
