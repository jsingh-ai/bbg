from __future__ import annotations

import json
import logging
import os
import subprocess
from datetime import datetime
from typing import Any

from ..config import get_settings
from .assistant_context import (
    apply_followup_context,
    clear_conversation,
    cleanup_old_conversations,
    get_conversation_memory_stats,
    get_recent_turns,
    remember_turn,
)
from .assistant_router import route_assistant_message
from .assistant_taxonomy import resolve_assistant_taxonomy
from .process_analysis import (
    _is_explicit_alarm_context_request,
    _is_explicit_counter_context_request,
    _is_explicit_plc_context_request,
    _is_explicit_speed_context_request,
    _is_explicit_state_context_request,
    find_last_stop,
    get_assistant_diagnostics,
    get_most_changed_parameters,
    get_production_candidates,
    get_production_debug,
    get_production_summary,
    get_stop_summary,
    get_values_around_stop,
    parse_time_range,
    search_tags,
)
from .section_parser import parse_section_key


SERVICE_STARTED_AT = datetime.now().isoformat()
logger = logging.getLogger(__name__)


def _build_cards(items: list[tuple[str, Any, str | None]]) -> list[dict[str, Any]]:
    return [{"label": label, "value": value, **({"unit": unit} if unit else {})} for label, value, unit in items]


def _build_table(title: str, columns: list[str], rows: list[list[Any]]) -> dict[str, Any]:
    return {"title": title, "columns": columns, "rows": rows}


def _comparison_range_for_route(route: dict[str, Any], message: str) -> str | None:
    if route.get("compare_to"):
        return str(route["compare_to"])
    return None


def _git_value(*args: str) -> str | None:
    try:
        return subprocess.check_output(["git", *args], text=True, stderr=subprocess.DEVNULL).strip() or None
    except Exception:
        return None


def _assistant_version_payload() -> dict[str, Any]:
    return {
        "ok": True,
        "service": "bbg-assistant",
        "raw_route_supported": True,
        "started_at": SERVICE_STARTED_AT,
        "process_id": os.getpid(),
        "git_commit": _git_value("rev-parse", "HEAD"),
        "git_branch": _git_value("branch", "--show-current"),
        "conversation_memory": get_conversation_memory_stats(),
    }


def _resolve_matching_tags(route: dict[str, Any], message: str, limit: int = 50) -> list[dict[str, Any]]:
    search_terms = list(route.get("section_terms") or [])
    if not search_terms and route.get("resolved_system"):
        taxonomy = resolve_assistant_taxonomy(message)
        search_terms = list(taxonomy.get("section_terms") or [])
    if not search_terms:
        return []
    matched: dict[int, dict[str, Any]] = {}
    for term in search_terms:
        for item in search_tags(term, limit=limit):
            section_key = str(item.get("section_key") or parse_section_key(item.get("opc_path")) or "")
            if term.lower() not in section_key.lower():
                continue
            matched[int(item["tag_id"])] = item
    return list(matched.values())


def _section_label(route: dict[str, Any], matching_tags: list[dict[str, Any]]) -> str | None:
    sections = []
    seen: set[str] = set()
    for item in matching_tags:
        section_key = str(item.get("section_key") or "")
        if section_key and section_key not in seen:
            seen.add(section_key)
            sections.append(section_key)
    if sections:
        if len(sections) == 1:
            return sections[0]
        if len(sections) <= 3:
            return ", ".join(sections)
        return f"{len(sections)} matched sections"
    if route.get("resolved_system"):
        return str(route["resolved_system"])
    return None


def _top_labels(items: list[dict[str, Any]], limit: int = 3) -> list[str]:
    if not items:
        return []
    label_counts: dict[str, int] = {}
    for item in items:
        label = str(item.get("label") or "")
        label_counts[label] = label_counts.get(label, 0) + 1
    resolved: list[str] = []
    for item in items[:limit]:
        label = str(item.get("label") or "")
        if label_counts.get(label, 0) > 1 and item.get("section_key"):
            resolved.append(f"{label} in {item['section_key']}")
        else:
            resolved.append(label)
    return resolved


