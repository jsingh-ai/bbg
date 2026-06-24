from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from ..db import pool
from .section_parser import display_name, is_numeric_data_type
from .sync_service import sync_machine
from .value_format import formatted_value, row_json_safe, rows_json_safe


def list_recipes(machine_id: int) -> list[dict[str, Any]]:
    rows = pool.fetch_all(
        """
        SELECT recipe_id, machine_id, recipe_name, recipe_code, description, is_active, created_at, updated_at
        FROM opc_recipes
        WHERE machine_id = %s
        ORDER BY is_active DESC, recipe_name
        """,
        (machine_id,),
    )
    return rows_json_safe(rows)


def get_recipe(recipe_id: int) -> dict[str, Any]:
    row = pool.fetch_one(
        """
        SELECT recipe_id, machine_id, recipe_name, recipe_code, description, is_active, created_at, updated_at
        FROM opc_recipes
        WHERE recipe_id = %s
        """,
        (recipe_id,),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Recipe not found")
    return row_json_safe(row)


def create_recipe(machine_id: int, data: dict[str, Any]) -> dict[str, Any]:
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO opc_recipes (machine_id, recipe_name, recipe_code, description)
                VALUES (%s, %s, %s, %s)
                """,
                (machine_id, data.get("recipe_name"), data.get("recipe_code"), data.get("description")),
            )
            recipe_id = int(cur.lastrowid)
    return get_recipe(recipe_id)


def update_recipe(recipe_id: int, data: dict[str, Any]) -> dict[str, Any]:
    allowed = {"recipe_name", "recipe_code", "description", "is_active"}
    sets: list[str] = []
    params: list[Any] = []
    for key, value in data.items():
        if key in allowed:
            sets.append(f"{key} = %s")
            params.append(value)
    if sets:
        params.append(recipe_id)
        pool.execute(f"UPDATE opc_recipes SET {', '.join(sets)} WHERE recipe_id = %s", tuple(params))
    return get_recipe(recipe_id)


def get_recipe_limits_for_section(recipe_id: int, section_key: str) -> dict[str, Any]:
    recipe = get_recipe(recipe_id)
    machine_id = int(recipe["machine_id"])
    sync_machine(machine_id)
    rows = pool.fetch_all(
        """
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
            l.value_kind,
            l.value_num,
            l.value_bool,
            l.value_text,
            l.error_text,
            lim.limit_id,
            lim.min_value,
            lim.max_value,
            COALESCE(lim.is_enabled, 0) AS is_limit_enabled
        FROM opc_tag_display_config cfg
        JOIN opc_tags t ON t.tag_id = cfg.tag_id
        LEFT JOIN opc_tag_latest l ON l.tag_id = t.tag_id
        LEFT JOIN opc_recipe_limits lim ON lim.recipe_id = %s AND lim.tag_id = t.tag_id
        WHERE cfg.machine_id = %s
          AND cfg.section_key = %s
          AND t.is_active = 1
        ORDER BY cfg.is_visible DESC, cfg.sort_order, COALESCE(t.display_name, t.browse_name, t.node_id)
        """,
        (recipe_id, machine_id, section_key),
    )
    items: list[dict[str, Any]] = []
    for row in rows:
        is_numeric = bool(row.get("value_kind") == 1 or is_numeric_data_type(row.get("data_type")))
        if not is_numeric:
            continue
        item = row_json_safe(row)
        item["label"] = display_name(row)
        item["current_value"] = formatted_value(row)
        item["is_numeric"] = is_numeric
        items.append(item)
    return {"recipe": recipe, "section_key": section_key, "limits": items}


def bulk_update_limits(recipe_id: int, limits: list[dict[str, Any]]) -> dict[str, Any]:
    recipe = get_recipe(recipe_id)
    machine_id = int(recipe["machine_id"])
    if not limits:
        return {"updated": 0}

    tag_ids = [int(item["tag_id"]) for item in limits]
    placeholders = ",".join(["%s"] * len(tag_ids))
    section_rows = pool.fetch_all(
        f"""
        SELECT tag_id, section_key
        FROM opc_tag_display_config
        WHERE machine_id = %s AND tag_id IN ({placeholders})
        """,
        tuple([machine_id, *tag_ids]),
    )
    section_by_tag = {int(row["tag_id"]): row["section_key"] for row in section_rows}

    params: list[tuple] = []
    for item in limits:
        tag_id = int(item["tag_id"])
        section_key = section_by_tag.get(tag_id)
        if not section_key:
            continue
        params.append(
            (
                recipe_id,
                machine_id,
                tag_id,
                section_key,
                item.get("min_value"),
                item.get("max_value"),
                1 if item.get("is_enabled", True) else 0,
            )
        )
    changed = pool.execute_many(
        """
        INSERT INTO opc_recipe_limits
            (recipe_id, machine_id, tag_id, section_key, min_value, max_value, is_enabled)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            section_key = VALUES(section_key),
            min_value = VALUES(min_value),
            max_value = VALUES(max_value),
            is_enabled = VALUES(is_enabled)
        """,
        params,
    )
    return {"updated": changed}
