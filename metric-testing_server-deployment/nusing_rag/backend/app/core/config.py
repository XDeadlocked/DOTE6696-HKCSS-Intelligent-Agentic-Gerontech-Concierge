from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
APP_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = APP_DIR / "data"


class Settings(BaseSettings):
    app_name: str = "Senior Care Assistant Backend"
    app_version: str = "0.1.0"
    environment: Literal["dev", "test", "prod"] = "dev"
    api_v1_prefix: str = "/api/v1"
    log_level: str = "INFO"

    session_ttl_minutes: int = 120
    session_sqlite_path: Path = DATA_DIR / "sessions.db"

    openrouter_api_key: str | None = Field(default=None, alias="OPENROUTER_API_KEY")
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    llm_model_candidates: str | list[str] = Field(
        default_factory=lambda: ["openai/gpt-4o-mini", "openai/gpt-4o"]
    )
    embedding_model_name: str = "BAAI/bge-m3"
    nursing_chroma_collection_name: str = "nursing_consultation"

    rule_json_path: Path = DATA_DIR / "logic_rule" / "02_LOGIC_RULE.json"
    product_csv_path: Path = DATA_DIR / "product_catalog" / "01_PRODUCT_MASTER_BASE.csv"
    product_json_path: Path = DATA_DIR / "product_catalog" / "03_PRODUCT_INFO.json"
    device_followup_json_path: Path = (
        DATA_DIR / "device_followup" / "04_PRODUCT_REFINE_LOGIC.json"
    )
    nursing_vectorstore_dir: Path = DATA_DIR / "nursing_rag" / "nursing_chroma_db"

    model_config = SettingsConfigDict(
        env_file=str(BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        populate_by_name=True,
    )

    @field_validator("llm_model_candidates", mode="before")
    @classmethod
    def parse_model_candidates(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, list):
            return value
        if not value:
            return ["openai/gpt-4o-mini", "openai/gpt-4o"]
        return [item.strip() for item in value.split(",") if item.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
