from __future__ import annotations

import threading
from datetime import datetime, timedelta
from typing import Any

from fastapi import HTTPException

from ..config import get_settings
from ..db import pool
from .dashboard_service import get_active_recipe
from .value_format import row_json_safe, rows_json_safe


_evaluation_locks: dict[int, threading.Lock] = {}
_evaluation_locks_guard = threading.Lock()


def _evaluation_lock(machine_id: int) -> threading.Lock:
    with _evaluation_locks_guard:
        return _evaluation_locks.setdefault(machine_id, threading.Lock())


def _limit_state(value: float, min_value: float | None, max_value: float | None) -> tuple[bool, str | None]:
    if min_value is not None and value < float(min_value):
        return True, "LOW"
    if max_value is not None and value > float(max_value):
        return True, "HIGH"
    return False, None


def evaluate_alerts(machine_id: int) -> dict[str, Any]:
    lock = _evaluation_lock(machine_id)
    if not lock.acquire(blocking=False):
        return {
            "evaluated": False,
            "reason": "Alert evaluation is already running for this machine",
            "created": 0,
            "updated": 0,
            "returned": 0,
        }
    try:
        return _evaluate_alerts_locked(machine_id)
    finally:
        lock.release()


def _evaluate_alerts_locked(machine_id: int) -> dict[str, Any]:
    active = get_active_recipe(machine_id)
    recipe_id = active.get("recipe_id") if active else None
    if not recipe_id:
        return {"evaluated": False, "reason": "No active recipe selected", "created": 0, "updated": 0, "returned": 0}

    rows = pool.fetch_all(
        """
        SELECT
            lim.limit_id,
            lim.recipe_id,
            lim.machine_id,
            lim.tag_id,
            lim.section_key,
            lim.min_value,
            lim.max_value,
            t.display_name,
            t.browse_name,
            t.node_id,
            l.captured_at,
            l.is_good,
            l.error_text,
            l.value_kind,
            l.value_num
        FROM opc_recipe_limits lim
        JOIN opc_tags t ON t.tag_id = lim.tag_id
        LEFT JOIN opc_tag_latest l ON l.tag_id = lim.tag_id
        WHERE lim.machine_id = %s
          AND lim.recipe_id = %s
          AND lim.is_enabled = 1
          AND (lim.min_value IS NOT NULL OR lim.max_value IS NOT NULL)
        """,
        (machine_id, recipe_id),
    )

    open_alert_rows = pool.fetch_all(
        """
        SELECT alert_id, tag_id, is_currently_out_of_range
        FROM opc_alert_events
        WHERE machine_id = %s
          AND recipe_id = %s
          AND is_acknowledged = 0
        """,
        (machine_id, recipe_id),
    )
    existing_by_tag = {
        int(row["tag_id"]): {
            "alert_id": row["alert_id"],
            "is_currently_out_of_range": row.get("is_currently_out_of_range"),
        }
        for row in open_alert_rows
        if row.get("tag_id") is not None
    }

    created = 0
    updated = 0
    returned = 0
    skipped_stale_or_bad = 0
    active_limit_tag_ids = {int(row["tag_id"]) for row in rows if row.get("tag_id") is not None}
    stale_cutoff = datetime.now() - timedelta(seconds=max(get_settings().alert_max_data_age_seconds, 1))
    for row in rows:
        captured_at = row.get("captured_at")
        if (
            row.get("value_kind") != 1
            or row.get("value_num") is None
            or not bool(row.get("is_good"))
            or bool(row.get("error_text"))
            or captured_at is None
            or captured_at < stale_cutoff
        ):
            skipped_stale_or_bad += 1
            continue
        value = float(row["value_num"])
        min_value = row.get("min_value")
        max_value = row.get("max_value")
        out_of_range, alert_type = _limit_state(value, min_value, max_value)
        display_name = row.get("display_name") or row.get("browse_name") or row.get("node_id") or f"Tag {row['tag_id']}"
        tag_id = int(row["tag_id"])
        existing = existing_by_tag.get(tag_id)

        if out_of_range:
            if existing:
                pool.execute(
                    """
                    UPDATE opc_alert_events
                    SET alert_type = %s,
                        current_value = %s,
                        section_key = %s,
                        display_name = %s,
                        min_value = %s,
                        max_value = %s,
                        last_seen_at = NOW(3),
                        is_currently_out_of_range = 1,
                        returned_to_range_at = NULL
                    WHERE alert_id = %s
                    """,
                    (
                        alert_type,
                        value,
                        row.get("section_key"),
                        display_name,
                        min_value,
                        max_value,
                        existing["alert_id"],
                    ),
                )
                updated += 1
            else:
                pool.execute(
                    """
                    INSERT INTO opc_alert_events
                        (machine_id, recipe_id, tag_id, section_key, display_name, alert_type,
                         min_value, max_value, trigger_value, current_value, triggered_at,
                         last_seen_at, is_currently_out_of_range)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                            COALESCE(%s, NOW(3)), NOW(3), 1)
                    """,
                    (
                        machine_id,
                        recipe_id,
                        tag_id,
                        row.get("section_key"),
                        display_name,
                        alert_type,
                        min_value,
                        max_value,
                        value,
                        value,
                        row.get("captured_at"),
                    ),
                )
                created += 1
        else:
            if existing and int(existing.get("is_currently_out_of_range") or 0) == 1:
                pool.execute(
                    """
                    UPDATE opc_alert_events
                    SET current_value = %s,
                        last_seen_at = NOW(3),
                        is_currently_out_of_range = 0,
                        returned_to_range_at = COALESCE(returned_to_range_at, NOW(3))
                    WHERE alert_id = %s
                    """,
                    (value, existing["alert_id"]),
                )
                returned += 1
                existing["is_currently_out_of_range"] = 0
            elif existing:
                pool.execute(
                    """
                    UPDATE opc_alert_events
                    SET current_value = %s,
                        last_seen_at = NOW(3)
                    WHERE alert_id = %s
                    """,
                    (value, existing["alert_id"]),
                )
                updated += 1

    retired_alert_ids = [
        int(item["alert_id"])
        for tag_id, item in existing_by_tag.items()
        if tag_id not in active_limit_tag_ids
        and int(item.get("is_currently_out_of_range") or 0) == 1
    ]
    if retired_alert_ids:
        placeholders = ",".join(["%s"] * len(retired_alert_ids))
        returned += pool.execute(
            f"""
            UPDATE opc_alert_events
            SET is_currently_out_of_range = 0,
                returned_to_range_at = COALESCE(returned_to_range_at, NOW(3)),
                last_seen_at = NOW(3)
            WHERE alert_id IN ({placeholders})
            """,
            tuple(retired_alert_ids),
        )

    return {
        "evaluated": True,
        "recipe_id": recipe_id,
        "created": created,
        "updated": updated,
        "returned": returned,
        "skipped_stale_or_bad": skipped_stale_or_bad,
    }


