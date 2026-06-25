from __future__ import annotations

import json
from typing import Any

from ..config import get_settings
from .process_analysis import (
    TimeRange,
    find_last_stop,
    get_assistant_diagnostics,
    get_most_changed_parameters,
    get_production_summary,
    get_stop_summary,
    get_values_around_stop,
    list_sections,
    parse_time_range,
    search_tags,
)
from .section_parser import normalize_key


SECTION_HINTS = ("unwinder", "dancer", "storage", "format")


def _build_cards(items: list[tuple[str, Any, str | None]]) -> list[dict[str, Any]]:
    return [{"label": label, "value": value, **({"unit": unit} if unit else {})} for label, value, unit in items]


def _build_table(title: str, columns: list[str], rows: list[list[Any]]) -> dict[str, Any]:
    return {"title": title, "columns": columns, "rows": rows}


def _infer_time_range_key(message: str, explicit: str | None) -> str:
    if explicit:
        return explicit
    normalized = normalize_key(message)
    if "yesterday" in normalized:
        return "yesterday"
    if "lastweek" in normalized or "week" in normalized:
        return "last_week"
    if "last24hours" in normalized or "24hours" in normalized:
        return "last_24_hours"
    if "lasthour" in normalized or "hour" in normalized:
        return "last_hour"
    return "today"


def _compare_range_for(key: str) -> TimeRange | None:
    if key == "today":
        return parse_time_range("yesterday")
    return None


def _match_section(message: str) -> str | None:
    normalized = normalize_key(message)
    for section in list_sections():
        if normalize_key(section) and normalize_key(section) in normalized:
            return section
    for hint in SECTION_HINTS:
        if hint in normalized:
            for section in list_sections():
                if hint in normalize_key(section):
                    return section
    return None


def _intent_for_message(message: str) -> str:
    normalized = normalize_key(message)
    if any(term in normalized for term in ("aroundlaststop", "beforestop", "whenstopped")):
        return "values_around_stop"
    if any(term in normalized for term in ("changedmost", "unstable", "variation", "uncertainty")):
        return "most_changed"
    if any(term in normalized for term in ("stop", "stops", "downtime", "speedzero")):
        return "stop_summary"
    if any(term in normalized for term in ("production", "good", "bad", "scrap", "yesterday", "today", "compare")):
        return "production_summary"
    if any(term in normalized for term in SECTION_HINTS):
        return "section_summary"
    return "production_summary"


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
        return str(error.get("message") or "The assistant could not complete that calculation.")
    if intent == "production_summary":
        answer = (
            f"{raw['range']['label']}: good bags {raw['good_bags']}, bad bags {raw['bad_bags']}, "
            f"total bags {raw['total_bags']}, bad rate {raw['bad_rate_pct']}%."
        )
        comparison = raw.get("comparison")
        if comparison:
            answer += (
                f" Compared with {comparison['range']['label']}, total bags changed by "
                f"{comparison['delta_total_bags']} and bad rate changed by {comparison['delta_bad_rate_pct']} points."
            )
        return answer
    if intent == "stop_summary":
        longest = raw.get("longest_stop")
        if longest:
            return (
                f"{raw['range']['label']}: {raw['stop_count']} stops, {raw['total_down_minutes']} down minutes total, "
                f"average stop {raw['average_stop_minutes']} minutes, longest stop {longest['duration_minutes']} minutes."
            )
        return f"{raw['range']['label']}: no qualifying stops were found."
    if intent == "most_changed":
        top = raw.get("parameters") or []
        if not top:
            return "No numeric parameter movement was found for that range."
        labels = ", ".join(item["label"] for item in top[:3])
        prefix = f"In {raw['section']}, " if raw.get("section") else ""
        return f"{prefix}the most changed parameters were {labels}."
    if intent == "values_around_stop":
        after = raw.get("after_stop_effect") or []
        before = raw.get("before_stop_movement") or []
        if not after and not before:
            return "I found the stop, but there were not enough surrounding numeric values to rank changes."
        after_label = after[0]["label"] if after else "n/a"
        before_label = before[0]["label"] if before else "n/a"
        return f"Around the last stop, the strongest pre-stop movement was {before_label} and the strongest post-stop effect was {after_label}."
    if intent == "section_summary":
        top = raw.get("most_changed", {}).get("parameters") or []
        return (
            f"For section {raw.get('section')}, I found {len(raw.get('matching_tags') or [])} matching tags. "
            f"The most changed parameters were {', '.join(item['label'] for item in top[:3]) or 'not enough data'}."
        )
    return "I analyzed the available OPC history and returned the requested summary."


