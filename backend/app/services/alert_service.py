from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from ..db import pool
from .dashboard_service import get_active_recipe
from .value_format import row_json_safe, rows_json_safe


def _limit_state(value: float, min_value: float | None, max_value: float | None) -> tuple[bool, str | None]:
    if min_value is not None and value < float(min_value):
        return True, "LOW"
    if max_value is not None and value > float(max_value):
        return True, "HIGH"
    return False, None


def evaluate_alerts(machine_id: int) -> dict[str, Any]:
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
            l.value_num
        FROM opc_recipe_limits lim
        JOIN opc_tags t ON t.tag_id = lim.tag_id
        JOIN opc_tag_latest l ON l.tag_id = lim.tag_id
        WHERE lim.machine_id = %s
          AND lim.recipe_id = %s
          AND lim.is_enabled = 1
          AND (lim.min_value IS NOT NULL OR lim.max_value IS NOT NULL)
          AND l.value_kind = 1
          AND l.value_num IS NOT NULL
        """,
        (machine_id, recipe_id),
    )

    created = 0
    updated = 0
    returned = 0
    for row in rows:
        value = float(row["value_num"])
        min_value = row.get("min_value")
        max_value = row.get("max_value")
        out_of_range, alert_type = _limit_state(value, min_value, max_value)
        display_name = row.get("display_name") or row.get("browse_name") or row.get("node_id") or f"Tag {row['tag_id']}"
        tag_id = int(row["tag_id"])

        existing = pool.fetch_one(
            """
            SELECT alert_id, is_currently_out_of_range
            FROM opc_alert_events
            WHERE machine_id = %s AND recipe_id = %s AND tag_id = %s AND is_acknowledged = 0
            ORDER BY triggered_at DESC
            LIMIT 1
            """,
            (machine_id, recipe_id, tag_id),
        )

        if out_of_range:
            if existing:
                pool.execute(
                    """
                    UPDATE opc_alert_events
                    SET alert_type = %s,
                        current_value = %s,
                        last_seen_at = NOW(3),
                        is_currently_out_of_range = 1,
                        returned_to_range_at = NULL
                    WHERE alert_id = %s
                    """,
                    (alert_type, value, existing["alert_id"]),
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

    return {"evaluated": True, "recipe_id": recipe_id, "created": created, "updated": updated, "returned": returned}


def list_alerts(machine_id: int, active_only: bool = True, limit: int = 200) -> list[dict[str, Any]]:
    where = "machine_id = %s"
    params: list[Any] = [machine_id]
    if active_only:
        where += " AND is_acknowledged = 0"
    params.append(limit)
    rows = pool.fetch_all(
        f"""
        SELECT alert_id, machine_id, recipe_id, tag_id, section_key, display_name, alert_type,
               min_value, max_value, trigger_value, current_value, triggered_at, last_seen_at,
               returned_to_range_at, is_currently_out_of_range, is_acknowledged,
               acknowledged_at, acknowledged_by, acknowledge_note, created_at, updated_at
        FROM opc_alert_events
        WHERE {where}
        ORDER BY is_acknowledged ASC, triggered_at DESC
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
