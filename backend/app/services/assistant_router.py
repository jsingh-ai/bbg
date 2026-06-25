from __future__ import annotations

from typing import Any

from .assistant_intents import (
    compare_to_key,
    has_around_stop_subject,
    has_change_subject,
    has_compare_modifier,
    has_explicit_alarm_context,
    has_explicit_counter_context,
    has_explicit_plc_context,
    has_explicit_speed_context,
    has_explicit_state_context,
    has_production_subject,
    has_stop_subject,
    infer_time_range_key,
)
from .assistant_taxonomy import resolve_assistant_taxonomy


def _route_payload(
    *,
    intent: str,
    time_range: str,
    compare_to: str | None,
    matched_rule: str,
    message: str,
    taxonomy: dict[str, Any],
) -> dict[str, Any]:
    return {
        "intent": intent,
        "time_range": time_range,
        "compare_to": compare_to,
        "matched_rule": matched_rule,
        "explicit_speed_context": has_explicit_speed_context(message),
        "explicit_state_context": has_explicit_state_context(message),
        "explicit_alarm_context": has_explicit_alarm_context(message, taxonomy.get("resolved_system")),
        "explicit_counter_context": has_explicit_counter_context(message),
        "explicit_plc_context": has_explicit_plc_context(message, taxonomy.get("resolved_system")),
        **taxonomy,
    }


def route_assistant_message(message: str, explicit_time_range: str | None = None) -> dict[str, Any]:
    taxonomy = resolve_assistant_taxonomy(message)
    time_range = infer_time_range_key(message, explicit_time_range)
    compare_to = compare_to_key(message)
    has_compare = has_compare_modifier(message)
    has_production = has_production_subject(message)
    has_stop = has_stop_subject(message)
    has_change = has_change_subject(message)
    has_around_stop = has_around_stop_subject(message)
    has_speed = has_explicit_speed_context(message)

    if has_around_stop:
        return _route_payload(
            intent="values_around_last_stop",
            time_range=time_range,
            compare_to=compare_to,
            matched_rule="values_around_last_stop",
            message=message,
            taxonomy=taxonomy,
        )

    if has_change:
        return _route_payload(
            intent="most_changed_parameters",
            time_range=time_range,
            compare_to=compare_to,
            matched_rule="most_changed_parameters",
            message=message,
            taxonomy=taxonomy,
        )

    if has_compare:
        if has_production or (not has_stop and not has_speed and not taxonomy.get("resolved_system")):
            return _route_payload(
                intent="production_summary",
                time_range=time_range,
                compare_to=compare_to,
                matched_rule="compare_production",
                message=message,
                taxonomy=taxonomy,
            )
        if has_stop:
            return _route_payload(
                intent="fallback",
                time_range=time_range,
                compare_to=compare_to,
                matched_rule="compare_stops_not_implemented",
                message=message,
                taxonomy=taxonomy,
            )
        if taxonomy.get("resolved_system"):
            return _route_payload(
                intent="section_summary",
                time_range=time_range,
                compare_to=compare_to,
                matched_rule="compare_section",
                message=message,
                taxonomy=taxonomy,
            )
        return _route_payload(
            intent="fallback",
            time_range=time_range,
            compare_to=compare_to,
            matched_rule="compare_not_implemented",
            message=message,
            taxonomy=taxonomy,
        )

    if taxonomy.get("resolved_system") and not has_production:
        return _route_payload(
            intent="section_summary",
            time_range=time_range,
            compare_to=compare_to,
            matched_rule="section_summary",
            message=message,
            taxonomy=taxonomy,
        )

    if has_stop:
        return _route_payload(
            intent="stop_summary",
            time_range=time_range,
            compare_to=compare_to,
            matched_rule="stop_summary",
            message=message,
            taxonomy=taxonomy,
        )

    if has_production:
        return _route_payload(
            intent="production_summary",
            time_range=time_range,
            compare_to=compare_to,
            matched_rule="production_summary",
            message=message,
            taxonomy=taxonomy,
        )

    return _route_payload(
        intent="fallback",
        time_range=time_range,
        compare_to=compare_to,
        matched_rule="fallback",
        message=message,
        taxonomy=taxonomy,
    )