def _deterministic_answer(intent: str, raw: dict[str, Any]) -> str:
    if raw.get("error"):
        error = raw["error"]
        code = error.get("code")
        if code == "missing_production_tags":
            paths = error.get("configured_paths") or {}
            return (
                "I could not calculate production because the configured good/bad bag tags were not found. "
                f"Good path: {paths.get('good_bags_tag_path', '--')}. "
                f"Bad path: {paths.get('bad_bags_tag_path', '--')}. "
                "Check /api/assistant/diagnostics for suggestions."
            )
        if code == "missing_speed_tag":
            return (
                "I could not calculate stops because the configured speed tag was not found. "
                f"Configured path: {error.get('configured_path', '--')}. "
                "Check /api/assistant/diagnostics for suggestions."
            )
        if code == "no_history_rows":
            return "I found the tag, but there were no historical samples in that time range."
        if code == "no_stop_found":
            return "I did not find a stop in the selected range."
        return str(error.get("message") or "The assistant could not complete that calculation.")

    if intent == "production_summary":
        answer = f"{raw['range']['label']} so far: good bags {raw['good_bags']}, bad bags {raw['bad_bags']}, total bags {raw['total_bags']}, bad rate {raw['bad_rate_pct']}%."
        if raw.get("total_counter_bags") is not None:
            answer += f" Total counter {raw['total_counter_bags']}."
        comparison = raw.get("comparison")
        if comparison and not comparison.get("error") and "delta_total_bags" in comparison and "delta_bad_rate_pct" in comparison:
            answer += (
                f" Compared with {comparison['range']['label']}, total bags changed by "
                f"{comparison['delta_total_bags']} and bad rate changed by {comparison['delta_bad_rate_pct']} points."
            )
        elif comparison and comparison.get("error"):
            oldest = comparison["error"].get("oldest_history_timestamp")
            if comparison["error"].get("code") == "no_history_rows" and oldest:
                answer += f" I cannot compare to yesterday because there are no samples from yesterday. Your history starts at {oldest}."
            else:
                answer += f" I could not complete the comparison range because {comparison['error'].get('message', 'comparison data was unavailable')}."
        return answer

    if intent == "stop_summary":
        longest = raw.get("longest_stop")
        if not longest:
            return f"{raw['range']['label']}: no qualifying stops were found."
        parts = [
            f"{raw['range']['label']}: {raw['transition_stop_count']} stops, {raw['downtime_period_count']} downtime periods, {raw['total_down_minutes']} down minutes total, average stop {raw['average_stop_minutes']} minutes, longest stop {longest['duration_minutes']} minutes."
        ]
        if raw.get("already_stopped_at_range_start"):
            parts.append("The machine was already stopped at the start of the available history/range.")
        if raw.get("has_open_ended_stop"):
            parts.append("The last stop is still open as of the latest sample.")
        return " ".join(parts)

    if intent == "most_changed_parameters":
        top = raw.get("parameters") or []
        if not top:
            context = raw.get("context", {})
            if context.get("machine_speed"):
                return "After filtering counters, alarms, PLC/IO, state/status values, dependent speeds, zero-range values, and the speed marker itself, I did not find other process variables that changed enough in the selected range."
            return "No visible process parameter movement was found for that range after applying the default filters."
        labels = ", ".join(_top_labels(top))
        prefix = f"In {raw['section']}, " if raw.get("section") else ""
        limit_suffix = " This analysis hit the configured safety cap, so treat it as a capped ranking." if (raw.get("limits") or {}).get("truncated") else ""
        return f"{prefix}the most changed parameters were {labels}.{limit_suffix}"

    if intent == "values_around_last_stop":
        after = raw.get("after_stop_effect") or []
        before = raw.get("before_stop_movement") or []
        route = raw.get("route") or {}
        speed_context = raw.get("context", {}).get("dependent_speed_changes") or []
        machine_speed = raw.get("context", {}).get("machine_speed")
        explicit_speed_context = bool(route.get("explicit_speed_context"))
        suffix = " The last stop is still open." if raw.get("context", {}).get("stop_is_open_ended") else ""
        limit_suffix = " This analysis hit the configured safety cap, so treat it as a capped ranking." if (raw.get("limits") or {}).get("truncated") else ""
        if not after and not before:
            stop_time = raw.get("stop_time") or "the detected stop time"
            if explicit_speed_context and (machine_speed or speed_context):
                return (
                    f"The machine speed dropped to zero at {stop_time}. I kept speed and performance rows in context for this request. "
                    f"No other ranked process variables met the selected thresholds.{suffix}{limit_suffix}"
                )
            return (
                f"The machine speed dropped to zero at {stop_time}. After filtering counters, alarms, PLC/IO, state/status values, dependent speeds, zero-range values, and the speed marker itself, "
                f"I did not find other process variables that changed enough in the selected window.{suffix}{limit_suffix}"
            )
        if explicit_speed_context:
            before_label = f"{before[0]['label']} in {before[0]['section_key']}" if before else "n/a"
            after_label = f"{after[0]['label']} in {after[0]['section_key']}" if after else "n/a"
            return (
                f"The machine speed dropped to zero at {raw.get('stop_time') or 'the detected stop time'}. "
                f"I included machine speed and dependent speed/performance rows in the Speed / Performance Context table. "
                f"The largest observed non-speed pre-stop movement was {before_label}. "
                f"The largest observed non-speed post-stop effect was {after_label}. "
                f"This is correlation around the stop, not proof of cause.{suffix}{limit_suffix}"
            )
        after_label = f"{after[0]['label']} in {after[0]['section_key']}" if after else "n/a"
        before_label = f"{before[0]['label']} in {before[0]['section_key']}" if before else "n/a"
        return (
            f"Around the last stop, the largest observed pre-stop movement was {before_label}. "
            f"The largest observed post-stop effect was {after_label}. "
            f"This is correlation around the stop, not proof of cause.{suffix}{limit_suffix}"
        )

    if intent == "section_summary":
        top = raw.get("most_changed", {}).get("parameters") or []
        section_label = raw.get("section_label") or raw.get("section") or "the requested section"
        prefix = "For sections" if "," in str(section_label) else "For"
        if top:
            return f"{prefix} {section_label}, the most changed parameters were {', '.join(_top_labels(top))}."
        excluded = raw.get("most_changed", {}).get("excluded_counts") or {}
        if excluded.get("zero_range", 0) > 0:
            return f"{prefix} {section_label}, I found tags for {section_label}, but the process values did not change in the selected range."
        return f"{prefix} {section_label}, I found matching tags, but no visible process variables remained after filtering."

    return (
        "I was not confident enough to choose an analysis automatically. "
        "Try prompts like: How was production today, How many stops in the last 24 hours, What changed the most in the last hour, or What happened in the unwinder today."
    )


