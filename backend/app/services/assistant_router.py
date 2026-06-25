from __future__ import annotations

from typing import Any

from .assistant_taxonomy import resolve_assistant_taxonomy
from .section_parser import normalize_key


def _has_any(normalized: str, phrases: tuple[str, ...]) -> bool:
    return any(phrase in normalized for phrase in phrases)


def _explicit_speed_context(normalized: str) -> bool:
    return _has_any(
        normalized,
        (
            "speed",
            "speeds",
            "currentspeed",
            "machinespeed",
            "cycleperformance",
            "performance",
            "drivespeed",
            "motion",
            "velocity",
        ),
    )


def _explicit_state_context(normalized: str) -> bool:
    return _has_any(
        normalized,
        (
            "state",
            "status",
            "mode",
            "condition",
            "runningcondition",
        ),
    )


def _explicit_alarm_context(normalized: str) -> bool:
    return _has_any(
        normalized,
        (
            "alarm",
            "alarms",
            "fault",
            "faults",
            "warning",
            "warnings",
            "maxseverity",
        ),
    )


def _explicit_counter_context(normalized: str) -> bool:
    return _has_any(
        normalized,
        (
            "counter",
            "counters",
            "count",
            "counts",
            "numberof",
            "packagecounter",
        ),
    )


def _explicit_plc_context(normalized: str) -> bool:
    return _has_any(
        normalized,
        (
            "plc",
            "io",
            "i/o",
            "systemhealth",
            "controller",
        ),
    )


def _infer_time_range_key(message: str, explicit: str | None) -> str:
    if explicit:
        return explicit
    normalized = normalize_key(message)
    if "comparetodaytoyesterday" in normalized or "todayvsyesterday" in normalized:
        return "today"
    if "last24hours" in normalized or "24hours" in normalized:
        return "last_24_hours"
    if "lasthour" in normalized or "hour" in normalized:
        return "last_hour"
    if "lastweek" in normalized or "week" in normalized:
        return "last_week"
    if "yesterday" in normalized:
        return "yesterday"
    return "today"


def route_assistant_message(message: str, explicit_time_range: str | None = None) -> dict[str, Any]:
    normalized = normalize_key(message)
    taxonomy = resolve_assistant_taxonomy(message)
    time_range = _infer_time_range_key(message, explicit_time_range)
    compare_to: str | None = None
    explicit_speed_context = _explicit_speed_context(normalized)
    explicit_state_context = _explicit_state_context(normalized)
    explicit_alarm_context = _explicit_alarm_context(normalized)
    explicit_counter_context = _explicit_counter_context(normalized)
    explicit_plc_context = _explicit_plc_context(normalized)

    if _has_any(
        normalized,
        (
            "comparetodaytoyesterday",
            "todayvsyesterday",
            "vsyesterday",
            "betterthanyesterday",
        ),
    ):
        compare_to = "yesterday"

    if (
        ("changedaround" in normalized and "stop" in normalized)
        or ("changedbefore" in normalized and "stop" in normalized)
        or ("whatchanged" in normalized and "stopped" in normalized)
        or _has_any(
            normalized,
            (
                "aroundthelaststop",
                "beforethelaststop",
                "whenspeedwentto0",
                "whenspeedwentzero",
            ),
        )
    ):
        return {
            "intent": "values_around_last_stop",
            "time_range": time_range,
            "compare_to": compare_to,
            "matched_rule": "values_around_last_stop",
            "explicit_speed_context": explicit_speed_context,
            "explicit_state_context": explicit_state_context,
            "explicit_alarm_context": explicit_alarm_context,
            "explicit_counter_context": explicit_counter_context,
            "explicit_plc_context": explicit_plc_context,
            **taxonomy,
        }

    if _has_any(
        normalized,
        (
            "changedthemost",
            "changesthemost",
            "mostchanged",
            "unstable",
            "variation",
            "uncertainty",
            "movingthemost",
            "bouncing",
        ),
    ):
        return {
            "intent": "most_changed_parameters",
            "time_range": time_range,
            "compare_to": compare_to,
            "matched_rule": "most_changed_parameters",
            "explicit_speed_context": explicit_speed_context,
            "explicit_state_context": explicit_state_context,
            "explicit_alarm_context": explicit_alarm_context,
            "explicit_counter_context": explicit_counter_context,
            "explicit_plc_context": explicit_plc_context,
            **taxonomy,
        }

    explicit_production = _has_any(
        normalized,
        (
            "production",
            "goodbags",
            "badbags",
            "bags",
            "scrap",
            "reject",
            "rejects",
            "quality",
            "shiftproduction",
            "comparetoday",
            "todayvsyesterday",
            "vsyesterday",
            "betterthanyesterday",
            "compare",
        ),
    )

    if taxonomy.get("resolved_system") and not explicit_production:
        return {
            "intent": "section_summary",
            "time_range": time_range,
            "compare_to": compare_to,
            "matched_rule": "section_summary",
            "explicit_speed_context": explicit_speed_context,
            "explicit_state_context": explicit_state_context,
            "explicit_alarm_context": explicit_alarm_context,
            "explicit_counter_context": explicit_counter_context,
            "explicit_plc_context": explicit_plc_context,
            **taxonomy,
        }

    if _has_any(
        normalized,
        (
            "howmanystops",
            "stopcount",
            "downtime",
            "downtime",
            "longeststop",
            "machinestopped",
        ),
    ):
        return {
            "intent": "stop_summary",
            "time_range": time_range,
            "compare_to": compare_to,
            "matched_rule": "stop_summary",
            "explicit_speed_context": explicit_speed_context,
            "explicit_state_context": explicit_state_context,
            "explicit_alarm_context": explicit_alarm_context,
            "explicit_counter_context": explicit_counter_context,
            "explicit_plc_context": explicit_plc_context,
            **taxonomy,
        }

    if explicit_production:
        return {
            "intent": "production_summary",
            "time_range": time_range,
            "compare_to": compare_to,
            "matched_rule": "production_summary",
            "explicit_speed_context": explicit_speed_context,
            "explicit_state_context": explicit_state_context,
            "explicit_alarm_context": explicit_alarm_context,
            "explicit_counter_context": explicit_counter_context,
            "explicit_plc_context": explicit_plc_context,
            **taxonomy,
        }

    return {
        "intent": "fallback",
        "time_range": time_range,
        "compare_to": compare_to,
        "matched_rule": "fallback",
        "explicit_speed_context": explicit_speed_context,
        "explicit_state_context": explicit_state_context,
        "explicit_alarm_context": explicit_alarm_context,
        "explicit_counter_context": explicit_counter_context,
        "explicit_plc_context": explicit_plc_context,
        **taxonomy,
    }
