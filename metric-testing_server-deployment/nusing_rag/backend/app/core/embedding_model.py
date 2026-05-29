from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from langchain_huggingface import HuggingFaceEmbeddings

try:
    from app.core.config import get_settings
except ModuleNotFoundError:
    from config import get_settings


DEFAULT_CACHE_DIR = Path(__file__).resolve().parent / "model_cache"


def get_embedding_cache_dir() -> Path:
    DEFAULT_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return DEFAULT_CACHE_DIR


@lru_cache(maxsize=1)
def get_embedding_function(
    model_name: str | None = None,
    cache_dir: str | Path | None = None,
) -> HuggingFaceEmbeddings:
    settings = get_settings()
    resolved_model_name = model_name or settings.embedding_model_name
    resolved_cache_dir = Path(cache_dir) if cache_dir else get_embedding_cache_dir()
    resolved_cache_dir.mkdir(parents=True, exist_ok=True)
    return HuggingFaceEmbeddings(
        model_name=resolved_model_name,
        cache_folder=str(resolved_cache_dir),
    )


def get_embeddings(
    model_name: str | None = None,
    cache_dir: str | Path | None = None,
) -> HuggingFaceEmbeddings:
    return get_embedding_function(model_name=model_name, cache_dir=cache_dir)


if __name__ == "__main__":
    embeddings = get_embedding_function()
    print(f"Embedding 模型加载完成: {embeddings.model_name}\n")
