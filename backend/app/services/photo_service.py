from __future__ import annotations

from pathlib import Path

from ..config import get_settings
from .section_parser import normalize_key

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg"}


def _as_static_url(path: str | None) -> str | None:
    if not path:
        return None
    text = path.replace("\\", "/").strip()
    if not text:
        return None
    if text.startswith("http://") or text.startswith("https://"):
        return text
    if text.startswith("/static/"):
        return text
    if text.startswith("static/"):
        return "/" + text
    return "/static/" + text.lstrip("/")


def static_url(path: str | None) -> str | None:
    return _as_static_url(path)


def list_photo_files() -> list[dict[str, str]]:
    settings = get_settings()
    root = settings.photo_root
    files: list[dict[str, str]] = []
    for item in root.rglob("*"):
        if item.is_file() and item.suffix.lower() in SUPPORTED_EXTENSIONS:
            rel = item.relative_to(root).as_posix()
            static_path = f"{settings.static_photo_dir}/{rel}"
            files.append(
                {
                    "file_name": item.name,
                    "relative_path": static_path,
                    "url": _as_static_url(static_path) or "",
                    "normalized": normalize_key(item.stem),
                }
            )
    return sorted(files, key=lambda f: f["relative_path"].lower())


def find_section_photo(section_key: str | None) -> str | None:
    if not section_key:
        return None
    target = normalize_key(section_key)
    for file_info in list_photo_files():
        if file_info["normalized"] == target:
            return file_info["relative_path"]
    return None


def safe_photo_url(configured_path: str | None, fallback_section_key: str | None = None) -> str | None:
    if configured_path:
        return _as_static_url(configured_path)
    matched = find_section_photo(fallback_section_key)
    return _as_static_url(matched)
