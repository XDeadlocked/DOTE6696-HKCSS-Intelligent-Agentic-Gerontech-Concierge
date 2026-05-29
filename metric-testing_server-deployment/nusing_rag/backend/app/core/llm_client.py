from __future__ import annotations

from langchain_openai import ChatOpenAI

from app.core.config import Settings


class LLMClientFactory:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @property
    def is_configured(self) -> bool:
        return bool(self.settings.openrouter_api_key)

    def get_model_names(self) -> list[str]:
        return list(self.settings.llm_model_candidates)

    def create_chat_model(
        self,
        model_name: str | None = None,
        temperature: float = 0.0,
    ) -> ChatOpenAI | None:
        if not self.is_configured:
            return None

        return ChatOpenAI(
            model=model_name or self.settings.llm_model_candidates[0],
            api_key=self.settings.openrouter_api_key,
            base_url=self.settings.openrouter_base_url,
            temperature=temperature,
            request_timeout=60,
            max_retries=1,
        )
