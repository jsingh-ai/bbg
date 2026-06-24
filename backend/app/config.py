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


@lru_cache
def get_settings() -> Settings:
    return Settings()
