from __future__ import annotations

import re
from typing import Iterable


def parse_section_key(opc_path: str | None) -> str | None:
    """Extract the machine section from an OPC path.

    Example:
        Global PV/020 - unwinder/state/state -> 020 - unwinder
        Global PV/290 - storage cylinder/para/offset -> 290 - storage cylinder
    """
    if not opc_path:
        return None
    parts = [part.strip() for part in opc_path.replace("\\", "/").split("/") if part.strip()]
    if not parts:
        return None

    if parts[0].lower() == "global pv" and len(parts) >= 2:
        return parts[1]
    if len(parts) >= 2 and parts[0].lower().startswith("global"):
        return parts[1]
    return parts[0]


def parse_section_keys(paths: Iterable[str | None]) -> list[str]:
    seen: set[str] = set()
    sections: list[str] = []
    for path in paths:
        section = parse_section_key(path)
        if section and section not in seen:
            seen.add(section)
            sections.append(section)
    return sections


def normalize_key(value: str | None) -> str:
    if not value:
        return ""
    value = value.lower().strip()
    value = re.sub(r"\.[a-z0-9]{2,5}$", "", value)
    value = re.sub(r"[^a-z0-9]+", "", value)
    return value


def extract_sort_number(value: str | None) -> int | None:
    if not value:
        return None
    match = re.match(r"^\s*(\d+)", value)
    if not match:
        return None
    return int(match.group(1))


def is_numeric_data_type(data_type: str | None) -> bool:
    if not data_type:
        return False
    text = data_type.lower()
    numeric_terms = (
        "int",
        "uint",
        "float",
        "double",
        "decimal",
        "number",
        "sbyte",
        "byte",
        "short",
        "long",
    )
    return any(term in text for term in numeric_terms) and "string" not in text and "bool" not in text


def display_name(row: dict) -> str:
    return row.get("display_name") or row.get("browse_name") or row.get("node_id") or f"Tag {row.get('tag_id', '')}".strip()
