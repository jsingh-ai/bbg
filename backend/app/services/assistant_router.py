from __future__ import annotations

from typing import Any

from .assistant_taxonomy import resolve_assistant_taxonomy
from .section_parser import normalize_key


def _has_any(normalized: str, phrases: tuple[str, ...]) -> bool:
    return any(phrase in normalized for phrase in phrases)


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

    if _has_any(
        normalized,
        (
            "comparetodaytoyesterday",
            "todayvsyesterday",
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
        ),
    )

    if taxonomy.get("resolved_system") and not explicit_production:
        return {
            "intent": "section_summary",
            "time_range": time_range,
            "compare_to": compare_to,
            "matched_rule": "section_summary",
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
            **taxonomy,
        }

    if explicit_production:
        return {
            "intent": "production_summary",
            "time_range": time_range,
            "compare_to": compare_to,
            "matched_rule": "production_summary",
            **taxonomy,
        }

    return {
        "intent": "fallback",
        "time_range": time_range,
        "compare_to": compare_to,
        "matched_rule": "fallback",
        **taxonomy,
    }