def _compact_route(route: dict[str, Any] | None) -> dict[str, Any]:
    route = route or {}
    return {
        "intent": route.get("intent"),
        "time_range": route.get("time_range"),
        "compare_to": route.get("compare_to"),
        "matched_rule": route.get("matched_rule"),
        "resolved_system": route.get("resolved_system"),
        "section_terms": route.get("section_terms"),
        "followup": {
            "used_context": (route.get("followup") or {}).get("used_context"),
            "reason": (route.get("followup") or {}).get("reason"),
            "resolved_intent": (route.get("followup") or {}).get("resolved_intent"),
            "resolved_time_range": (route.get("followup") or {}).get("resolved_time_range"),
        },
    }


def _sanitize_tables_for_llm(tables: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    sanitized: list[dict[str, Any]] = []
    for table in tables or []:
        columns = list(table.get("columns") or [])
        keep_indexes = [
            index
            for index, column in enumerate(columns)
            if "opc path" not in str(column).lower() and "configured path" not in str(column).lower()
        ]
        sanitized.append(
            {
                "title": table.get("title"),
                "columns": [columns[index] for index in keep_indexes],
                "rows": [
                    [cell for index, cell in enumerate(row) if index in keep_indexes]
                    for row in table.get("rows", [])
                ],
            }
        )
    return sanitized


def _sanitize_error_for_llm(error: dict[str, Any] | None) -> dict[str, Any] | None:
    if not error:
        return None
    return {
        key: value
        for key, value in error.items()
        if key not in {"configured_path", "configured_paths", "opc_path", "suggestions"}
    }


def _build_sanitized_llm_payload(
    message: str,
    intent: str,
    raw: dict[str, Any],
    cards: list[dict[str, Any]] | None = None,
    tables: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "intent": intent,
        "question": message,
        "route": _compact_route(raw.get("route")),
        "cards": cards or [],
        "tables": _sanitize_tables_for_llm(tables),
    }
    if raw.get("error"):
        payload["error"] = _sanitize_error_for_llm(raw.get("error"))
    for key in ("warnings", "range", "limits", "stop_time"):
        if key in raw:
            payload[key] = raw[key]
    if raw.get("context", {}).get("stop_is_open_ended"):
        payload["context"] = {"stop_is_open_ended": True}
    return payload


def _build_openai_messages(
    message: str,
    intent: str,
    raw: dict[str, Any],
    cards: list[dict[str, Any]] | None = None,
    tables: list[dict[str, Any]] | None = None,
    *,
    send_raw: bool = False,
) -> list[dict[str, str]]:
    system_prompt = (
        "You are only rewriting the supplied backend-computed JSON. "
        "Only use supplied JSON. Do not invent numbers, causes, alerts, tags, downtime, or recommendations not present in the JSON. "
        "If a value is not present, say it is not available. "
        "Do not claim causation; say observed or correlated if applicable. "
        "Keep the answer short and plant-floor practical. "
        "Do not mention SQL or internal implementation details. "
        "Warnings are shown separately in the UI. Do not repeat warnings in the main answer unless the user explicitly asks about them."
    )
    prompt = {"intent": intent, "question": message, "analysis_result": raw} if send_raw else _build_sanitized_llm_payload(message, intent, raw, cards, tables)
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": json.dumps(prompt, default=str)},
    ]


