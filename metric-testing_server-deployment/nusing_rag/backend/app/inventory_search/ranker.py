from __future__ import annotations

import re
from difflib import SequenceMatcher


STOPWORDS = {
    "我想",
    "找",
    "一款",
    "相關",
    "產品",
    "主要",
    "需求",
    "是",
    "有什麼",
    "你們",
    "請",
    "推薦",
    "介紹",
}


def normalize_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "")).strip().lower()


def extract_recommend_tokens(text: str) -> list[str]:
    normalized = normalize_text(text)
    parts = re.split(r"[，,。；;：:\s/()\[\]【】\-]+", normalized)
    tokens: list[str] = []
    for part in parts:
        cleaned = part.strip()
        if len(cleaned) < 2 or cleaned in STOPWORDS:
            continue
        if cleaned not in tokens:
            tokens.append(cleaned)
    return tokens


def similarity_score(query: str, candidate_text: str) -> float:
    if not query or not candidate_text:
        return 0.0
    return SequenceMatcher(None, normalize_text(query), normalize_text(candidate_text)).ratio()


def token_overlap_score(query: str, candidate_text: str) -> float:
    tokens = extract_recommend_tokens(query)
    if not tokens:
        return 0.0
    candidate = normalize_text(candidate_text)
    hits = sum(1 for token in tokens if token in candidate)
    return hits / len(tokens)
