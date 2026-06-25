from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = Path(__file__).resolve().parent
STATIC_ROOT = APP_ROOT / "static"
FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"


class Settings(BaseSettings):
    app_name: str = "BBG OPC Dashboard"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    environment: str = "production"

    db_host: str = "127.0.0.1"
    db_port: int = 3306
    db_name: str = "opc_collector"
    db_user: str = "opc_user"
    db_password: str = "change_me"
    db_pool_size: int = 8
    db_connect_timeout: int = 8

    default_machine_id: int = 1
    static_photo_dir: str = "opc_photos"
    live_refresh_seconds: int = 60
    default_history_minutes: int = 60
    openai_api_key: str = ""
    openai_model: str = "gpt-4.1-mini"
    assistant_enabled: bool = False
    assistant_max_rows: int = 5000
    assistant_default_timezone: str = "America/Chicago"
    assistant_speed_tag_path: str = "Global PV/200 - format/state/machine speed"
    assistant_good_bags_tag_path: str = "Global PV/info/state/shift: good"
    assistant_bad_bags_tag_path: str = "Global PV/info/state/shift: bad"
    assistant_running_speed_threshold: float = 0
    assistant_min_stop_minutes: int = 1
    assistant_excluded_section_keys: str = "i,alarm system"
    assistant_excluded_path_contains: str = "/i/o/,alarm system"
    assistant_excluded_tag_terms: str = "counter,count,number of,good,bad,total,shift,job,active alarms,max severity,storageWear"

    cors_origins: str = Field(default="http://localhost:5173,http://127.0.0.1:5173")

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def photo_root(self) -> Path:
        path = STATIC_ROOT / self.static_photo_dir
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def assistant_llm_enabled(self) -> bool:
        return bool(self.assistant_enabled and self.openai_api_key.strip())

    @property
    def assistant_excluded_section_key_list(self) -> list[str]:
        return [item.strip().lower() for item in self.assistant_excluded_section_keys.split(",") if item.strip()]

    @property
    def assistant_excluded_path_contains_list(self) -> list[str]:
        return [item.strip().lower() for item in self.assistant_excluded_path_contains.split(",") if item.strip()]

    @property
    def assistant_excluded_tag_term_list(self) -> list[str]:
        return [item.strip().lower() for item in self.assistant_excluded_tag_terms.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
