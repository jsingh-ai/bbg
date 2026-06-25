from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from math import sqrt
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ..config import get_settings
from ..db import pool
from .assistant_intents import (
    has_explicit_alarm_context,
    has_explicit_counter_context,
    has_explicit_plc_context,
    has_explicit_speed_context,
    has_explicit_state_context,
)
from .section_parser import display_name, normalize_key, parse_section_key
from .value_format import formatted_value, row_json_safe, rows_json_safe


COUNTER_HINTS = ("good", "bad", "total", "count", "counter", "shift", "job")
SECTION_TERMS = (
    "unwinder",
    "dancer",
    "dance",
    "storage",
    "storage cylinder",
    "format",
    "forming",
    "cylinder",
    "tension",
    "web",
    "seal",
    "knife",
    "temperature",
    "pressure",
)
GENERIC_PATH_SEGMENTS = {"global pv", "state", "para", "info"}


@dataclass(frozen=True)
class TimeRange:
    key: str
    label: str
    start: datetime
    end: datetime
    timezone: str


def _settings():
    return get_settings()


def _machine_id() -> int:
    return _settings().default_machine_id


def _timezone(name: str | None = None):
    try:
        return ZoneInfo(name or _settings().assistant_default_timezone)
    except ZoneInfoNotFoundError:
        return datetime.now().astimezone().tzinfo


def _timezone_name(zone: Any, configured_name: str | None = None) -> str:
    if hasattr(zone, "key") and getattr(zone, "key"):
        return str(getattr(zone, "key"))
    if configured_name:
        return configured_name
    if hasattr(zone, "tzname"):
        try:
            return str(zone.tzname(None) or "local")
        except Exception:
            return "local"
    return "local"


def _as_iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _range_dict(time_range: TimeRange) -> dict[str, Any]:
    return {
        "key": time_range.key,
        "label": time_range.label,
        "timezone": time_range.timezone,
        "start": _as_iso(time_range.start),
        "end": _as_iso(time_range.end),
    }


def _safe_stddev(count: int, sum_value: float, sum_sq: float) -> float:
    if count <= 1:
        return 0.0
    mean = sum_value / count
    variance = max((sum_sq / count) - (mean * mean), 0.0)
    return sqrt(variance)


def _movement_score(avg: float, min_value: float, max_value: float) -> float:
    return (max_value - min_value) / max(abs(avg), 1.0)


def _section_filter_sql(section: str | None) -> tuple[str, list[Any]]:
    if not section:
        return "", []
    return " AND cfg.section_key = %s", [section]


def _counter_delta(rows: list[dict[str, Any]]) -> float:
    total = 0.0
    previous: float | None = None
    for row in rows:
        current = row.get("value_num")
        if current is None:
            continue
        value = float(current)
        if previous is not None and value >= previous:
            total += value - previous
        previous = value
    return total


def _counter_stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
    numeric_rows = [row for row in rows if row.get("value_num") is not None and row.get("created_at") is not None]
    if not numeric_rows:
        return {
            "first": None,
            "last": None,
            "delta_sum": 0.0,
            "raw_delta": 0.0,
            "reset_count": 0,
            "sample_count": 0,
        }
    reset_count = 0
    previous: float | None = None
    for row in numeric_rows:
        current = float(row["value_num"])
        if previous is not None and current < previous:
            reset_count += 1
        previous = current
    first_row = numeric_rows[0]
    last_row = numeric_rows[-1]
    raw_delta = float(last_row["value_num"]) - float(first_row["value_num"])
    return {
        "first": {"timestamp": _as_iso(first_row["created_at"]), "value": float(first_row["value_num"])},
        "last": {"timestamp": _as_iso(last_row["created_at"]), "value": float(last_row["value_num"])},
        "delta_sum": round(_counter_delta(numeric_rows), 3),
        "raw_delta": round(raw_delta, 3),
        "reset_count": reset_count,
        "sample_count": len(numeric_rows),
    }


def _production_warnings(good_bags: float, bad_bags: float, total_bags: float, bad_rate_pct: float) -> list[str]:
    warnings: list[str] = []
    if total_bags > 0 and bad_bags > good_bags * 2:
        warnings.append(
            "Bad bag delta is much larger than good bag delta. Verify ASSISTANT_GOOD_BAGS_TAG_PATH and ASSISTANT_BAD_BAGS_TAG_PATH."
        )
    if bad_rate_pct > 50:
        warnings.append(
            "Bad rate is unusually high. This may indicate the configured production tags are not the desired good/bad production counters."
        )
    return warnings


def _is_explicit_speed_context_request(message: str | None = None) -> bool:
    return has_explicit_speed_context(message)


def _is_explicit_state_context_request(message: str | None = None) -> bool:
    return has_explicit_state_context(message)


def _is_explicit_alarm_context_request(message: str | None = None, resolved_system: str | None = None) -> bool:
    return has_explicit_alarm_context(message, resolved_system)


def _is_explicit_counter_context_request(message: str | None = None) -> bool:
    return has_explicit_counter_context(message)


def _is_explicit_plc_context_request(message: str | None = None, resolved_system: str | None = None) -> bool:
    return has_explicit_plc_context(message, resolved_system)


def _excluded_counts() -> dict[str, int]:
    return {
        "excluded_section": 0,
        "excluded_tag_term": 0,
        "zero_range": 0,
        "machine_speed_context": 0,
        "state_context": 0,
        "dependent_speed_context": 0,
        "alarm_context": 0,
        "counter_context": 0,
        "plc_context": 0,
    }


def _is_alarm_term(term: str) -> bool:
    return any(token in term for token in ("alarm", "severity", "fault", "warning"))


def _is_counter_term(term: str) -> bool:
    return any(token in term for token in ("counter", "count", "number of", "good", "bad", "total", "shift", "job", "package"))


def _row_blob(item: dict[str, Any]) -> str:
    return " ".join(
        str(item.get(key) or "").lower()
        for key in ("section_key", "opc_path", "label", "display_name", "browse_name", "node_id")
    )


def _context_score(row: dict[str, Any]) -> tuple[float, float, float]:
    range_value = abs(float(row.get("range") or row.get("range_value") or 0))
    score_value = max(
        abs(float(row.get("before_movement_score") or 0)),
        abs(float(row.get("after_effect_score") or 0)),
        abs(float(row.get("movement_score") or 0)),
        abs(float(row.get("before_stop_movement") or 0)),
        abs(float(row.get("after_stop_effect") or 0)),
        abs(float(row.get("delta_avg") or 0)),
    )
    return (range_value, score_value, float(row.get("sample_count") or 0))


def _around_context_row(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "tag_id": item.get("tag_id"),
        "label": item.get("label"),
        "display_name": item.get("display_name"),
        "section_key": item.get("section_key"),
        "opc_path": item.get("opc_path"),
        "before_avg": item.get("before_avg"),
        "after_avg": item.get("after_avg"),
        "delta_avg": item.get("delta_avg"),
        "before_stop_movement": item.get("before_stop_movement"),
        "after_stop_effect": item.get("after_stop_effect"),
        "before_movement_score": item.get("before_movement_score"),
        "after_effect_score": item.get("after_effect_score"),
        "movement_score": item.get("movement_score"),
    }


