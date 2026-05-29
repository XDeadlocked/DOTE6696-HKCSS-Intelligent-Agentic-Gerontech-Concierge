from __future__ import annotations

from langchain_openai import ChatOpenAI
from ragas.llms import LangchainLLMWrapper

from tests.common.test_env import get_test_openrouter_settings


def build_openrouter_evaluator(temperature: float = 0.0) -> tuple[LangchainLLMWrapper, dict[str, str]]:
    settings = get_test_openrouter_settings()
    api_key = settings["api_key"]
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is required in tests/.env for online evaluation.")

    chat_model = ChatOpenAI(
        model=settings["evaluation_model"],
        api_key=api_key,
        base_url=settings["base_url"],
        temperature=temperature,
    )
    return LangchainLLMWrapper(chat_model), settings
