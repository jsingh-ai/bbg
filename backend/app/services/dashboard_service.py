from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

from fastapi import HTTPException

from ..config import get_settings
from ..db import pool
from .photo_service import safe_photo_url, static_url
from .section_parser import display_name, is_numeric_data_type, normalize_key
from .sync_service import sync_machine
from .value_format import formatted_value, row_json_safe, rows_json_safe

SPEED_PATH = "Global PV/200 - format/state/machine speed"
PRODUCTION_PATHS = {
    "shift": {
        "good": "Global PV/info/state/shift: good",
        "bad": "Global PV/info/state/shift: bad",
    },
    "job": {
        "good": "Global PV/info/state/job: good",
        "bad": "Global PV/info/state/job: bad",
    },
    "total": {
        "good": "Global PV/info/state/total: good",
        "bad": "Global PV/info/state/total: bad",
    },
}

UPTIME_WINDOW_MINUTES = 24 * 60


def _latest_numeric_history_by_tag(tag_ids: list[int]) -> dict[int, dict[str, Any]]:
    if not tag_ids:
        return {}
    placeholders = ",".join(["%s"] * len(tag_ids))
    rows = pool.fetch_all(
        f"""
        SELECT v.tag_id, v.created_at, v.value_num
        FROM opc_tag_values v
        JOIN (
            SELECT tag_id, MAX(created_at) AS latest_created_at
            FROM opc_tag_values
            WHERE tag_id IN ({placeholders})
              AND value_kind = 1
              AND value_num IS NOT NULL
            GROUP BY tag_id
        ) latest
          ON latest.tag_id = v.tag_id
         AND latest.latest_created_at = v.created_at
        WHERE v.tag_id IN ({placeholders})
          AND v.value_kind = 1
          AND v.value_num IS NOT NULL
        """,
        tuple([*tag_ids, *tag_ids]),
    )
    latest_by_tag: dict[int, dict[str, Any]] = {}
    for row in rows:
        tag_id = int(row["tag_id"])
        current = latest_by_tag.get(tag_id)
        created_at = row.get("created_at")
        if current is None or (created_at and current.get("created_at") and created_at > current["created_at"]):
            latest_by_tag[tag_id] = row
    return latest_by_tag


def _should_use_history_fallback(row: dict[str, Any]) -> bool:
    if row.get("value_num") is not None:
        return False
    if row.get("value_bool") is not None:
        return False
    if row.get("value_text") not in (None, ""):
        return False
    error_text = row.get("error_text")
    return bool(error_text)


def _apply_numeric_history_fallback(item: dict[str, Any], history_row: dict[str, Any] | None) -> None:
    if not history_row:
        return
    item["value_kind"] = 1
    item["value_num"] = history_row.get("value_num")
    item["error_text"] = None
    item["current_value"] = formatted_value(item)


