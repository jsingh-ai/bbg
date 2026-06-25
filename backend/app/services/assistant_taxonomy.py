from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


STOPWORDS = {
    "in",
    "on",
    "at",
    "the",
    "a",
    "an",
    "and",
    "or",
    "of",
    "for",
    "to",
    "today",
    "yesterday",
    "last",
    "hour",
    "hours",
    "day",
    "days",
    "week",
    "changed",
    "change",
    "most",
    "happened",
    "what",
    "when",
    "around",
    "before",
    "after",
    "stop",
    "stops",
    "machine",
}


@dataclass(frozen=True)
class SystemRule:
    key: str
    aliases: tuple[str, ...]
    section_contains: tuple[str, ...]


SYSTEM_RULES: tuple[SystemRule, ...] = (
    SystemRule("unwinder", ("unwinder", "winder"), ("unwinder",)),
    SystemRule("dancer", ("dancer", "dance"), ("dancer",)),
    SystemRule("storage cylinder", ("storage cylinder", "storage"), ("storage cylinder",)),
    SystemRule("format", ("format", "machine speed"), ("format",)),
    SystemRule("bottom sealing", ("bottom sealing", "sealing"), ("bottom sealing",)),
    SystemRule("main draw", ("main draw", "draw"), ("main draw",)),
    SystemRule("base frame", ("base frame",), ("base frame",)),
    SystemRule("general air", ("air pressure", "air flow", "air"), ("general",)),
    SystemRule("alarm/system", ("active alarms", "max severity", "warnings", "warning", "faults", "fault", "alarms", "alarm"), ("alarm system",)),
    SystemRule("plc/io/system", ("plc temperature", "system health", "i/o", "plc", "io"), ("i",)),
)


EXPLICIT_SHORT_ALIASES = {"io", "i/o"}


def _normalize_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lower())


def _tokenize(value: str | None) -> list[str]:
    return re.findall(r"[a-z0-9/]+", (value or "").lower())


def _contains_alias(message: str, alias: str) -> bool:
    if "/" in alias:
        return alias in message
    return re.search(rf"\b{re.escape(alias)}\b", message) is not None


def resolve_assistant_taxonomy(message: str) -> dict[str, Any]:
    message_lower = _normalize_text(message)
    query_terms: list[str] = []
    for token in _tokenize(message_lower):
        if token in STOPWORDS:
            continue
        if len(token) < 3 and token not in EXPLICIT_SHORT_ALIASES:
            continue
        query_terms.append(token)

    matched_rule: SystemRule | None = None
    matched_alias: str | None = None
    for rule in SYSTEM_RULES:
        for alias in sorted(rule.aliases, key=len, reverse=True):
            if _contains_alias(message_lower, alias):
                matched_rule = rule
                matched_alias = alias
                break
        if matched_rule:
            break

    section_terms = list(matched_rule.section_contains) if matched_rule else []
    return {
        "query_terms": query_terms,
        "resolved_system": matched_rule.key if matched_rule else None,
        "section_terms": section_terms,
        "matched_alias": matched_alias,
    }