def _openai_answer(message: str, intent: str, raw: dict[str, Any], cards: list[dict[str, Any]], tables: list[dict[str, Any]]) -> str | None:
    settings = get_settings()
    if not settings.assistant_llm_enabled:
        return None
    try:
        from openai import OpenAI
    except Exception as exc:
        logger.exception("OpenAI SDK import failed for assistant answer generation: %s", exc)
        return None

    try:
        client = OpenAI(api_key=settings.openai_api_key, timeout=settings.openai_timeout_seconds)
    except TypeError:
        client = OpenAI(api_key=settings.openai_api_key)
    except Exception as exc:
        logger.exception("OpenAI client initialization failed for assistant answer generation: %s", exc)
        return None
    messages = _build_openai_messages(message, intent, raw, cards, tables, send_raw=settings.assistant_llm_send_raw)
    request_payload = {
        "model": settings.openai_model,
        "input": messages,
        "max_output_tokens": settings.openai_max_output_tokens,
        "temperature": settings.openai_temperature,
    }
    try:
        response = client.responses.create(**request_payload)
    except Exception as exc:
        if "temperature" in str(exc).lower():
            request_payload.pop("temperature", None)
            try:
                response = client.responses.create(**request_payload)
            except Exception as retry_exc:
                logger.exception("OpenAI Responses API retry failed; chat-completions fallback will be attempted: %s", retry_exc)
                response = None
        else:
            logger.exception("OpenAI Responses API failed; chat-completions fallback will be attempted: %s", exc)
            response = None
    if response is not None:
        output_text = getattr(response, "output_text", None)
        if output_text:
            return output_text
    chat_payload = {
        "model": settings.openai_model,
        "messages": messages,
        "max_tokens": settings.openai_max_output_tokens,
        "temperature": settings.openai_temperature,
    }
    try:
        chat_response = client.chat.completions.create(**chat_payload)
    except Exception as exc:
        if "temperature" in str(exc).lower():
            chat_payload.pop("temperature", None)
            try:
                chat_response = client.chat.completions.create(**chat_payload)
            except Exception as retry_exc:
                logger.exception("OpenAI chat-completions fallback failed; deterministic fallback will be used: %s", retry_exc)
                return None
        else:
            logger.exception("OpenAI chat-completions fallback failed; deterministic fallback will be used: %s", exc)
            return None
    choices = getattr(chat_response, "choices", None) or []
    if not choices:
        return None
    message_obj = getattr(choices[0], "message", None)
    return getattr(message_obj, "content", None) or None


