from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.core.config import get_settings


class LogicRuleRepository:
    def __init__(self, json_path: Path | None = None) -> None:
        settings = get_settings()
        self.json_path = json_path or settings.rule_json_path

    def load(self) -> dict[str, Any]:
        with self.json_path.open("r", encoding="utf-8") as file:
            return json.load(file)
