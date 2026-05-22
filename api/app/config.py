from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(slots=True)
class Settings:
    api_key: str = os.getenv("API_KEY", "dev-api-key-please-change-me-32chars")
    clickhouse_host: str = os.getenv("CH_HOST", "clickhouse")
    clickhouse_port: int = int(os.getenv("CH_PORT", "8123"))
    clickhouse_user: str = os.getenv("CH_USER", "changelog")
    clickhouse_password: str = os.getenv("CH_PASSWORD", "change-me")
    clickhouse_db: str = os.getenv("CH_DB", "changelog_db")
    clickhouse_timeout: float = float(os.getenv("CH_TIMEOUT", "10"))


settings = Settings()