def _openai_answer(message: str, intent: str, raw: dict[str, Any]) -> str | None:
    settings = get_settings()
    if not settings.assistant_llm_enabled:
        return None
    try:
        from openai import OpenAI
    except Exception:
        return None

    client = OpenAI(api_key=settings.openai_api_key)
    prompt = {
        "intent": intent,
        "question": message,
        "analysis_result": raw,
        "rules": [
            "Be concise and factual.",
            "Use the computed backend numbers directly.",
            "Do not claim causation unless the data only shows correlation.",
            "This is a read-only production/process analyst for OPC history.",
        ],
    }
    try:
        response = client.responses.create(
            model=settings.openai_model,
            input=[
                {
                    "role": "system",
                    "content": "You explain industrial process analytics from structured data. Stay concise, practical, and read-only.",
                },
                {"role": "user", "content": json.dumps(prompt, default=str)},
            ],
        )
    except Exception:
        return None

    return getattr(response, "output_text", None) or None


def _format_production_response(raw: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if raw.get("error"):
        error = raw["error"]
        cards = _build_cards([("Status", error.get("code", "error"), None)])
        tables = []
        configured_paths = error.get("configured_paths")
        if configured_paths:
            tables.append(
                _build_table(
                    "Configured Production Tags",
                    ["Setting", "Configured Path"],
                    [[key, value] for key, value in configured_paths.items()],
                )
            )
        return cards, tables
    cards = _build_cards(
        [
            ("Good Bags", raw["good_bags"], None),
            ("Bad Bags", raw["bad_bags"], None),
            ("Total Bags", raw["total_bags"], None),
            ("Bad Rate", raw["bad_rate_pct"], "%"),
        ]
    )
    tables: list[dict[str, Any]] = []
    comparison = raw.get("comparison")
    if comparison:
        tables.append(
            _build_table(
                "Production Comparison",
                ["Range", "Good", "Bad", "Total", "Bad Rate %"],
                [
                    [raw["range"]["label"], raw["good_bags"], raw["bad_bags"], raw["total_bags"], raw["bad_rate_pct"]],
                    [
                        comparison["range"]["label"],
                        comparison["good_bags"],
                        comparison["bad_bags"],
                        comparison["total_bags"],
                        comparison["bad_rate_pct"],
                    ],
                ],
            )
        )
    return cards, tables


def _format_stop_response(raw: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if raw.get("error"):
        error = raw["error"]
        cards = _build_cards([("Status", error.get("code", "error"), None)])
        tables = []
        if error.get("configured_path"):
            tables.append(_build_table("Configured Speed Tag", ["Configured Path"], [[error["configured_path"]]]))
        return cards, tables
    longest = raw.get("longest_stop") or {}
    cards = _build_cards(
        [
            ("Stops", raw["stop_count"], None),
            ("Down Minutes", raw["total_down_minutes"], "min"),
            ("Longest Stop", longest.get("duration_minutes", 0), "min"),
            ("Average Stop", raw["average_stop_minutes"], "min"),
        ]
    )
    tables = [
        _build_table(
            "Stops",
            ["Start", "End", "Minutes"],
            [[item.get("start"), item.get("end"), item.get("duration_minutes")] for item in raw.get("stops", [])[:20]],
        )
    ]
    return cards, tables


def _format_most_changed_response(raw: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    top = raw.get("parameters") or []
    cards = _build_cards(
        [
            ("Section", raw.get("section") or "All", None),
            ("Variables Ranked", len(top), None),
        ]
    )
    tables = [
        _build_table(
            "Most Changed Parameters",
            ["Section", "Variable", "Avg", "Min", "Max", "Range", "StdDev", "Score", "Samples"],
            [
                [
                    item.get("section_key"),
                    item.get("label"),
                    item.get("avg_value"),
                    item.get("min_value"),
                    item.get("max_value"),
                    item.get("range_value"),
                    item.get("stddev_value"),
                    item.get("movement_score"),
                    item.get("sample_count"),
                ]
                for item in top
            ],
        )
    ]
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
                    item.get("movement_score"),
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
                    item.get("movement_score"),
                ]
                for item in raw.get("after_stop_effect", [])
            ],
        ),
    ]
    return cards, tables


