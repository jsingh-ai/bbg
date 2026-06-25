from __future__ import annotations

import re

from .section_parser import normalize_key


PRODUCTION_TERMS = (
    "production",
    "bag",
    "bags",
    "good bags",
    "bad bags",
    "scrap",
    "reject",
    "rejects",
    "quality",
    "shift production",
    "output",
)
STOP_TERMS = ("stop", "stops", "stopped", "downtime", "down time", "longest stop", "machine stopped")
CHANGE_TERMS = (
    "changed the most",
    "changes the most",
    "most changed",
    "unstable",
    "variation",
    "uncertainty",
    "moving the most",
    "bouncing",
)
AROUND_STOP_TERMS = (
    "changed around stop",
    "changed around the stop",
    "changed before stop",
    "around the last stop",
    "before the last stop",
    "when speed went to 0",
    "when speed went zero",
)
SPEED_TERMS = (
    "speed",
    "speeds",
    "current speed",
    "machine speed",
    "cycle performance",
    "performance",
    "drive speed",
    "motion",
    "velocity",
)
STATE_TERMS = ("state", "status", "mode", "condition", "running condition")
ALARM_TERMS = ("alarm", "alarms", "active alarms", "max severity", "fault", "faults", "warning", "warnings")
COUNTER_TERMS = ("counter", "counters", "count", "counts", "number of", "package counter")
PLC_TERMS = ("plc", "io", "i/o", "system health", "controller")
COMPARE_TERMS = ("compare", "vs", "versus", "better than", "worse than")
TIME_RANGE_TERMS = (
    "today",
    "yesterday",
    "this week",
    "last week",
    "week",
    "last hour",
    "hour",
    "24 hours",
    "last 24 hours",
)


def tokenize_message(message: str | None) -> list[str]:
    return re.findall(r"[a-z0-9/]+", (message or "").lower())


def contains_word_or_phrase(message: str | None, terms: tuple[str, ...]) -> bool:
    text = (message or "").lower()
    tokens = set(tokenize_message(message))
    normalized = normalize_key(message)
    for term in terms:
        lowered = term.lower()
        if lowered == "io":
            if "io" in tokens:
                return True
            continue
        if lowered == "i/o":
            if "i/o" in tokens or "i/o" in text:
                return True
            continue
        term_tokens = tokenize_message(lowered)
        if len(term_tokens) == 1:
            if term_tokens[0] in tokens:
                return True
            continue
        if normalize_key(lowered) in normalized:
            return True
    return False


def has_explicit_speed_context(message: str | None) -> bool:
    return contains_word_or_phrase(message, SPEED_TERMS)


def has_explicit_state_context(message: str | None) -> bool:
    return contains_word_or_phrase(message, STATE_TERMS)


def has_explicit_alarm_context(message: str | None, resolved_system: str | None = None) -> bool:
    return resolved_system == "alarm/system" or contains_word_or_phrase(message, ALARM_TERMS)


def has_explicit_counter_context(message: str | None) -> bool:
    return contains_word_or_phrase(message, COUNTER_TERMS)


def has_explicit_plc_context(message: str | None, resolved_system: str | None = None) -> bool:
    return resolved_system == "plc/io/system" or contains_word_or_phrase(message, PLC_TERMS)


def has_compare_modifier(message: str | None) -> bool:
    return contains_word_or_phrase(message, COMPARE_TERMS)


def has_production_subject(message: str | None) -> bool:
    return contains_word_or_phrase(message, PRODUCTION_TERMS)


def has_stop_subject(message: str | None) -> bool:
    return contains_word_or_phrase(message, STOP_TERMS)


def has_change_subject(message: str | None) -> bool:
    return contains_word_or_phrase(message, CHANGE_TERMS)


def has_around_stop_subject(message: str | None) -> bool:
    return contains_word_or_phrase(message, AROUND_STOP_TERMS)


def has_time_range(message: str | None) -> bool:
    return contains_word_or_phrase(message, TIME_RANGE_TERMS)


def infer_time_range_key(message: str | None, explicit: str | None = None) -> str:
    if explicit:
        return explicit
    normalized = normalize_key(message)
    tokens = set(tokenize_message(message))
    if (
        "comparetodaytoyesterday" in normalized
        or "todayvsyesterday" in normalized
        or (has_compare_modifier(message) and "today" in tokens and "yesterday" in tokens)
    ):
        return "today"
    if "last24hours" in normalized or "24hours" in normalized:
        return "last_24_hours"
    if "lasthour" in normalized or "hour" in normalized:
        return "last_hour"
    if "lastweek" in normalized or "thisweek" in normalized or "week" in normalized:
        return "last_week"
    if "yesterday" in normalized:
        return "yesterday"
    return "today"


def compare_to_key(message: str | None) -> str | None:
    normalized = normalize_key(message)
    tokens = set(tokenize_message(message))
    if (
        "comparetodaytoyesterday" in normalized
        or "todayvsyesterday" in normalized
        or "vsyesterday" in normalized
        or "versusyesterday" in normalized
        or "betterthanyesterday" in normalized
        or "worsethanyesterday" in normalized
        or (has_compare_modifier(message) and "today" in tokens and "yesterday" in tokens)
    ):
        return "yesterday"
    return None
