from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any


def json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def row_json_safe(row: dict[str, Any]) -> dict[str, Any]:
    return {key: json_safe(value) for key, value in row.items()}


def rows_json_safe(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [row_json_safe(row) for row in rows]


def formatted_value(row: dict[str, Any]) -> str:
    kind = row.get("value_kind")
    if kind == 1 and row.get("value_num") is not None:
        value = row.get("value_num")
        try:
            num = float(value)
            if num.is_integer():
                return str(int(num))
            return f"{num:g}"
        except Exception:
            return str(value)
    if kind == 2 and row.get("value_bool") is not None:
        return "True" if bool(row.get("value_bool")) else "False"
    if row.get("value_text") is not None:
        return str(row.get("value_text"))
    if row.get("error_text"):
        return str(row.get("error_text"))
    return "--"
