from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

TESTS_ROOT = Path(__file__).resolve().parents[1]
TEST_ENV_PATH = TESTS_ROOT / ".env"


def load_test_env(override: bool = False) -> Path:
    """Load the tests/.env file so evaluation code can reuse test-scoped settings."""
    load_dotenv(TEST_ENV_PATH, override=override)
    return TEST_ENV_PATH


def get_test_openrouter_settings() -> dict[str, str]:
    load_test_env()
    return {
        "api_key": os.getenv("OPENROUTER_API_KEY", "").strip(),
        "base_url": os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").strip(),
        "evaluation_model": os.getenv("EVALUATION_MODEL", "openai/gpt-4.1").strip(),
    }