def _most_changed_context_row(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "tag_id": item.get("tag_id"),
        "label": item.get("label"),
        "display_name": item.get("display_name"),
        "section_key": item.get("section_key"),
        "opc_path": item.get("opc_path"),
        "min": item.get("min_value"),
        "max": item.get("max_value"),
        "avg": item.get("avg_value"),
        "range": item.get("range_value"),
        "sample_count": item.get("sample_count"),
    }


def _context_bucket_for_filtered_row(
    item: dict[str, Any],
    *,
    explicit_alarm_context: bool,
    explicit_counter_context: bool,
    explicit_plc_context: bool,
) -> str | None:
    blob = _row_blob(item)
    if not explicit_plc_context and ("/i/o/" in blob or "plc" in blob or "system health" in blob):
        return "plc_changes"
    if not explicit_alarm_context and any(token in blob for token in ("alarm", "active alarms", "max severity", "fault", "warning")):
        return "alarm_changes"
    if not explicit_counter_context and any(
        token in blob for token in ("counter", "count", "number of", "good", "bad", "total", "shift", "job", "package")
    ):
        return "counter_changes"
    return None


def should_exclude_section(section_key: str, terms: list[str]) -> bool:
    normalized_section = section_key.lower().strip()
    if not normalized_section:
        return False
    for term in terms:
        normalized_term = str(term).lower().strip()
        if not normalized_term:
            continue
        if len(normalized_term) <= 2:
            if normalized_section == normalized_term:
                return True
            continue
        if normalized_section == normalized_term or normalized_term in normalized_section:
            return True
    return False


def _speed_context_row(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "tag_id": item.get("tag_id"),
        "opc_path": item.get("opc_path"),
        "section_key": item.get("section_key"),
        "label": item.get("label"),
        "min": item.get("min_value"),
        "max": item.get("max_value"),
        "avg": item.get("avg_value"),
        "range": item.get("range_value"),
        "sample_count": item.get("sample_count"),
    }


def make_contextual_label(row_or_tag: dict[str, Any]) -> str:
    opc_path = str(row_or_tag.get("opc_path") or "")
    fallback = (
        row_or_tag.get("label")
        or row_or_tag.get("display_name")
        or row_or_tag.get("browse_name")
        or row_or_tag.get("node_id")
        or "Tag"
    )
    if not opc_path:
        return str(fallback)
    parts = [part.strip() for part in opc_path.replace("\\", "/").split("/") if part.strip()]
    if len(parts) < 2:
        return str(fallback)
    trimmed: list[str] = []
    start_index = 2 if len(parts) >= 2 and parts[0].lower() == "global pv" else 1
    for part in parts[start_index:]:
        if part.lower() in GENERIC_PATH_SEGMENTS:
            continue
        trimmed.append(part)
    if not trimmed:
        return str(fallback)
    if len(trimmed) == 1:
        return str(fallback)
    leaf = trimmed[-1]
    parent = trimmed[-2]
    return f"{parent} / {leaf}"


def dedupe_rows(rows: list[dict[str, Any]], score_fn) -> list[dict[str, Any]]:
    deduped: dict[str, dict[str, Any]] = {}
    for row in rows:
        opc_path = str(row.get("opc_path") or "").strip().lower()
        if opc_path:
            key = opc_path
        else:
            key = f"{str(row.get('section_key') or '').strip().lower()}|{str(row.get('label') or '').strip().lower()}"
        existing = deduped.get(key)
        if existing is None or score_fn(row) > score_fn(existing):
            deduped[key] = row
    return list(deduped.values())


def _is_state_context_row(item: dict[str, Any], *, explicit_state_context: bool = False) -> bool:
    settings = _settings()
    if not settings.assistant_state_context_enabled or explicit_state_context:
        return False
    label = str(item.get("display_name") or item.get("label") or "").lower().strip()
    opc_path = str(item.get("opc_path") or "").lower().strip()
    if label in settings.assistant_excluded_state_term_list:
        return True
    return opc_path.endswith("/state/state") or opc_path.endswith("/para/mode")


def _is_dependent_speed_context_row(item: dict[str, Any], *, explicit_speed_context: bool = False) -> bool:
    if explicit_speed_context:
        return False
    return _is_dependent_speed_row(item)


def _is_dependent_speed_row(item: dict[str, Any]) -> bool:
    settings = _settings()
    if not settings.assistant_speed_context_enabled:
        return False
    blob = " ".join(
        [
            str(item.get("display_name") or item.get("label") or ""),
            str(item.get("opc_path") or ""),
            str(item.get("browse_name") or ""),
        ]
    ).lower()
    return any(term in blob for term in settings.assistant_dependent_speed_term_list)


def _is_machine_speed_context_row(item: dict[str, Any], speed_tag_id: int | None) -> bool:
    return bool(speed_tag_id and int(item.get("tag_id") or 0) == speed_tag_id)


