from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from langchain_chroma import Chroma

from app.core.config import get_settings
from app.core.embedding_model import get_embedding_function

DOMAIN_TERMS = [
    "认知障碍症",
    "認知障礙症",
    "照护",
    "照顧",
    "照顾者",
    "照顧者",
    "压力",
    "壓力",
    "抑郁",
    "抑鬱",
    "睡眠紊乱",
    "睡眠紊亂",
    "妄想",
    "幻觉",
    "幻覺",
    "沟通",
    "溝通",
    "诊断",
    "診斷",
    "训练",
    "訓練",
    "情绪",
    "情緒",
    "自杀",
    "自殺",
    "扶抱",
    "转移",
    "轉移",
    "安全",
    "家居安全",
    "困難",
    "困难",
    "活动",
    "活動",
    "紀錄",
    "记录",
    "日常規律",
    "规律",
]


def normalize_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "")).strip()


def extract_keywords(question: str) -> list[str]:
    normalized = normalize_text(question)
    matched_terms = [term for term in DOMAIN_TERMS if term in normalized]
    if matched_terms:
        seen_terms: list[str] = []
        for term in matched_terms:
            if term not in seen_terms:
                seen_terms.append(term)
        return seen_terms
    parts = re.split(r"[，,。；;：:\s/()\[\]【】\-]+", normalized)
    tokens: list[str] = []
    for part in parts:
        token = part.strip()
        if len(token) < 2:
            continue
        if token not in tokens:
            tokens.append(token)
    return tokens


class NursingKnowledgeRepository:
    def __init__(
        self,
        persist_directory: Path | None = None,
        collection_name: str | None = None,
    ) -> None:
        settings = get_settings()
        self.persist_directory = persist_directory or settings.nursing_vectorstore_dir
        self.collection_name = (
            collection_name or settings.nursing_chroma_collection_name
        )
        self.embedding_function = get_embedding_function(
            model_name=settings.embedding_model_name
        )

    @lru_cache(maxsize=1)
    def get_vectorstore(self) -> Chroma:
        return Chroma(
            persist_directory=str(self.persist_directory),
            collection_name=self.collection_name,
            embedding_function=self.embedding_function,
        )

    def search(self, question: str, top_k: int = 3) -> list[dict[str, object]]:
        query = normalize_text(question)
        if not query:
            return []

        matches = self.get_vectorstore().similarity_search_with_relevance_scores(
            query,
            k=top_k,
        )
        retrievals: list[dict[str, object]] = []
        for document, score in matches:
            content = normalize_text(document.page_content)
            if not content:
                continue
            metadata = dict(document.metadata or {})
            retrievals.append(
                {
                    "rowid": str(getattr(document, "id", "")),
                    "content": content,
                    "score": round(float(score), 6),
                    "title": metadata.get("title") or metadata.get("source") or "",
                    "source": metadata.get("source", ""),
                    "page": metadata.get("page"),
                    "metadata": metadata,
                }
            )
        return retrievals
