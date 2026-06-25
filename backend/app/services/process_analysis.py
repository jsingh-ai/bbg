from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from math import sqrt
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ..config import get_settings
from ..db import pool
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
SYSTEM_EXEMPT_TERMS = ("alarm", "counter", "plc", "io", "i/o", "system health")


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


def _is_explicit_system_request(message: str | None = None, resolved_system: str | None = None) -> bool:
    if resolved_system in {"plc/io/system", "alarm/system"}:
        return True
    normalized = (message or "").lower()
    return any(term in normalized for term in SYSTEM_EXEMPT_TERMS)


def _is_explicit_speed_request(message: str | None = None) -> bool:
    normalized = normalize_key(message or "")
    return any(
        term in normalized
        for term in (
            "speed",
            "stops",
            "stop",
            "downtime",
            "machinestate",
            "runningstate",
            "machineisrunning",
            "machineisstopped",
        )
    )


def _excluded_counts() -> dict[str, int]:
    return {"excluded_section": 0, "excluded_tag_term": 0, "zero_range": 0, "machine_speed_context": 0}


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


def _filter_process_row(
    row: dict[str, Any],
    *,
    apply_process_filters: bool,
    explicit_system_request: bool,
    keep_tag_ids: set[int] | None = None,
) -> str | None:
    if not apply_process_filters or explicit_system_request:
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
        return "excluded_section"
    if any(term and term in opc_path for term in settings.assistant_excluded_path_contains_list):
        return "excluded_section"
    if any(term and term in blob for term in settings.assistant_excluded_tag_term_list):
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
        "running_speed_threshold": settings.assistant_running_speed_threshold,
        "min_stop_minutes": settings.assistant_min_stop_minutes,
        "max_rows": settings.assistant_max_rows,
        "excluded_section_keys": settings.assistant_excluded_section_key_list,
        "excluded_path_contains": settings.assistant_excluded_path_contains_list,
        "excluded_tag_terms": settings.assistant_excluded_tag_term_list,
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
    explicit_system_request: bool = False,
    keep_tag_ids: list[int] | None = None,
    include_speed_in_ranking: bool = False,
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
            SUM(v.value_num * v.value_num) AS sum_sq_value
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
        ORDER BY sample_count DESC, t.tag_id
        LIMIT %s
        """,
        tuple([_machine_id(), time_range.start, time_range.end, *section_params, *allowed_params, settings.assistant_max_rows]),
    )
    ranked: list[dict[str, Any]] = []
    excluded_counts = _excluded_counts()
    keep_tag_id_set = set(keep_tag_ids or [])
    machine_speed_context: dict[str, Any] | None = None
    for row in rows:
        item = row_json_safe(row)
        min_value = float(row.get("min_value") or 0)
        max_value = float(row.get("max_value") or 0)
        avg_value = float(row.get("avg_value") or 0)
        sample_count = int(row.get("sample_count") or 0)
        item.update(
            {
                "label": display_name(row),
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
            explicit_system_request=explicit_system_request,
            keep_tag_ids=keep_tag_id_set,
        )
        if exclusion_reason:
            excluded_counts[exclusion_reason] += 1
            continue
        if speed_tag_id and int(item.get("tag_id") or 0) == speed_tag_id and not include_speed_in_ranking:
            excluded_counts["machine_speed_context"] += 1
            machine_speed_context = _speed_context_row(item)
            continue
        if float(item["range_value"]) == 0:
            excluded_counts["zero_range"] += 1
            continue
        ranked.append(item)
    ranked.sort(key=lambda row: (row["movement_score"], row["range_value"]), reverse=True)
    return {
        "range": _range_dict(time_range),
        "section": section,
        "parameters": ranked[: max(limit, 1)],
        "excluded_counts": excluded_counts,
        "context": {"machine_speed": machine_speed_context} if machine_speed_context else {},
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
    explicit_system_request: bool = False,
    keep_tag_ids: list[int] | None = None,
    context: dict[str, Any] | None = None,
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
          {section_sql}
          {allowed_sql}
        ORDER BY v.tag_id, v.created_at
        LIMIT %s
        """,
        tuple([_machine_id(), before_start, after_end, *section_params, *allowed_params, settings.assistant_max_rows]),
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
        }
    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[int(row["tag_id"])].append(row)
    changes: list[dict[str, Any]] = []
    excluded_counts = _excluded_counts()
    keep_tag_id_set = set(keep_tag_ids or [])
    machine_speed_context: dict[str, Any] | None = None
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
            "label": display_name(anchor),
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
            explicit_system_request=explicit_system_request,
            keep_tag_ids=keep_tag_id_set,
        )
        if exclusion_reason:
            excluded_counts[exclusion_reason] += 1
            continue
        if speed_tag_id and int(item.get("tag_id") or 0) == speed_tag_id:
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
        if item["before_stop_movement"] == 0 and item["after_stop_effect"] == 0 and item["delta_avg"] == 0:
            excluded_counts["zero_range"] += 1
            continue
        changes.append(item)
    deduped: dict[str, dict[str, Any]] = {}
    for item in changes:
        dedupe_key = "|".join(
            [
                str(item.get("section_key") or "").lower(),
                str(item.get("label") or "").lower(),
                str(item.get("opc_path") or "").lower(),
            ]
        )
        existing = deduped.get(dedupe_key)
        candidate_score = max(float(item.get("before_movement_score") or 0), float(item.get("after_effect_score") or 0))
        existing_score = max(float(existing.get("before_movement_score") or 0), float(existing.get("after_effect_score") or 0)) if existing else -1
        if existing is None or candidate_score > existing_score:
            deduped[dedupe_key] = item
    visible = list(deduped.values())
    return {
        "stop_time": _as_iso(stop_time),
        "section": section,
        "before_minutes": before_minutes,
        "after_minutes": after_minutes,
        "before_stop_movement": sorted(visible, key=lambda row: (row["before_movement_score"], abs(row["before_stop_movement"])), reverse=True)[: max(limit, 1)],
        "after_stop_effect": sorted(visible, key=lambda row: (row["after_effect_score"], abs(row["after_stop_effect"])), reverse=True)[: max(limit, 1)],
        "excluded_counts": excluded_counts,
        "context": {**(context or {}), **({"machine_speed": machine_speed_context} if machine_speed_context else {})},
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
        row["label"] = display_name(row)
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