def _rank_visible_around_stop_rows(changes: list[dict[str, Any]], limit: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    visible = dedupe_rows(
        changes,
        lambda row: max(float(row.get("before_movement_score") or 0), float(row.get("after_effect_score") or 0), float(row.get("movement_score") or 0)),
    )
    visible = [item for item in visible if float(item.get("before_movement_score") or 0) > 0 or float(item.get("after_effect_score") or 0) > 0]
    before_rows = [item for item in visible if float(item.get("before_movement_score") or 0) > 0]
    after_rows = [item for item in visible if float(item.get("after_effect_score") or 0) > 0]
    return (
        sorted(before_rows, key=lambda row: (row["before_movement_score"], abs(row["before_stop_movement"])), reverse=True)[: max(limit, 1)],
        sorted(after_rows, key=lambda row: (row["after_effect_score"], abs(row["after_stop_effect"])), reverse=True)[: max(limit, 1)],
    )


def _filter_process_row(
    row: dict[str, Any],
    *,
    apply_process_filters: bool,
    explicit_alarm_context: bool,
    explicit_counter_context: bool,
    explicit_plc_context: bool,
    keep_tag_ids: set[int] | None = None,
) -> str | None:
    if not apply_process_filters:
        return None
    tag_id = int(row.get("tag_id") or 0)
    if keep_tag_ids and tag_id in keep_tag_ids:
        return None
    settings = _settings()
    section_key = str(row.get("section_key") or "").lower()
    opc_path = str(row.get("opc_path") or "").lower()
    label = str(row.get("label") or row.get("display_name") or row.get("browse_name") or "").lower()
    blob = " ".join(part for part in (section_key, opc_path, label) if part)
    if should_exclude_section(section_key, settings.assistant_excluded_section_key_list):
        if explicit_plc_context and section_key == "i":
            return None
        if explicit_alarm_context and "alarm system" in section_key:
            return None
        return "excluded_section"
    for term in settings.assistant_excluded_path_contains_list:
        if not term or term not in opc_path:
            continue
        if explicit_plc_context and term == "/i/o/":
            continue
        if explicit_alarm_context and "alarm system" in term:
            continue
        return "excluded_section"
    for term in settings.assistant_excluded_tag_term_list:
        if not term or term not in blob:
            continue
        if explicit_alarm_context and _is_alarm_term(term):
            continue
        if explicit_counter_context and _is_counter_term(term):
            continue
        return "excluded_tag_term"
    return None


def get_table_count_safe(table_name: str) -> int | None:
    settings = _settings()
    allowed = {"opc_tags", "opc_tag_values"}
    if table_name not in allowed:
        return None
    if table_name == "opc_tag_values":
        row = pool.fetch_one(
            """
            SELECT TABLE_ROWS AS table_rows
            FROM information_schema.tables
            WHERE table_schema = %s AND table_name = %s
            """,
            (settings.db_name, table_name),
        )
        return int(row.get("table_rows") or 0) if row else None
    row = pool.fetch_one(f"SELECT COUNT(*) AS row_count FROM {table_name}")
    return int(row.get("row_count") or 0) if row else 0


def get_history_bounds() -> dict[str, Any]:
    row = pool.fetch_one(
        """
        SELECT MIN(created_at) AS oldest_history_timestamp,
               MAX(created_at) AS latest_history_timestamp
        FROM opc_tag_values
        """
    )
    if not row:
        return {"oldest_history_timestamp": None, "latest_history_timestamp": None}
    return row_json_safe(row)


def get_tag_latest_history_sample(tag_id: int) -> dict[str, Any] | None:
    row = pool.fetch_one(
        """
        SELECT created_at, value_num, value_kind
        FROM opc_tag_values
        WHERE tag_id = %s
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (tag_id,),
    )
    return row_json_safe(row) if row else None


def _tag_suggestions(query: str, limit: int = 5) -> list[dict[str, Any]]:
    rows = pool.fetch_all(
        """
        SELECT tag_id, opc_path, display_name, browse_name, node_id
        FROM opc_tags
        WHERE machine_id = %s
          AND is_active = 1
          AND (
            opc_path LIKE %s
            OR COALESCE(display_name, '') LIKE %s
            OR COALESCE(browse_name, '') LIKE %s
            OR COALESCE(node_id, '') LIKE %s
          )
        ORDER BY opc_path
        LIMIT %s
        """,
        (_machine_id(), f"%{query}%", f"%{query}%", f"%{query}%", f"%{query}%", max(limit, 1)),
    )
    results = []
    for row in rows_json_safe(rows):
        row["label"] = display_name(row)
        results.append({"tag_id": row.get("tag_id"), "label": row.get("label"), "opc_path": row.get("opc_path")})
    return results


def resolve_configured_tag(path: str, fallback_terms: list[str] | tuple[str, ...]) -> dict[str, Any]:
    rows = pool.fetch_all(
        """
        SELECT tag_id, machine_id, opc_path, display_name, browse_name, node_id
        FROM opc_tags
        WHERE machine_id = %s
          AND is_active = 1
        ORDER BY opc_path
        """,
        (_machine_id(),),
    )

    exact = next((row for row in rows if str(row.get("opc_path") or "") == path), None)
    if exact:
        return {
            "configured_path": path,
            "found": True,
            "match_type": "exact",
            "tag": exact,
        }

    lower_path = path.lower()
    case_insensitive = next((row for row in rows if str(row.get("opc_path") or "").lower() == lower_path), None)
    if case_insensitive:
        return {
            "configured_path": path,
            "found": True,
            "match_type": "case_insensitive",
            "tag": case_insensitive,
        }

    suggestions: list[dict[str, Any]] = []
    seen_tag_ids: set[int] = set()
    search_terms = [term for term in [path, *fallback_terms] if term]
    for term in search_terms:
        for suggestion in _tag_suggestions(term):
            tag_id = int(suggestion.get("tag_id") or 0)
            if tag_id and tag_id not in seen_tag_ids:
                seen_tag_ids.add(tag_id)
                suggestions.append(suggestion)
            if len(suggestions) >= 5:
                break
        if len(suggestions) >= 5:
            break

    return {
        "configured_path": path,
        "found": False,
        "match_type": None,
        "tag": None,
        "suggestions": suggestions,
    }


def _latest_latest_row(tag_id: int) -> dict[str, Any] | None:
    row = pool.fetch_one(
        """
        SELECT t.tag_id, t.opc_path, t.display_name, t.browse_name, t.node_id,
               l.captured_at, l.updated_at, l.value_kind, l.value_num, l.value_bool, l.value_text, l.error_text
        FROM opc_tags t
        LEFT JOIN opc_tag_latest l ON l.tag_id = t.tag_id
        WHERE t.tag_id = %s
        """,
        (tag_id,),
    )
    return row if row else None


def get_assistant_diagnostics() -> dict[str, Any]:
    settings = _settings()
    config_block = {
        "speed_tag_path": settings.assistant_speed_tag_path,
        "good_bags_tag_path": settings.assistant_good_bags_tag_path,
        "bad_bags_tag_path": settings.assistant_bad_bags_tag_path,
        "total_bags_tag_path": settings.assistant_total_bags_tag_path,
        "production_mode": settings.assistant_production_mode,
        "llm_send_raw": settings.assistant_llm_send_raw,
        "expose_raw_response": settings.assistant_expose_raw_response,
        "running_speed_threshold": settings.assistant_running_speed_threshold,
        "min_stop_minutes": settings.assistant_min_stop_minutes,
        "max_rows": settings.assistant_max_rows,
        "excluded_section_keys": settings.assistant_excluded_section_key_list,
        "excluded_path_contains": settings.assistant_excluded_path_contains_list,
        "excluded_tag_terms": settings.assistant_excluded_tag_term_list,
        "excluded_state_terms": settings.assistant_excluded_state_term_list,
        "state_context_enabled": settings.assistant_state_context_enabled,
        "dependent_speed_terms": settings.assistant_dependent_speed_term_list,
        "speed_context_enabled": settings.assistant_speed_context_enabled,
    }
    try:
        database = {
            "connected": True,
            "opc_tags_count": get_table_count_safe("opc_tags"),
            "opc_tag_values_count_estimate": get_table_count_safe("opc_tag_values"),
            **get_history_bounds(),
        }

        required = {
            "speed": resolve_configured_tag(settings.assistant_speed_tag_path, ["speed", "machine speed", "format"]),
            "good_bags": resolve_configured_tag(settings.assistant_good_bags_tag_path, ["good", "bags", "shift good"]),
            "bad_bags": resolve_configured_tag(settings.assistant_bad_bags_tag_path, ["bad", "bags", "shift bad"]),
        }

        required_tags: dict[str, Any] = {}
        suggested_fixes: list[str] = []
        for key, resolved in required.items():
            if resolved["found"] and resolved["tag"]:
                tag = resolved["tag"]
                latest_history = get_tag_latest_history_sample(int(tag["tag_id"]))
                latest_live = _latest_latest_row(int(tag["tag_id"]))
                label = display_name(tag)
                last_sample_at = latest_history.get("created_at") if latest_history else None
                latest_value = None
                if latest_live:
                    latest_value = formatted_value(latest_live)
                    if latest_live.get("value_kind") == 1 and latest_live.get("value_num") is not None:
                        latest_value = row_json_safe({"value": latest_live.get("value_num")}).get("value")
                elif latest_history and latest_history.get("value_num") is not None:
                    latest_value = latest_history.get("value_num")
                required_tags[key] = {
                    "configured_path": resolved["configured_path"],
                    "found": True,
                    "tag_id": int(tag["tag_id"]),
                    "label": label,
                    "last_sample_at": last_sample_at,
                    "last_value": latest_value,
                }
            else:
                required_tags[key] = {
                    "configured_path": resolved["configured_path"],
                    "found": False,
                    "suggestions": resolved.get("suggestions", []),
                }
                suggested_fixes.append(
                    f"{key} tag not found for configured path '{resolved['configured_path']}'. Check /api/assistant/diagnostics suggestions and update .env."
                )
    except Exception as exc:
        database = {
            "connected": False,
            "opc_tags_count": None,
            "opc_tag_values_count_estimate": None,
            "latest_history_timestamp": None,
            "oldest_history_timestamp": None,
            "error": str(exc),
        }
        required_tags = {
            "speed": {"configured_path": settings.assistant_speed_tag_path, "found": False, "suggestions": []},
            "good_bags": {"configured_path": settings.assistant_good_bags_tag_path, "found": False, "suggestions": []},
            "bad_bags": {"configured_path": settings.assistant_bad_bags_tag_path, "found": False, "suggestions": []},
        }
        suggested_fixes = ["Database connection failed while loading assistant diagnostics."]

    return {
        "ok": True,
        "assistant_enabled": bool(settings.assistant_enabled),
        "openai_configured": bool(settings.openai_api_key.strip()),
        "timezone": settings.assistant_default_timezone,
        "config": config_block,
        "database": database,
        "required_tags": required_tags,
        "suggested_fixes": suggested_fixes,
    }


def parse_time_range(text_or_enum: str | None, timezone: str | None = None) -> TimeRange:
    configured_timezone = timezone or _settings().assistant_default_timezone
    zone = _timezone(configured_timezone)
    timezone_name = _timezone_name(zone, configured_timezone)
    now = datetime.now(zone).replace(second=0, microsecond=0)
    raw = normalize_key(text_or_enum or "")
    mapping = {
        "today": "today",
        "yesterday": "yesterday",
        "lasthour": "last_hour",
        "last24hours": "last_24_hours",
        "lastweek": "last_week",
    }
    key = mapping.get(raw, "today")
    if key == "today":
        start = now.replace(hour=0, minute=0)
        return TimeRange(key=key, label="Today", start=start.replace(tzinfo=None), end=now.replace(tzinfo=None), timezone=timezone_name)
    if key == "yesterday":
        today_start = now.replace(hour=0, minute=0)
        start = today_start - timedelta(days=1)
        return TimeRange(key=key, label="Yesterday", start=start.replace(tzinfo=None), end=today_start.replace(tzinfo=None), timezone=timezone_name)
    if key == "last_hour":
        start = now - timedelta(hours=1)
        return TimeRange(key=key, label="Last Hour", start=start.replace(tzinfo=None), end=now.replace(tzinfo=None), timezone=timezone_name)
    if key == "last_24_hours":
        start = now - timedelta(hours=24)
        return TimeRange(key=key, label="Last 24 Hours", start=start.replace(tzinfo=None), end=now.replace(tzinfo=None), timezone=timezone_name)
    start = now - timedelta(days=7)
    return TimeRange(key=key, label="Last Week", start=start.replace(tzinfo=None), end=now.replace(tzinfo=None), timezone=timezone_name)


def _fetch_numeric_series(
    tag_id: int,
    start: datetime,
    end: datetime,
    *,
    include_prior: bool = False,
    max_rows: int | None = None,
) -> list[dict[str, Any]]:
    settings = _settings()
    rows: list[dict[str, Any]] = []
    if include_prior:
        prior = pool.fetch_one(
            """
            SELECT created_at, tag_id, value_num
            FROM opc_tag_values
            WHERE tag_id = %s
              AND created_at < %s
              AND value_kind = 1
              AND value_num IS NOT NULL
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (tag_id, start),
        )
        if prior:
            rows.append(prior)
    bounded_limit = max_rows or settings.assistant_max_rows
    rows.extend(
        pool.fetch_all(
            """
            SELECT created_at, tag_id, value_num
            FROM opc_tag_values
            WHERE tag_id = %s
              AND created_at >= %s
              AND created_at <= %s
              AND value_kind = 1
              AND value_num IS NOT NULL
            ORDER BY created_at
            LIMIT %s
            """,
            (tag_id, start, end, bounded_limit),
        )
    )
    return rows


def get_production_summary(time_range: TimeRange, compare_to: TimeRange | None = None) -> dict[str, Any]:
    settings = _settings()
    good_resolution = resolve_configured_tag(settings.assistant_good_bags_tag_path, ["good", "bags", "shift good"])
    bad_resolution = resolve_configured_tag(settings.assistant_bad_bags_tag_path, ["bad", "bags", "shift bad"])
    total_resolution = resolve_configured_tag(settings.assistant_total_bags_tag_path, ["endless counter", "total", "bags", "package"])

    if not good_resolution["found"] or not bad_resolution["found"]:
        return {
            "range": _range_dict(time_range),
            "error": {
                "code": "missing_production_tags",
                "message": "I could not calculate production because the configured good/bad bag tags were not found.",
                "configured_paths": {
                    "good_bags_tag_path": settings.assistant_good_bags_tag_path,
                    "bad_bags_tag_path": settings.assistant_bad_bags_tag_path,
                },
                "diagnostics_endpoint": "/api/assistant/diagnostics",
            },
        }

    good_tag = good_resolution["tag"]
    bad_tag = bad_resolution["tag"]
    good_rows = _fetch_numeric_series(int(good_tag["tag_id"]), time_range.start, time_range.end, max_rows=settings.assistant_max_rows)
    bad_rows = _fetch_numeric_series(int(bad_tag["tag_id"]), time_range.start, time_range.end, max_rows=settings.assistant_max_rows)
    total_counter_bags = None
    total_counter_tag = None
    if total_resolution["found"] and total_resolution["tag"]:
        total_counter_tag = {
            "tag_id": int(total_resolution["tag"]["tag_id"]),
            "label": display_name(total_resolution["tag"]),
            "opc_path": total_resolution["tag"].get("opc_path"),
        }
        total_rows = _fetch_numeric_series(int(total_resolution["tag"]["tag_id"]), time_range.start, time_range.end, max_rows=settings.assistant_max_rows)
        total_counter_bags = round(_counter_delta(total_rows), 3)

    timestamps = [row.get("created_at") for row in [*good_rows, *bad_rows] if row.get("created_at") is not None]
    if not timestamps:
        return {
            "range": _range_dict(time_range),
            "error": {
                "code": "no_history_rows",
                "message": "I found the tag, but there were no historical samples in that time range.",
                **get_history_bounds(),
            },
            "good_bags": 0,
            "bad_bags": 0,
            "total_bags": 0,
            "total_counter_bags": total_counter_bags,
            "total_counter_tag": total_counter_tag,
            "production_mode": settings.assistant_production_mode,
            "bad_rate_pct": 0.0,
            "first_timestamp": None,
            "last_timestamp": None,
        }

    result = {
        "range": _range_dict(time_range),
        "good_bags": round(_counter_delta(good_rows), 3),
        "bad_bags": round(_counter_delta(bad_rows), 3),
        "total_counter_bags": total_counter_bags,
        "total_counter_tag": total_counter_tag,
        "production_mode": settings.assistant_production_mode,
        "first_timestamp": _as_iso(min(timestamps)),
        "last_timestamp": _as_iso(max(timestamps)),
    }
    result["total_bags"] = round(result["good_bags"] + result["bad_bags"], 3)
    result["bad_rate_pct"] = round((result["bad_bags"] / result["total_bags"]) * 100, 2) if result["total_bags"] > 0 else 0.0
    result["warnings"] = _production_warnings(result["good_bags"], result["bad_bags"], result["total_bags"], result["bad_rate_pct"])

    if compare_to:
        baseline = get_production_summary(compare_to, None)
        if not baseline.get("error"):
            result["comparison"] = {
                "range": baseline["range"],
                "good_bags": baseline["good_bags"],
                "bad_bags": baseline["bad_bags"],
                "total_bags": baseline["total_bags"],
                "bad_rate_pct": baseline["bad_rate_pct"],
                "delta_good_bags": round(result["good_bags"] - baseline["good_bags"], 3),
                "delta_bad_bags": round(result["bad_bags"] - baseline["bad_bags"], 3),
                "delta_total_bags": round(result["total_bags"] - baseline["total_bags"], 3),
                "delta_bad_rate_pct": round(result["bad_rate_pct"] - baseline["bad_rate_pct"], 2),
            }
        else:
            result["comparison"] = baseline
    return result


def get_production_debug(time_range: TimeRange) -> dict[str, Any]:
    settings = _settings()
    warnings: list[str] = []
    good_resolution = resolve_configured_tag(settings.assistant_good_bags_tag_path, ["good", "bags", "shift good"])
    bad_resolution = resolve_configured_tag(settings.assistant_bad_bags_tag_path, ["bad", "bags", "shift bad"])
    total_resolution = resolve_configured_tag(settings.assistant_total_bags_tag_path, ["endless counter", "total", "bags", "package"])

    def debug_for_resolution(resolution: dict[str, Any], fallback_key: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        if not resolution["found"] or not resolution["tag"]:
            warnings.append(f"{fallback_key} tag not found for configured path '{resolution['configured_path']}'.")
            return {"configured_path": resolution["configured_path"], "found": False, "suggestions": resolution.get("suggestions", [])}, []
        tag = resolution["tag"]
        rows = _fetch_numeric_series(int(tag["tag_id"]), time_range.start, time_range.end, max_rows=settings.assistant_max_rows)
        return {
            "configured_path": resolution["configured_path"],
            "found": True,
            "tag_id": int(tag["tag_id"]),
            "label": display_name(tag),
            "opc_path": tag.get("opc_path"),
        }, rows

    good_tag, good_rows = debug_for_resolution(good_resolution, "good")
    bad_tag, bad_rows = debug_for_resolution(bad_resolution, "bad")
    total_tag, total_rows = debug_for_resolution(total_resolution, "total")
    good_stats = _counter_stats(good_rows)
    bad_stats = _counter_stats(bad_rows)
    total_stats = _counter_stats(total_rows)
    good_delta = float(good_stats.get("delta_sum") or 0.0)
    bad_delta = float(bad_stats.get("delta_sum") or 0.0)
    total_delta = good_delta + bad_delta
    bad_rate_pct = round((bad_delta / total_delta) * 100, 2) if total_delta > 0 else 0.0
    warnings.extend(_production_warnings(good_delta, bad_delta, total_delta, bad_rate_pct))
    return {
        "range": _range_dict(time_range),
        "good_tag": good_tag,
        "bad_tag": bad_tag,
        "total_tag": total_tag,
        "good_samples": good_stats,
        "bad_samples": bad_stats,
        "total_samples": total_stats,
        "production_mode": settings.assistant_production_mode,
        "warnings": warnings,
    }


def get_production_candidates(time_range: TimeRange, limit: int = 50) -> dict[str, Any]:
    candidate_terms = ("good", "bad", "bag", "bags", "reject", "rejects", "scrap", "count", "counter", "shift", "job", "total", "package")
    rows = pool.fetch_all(
        """
        SELECT tag_id, opc_path, display_name, browse_name, node_id
        FROM opc_tags
        WHERE machine_id = %s
          AND is_active = 1
        ORDER BY opc_path
        """,
        (_machine_id(),),
    )
    candidates: list[dict[str, Any]] = []
    for row in rows:
        blob = " ".join(
            [
                str(row.get("opc_path") or ""),
                str(row.get("display_name") or ""),
                str(row.get("browse_name") or ""),
                str(row.get("node_id") or ""),
            ]
        ).lower()
        if not any(term in blob for term in candidate_terms):
            continue
        series = _fetch_numeric_series(int(row["tag_id"]), time_range.start, time_range.end, max_rows=_settings().assistant_max_rows)
        stats = _counter_stats(series)
        candidates.append(
            {
                "tag_id": int(row["tag_id"]),
                "label": display_name(row),
                "opc_path": row.get("opc_path"),
                "section_key": parse_section_key(row.get("opc_path")),
                "first_value": stats["first"]["value"] if stats.get("first") else None,
                "last_value": stats["last"]["value"] if stats.get("last") else None,
                "delta_sum": stats["delta_sum"],
                "raw_delta": stats["raw_delta"],
                "reset_count": stats["reset_count"],
                "sample_count": stats["sample_count"],
            }
        )
    candidates.sort(key=lambda item: (int(item["sample_count"]), abs(float(item["delta_sum"] or 0))), reverse=True)
    return {"range": _range_dict(time_range), "candidates": candidates[: max(limit, 1)]}


def get_stop_summary(time_range: TimeRange) -> dict[str, Any]:
    settings = _settings()
    speed_resolution = resolve_configured_tag(settings.assistant_speed_tag_path, ["speed", "machine speed", "format"])
    if not speed_resolution["found"]:
        return {
            "range": _range_dict(time_range),
            "error": {
                "code": "missing_speed_tag",
                "message": "I could not calculate stops because the configured speed tag was not found.",
                "configured_path": settings.assistant_speed_tag_path,
                "diagnostics_endpoint": "/api/assistant/diagnostics",
            },
            "stop_count": 0,
            "total_down_minutes": 0,
            "longest_stop": None,
            "average_stop_minutes": 0,
            "stops": [],
        }

    rows = _fetch_numeric_series(
        int(speed_resolution["tag"]["tag_id"]),
        time_range.start,
        time_range.end,
        include_prior=True,
        max_rows=settings.assistant_max_rows,
    )
    in_range_rows = [row for row in rows if row.get("created_at") and row["created_at"] >= time_range.start]
    if not in_range_rows:
        return {
            "range": _range_dict(time_range),
            "error": {
                "code": "no_history_rows",
                "message": "I found the tag, but there were no historical samples in that time range.",
            },
            "stop_count": 0,
            "total_down_minutes": 0,
            "longest_stop": None,
            "average_stop_minutes": 0,
            "stops": [],
        }

    threshold = settings.assistant_running_speed_threshold
    min_stop = max(settings.assistant_min_stop_minutes, 1)
    stops: list[dict[str, Any]] = []
    active_start: datetime | None = None
    transition_stop_count = 0
    already_stopped_at_start = False

    for index, row in enumerate(rows):
        created_at = row.get("created_at")
        value_num = row.get("value_num")
        if created_at is None or value_num is None:
            continue
        current_running = float(value_num) > threshold
        if index == 0:
            if created_at < time_range.start and not current_running:
                active_start = time_range.start
                already_stopped_at_start = True
            elif created_at >= time_range.start and not current_running:
                active_start = created_at
                already_stopped_at_start = True
            continue
        previous = rows[index - 1]
        previous_value = previous.get("value_num")
        previous_ts = previous.get("created_at")
        if previous_value is None or previous_ts is None:
            continue
        was_running = float(previous_value) > threshold
        if was_running and not current_running and created_at >= time_range.start:
            active_start = created_at
            transition_stop_count += 1
        elif not was_running and current_running and active_start is not None:
            duration = max(int((created_at - active_start).total_seconds() // 60), 0)
            if duration >= min_stop:
                stop_row = {"start": _as_iso(active_start), "end": _as_iso(created_at), "duration_minutes": duration}
                if already_stopped_at_start and active_start <= time_range.start:
                    stop_row["open_at_range_start"] = True
                    stop_row["already_stopped_at_history_start"] = True
                stops.append(stop_row)
            active_start = None

    if active_start is not None:
        duration = max(int((time_range.end - active_start).total_seconds() // 60), 0)
        if duration >= min_stop:
            stop_row = {"start": _as_iso(active_start), "end": _as_iso(time_range.end), "duration_minutes": duration, "open_ended": True}
            if already_stopped_at_start and active_start <= time_range.start:
                stop_row["open_at_range_start"] = True
                stop_row["already_stopped_at_history_start"] = True
            stops.append(stop_row)

    total_down_minutes = sum(int(stop["duration_minutes"]) for stop in stops)
    longest = max(stops, key=lambda item: int(item["duration_minutes"]), default=None)
    average = round(total_down_minutes / len(stops), 2) if stops else 0.0
    return {
        "range": _range_dict(time_range),
        "stop_count": transition_stop_count,
        "transition_stop_count": transition_stop_count,
        "downtime_period_count": len(stops),
        "already_stopped_at_range_start": already_stopped_at_start,
        "has_open_ended_stop": bool(stops and stops[-1].get("open_ended")),
        "total_down_minutes": total_down_minutes,
        "longest_stop": longest,
        "average_stop_minutes": average,
        "stops": stops,
    }


def get_most_changed_parameters(
    time_range: TimeRange,
    section: str | None = None,
    limit: int = 10,
    *,
    allowed_tag_ids: list[int] | None = None,
    apply_process_filters: bool = True,
    explicit_alarm_context: bool = False,
    explicit_counter_context: bool = False,
    explicit_plc_context: bool = False,
    explicit_state_context: bool = False,
    keep_tag_ids: list[int] | None = None,
    explicit_speed_context: bool = False,
) -> dict[str, Any]:
    settings = _settings()
    speed_resolution = resolve_configured_tag(settings.assistant_speed_tag_path, ["speed", "machine speed", "format"])
    speed_tag_id = int(speed_resolution["tag"]["tag_id"]) if speed_resolution.get("found") and speed_resolution.get("tag") else None
    section_sql, section_params = _section_filter_sql(section)
    allowed_sql = ""
    allowed_params: list[Any] = []
    if allowed_tag_ids:
        placeholders = ",".join(["%s"] * len(allowed_tag_ids))
        allowed_sql = f" AND v.tag_id IN ({placeholders})"
        allowed_params.extend(allowed_tag_ids)
    max_ranked_tags = max(int(settings.assistant_max_rows or 0), max(limit, 1))
    rows = pool.fetch_all(
        f"""
        SELECT
            v.tag_id,
            t.opc_path,
            t.display_name,
            t.browse_name,
            t.node_id,
            cfg.section_key,
            COUNT(*) AS sample_count,
            MIN(v.value_num) AS min_value,
            MAX(v.value_num) AS max_value,
            AVG(v.value_num) AS avg_value,
            SUM(v.value_num) AS sum_value,
            SUM(v.value_num * v.value_num) AS sum_sq_value,
            (MAX(v.value_num) - MIN(v.value_num)) AS range_value,
            ((MAX(v.value_num) - MIN(v.value_num)) / GREATEST(ABS(AVG(v.value_num)), 1)) AS movement_score
        FROM opc_tag_values v
        JOIN opc_tags t ON t.tag_id = v.tag_id
        LEFT JOIN opc_tag_display_config cfg ON cfg.tag_id = t.tag_id AND cfg.machine_id = t.machine_id
        WHERE t.machine_id = %s
          AND v.created_at >= %s
          AND v.created_at <= %s
          AND v.value_kind = 1
          AND v.value_num IS NOT NULL
          {section_sql}
          {allowed_sql}
        GROUP BY v.tag_id, t.opc_path, t.display_name, t.browse_name, t.node_id, cfg.section_key
        ORDER BY movement_score DESC, range_value DESC, t.tag_id
        LIMIT %s
        """,
        tuple([_machine_id(), time_range.start, time_range.end, *section_params, *allowed_params, max_ranked_tags + 1]),
    )
    truncated = len(rows) > max_ranked_tags
    if truncated:
        rows = rows[:max_ranked_tags]
    ranked: list[dict[str, Any]] = []
    excluded_counts = _excluded_counts()
    keep_tag_id_set = set(keep_tag_ids or [])
    machine_speed_context: dict[str, Any] | None = None
    state_changes: list[dict[str, Any]] = []
    dependent_speed_changes: list[dict[str, Any]] = []
    alarm_changes: list[dict[str, Any]] = []
    counter_changes: list[dict[str, Any]] = []
    plc_changes: list[dict[str, Any]] = []
    for row in rows:
        item = row_json_safe(row)
        min_value = float(row.get("min_value") or 0)
        max_value = float(row.get("max_value") or 0)
        avg_value = float(row.get("avg_value") or 0)
        sample_count = int(row.get("sample_count") or 0)
        item.update(
            {
                "display_name": display_name(row),
                "label": make_contextual_label(row),
                "section_key": row.get("section_key") or parse_section_key(row.get("opc_path")),
                "range_value": round(max_value - min_value, 6),
                "stddev_value": round(_safe_stddev(sample_count, float(row.get("sum_value") or 0), float(row.get("sum_sq_value") or 0)), 6),
                "movement_score": round(_movement_score(avg_value, min_value, max_value), 6),
                "sample_count": sample_count,
            }
        )
        exclusion_reason = _filter_process_row(
            item,
            apply_process_filters=apply_process_filters,
            explicit_alarm_context=explicit_alarm_context,
            explicit_counter_context=explicit_counter_context,
            explicit_plc_context=explicit_plc_context,
            keep_tag_ids=keep_tag_id_set,
        )
        if exclusion_reason:
            excluded_counts[exclusion_reason] += 1
            bucket = _context_bucket_for_filtered_row(
                item,
                explicit_alarm_context=explicit_alarm_context,
                explicit_counter_context=explicit_counter_context,
                explicit_plc_context=explicit_plc_context,
            )
            if bucket and float(item["range_value"]) > 0:
                if bucket == "alarm_changes":
                    alarm_changes.append(_most_changed_context_row(item))
                    excluded_counts["alarm_context"] += 1
                elif bucket == "counter_changes":
                    counter_changes.append(_most_changed_context_row(item))
                    excluded_counts["counter_context"] += 1
                elif bucket == "plc_changes":
                    plc_changes.append(_most_changed_context_row(item))
                    excluded_counts["plc_context"] += 1
            continue
        if _is_machine_speed_context_row(item, speed_tag_id) and not explicit_speed_context:
            excluded_counts["machine_speed_context"] += 1
            machine_speed_context = _speed_context_row(item)
            continue
        if _is_state_context_row(item, explicit_state_context=explicit_state_context):
            if float(item["range_value"]) > 0:
                state_changes.append(_most_changed_context_row(item))
            excluded_counts["state_context"] += 1
            continue
        if _is_dependent_speed_context_row(item, explicit_speed_context=explicit_speed_context):
            if float(item["range_value"]) > 0:
                dependent_speed_changes.append(_most_changed_context_row(item))
            excluded_counts["dependent_speed_context"] += 1
            continue
        if float(item["range_value"]) == 0:
            excluded_counts["zero_range"] += 1
            continue
        ranked.append(item)
    ranked = dedupe_rows(ranked, lambda row: (float(row.get("movement_score") or 0), float(row.get("range_value") or 0)))
    ranked.sort(key=lambda row: (row["movement_score"], row["range_value"]), reverse=True)
    state_changes = dedupe_rows(state_changes, _context_score)
    dependent_speed_changes = dedupe_rows(dependent_speed_changes, _context_score)
    alarm_changes = dedupe_rows(alarm_changes, _context_score)
    counter_changes = dedupe_rows(counter_changes, _context_score)
    plc_changes = dedupe_rows(plc_changes, _context_score)
    return {
        "range": _range_dict(time_range),
        "section": section,
        "parameters": ranked[: max(limit, 1)],
        "excluded_counts": excluded_counts,
        "limits": {
            "candidate_tag_limit": max_ranked_tags,
            "candidate_tags_returned": len(rows),
            "truncated": truncated,
            "note": "SQL aggregation is ranked before this safety cap; Python process filters are applied before visible output.",
        },
        "context": {
            **({"machine_speed": machine_speed_context} if machine_speed_context else {}),
            **({"state_changes": state_changes[:10]} if state_changes else {}),
            **({"dependent_speed_changes": dependent_speed_changes[:10]} if dependent_speed_changes else {}),
            **({"alarm_changes": alarm_changes[:5]} if alarm_changes and (explicit_alarm_context or len(alarm_changes) <= 5) else {}),
            **({"counter_changes": counter_changes[:5]} if counter_changes and (explicit_counter_context or len(counter_changes) <= 5) else {}),
            **({"plc_changes": plc_changes[:5]} if plc_changes and (explicit_plc_context or len(plc_changes) <= 5) else {}),
        },
    }


def find_last_stop(time_range: TimeRange) -> dict[str, Any] | None:
    summary = get_stop_summary(time_range)
    if summary.get("error"):
        return None
    stops = summary.get("stops") or []
    return stops[-1] if stops else None


def get_values_around_stop(
    stop_time: datetime,
    before_minutes: int = 10,
    after_minutes: int = 10,
    section: str | None = None,
    limit: int = 15,
    *,
    allowed_tag_ids: list[int] | None = None,
    apply_process_filters: bool = True,
    explicit_alarm_context: bool = False,
    explicit_counter_context: bool = False,
    explicit_plc_context: bool = False,
    explicit_state_context: bool = False,
    keep_tag_ids: list[int] | None = None,
    context: dict[str, Any] | None = None,
    explicit_speed_context: bool = False,
) -> dict[str, Any]:
    settings = _settings()
    speed_resolution = resolve_configured_tag(settings.assistant_speed_tag_path, ["speed", "machine speed", "format"])
    speed_tag_id = int(speed_resolution["tag"]["tag_id"]) if speed_resolution.get("found") and speed_resolution.get("tag") else None
    before_start = stop_time - timedelta(minutes=max(before_minutes, 1))
    after_end = stop_time + timedelta(minutes=max(after_minutes, 1))
    section_sql, section_params = _section_filter_sql(section)
    allowed_sql = ""
    allowed_params: list[Any] = []
    if allowed_tag_ids:
        placeholders = ",".join(["%s"] * len(allowed_tag_ids))
        allowed_sql = f" AND v.tag_id IN ({placeholders})"
        allowed_params.extend(allowed_tag_ids)
    max_candidate_tags = max(int(settings.assistant_max_rows or 0), max(limit, 1))
    candidate_rows = pool.fetch_all(
        f"""
        SELECT
            v.tag_id,
            t.opc_path,
            t.display_name,
            t.browse_name,
            t.node_id,
            cfg.section_key,
            COUNT(*) AS sample_count,
            MIN(v.value_num) AS min_value,
            MAX(v.value_num) AS max_value,
            AVG(v.value_num) AS avg_value,
            (MAX(v.value_num) - MIN(v.value_num)) AS range_value,
            ((MAX(v.value_num) - MIN(v.value_num)) / GREATEST(ABS(AVG(v.value_num)), 1)) AS movement_score
        FROM opc_tag_values v
        JOIN opc_tags t ON t.tag_id = v.tag_id
        LEFT JOIN opc_tag_display_config cfg ON cfg.tag_id = t.tag_id AND cfg.machine_id = t.machine_id
        WHERE t.machine_id = %s
          AND v.created_at >= %s
          AND v.created_at <= %s
          AND v.value_kind = 1
          AND v.value_num IS NOT NULL
          {section_sql}
          {allowed_sql}
        GROUP BY v.tag_id, t.opc_path, t.display_name, t.browse_name, t.node_id, cfg.section_key
        ORDER BY movement_score DESC, range_value DESC, t.tag_id
        LIMIT %s
        """,
        tuple([_machine_id(), before_start, after_end, *section_params, *allowed_params, max_candidate_tags + 1]),
    )
    truncated = len(candidate_rows) > max_candidate_tags
    if truncated:
        candidate_rows = candidate_rows[:max_candidate_tags]
    candidate_tag_ids = [int(row["tag_id"]) for row in candidate_rows if row.get("tag_id") is not None]
    rows: list[dict[str, Any]] = []
    if candidate_tag_ids:
        placeholders = ",".join(["%s"] * len(candidate_tag_ids))
        rows = pool.fetch_all(
            f"""
            SELECT
                v.tag_id,
                v.created_at,
                v.value_num,
                t.opc_path,
                t.display_name,
                t.browse_name,
                t.node_id,
                cfg.section_key
            FROM opc_tag_values v
            JOIN opc_tags t ON t.tag_id = v.tag_id
            LEFT JOIN opc_tag_display_config cfg ON cfg.tag_id = t.tag_id AND cfg.machine_id = t.machine_id
            WHERE t.machine_id = %s
              AND v.created_at >= %s
              AND v.created_at <= %s
              AND v.value_kind = 1
              AND v.value_num IS NOT NULL
              AND v.tag_id IN ({placeholders})
            ORDER BY v.tag_id, v.created_at
            """,
            tuple([_machine_id(), before_start, after_end, *candidate_tag_ids]),
        )
    if not rows:
        return {
            "stop_time": _as_iso(stop_time),
            "section": section,
            "before_minutes": before_minutes,
            "after_minutes": after_minutes,
            "error": {"code": "no_history_rows", "message": "I found the tag, but there were no historical samples in that time range."},
            "before_stop_movement": [],
            "after_stop_effect": [],
            "excluded_counts": _excluded_counts(),
            "context": context or {},
            "limits": {
                "candidate_tag_limit": max_candidate_tags,
                "candidate_tags_returned": len(candidate_rows),
                "truncated": truncated,
                "note": "Candidate tags are selected before fetching around-stop samples.",
            },
        }
    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[int(row["tag_id"])].append(row)
    changes: list[dict[str, Any]] = []
    excluded_counts = _excluded_counts()
    keep_tag_id_set = set(keep_tag_ids or [])
    machine_speed_context: dict[str, Any] | None = None
    state_changes: list[dict[str, Any]] = []
    dependent_speed_changes: list[dict[str, Any]] = []
    alarm_changes: list[dict[str, Any]] = []
    counter_changes: list[dict[str, Any]] = []
    plc_changes: list[dict[str, Any]] = []
    for tag_rows in grouped.values():
        before = [row for row in tag_rows if row.get("created_at") and row["created_at"] < stop_time]
        after = [row for row in tag_rows if row.get("created_at") and row["created_at"] >= stop_time]
        if not before or not after:
            continue
        before_values = [float(row["value_num"]) for row in before if row.get("value_num") is not None]
        after_values = [float(row["value_num"]) for row in after if row.get("value_num") is not None]
        if not before_values or not after_values:
            continue
        before_avg = sum(before_values) / len(before_values)
        after_avg = sum(after_values) / len(after_values)
        last_before = before_values[-1]
        first_after = after_values[0]
        anchor = tag_rows[0]
        section_key = anchor.get("section_key") or parse_section_key(anchor.get("opc_path"))
        item = {
            "tag_id": int(anchor["tag_id"]),
            "display_name": display_name(anchor),
            "label": make_contextual_label(anchor),
            "section_key": section_key,
            "opc_path": anchor.get("opc_path"),
            "before_avg": round(before_avg, 6),
            "after_avg": round(after_avg, 6),
            "delta_avg": round(after_avg - before_avg, 6),
            "before_stop_movement": round(last_before - before_values[0], 6),
            "after_stop_effect": round(first_after - last_before, 6),
            "movement_score": round(abs(after_avg - before_avg) / max(abs(before_avg), 1.0), 6),
            "before_movement_score": round(abs(last_before - before_values[0]) / max(abs(before_avg), 1.0), 6),
            "after_effect_score": round(abs(first_after - last_before) / max(abs(before_avg), 1.0), 6),
        }
        exclusion_reason = _filter_process_row(
            item,
            apply_process_filters=apply_process_filters,
            explicit_alarm_context=explicit_alarm_context,
            explicit_counter_context=explicit_counter_context,
            explicit_plc_context=explicit_plc_context,
            keep_tag_ids=keep_tag_id_set,
        )
        if exclusion_reason:
            excluded_counts[exclusion_reason] += 1
            bucket = _context_bucket_for_filtered_row(
                item,
                explicit_alarm_context=explicit_alarm_context,
                explicit_counter_context=explicit_counter_context,
                explicit_plc_context=explicit_plc_context,
            )
            if bucket and (item["before_movement_score"] > 0 or item["after_effect_score"] > 0 or item["movement_score"] > 0):
                if bucket == "alarm_changes":
                    alarm_changes.append(_around_context_row(item))
                    excluded_counts["alarm_context"] += 1
                elif bucket == "counter_changes":
                    counter_changes.append(_around_context_row(item))
                    excluded_counts["counter_context"] += 1
                elif bucket == "plc_changes":
                    plc_changes.append(_around_context_row(item))
                    excluded_counts["plc_context"] += 1
            continue
        if _is_machine_speed_context_row(item, speed_tag_id):
            excluded_counts["machine_speed_context"] += 1
            machine_speed_context = {
                "tag_id": item.get("tag_id"),
                "opc_path": item.get("opc_path"),
                "section_key": item.get("section_key"),
                "label": item.get("label"),
                "before_avg": item.get("before_avg"),
                "after_avg": item.get("after_avg"),
                "before_stop_movement": item.get("before_stop_movement"),
                "after_stop_effect": item.get("after_stop_effect"),
                "before_movement_score": item.get("before_movement_score"),
                "after_effect_score": item.get("after_effect_score"),
            }
            continue
        if _is_state_context_row(item, explicit_state_context=explicit_state_context):
            if explicit_state_context:
                changes.append(item)
                continue
            if item["before_movement_score"] > 0 or item["after_effect_score"] > 0:
                state_changes.append(_around_context_row(item))
            excluded_counts["state_context"] += 1
            continue
        if _is_dependent_speed_row(item):
            if item["before_movement_score"] > 0 or item["after_effect_score"] > 0 or explicit_speed_context:
                dependent_speed_changes.append(_around_context_row(item))
            excluded_counts["dependent_speed_context"] += 1
            continue
        if item["before_stop_movement"] == 0 and item["after_stop_effect"] == 0 and item["delta_avg"] == 0:
            excluded_counts["zero_range"] += 1
            continue
        changes.append(item)
    before_rows, after_rows = _rank_visible_around_stop_rows(changes, limit)
    state_changes = dedupe_rows(
        [row for row in state_changes if explicit_state_context or float(row.get("before_stop_movement") or 0) != 0 or float(row.get("after_stop_effect") or 0) != 0 or float(row.get("delta_avg") or 0) != 0],
        _context_score,
    )
    dependent_speed_changes = dedupe_rows(
        [row for row in dependent_speed_changes if explicit_speed_context or float(row.get("before_stop_movement") or 0) != 0 or float(row.get("after_stop_effect") or 0) != 0 or float(row.get("delta_avg") or 0) != 0],
        _context_score,
    )
    alarm_changes = dedupe_rows(alarm_changes, _context_score)
    counter_changes = dedupe_rows(counter_changes, _context_score)
    plc_changes = dedupe_rows(plc_changes, _context_score)
    return {
        "stop_time": _as_iso(stop_time),
        "section": section,
        "before_minutes": before_minutes,
        "after_minutes": after_minutes,
        "before_stop_movement": before_rows,
        "after_stop_effect": after_rows,
        "excluded_counts": excluded_counts,
        "limits": {
            "candidate_tag_limit": max_candidate_tags,
            "candidate_tags_returned": len(candidate_rows),
            "truncated": truncated,
            "raw_rows_fetched": len(rows),
            "note": "Candidate tags are selected before fetching around-stop samples; truncated=true means the analysis is capped.",
        },
        "context": {
            **(context or {}),
            **({"machine_speed": machine_speed_context} if machine_speed_context else {}),
            **({"state_changes": state_changes[:10]} if state_changes else {}),
            **({"dependent_speed_changes": dependent_speed_changes[:10]} if dependent_speed_changes else {}),
            **({"alarm_changes": alarm_changes[:5]} if alarm_changes and (explicit_alarm_context or len(alarm_changes) <= 5) else {}),
            **({"counter_changes": counter_changes[:5]} if counter_changes and (explicit_counter_context or len(counter_changes) <= 5) else {}),
            **({"plc_changes": plc_changes[:5]} if plc_changes and (explicit_plc_context or len(plc_changes) <= 5) else {}),
        },
    }


def search_tags(query: str, limit: int = 20) -> list[dict[str, Any]]:
    rows = pool.fetch_all(
        """
        SELECT tag_id, opc_path, display_name, browse_name, node_id
        FROM opc_tags
        WHERE machine_id = %s
          AND is_active = 1
          AND (
            opc_path LIKE %s
            OR COALESCE(display_name, '') LIKE %s
            OR COALESCE(browse_name, '') LIKE %s
            OR COALESCE(node_id, '') LIKE %s
          )
        ORDER BY opc_path
        LIMIT %s
        """,
        (_machine_id(), f"%{query}%", f"%{query}%", f"%{query}%", f"%{query}%", max(limit, 1)),
    )
    results = []
    for row in rows_json_safe(rows):
        row["display_name"] = display_name(row)
        row["label"] = make_contextual_label(row)
        row["section_key"] = parse_section_key(row.get("opc_path"))
        results.append(row)
    return results


def list_sections() -> list[str]:
    rows = pool.fetch_all(
        """
        SELECT section_key
        FROM opc_machine_sections
        WHERE machine_id = %s
        ORDER BY sort_order, section_key
        """,
        (_machine_id(),),
    )
    return [str(row["section_key"]) for row in rows if row.get("section_key")]