def list_alerts(
    machine_id: int,
    active_only: bool = True,
    limit: int = 200,
    recipe_id: int | None = None,
) -> list[dict[str, Any]]:
    where = "a.machine_id = %s"
    params: list[Any] = [machine_id]
    if active_only:
        where += " AND a.is_acknowledged = 0"
    if recipe_id is not None:
        where += " AND a.recipe_id = %s"
        params.append(recipe_id)
    params.append(limit)
    rows = pool.fetch_all(
        f"""
        SELECT a.alert_id, a.machine_id, a.recipe_id, a.tag_id, a.section_key, a.display_name, t.node_id,
               a.alert_type, a.min_value, a.max_value, a.trigger_value, a.current_value,
               a.triggered_at, a.last_seen_at, a.returned_to_range_at,
               a.is_currently_out_of_range, a.is_acknowledged, a.acknowledged_at,
               a.acknowledged_by, a.acknowledge_note, a.created_at, a.updated_at
        FROM opc_alert_events a
        LEFT JOIN opc_tags t ON t.tag_id = a.tag_id AND t.machine_id = a.machine_id
        WHERE {where}
        ORDER BY a.is_acknowledged ASC, a.triggered_at DESC
        LIMIT %s
        """,
        tuple(params),
    )
    return rows_json_safe(rows)


def acknowledge_alert(alert_id: int, acknowledged_by: str | None, acknowledge_note: str | None) -> dict[str, Any]:
    changed = pool.execute(
        """
        UPDATE opc_alert_events
        SET is_acknowledged = 1,
            acknowledged_at = NOW(3),
            acknowledged_by = %s,
            acknowledge_note = %s
        WHERE alert_id = %s
        """,
        (acknowledged_by or "dashboard", acknowledge_note, alert_id),
    )
    if not changed:
        raise HTTPException(status_code=404, detail="Alert not found")
    row = pool.fetch_one("SELECT * FROM opc_alert_events WHERE alert_id = %s", (alert_id,))
    return row_json_safe(row)