def _format_production_response(raw: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if raw.get("error"):
        error = raw["error"]
        cards = _build_cards([("Status", error.get("code", "error"), None)])
        tables: list[dict[str, Any]] = []
        configured_paths = error.get("configured_paths")
        if configured_paths:
            tables.append(_build_table("Configured Production Tags", ["Setting", "Configured Path"], [[key, value] for key, value in configured_paths.items()]))
        return cards, tables

    cards = _build_cards(
        [
            ("Good Bags", raw["good_bags"], None),
            ("Bad Bags", raw["bad_bags"], None),
            ("Total Bags", raw["total_bags"], None),
            *([("Total Counter", raw["total_counter_bags"], None)] if raw.get("total_counter_bags") is not None else []),
            ("Bad Rate", raw["bad_rate_pct"], "%"),
        ]
    )
    tables: list[dict[str, Any]] = []
    if raw.get("warnings"):
        tables.append(_build_table("Warnings", ["Message"], [[warning] for warning in raw["warnings"]]))
    comparison = raw.get("comparison")
    if comparison and not comparison.get("error") and "range" in comparison:
        tables.append(
            _build_table(
                "Production Comparison",
                ["Range", "Good", "Bad", "Total", "Bad Rate %"],
                [
                    [raw["range"]["label"], raw["good_bags"], raw["bad_bags"], raw["total_bags"], raw["bad_rate_pct"]],
                    [comparison["range"]["label"], comparison["good_bags"], comparison["bad_bags"], comparison["total_bags"], comparison["bad_rate_pct"]],
                ],
            )
        )
    elif comparison and comparison.get("error"):
        tables.append(
            _build_table(
                "Comparison Status",
                ["Status", "Message"],
                [[comparison["error"].get("code", "error"), comparison["error"].get("message", "Comparison data unavailable")]],
            )
        )
    return cards, tables


def _format_stop_response(raw: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if raw.get("error"):
        error = raw["error"]
        cards = _build_cards([("Status", error.get("code", "error"), None)])
        tables: list[dict[str, Any]] = []
        if error.get("configured_path"):
            tables.append(_build_table("Configured Speed Tag", ["Configured Path"], [[error["configured_path"]]]))
        return cards, tables

    longest = raw.get("longest_stop") or {}
    cards = _build_cards(
        [
            ("Stops", raw["transition_stop_count"], None),
            ("Downtime Periods", raw["downtime_period_count"], None),
            ("Down Minutes", raw["total_down_minutes"], "min"),
            ("Longest Stop", longest.get("duration_minutes", 0), "min"),
        ]
    )
    tables = [
        _build_table(
            "Stops",
            ["Start", "End", "Minutes", "Open At Start", "Open Ended"],
            [
                [
                    item.get("start"),
                    item.get("end"),
                    item.get("duration_minutes"),
                    bool(item.get("open_at_range_start")),
                    bool(item.get("open_ended")),
                ]
                for item in raw.get("stops", [])[:20]
            ],
        )
    ]
    return cards, tables


def _format_most_changed_response(raw: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    top = raw.get("parameters") or []
    cards = _build_cards([("Section", raw.get("section") or "Process", None), ("Variables Ranked", len(top), None)])
    tables: list[dict[str, Any]] = [
        _build_table(
            "Most Changed Parameters",
            ["Tag", "Section", "Min", "Max", "Range", "Avg", "Samples"],
            [
                [
                    item.get("label"),
                    item.get("section_key"),
                    item.get("min_value"),
                    item.get("max_value"),
                    item.get("range_value"),
                    item.get("avg_value"),
                    item.get("sample_count"),
                ]
                for item in top
            ],
        )
    ]
    excluded = raw.get("excluded_counts") or {}
    tables.append(
        _build_table(
            "Excluded Rows",
            [
                "Excluded Section",
                "Excluded Tag Term",
                "Zero Range",
                "Machine Speed Context",
                "State Context",
                "Dependent Speed Context",
                "Alarm Context",
                "Counter Context",
                "PLC Context",
            ],
            [[
                excluded.get("excluded_section", 0),
                excluded.get("excluded_tag_term", 0),
                excluded.get("zero_range", 0),
                excluded.get("machine_speed_context", 0),
                excluded.get("state_context", 0),
                excluded.get("dependent_speed_context", 0),
                excluded.get("alarm_context", 0),
                excluded.get("counter_context", 0),
                excluded.get("plc_context", 0),
            ]],
        )
    )
    limits = raw.get("limits") or {}
    if limits:
        tables.append(
            _build_table(
                "Query Limits",
                ["Candidate Tag Limit", "Candidate Tags Returned", "Truncated", "Note"],
                [[limits.get("candidate_tag_limit"), limits.get("candidate_tags_returned"), bool(limits.get("truncated")), limits.get("note")]],
            )
        )
    context = raw.get("context") or {}
    if context.get("state_changes"):
        tables.append(
            _build_table(
                "State / Status Changes",
                ["Section", "Variable", "Min", "Max", "Range", "Avg", "Samples"],
                [
                    [item.get("section_key"), item.get("label"), item.get("min"), item.get("max"), item.get("range"), item.get("avg"), item.get("sample_count")]
                    for item in context.get("state_changes", [])
                ],
            )
        )
    if context.get("dependent_speed_changes") or context.get("machine_speed"):
        speed_rows = []
        if context.get("machine_speed"):
            speed = context["machine_speed"]
            speed_rows.append([speed.get("section_key"), speed.get("label"), speed.get("min"), speed.get("max"), speed.get("range"), speed.get("avg"), speed.get("sample_count")])
        speed_rows.extend(
            [
                [item.get("section_key"), item.get("label"), item.get("min"), item.get("max"), item.get("range"), item.get("avg"), item.get("sample_count")]
                for item in context.get("dependent_speed_changes", [])
            ]
        )
        tables.append(
            _build_table(
                "Speed / Performance Context",
                ["Section", "Variable", "Min", "Max", "Range", "Avg", "Samples"],
                speed_rows,
            )
        )
    for key, title in (
        ("alarm_changes", "Alarm Context"),
        ("counter_changes", "Counter Context"),
        ("plc_changes", "PLC / IO Context"),
    ):
        if context.get(key):
            tables.append(
                _build_table(
                    title,
                    ["Section", "Variable", "Min", "Max", "Range", "Avg", "Samples"],
                    [
                        [item.get("section_key"), item.get("label"), item.get("min"), item.get("max"), item.get("range"), item.get("avg"), item.get("sample_count")]
                        for item in context.get(key, [])
                    ],
                )
            )
    return cards, tables


def _format_around_stop_response(raw: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if raw.get("error"):
        return _build_cards([("Status", raw["error"].get("code", "error"), None)]), []
    cards = _build_cards(
        [
            ("Stop Time", raw.get("stop_time") or "--", None),
            ("Before Window", raw.get("before_minutes", 0), "min"),
            ("After Window", raw.get("after_minutes", 0), "min"),
        ]
    )
    tables = [
        _build_table(
            "Before Stop Movement",
            ["Section", "Variable", "Before Avg", "After Avg", "Before Movement", "Score"],
            [
                [
                    item.get("section_key"),
                    item.get("label"),
                    item.get("before_avg"),
                    item.get("after_avg"),
                    item.get("before_stop_movement"),
                    item.get("before_movement_score"),
                ]
                for item in raw.get("before_stop_movement", [])
            ],
        ),
        _build_table(
            "After Stop Effect",
            ["Section", "Variable", "Before Avg", "After Avg", "After Effect", "Score"],
            [
                [
                    item.get("section_key"),
                    item.get("label"),
                    item.get("before_avg"),
                    item.get("after_avg"),
                    item.get("after_stop_effect"),
                    item.get("after_effect_score"),
                ]
                for item in raw.get("after_stop_effect", [])
            ],
        ),
    ]
    excluded = raw.get("excluded_counts") or {}
    tables.append(
        _build_table(
            "Excluded Rows",
            [
                "Excluded Section",
                "Excluded Tag Term",
                "Zero Range",
                "Machine Speed Context",
                "State Context",
                "Dependent Speed Context",
                "Alarm Context",
                "Counter Context",
                "PLC Context",
            ],
            [[
                excluded.get("excluded_section", 0),
                excluded.get("excluded_tag_term", 0),
                excluded.get("zero_range", 0),
                excluded.get("machine_speed_context", 0),
                excluded.get("state_context", 0),
                excluded.get("dependent_speed_context", 0),
                excluded.get("alarm_context", 0),
                excluded.get("counter_context", 0),
                excluded.get("plc_context", 0),
            ]],
        )
    )
    limits = raw.get("limits") or {}
    if limits:
        tables.append(
            _build_table(
                "Query Limits",
                ["Candidate Tag Limit", "Candidate Tags Returned", "Raw Rows Fetched", "Truncated", "Note"],
                [[limits.get("candidate_tag_limit"), limits.get("candidate_tags_returned"), limits.get("raw_rows_fetched"), bool(limits.get("truncated")), limits.get("note")]],
            )
        )
    context = raw.get("context") or {}
    if context.get("state_changes"):
        tables.append(
            _build_table(
                "State / Status Changes",
                ["Section", "Variable", "Before Avg", "After Avg", "Delta Avg", "Before Movement", "After Effect"],
                [
                    [
                        item.get("section_key"),
                        item.get("label"),
                        item.get("before_avg"),
                        item.get("after_avg"),
                        item.get("delta_avg"),
                        item.get("before_stop_movement"),
                        item.get("after_stop_effect"),
                    ]
                    for item in context.get("state_changes", [])
                ],
            )
        )
    if context.get("dependent_speed_changes") or context.get("machine_speed"):
        speed_rows = []
        if context.get("machine_speed"):
            speed = context["machine_speed"]
            speed_rows.append(
                [
                    speed.get("section_key"),
                    speed.get("label"),
                    speed.get("before_avg"),
                    speed.get("after_avg"),
                    None,
                    speed.get("before_stop_movement"),
                    speed.get("after_stop_effect"),
                ]
            )
        speed_rows.extend(
            [
                [
                    item.get("section_key"),
                    item.get("label"),
                    item.get("before_avg"),
                    item.get("after_avg"),
                    item.get("delta_avg"),
                    item.get("before_stop_movement"),
                    item.get("after_stop_effect"),
                ]
                for item in context.get("dependent_speed_changes", [])
            ]
        )
        tables.append(
            _build_table(
                "Speed / Performance Context",
                ["Section", "Variable", "Before Avg", "After Avg", "Delta Avg", "Before Movement", "After Effect"],
                speed_rows,
            )
        )
    for key, title in (
        ("alarm_changes", "Alarm Context"),
        ("counter_changes", "Counter Context"),
        ("plc_changes", "PLC / IO Context"),
    ):
        if context.get(key):
            tables.append(
                _build_table(
                    title,
                    ["Section", "Variable", "Before Avg", "After Avg", "Delta Avg", "Before Movement", "After Effect"],
                    [
                        [
                            item.get("section_key"),
                            item.get("label"),
                            item.get("before_avg"),
                            item.get("after_avg"),
                            item.get("delta_avg"),
                            item.get("before_stop_movement"),
                            item.get("after_stop_effect"),
                        ]
                        for item in context.get(key, [])
                    ],
                )
            )
    return cards, tables


def _format_section_response(raw: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    matching_tags = raw.get("matching_tags") or []
    most_changed = raw.get("most_changed", {}).get("parameters") or []
    cards = _build_cards([("Section", raw.get("section_label") or raw.get("section") or "--", None), ("Matching Tags", len(matching_tags), None), ("Ranked Variables", len(most_changed), None)])
    tables: list[dict[str, Any]] = [
        _build_table("Matching Tags", ["Label", "Section", "OPC Path"], [[item.get("label"), item.get("section_key"), item.get("opc_path")] for item in matching_tags[:20]]),
        _build_table(
            "Most Changed In Section",
            ["Variable", "Avg", "Min", "Max", "Range", "Score"],
            [[item.get("label"), item.get("avg_value"), item.get("min_value"), item.get("max_value"), item.get("range_value"), item.get("movement_score")] for item in most_changed],
        ),
    ]
    excluded = raw.get("most_changed", {}).get("excluded_counts") or {}
    tables.append(
        _build_table(
            "Excluded Rows",
            [
                "Excluded Section",
                "Excluded Tag Term",
                "Zero Range",
                "Machine Speed Context",
                "State Context",
                "Dependent Speed Context",
                "Alarm Context",
                "Counter Context",
                "PLC Context",
            ],
            [[
                excluded.get("excluded_section", 0),
                excluded.get("excluded_tag_term", 0),
                excluded.get("zero_range", 0),
                excluded.get("machine_speed_context", 0),
                excluded.get("state_context", 0),
                excluded.get("dependent_speed_context", 0),
                excluded.get("alarm_context", 0),
                excluded.get("counter_context", 0),
                excluded.get("plc_context", 0),
            ]],
        )
    )
    return cards, tables


def _format_fallback_response() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    return [], [
        _build_table(
            "Suggested Prompts",
            ["Prompt"],
            [
                ["How was production today?"],
                ["Compare today to yesterday"],
                ["How many stops in the last 24 hours?"],
                ["What changed the most in the last hour?"],
                ["What changed around the last stop?"],
                ["What happened in the unwinder today?"],
            ],
        )
    ]


def handle_assistant_chat(message: str, time_range: str | None = None, conversation_id: str | None = None) -> dict[str, Any]:
    settings = get_settings()
    route = route_assistant_message(message, time_range)
    if settings.assistant_context_enabled and conversation_id:
        cleanup_old_conversations(settings.assistant_context_max_age_minutes)
        recent_turns = get_recent_turns(conversation_id)
        route = apply_followup_context(message, route, recent_turns)
        if "followup" in route:
            route["followup"]["conversation_id"] = conversation_id
    else:
        route["followup"] = {
            "used_context": False,
            "reason": "context_disabled_or_missing_conversation_id",
            "conversation_id": conversation_id,
            "history_turns_available": 0,
            "previous_intent": None,
            "previous_time_range": None,
            "original_intent": route.get("intent"),
            "original_time_range": route.get("time_range"),
            "resolved_intent": route.get("intent"),
            "resolved_time_range": route.get("time_range"),
            "inherited_intent": None,
            "inherited_time_range": None,
            "changed_intent": False,
            "changed_time_range": False,
            "inherited_resolved_system": None,
            "inherited_section_terms": [],
        }
    intent = str(route["intent"])
    range_key = str(route["time_range"])
    selected_range = parse_time_range(range_key)
    explicit_speed_context = bool(route.get("explicit_speed_context")) or _is_explicit_speed_context_request(message)
    explicit_state_context = bool(route.get("explicit_state_context")) or _is_explicit_state_context_request(message)
    explicit_alarm_context = bool(route.get("explicit_alarm_context")) or _is_explicit_alarm_context_request(message, route.get("resolved_system"))
    explicit_counter_context = bool(route.get("explicit_counter_context")) or _is_explicit_counter_context_request(message)
    explicit_plc_context = bool(route.get("explicit_plc_context")) or _is_explicit_plc_context_request(message, route.get("resolved_system"))
    raw: dict[str, Any]

    if intent == "production_summary":
        comparison_key = _comparison_range_for_route(route, message)
        comparison_range = parse_time_range(comparison_key) if comparison_key else None
        raw = get_production_summary(selected_range, comparison_range)
        cards, tables = _format_production_response(raw)
    elif intent == "stop_summary":
        if range_key == "today":
            selected_range = parse_time_range("last_24_hours")
        raw = get_stop_summary(selected_range)
        cards, tables = _format_stop_response(raw)
    elif intent == "most_changed_parameters":
        if range_key == "today":
            selected_range = parse_time_range("last_hour")
        matching_tags = _resolve_matching_tags(route, message, limit=50)
        raw = get_most_changed_parameters(
            selected_range,
            allowed_tag_ids=[int(item["tag_id"]) for item in matching_tags] if matching_tags else None,
            apply_process_filters=True,
            explicit_alarm_context=explicit_alarm_context,
            explicit_counter_context=explicit_counter_context,
            explicit_plc_context=explicit_plc_context,
            explicit_state_context=explicit_state_context,
            explicit_speed_context=explicit_speed_context,
        )
        if route.get("resolved_system"):
            raw["section"] = route.get("resolved_system")
        cards, tables = _format_most_changed_response(raw)
    elif intent == "values_around_last_stop":
        stop_range = parse_time_range("last_24_hours" if range_key == "today" else range_key)
        stop_summary = get_stop_summary(stop_range)
        if stop_summary.get("error"):
            raw = stop_summary
            cards, tables = _format_stop_response(raw)
        else:
            last_stop = find_last_stop(stop_range)
            if not last_stop or not last_stop.get("start"):
                raw = {
                    "stop_time": None,
                    "before_stop_movement": [],
                    "after_stop_effect": [],
                    "error": {"code": "no_stop_found", "message": "No stop was found in the selected range."},
                    "route": route,
                }
                cards, tables = _format_around_stop_response(raw)
            else:
                matching_tags = _resolve_matching_tags(route, message, limit=50)
                stop_time = datetime.fromisoformat(str(last_stop["start"]))
                raw = get_values_around_stop(
                    stop_time,
                    allowed_tag_ids=[int(item["tag_id"]) for item in matching_tags] if matching_tags else None,
                    apply_process_filters=True,
                    explicit_alarm_context=explicit_alarm_context,
                    explicit_counter_context=explicit_counter_context,
                    explicit_plc_context=explicit_plc_context,
                    explicit_state_context=explicit_state_context,
                    context={"stop_is_open_ended": bool(last_stop.get("open_ended"))},
                    explicit_speed_context=explicit_speed_context,
                )
                cards, tables = _format_around_stop_response(raw)
    elif intent == "section_summary":
        matching_tags = _resolve_matching_tags(route, message, limit=50)
        allowed_tag_ids = [int(item["tag_id"]) for item in matching_tags]
        section = route.get("section_terms", [None])[0] if route.get("section_terms") else None
        raw = {
            "section": route.get("resolved_system") or section,
            "section_label": _section_label(route, matching_tags),
            "matching_tags": matching_tags[:20],
            "most_changed": get_most_changed_parameters(
                selected_range,
                allowed_tag_ids=allowed_tag_ids or None,
                apply_process_filters=True,
                explicit_alarm_context=explicit_alarm_context,
                explicit_counter_context=explicit_counter_context,
                explicit_plc_context=explicit_plc_context,
                explicit_state_context=explicit_state_context,
                explicit_speed_context=explicit_speed_context,
            ),
        }
        cards, tables = _format_section_response(raw)
    else:
        raw = {"suggested_prompts": True}
        cards, tables = _format_fallback_response()

    raw["route"] = route
    llm_answer = _openai_answer(message, intent, raw, cards, tables)
    if llm_answer:
        raw["llm"] = {"used": True}
        answer = llm_answer
    else:
        raw["llm"] = {"used": False, "error": "fallback_used"}
        answer = _deterministic_answer(intent, raw)
    remember_turn(conversation_id, message, route, raw)
    response_raw = raw if settings.assistant_expose_raw_response else {"route": route, "llm": raw.get("llm")}
    return {
        "answer": answer,
        "intent": intent,
        "conversation_id": conversation_id,
        "cards": cards,
        "tables": tables,
        "raw": response_raw,
    }


def get_assistant_diagnostics_response() -> dict[str, Any]:
    diagnostics = get_assistant_diagnostics()
    diagnostics["version"] = _assistant_version_payload()
    diagnostics["conversation_memory"] = get_conversation_memory_stats()
    return diagnostics


def get_production_debug_response(time_range: str | None = None) -> dict[str, Any]:
    return get_production_debug(parse_time_range(time_range or "today"))


def get_production_candidates_response(time_range: str | None = None, limit: int = 50) -> dict[str, Any]:
    return get_production_candidates(parse_time_range(time_range or "today"), limit=limit)


def get_assistant_version_response() -> dict[str, Any]:
    return _assistant_version_payload()


def clear_assistant_conversation(conversation_id: str | None) -> dict[str, Any]:
    clear_conversation(conversation_id)
    return {"ok": True, "conversation_id": conversation_id}