def get_machine(machine_id: int) -> dict[str, Any]:
    row = pool.fetch_one(
        """
        SELECT machine_id, machine_name, endpoint_url, main_image_path, is_active, created_at, updated_at
        FROM opc_machines
        WHERE machine_id = %s
        """,
        (machine_id,),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Machine not found")
    row = row_json_safe(row)
    row["main_image_url"] = static_url(row.get("main_image_path"))
    return row


def get_dashboard_summary(machine_id: int, minutes: int | None = None) -> dict[str, Any]:
    history_minutes = minutes or 60
    start = datetime.now() - timedelta(minutes=history_minutes)
    required_paths = [SPEED_PATH]
    for mode_paths in PRODUCTION_PATHS.values():
        required_paths.extend(mode_paths.values())
    required_paths = list(dict.fromkeys(required_paths))
    path_placeholders = ",".join(["%s"] * len(required_paths))

    tag_rows = pool.fetch_all(
        f"""
        SELECT
            t.tag_id,
            t.opc_path,
            t.display_name,
            t.browse_name,
            t.node_id,
            l.value_kind,
            l.value_num,
            l.value_bool,
            l.value_text,
            l.error_text
        FROM opc_tags t
        LEFT JOIN opc_tag_latest l ON l.tag_id = t.tag_id
        WHERE t.machine_id = %s
          AND t.is_active = 1
          AND t.opc_path IN ({path_placeholders})
        """,
        tuple([machine_id, *required_paths]),
    )
    tag_by_path = {normalize_key(str(row.get("opc_path") or "")): row for row in tag_rows}
    tag_ids = [int(row["tag_id"]) for row in tag_rows if row.get("tag_id") is not None]
    history_by_tag: dict[int, list[list[Any]]] = defaultdict(list)
    latest_numeric_history = _latest_numeric_history_by_tag(tag_ids)

    if tag_ids:
        history_placeholders = ",".join(["%s"] * len(tag_ids))
        history_rows = pool.fetch_all(
            f"""
            SELECT created_at, tag_id, value_num
            FROM opc_tag_values
            WHERE tag_id IN ({history_placeholders})
              AND created_at >= %s
              AND value_kind = 1
              AND value_num IS NOT NULL
            ORDER BY created_at, tag_id
            """,
            tuple([*tag_ids, start]),
        )
        for row in history_rows:
            captured = row.get("created_at")
            timestamp = captured.isoformat() if hasattr(captured, "isoformat") else str(captured)
            history_by_tag[int(row["tag_id"])].append([timestamp, row.get("value_num")])

    def metric_for_path(opc_path: str) -> dict[str, Any]:
        row = tag_by_path.get(normalize_key(opc_path))
        if not row:
            return {"opc_path": opc_path, "label": opc_path, "current_value": "--", "value_num": None, "points": []}
        item = row_json_safe(row)
        item["label"] = display_name(row)
        item["current_value"] = formatted_value(row)
        if _should_use_history_fallback(row):
            _apply_numeric_history_fallback(item, latest_numeric_history.get(int(row["tag_id"])))
        item["points"] = history_by_tag.get(int(row["tag_id"]), [])
        return item

    def uptime_for_speed() -> dict[str, Any]:
        speed_metric = metric_for_path(SPEED_PATH)
        speed_tag_id = speed_metric.get("tag_id")
        if speed_tag_id is None:
            return {
                "window_minutes": UPTIME_WINDOW_MINUTES,
                "online_minutes": 0,
                "offline_minutes": 0,
                "down_minutes": UPTIME_WINDOW_MINUTES,
                "uptime_pct": 0.0,
            }

        uptime_start = datetime.now() - timedelta(minutes=UPTIME_WINDOW_MINUTES)
        uptime_rows = pool.fetch_all(
            """
            SELECT created_at, value_num
            FROM opc_tag_values
            WHERE tag_id = %s
              AND created_at >= %s
              AND value_kind = 1
              AND value_num IS NOT NULL
            ORDER BY created_at
            """,
            (speed_tag_id, uptime_start),
        )

        latest_by_minute: dict[str, float] = {}
        for row in uptime_rows:
            created_at = row.get("created_at")
            value_num = row.get("value_num")
            if created_at is None or value_num is None:
                continue
            minute_key = created_at.strftime("%Y-%m-%d %H:%M")
            latest_by_minute[minute_key] = float(value_num)

        online_minutes = sum(1 for value in latest_by_minute.values() if value != 0)
        offline_minutes = sum(1 for value in latest_by_minute.values() if value == 0)
        down_minutes = max(0, UPTIME_WINDOW_MINUTES - len(latest_by_minute))
        uptime_pct = round((online_minutes / UPTIME_WINDOW_MINUTES) * 100, 1) if UPTIME_WINDOW_MINUTES else 0.0

        return {
            "window_minutes": UPTIME_WINDOW_MINUTES,
            "online_minutes": online_minutes,
            "offline_minutes": offline_minutes,
            "down_minutes": down_minutes,
            "uptime_pct": uptime_pct,
        }

    return {
        "speed": metric_for_path(SPEED_PATH),
        "production": {
            mode: {
                kind: metric_for_path(PRODUCTION_PATHS[mode][kind])
                for kind in ("good", "bad")
            }
            for mode in ("shift", "job", "total")
        },
        "uptime": uptime_for_speed(),
    }


def list_machines() -> list[dict[str, Any]]:
    rows = pool.fetch_all(
        """
        SELECT machine_id, machine_name, endpoint_url, main_image_path, is_active
        FROM opc_machines
        WHERE is_active = 1
        ORDER BY machine_name, machine_id
        """
    )
    result = rows_json_safe(rows)
    for row in result:
        row["main_image_url"] = static_url(row.get("main_image_path"))
    return result


def get_active_recipe(machine_id: int) -> dict[str, Any] | None:
    row = pool.fetch_one(
        """
        SELECT ar.machine_id, ar.recipe_id, ar.selection_mode, ar.selected_at, ar.updated_at,
               r.recipe_name, r.recipe_code, r.description, r.is_active
        FROM opc_machine_active_recipe ar
        LEFT JOIN opc_recipes r ON r.recipe_id = ar.recipe_id
        WHERE ar.machine_id = %s
        """,
        (machine_id,),
    )
    return row_json_safe(row) if row else None


def set_active_recipe(machine_id: int, recipe_id: int | None, selection_mode: str) -> dict[str, Any] | None:
    if recipe_id is not None:
        recipe = pool.fetch_one(
            "SELECT recipe_id FROM opc_recipes WHERE machine_id = %s AND recipe_id = %s AND is_active = 1",
            (machine_id, recipe_id),
        )
        if not recipe:
            raise HTTPException(status_code=404, detail="Recipe not found for machine")
    pool.execute(
        """
        INSERT INTO opc_machine_active_recipe (machine_id, recipe_id, selection_mode, selected_at)
        VALUES (%s, %s, %s, NOW(3))
        ON DUPLICATE KEY UPDATE
            recipe_id = VALUES(recipe_id),
            selection_mode = VALUES(selection_mode),
            selected_at = NOW(3),
            updated_at = CURRENT_TIMESTAMP
        """,
        (machine_id, recipe_id, selection_mode),
    )
    return get_active_recipe(machine_id)


def get_sections(machine_id: int, include_hidden: bool = True, sync: bool = False) -> list[dict[str, Any]]:
    if sync:
        sync_machine(machine_id)
    active_recipe = get_active_recipe(machine_id)
    recipe_id = active_recipe.get("recipe_id") if active_recipe else None

    params: list[Any] = [machine_id]
    where = "s.machine_id = %s"
    if not include_hidden:
        where += " AND s.is_visible = 1"

    rows = pool.fetch_all(
        f"""
        SELECT
            s.section_id,
            s.machine_id,
            s.section_key,
            COALESCE(NULLIF(s.display_label, ''), s.section_key) AS display_label,
            s.section_photo_path,
            s.is_visible,
            s.sort_order,
            s.box_x_pct,
            s.box_y_pct,
            s.box_w_pct,
            s.box_h_pct,
            COUNT(DISTINCT cfg.tag_id) AS tag_count,
            SUM(CASE WHEN cfg.is_visible = 1 THEN 1 ELSE 0 END) AS visible_tag_count
        FROM opc_machine_sections s
        LEFT JOIN opc_tag_display_config cfg
            ON cfg.machine_id = s.machine_id AND cfg.section_key = s.section_key
        WHERE {where}
        GROUP BY s.section_id, s.machine_id, s.section_key, s.display_label, s.section_photo_path,
                 s.is_visible, s.sort_order, s.box_x_pct, s.box_y_pct, s.box_w_pct, s.box_h_pct
        ORDER BY s.sort_order, s.section_key
        """,
        tuple(params),
    )

    limits_by_section: dict[str, int] = {}
    if recipe_id:
        limit_rows = pool.fetch_all(
            """
            SELECT section_key, COUNT(*) AS limit_count
            FROM opc_recipe_limits
            WHERE recipe_id = %s AND machine_id = %s AND is_enabled = 1
              AND (min_value IS NOT NULL OR max_value IS NOT NULL)
            GROUP BY section_key
            """,
            (recipe_id, machine_id),
        )
        limits_by_section = {str(row["section_key"]): int(row["limit_count"] or 0) for row in limit_rows}

    alert_rows = pool.fetch_all(
        """
        SELECT section_key,
               SUM(CASE WHEN is_currently_out_of_range = 1 THEN 1 ELSE 0 END) AS current_alert_count,
               COUNT(*) AS open_alert_count
        FROM opc_alert_events
        WHERE machine_id = %s AND is_acknowledged = 0
        GROUP BY section_key
        """,
        (machine_id,),
    )
    alerts_by_section = {
        str(row["section_key"]): {
            "current_alert_count": int(row["current_alert_count"] or 0),
            "open_alert_count": int(row["open_alert_count"] or 0),
        }
        for row in alert_rows
    }

    result: list[dict[str, Any]] = []
    for row in rows:
        section_key = str(row["section_key"])
        alert_counts = alerts_by_section.get(section_key, {"current_alert_count": 0, "open_alert_count": 0})
        limit_count = limits_by_section.get(section_key, 0)
        if alert_counts["current_alert_count"] > 0:
            status = "red"
        elif alert_counts["open_alert_count"] > 0:
            status = "orange"
        elif recipe_id and limit_count > 0:
            status = "green"
        else:
            status = "neutral"

        item = row_json_safe(row)
        item["section_photo_url"] = safe_photo_url(row.get("section_photo_path"), section_key)
        item["has_box"] = all(row.get(k) is not None for k in ("box_x_pct", "box_y_pct", "box_w_pct", "box_h_pct"))
        item["limit_count"] = limit_count
        item["open_alert_count"] = alert_counts["open_alert_count"]
        item["current_alert_count"] = alert_counts["current_alert_count"]
        item["status"] = status
        result.append(item)
    return result


def update_section(section_id: int, data: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "display_label",
        "section_photo_path",
        "is_visible",
        "sort_order",
        "box_x_pct",
        "box_y_pct",
        "box_w_pct",
        "box_h_pct",
    }
    current_row = pool.fetch_one("SELECT * FROM opc_machine_sections WHERE section_id = %s", (section_id,))
    if not current_row:
        raise HTTPException(status_code=404, detail="Section not found")

    if "display_label" in data and data["display_label"] is not None:
        label = str(data["display_label"]).strip()
        if label:
            duplicate = pool.fetch_one(
                """
                SELECT section_id
                FROM opc_machine_sections
                WHERE machine_id = %s
                  AND section_id <> %s
                  AND COALESCE(NULLIF(display_label, ''), section_key) = %s
                LIMIT 1
                """,
                (current_row["machine_id"], section_id, label),
            )
            if duplicate:
                raise HTTPException(status_code=400, detail=f'Display label "{label}" is already used by another section')
            data["display_label"] = label

    sets: list[str] = []
    params: list[Any] = []
    for key, value in data.items():
        if key in allowed:
            sets.append(f"{key} = %s")
            params.append(value)
    if not sets:
        return row_json_safe(current_row)
    params.append(section_id)
    changed = pool.execute(f"UPDATE opc_machine_sections SET {', '.join(sets)} WHERE section_id = %s", tuple(params))
    row = pool.fetch_one("SELECT * FROM opc_machine_sections WHERE section_id = %s", (section_id,))
    if not row:
        raise HTTPException(status_code=404, detail="Section not found")
    item = row_json_safe(row)
    item["section_photo_url"] = safe_photo_url(row.get("section_photo_path"), row.get("section_key"))
    item["changed"] = changed
    return item


def get_section_live_values(machine_id: int, section_key: str, include_hidden: bool = True) -> dict[str, Any]:
    hidden_filter = "" if include_hidden else "AND cfg.is_visible = 1"
    rows = pool.fetch_all(
        f"""
        SELECT
            t.tag_id,
            t.opc_path,
            t.node_id,
            t.display_name,
            t.browse_name,
            t.data_type,
            cfg.section_key,
            cfg.is_visible,
            cfg.show_in_history_default,
            cfg.sort_order,
            l.captured_at,
            l.is_good,
            l.value_kind,
            l.value_num,
            l.value_bool,
            l.value_text,
            l.error_text,
            l.updated_at
        FROM opc_tag_display_config cfg
        JOIN opc_tags t ON t.tag_id = cfg.tag_id
        LEFT JOIN opc_tag_latest l ON l.tag_id = t.tag_id
        WHERE cfg.machine_id = %s
          AND cfg.section_key = %s
          AND t.is_active = 1
          {hidden_filter}
        ORDER BY cfg.is_visible DESC, cfg.sort_order, COALESCE(t.display_name, t.browse_name, t.node_id)
        """,
        (machine_id, section_key),
    )
    latest_numeric_history = _latest_numeric_history_by_tag(
        [int(row["tag_id"]) for row in rows if row.get("tag_id") is not None]
    )
    items: list[dict[str, Any]] = []
    for row in rows:
        item = row_json_safe(row)
        item["label"] = display_name(row)
        item["current_value"] = formatted_value(row)
        item["is_numeric"] = bool(row.get("value_kind") == 1 or is_numeric_data_type(row.get("data_type")))
        if _should_use_history_fallback(row):
            _apply_numeric_history_fallback(item, latest_numeric_history.get(int(row["tag_id"])))
        items.append(item)

    section = pool.fetch_one(
        """
        SELECT section_id, section_key, COALESCE(NULLIF(display_label, ''), section_key) AS display_label,
               section_photo_path, is_visible
        FROM opc_machine_sections
        WHERE machine_id = %s AND section_key = %s
        """,
        (machine_id, section_key),
    )
    section_info = row_json_safe(section) if section else {"section_key": section_key, "display_label": section_key}
    section_info["section_photo_url"] = safe_photo_url(section_info.get("section_photo_path"), section_key)
    return {"section": section_info, "values": items}


def update_tag_config(machine_id: int, tag_id: int, data: dict[str, Any]) -> dict[str, Any]:
    allowed = {"is_visible", "show_in_history_default", "sort_order"}
    sets: list[str] = []
    params: list[Any] = []
    for key, value in data.items():
        if key in allowed:
            sets.append(f"{key} = %s")
            params.append(value)
    if not sets:
        row = pool.fetch_one("SELECT * FROM opc_tag_display_config WHERE machine_id = %s AND tag_id = %s", (machine_id, tag_id))
        if not row:
            raise HTTPException(status_code=404, detail="Tag config not found")
        return row_json_safe(row)
    params.extend([machine_id, tag_id])
    pool.execute(
        f"UPDATE opc_tag_display_config SET {', '.join(sets)} WHERE machine_id = %s AND tag_id = %s",
        tuple(params),
    )
    row = pool.fetch_one("SELECT * FROM opc_tag_display_config WHERE machine_id = %s AND tag_id = %s", (machine_id, tag_id))
    if not row:
        raise HTTPException(status_code=404, detail="Tag config not found")
    return row_json_safe(row)


def get_history(machine_id: int, section_key: str | None, start: datetime, end: datetime, tag_ids: list[int]) -> dict[str, Any]:
    if not tag_ids:
        return {"series": []}
    if end <= start:
        raise HTTPException(status_code=400, detail="End time must be after start time")
    if len(tag_ids) > 25:
        raise HTTPException(status_code=400, detail="Select 25 or fewer tags for one chart")

    placeholders = ",".join(["%s"] * len(tag_ids))
    params: list[Any] = [machine_id]
    section_filter = ""
    if section_key:
        section_filter = "AND cfg.section_key = %s"
        params.append(section_key)
    params.extend([start, end, *tag_ids])
    rows = pool.fetch_all(
        f"""
        SELECT
            v.created_at,
            v.tag_id,
            v.value_num,
            cfg.section_key,
            t.display_name,
            t.browse_name,
            t.node_id
        FROM opc_tag_values v
        JOIN opc_tags t ON t.tag_id = v.tag_id
        JOIN opc_tag_display_config cfg ON cfg.tag_id = t.tag_id AND cfg.machine_id = t.machine_id
        WHERE t.machine_id = %s
          {section_filter}
          AND v.created_at >= %s
          AND v.created_at <= %s
          AND v.tag_id IN ({placeholders})
          AND v.value_kind = 1
          AND v.value_num IS NOT NULL
        ORDER BY v.created_at, v.tag_id
        """,
        tuple(params),
    )
    labels: dict[int, str] = {}
    sections: dict[int, str] = {}
    points_by_tag: dict[int, list[list[Any]]] = defaultdict(list)
    for row in rows:
        tag_id = int(row["tag_id"])
        labels[tag_id] = display_name(row)
        sections[tag_id] = str(row.get("section_key") or "")
        captured = row.get("created_at")
        timestamp = captured.isoformat() if hasattr(captured, "isoformat") else str(captured)
        points_by_tag[tag_id].append([timestamp, row.get("value_num")])

    series = [
        {
            "tag_id": tag_id,
            "label": labels.get(tag_id, str(tag_id)),
            "section_key": sections.get(tag_id, ""),
            "points": points_by_tag.get(tag_id, []),
        }
        for tag_id in tag_ids
    ]
    return {"series": series, "start": start.isoformat(), "end": end.isoformat()}


def default_history_range() -> tuple[datetime, datetime]:
    settings = get_settings()
    end = datetime.now()
    start = end - timedelta(minutes=settings.default_history_minutes)
    return start, end
