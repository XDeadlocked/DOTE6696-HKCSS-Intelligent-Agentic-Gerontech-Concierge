from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.core.config import get_settings


class DeviceFollowupService:
    def __init__(self, config_path: Path | None = None) -> None:
        settings = get_settings()
        self.config_path = config_path or settings.device_followup_json_path
        with self.config_path.open("r", encoding="utf-8") as file:
            self.category_config: dict[str, Any] = json.load(file)

    def get_config(self, device_tag: str) -> dict[str, Any] | None:
        return self.category_config.get(str(device_tag))

    def get_question(self, device_tag: str) -> dict[str, Any] | None:
        config = self.get_config(device_tag)
        if not config:
            return None
        return {
            "tag": str(device_tag),
            "category_name": config["name"],
            "mode": config["mode"],
            "question": config["question"],
            "options": config.get("options", []),
        }

    def answer(
        self,
        device_tag: str,
        user_input: str,
        nested_input: str | None = None,
    ) -> dict[str, Any]:
        config = self.get_config(device_tag)
        if not config:
            return {"status": "not_found", "tag": str(device_tag)}

        mode = config["mode"]
        selected, is_custom, custom_text = self._parse_choice(user_input, config.get("options", []))

        if mode in {"recommend", "nested"}:
            if is_custom:
                return self._trigger_inventory_search(device_tag, config["name"], f"自由输入: {custom_text}")
            if not selected:
                return {"status": "invalid_option", "tag": str(device_tag), "mode": mode}
            if selected.get("is_other"):
                return self._trigger_inventory_search(device_tag, config["name"], f"其他: {custom_text or selected['text']}")
            if "followup" in selected:
                followup = selected["followup"]
                if nested_input is None:
                    return {
                        "status": "need_nested_choice",
                        "tag": str(device_tag),
                        "mode": mode,
                        "category": config["name"],
                        "choice": selected["text"],
                        "followup_question": followup["question"],
                        "followup_options": followup["options"],
                    }
                sub_choice, sub_is_custom, sub_custom_text = self._parse_choice(nested_input, followup["options"])
                if sub_is_custom:
                    return self._trigger_inventory_search(
                        device_tag,
                        config["name"],
                        f"{selected['text']}-{sub_custom_text}",
                    )
                if not sub_choice:
                    return {"status": "invalid_nested_option", "tag": str(device_tag), "mode": mode}
                if sub_choice.get("is_other"):
                    return self._trigger_inventory_search(
                        device_tag,
                        config["name"],
                        f"{selected['text']}-{sub_custom_text or sub_choice['text']}",
                    )
                return {
                    "status": "recommendation",
                    "tag": str(device_tag),
                    "mode": mode,
                    "category": config["name"],
                    "choice": selected["text"],
                    "sub_choice": sub_choice["text"],
                    "recommend": sub_choice["recommend"],
                }
            return {
                "status": "recommendation",
                "tag": str(device_tag),
                "mode": mode,
                "category": config["name"],
                "choice": selected["text"],
                "recommend": selected["recommend"],
            }

        if mode == "no_product":
            if is_custom:
                return self._trigger_inventory_search(device_tag, config["name"], custom_text)
            if selected and selected.get("is_other"):
                return self._trigger_inventory_search(
                    device_tag,
                    config["name"],
                    custom_text or selected["text"],
                )
            return {
                "status": "no_product",
                "tag": str(device_tag),
                "mode": mode,
                "category": config["name"],
                "choice": selected["text"] if selected else None,
            }

        if mode == "redirect":
            if is_custom:
                return self._trigger_inventory_search(device_tag, config["name"], custom_text)
            if selected and selected.get("is_other"):
                return self._trigger_inventory_search(
                    device_tag,
                    config["name"],
                    custom_text or selected["text"],
                )
            return {
                "status": "redirect",
                "tag": str(device_tag),
                "mode": mode,
                "category": config["name"],
                "choice": selected["text"] if selected else None,
                "redirect_to_human": True,
            }

        return {"status": "unknown_mode", "tag": str(device_tag), "mode": mode}

    def _parse_choice(
        self,
        user_input: str,
        options: list[dict[str, Any]],
    ) -> tuple[dict[str, Any] | None, bool, str]:
        text = user_input.strip()
        if not text:
            return None, False, ""
        by_label = next((option for option in options if option["label"] == text), None)
        if by_label:
            return by_label, False, ""
        by_text = next(
            (
                option
                for option in options
                if text in option["text"] or option["text"] in text
            ),
            None,
        )
        if by_text:
            return by_text, False, ""
        return None, True, text

    def _trigger_inventory_search(
        self,
        tag: str,
        category_name: str,
        user_desc: str = "",
    ) -> dict[str, Any]:
        return {
            "status": "inventory_search",
            "trigger_inventory_search": True,
            "tag": str(tag),
            "category": category_name,
            "user_choice": user_desc,
        }
