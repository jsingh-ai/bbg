from __future__ import annotations

from ..db import pool
from .photo_service import find_section_photo
from .section_parser import parse_section_key


def sync_sections(machine_id: int) -> int:
    rows = pool.fetch_all(
        """
        SELECT opc_path
        FROM opc_tags
        WHERE machine_id = %s AND is_active = 1
        ORDER BY opc_path
        """,
        (machine_id,),
    )
    seen: set[str] = set()
    params: list[tuple] = []
    sort_order = 0
    for row in rows:
        section_key = parse_section_key(row.get("opc_path"))
        if not section_key or section_key in seen:
            continue
        seen.add(section_key)
        photo_path = find_section_photo(section_key)
        params.append((machine_id, section_key, section_key, photo_path, sort_order))
        sort_order += 10

    return pool.execute_many(
        """
        INSERT INTO opc_machine_sections
            (machine_id, section_key, display_label, section_photo_path, sort_order)
        VALUES (%s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            display_label = COALESCE(display_label, VALUES(display_label)),
            section_photo_path = COALESCE(section_photo_path, VALUES(section_photo_path))
        """,
        params,
    )


def sync_tag_display_config(machine_id: int) -> int:
    rows = pool.fetch_all(
        """
        SELECT tag_id, opc_path
        FROM opc_tags
        WHERE machine_id = %s AND is_active = 1
        """,
        (machine_id,),
    )
    params: list[tuple] = []
    for row in rows:
        section_key = parse_section_key(row.get("opc_path"))
        if section_key:
            params.append((machine_id, int(row["tag_id"]), section_key))
    return pool.execute_many(
        """
        INSERT INTO opc_tag_display_config (machine_id, tag_id, section_key)
        VALUES (%s, %s, %s)
        ON DUPLICATE KEY UPDATE section_key = VALUES(section_key)
        """,
        params,
    )


def sync_machine(machine_id: int) -> dict[str, int]:
    return {
        "sections_changed": sync_sections(machine_id),
        "tag_configs_changed": sync_tag_display_config(machine_id),
    }