def _format_section_response(raw: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    matching_tags = raw.get("matching_tags") or []
    most_changed = raw.get("most_changed", {}).get("parameters") or []
    cards = _build_cards(
        [
            ("Section", raw.get("section") or "--", None),
            ("Matching Tags", len(matching_tags), None),
            ("Ranked Variables", len(most_changed), None),
        ]
    )
    tables = [
        _build_table(
            "Matching Tags",
            ["Label", "Section", "OPC Path"],
            [[item.get("label"), item.get("section_key"), item.get("opc_path")] for item in matching_tags[:20]],
        ),
        _build_table(
            "Most Changed In Section",
            ["Variable", "Avg", "Min", "Max", "Range", "Score"],
            [
                [
                    item.get("label"),
                    item.get("avg_value"),
                    item.get("min_value"),
                    item.get("max_value"),
                    item.get("range_value"),
                    item.get("movement_score"),
                ]
                for item in most_changed
            ],
        ),
    ]
    return cards, tables


def handle_assistant_chat(message: str, time_range: str | None = None, conversation_id: str | None = None) -> dict[str, Any]:
    intent = _intent_for_message(message)
    range_key = _infer_time_range_key(message, time_range)
    selected_range = parse_time_range(range_key)
    raw: dict[str, Any]

    if intent == "production_summary":
        comparison_range = _compare_range_for(selected_range.key) if "compare" in normalize_key(message) or selected_range.key == "today" else None
        raw = get_production_summary(selected_range, comparison_range)
        cards, tables = _format_production_response(raw)
    elif intent == "stop_summary":
        if range_key == "today":
            selected_range = parse_time_range("last_24_hours")
        raw = get_stop_summary(selected_range)
        cards, tables = _format_stop_response(raw)
    elif intent == "most_changed":
        if range_key == "today":
            selected_range = parse_time_range("last_hour")
        section = _match_section(message)
        raw = get_most_changed_parameters(selected_range, section=section)
        cards, tables = _format_most_changed_response(raw)
    elif intent == "values_around_stop":
        stop_range = parse_time_range("last_24_hours" if range_key == "today" else range_key)
        stop_summary = get_stop_summary(stop_range)
        if stop_summary.get("error"):
            raw = stop_summary
            cards, tables = _format_stop_response(raw)
        else:
            last_stop = find_last_stop(stop_range)
            if not last_stop or not last_stop.get("start"):
                raw = {"stop_time": None, "before_stop_movement": [], "after_stop_effect": []}
                cards, tables = _format_around_stop_response(raw)
            else:
                section = _match_section(message)
                stop_time = datetime.fromisoformat(str(last_stop["start"]))
                raw = get_values_around_stop(stop_time, section=section)
                cards, tables = _format_around_stop_response(raw)
    else:
        section = _match_section(message)
        if range_key == "today":
            selected_range = parse_time_range("today")
        raw = {
            "section": section,
            "matching_tags": search_tags(section or message, limit=20),
            "most_changed": get_most_changed_parameters(selected_range, section=section),
        }
        cards, tables = _format_section_response(raw)
        intent = "section_summary"

    answer = _openai_answer(message, intent, raw) or _deterministic_answer(intent, raw)
    return {
        "answer": answer,
        "intent": intent,
        "conversation_id": conversation_id,
        "cards": cards,
        "tables": tables,
        "raw": raw,
    }


def get_assistant_diagnostics_response() -> dict[str, Any]:
    return get_assistant_diagnostics()
