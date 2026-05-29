from __future__ import annotations

import json
import re

from app.core.llm_client import LLMClientFactory
from app.product_catalog.repository import ProductCatalogRepository
from app.schemas.inventory import InventoryItem, InventorySearchResponse

from .ranker import extract_recommend_tokens, normalize_text, similarity_score, token_overlap_score


class InventorySearchService:
    def __init__(
        self,
        repository: ProductCatalogRepository | None = None,
        llm_factory: LLMClientFactory | None = None,
    ) -> None:
        self.repository = repository or ProductCatalogRepository()
        self.llm_factory = llm_factory

    def search(
        self,
        query: str,
        tag: str | None = None,
        category_name: str | None = None,
        top_k: int = 5,
        mode: str = "semantic_rerank",
    ) -> InventorySearchResponse:
        if mode == "strict":
            items = self.search_strict(
                tag=tag,
                category_name=category_name,
                recommend_text=query,
                top_k=top_k,
            )
        else:
            items = self.search_semantic_rerank(
                tag=tag,
                category_name=category_name,
                user_desc=query,
                top_k=top_k,
            )
        return InventorySearchResponse(
            query=query,
            items=[
                InventoryItem(
                    product_name=item["product_name"],
                    category_name=item["category_name"],
                    score=item["score"],
                    stock_status=item["stock_status"],
                )
                for item in items
            ],
        )

    def search_strict(
        self,
        tag: str | None = None,
        category_name: str | None = None,
        recommend_text: str = "",
        top_k: int = 5,
    ) -> list[dict]:
        candidates = self._get_candidates(tag=tag, category_name=category_name, query=recommend_text)
        if not candidates:
            return []

        normalized_query = normalize_text(recommend_text)
        tokens = extract_recommend_tokens(recommend_text)
        ranked: list[dict] = []
        for item in candidates:
            product_name = normalize_text(item["product_name"])
            description = normalize_text(item["description"])
            score = 0.0
            if normalized_query == product_name:
                score += 10.0
            if normalized_query and normalized_query in product_name:
                score += 4.0
            score += similarity_score(recommend_text, item["product_name"]) * 2.5
            score += similarity_score(recommend_text, item["description"]) * 0.5
            if tokens:
                score += sum(
                    1.0
                    for token in tokens
                    if token in product_name or token in description
                )
            ranked.append({**item, "score": round(score, 4)})
        return self._sort_ranked(ranked)[:top_k]

    def search_semantic_rerank(
        self,
        tag: str | None = None,
        category_name: str | None = None,
        user_desc: str = "",
        top_k: int = 5,
    ) -> list[dict]:
        candidates = self._get_candidates(tag=tag, category_name=category_name, query=user_desc)
        if not candidates:
            return []

        ranked = self._rank_semantic_candidates(candidates, user_desc=user_desc)
        llm_ranked = self._rerank_with_llm(
            ranked,
            user_desc=user_desc,
            top_k=top_k,
            category_name=category_name,
        )
        if llm_ranked:
            return llm_ranked[:top_k]
        return ranked[:top_k]

    def _get_candidates(
        self,
        tag: str | None,
        category_name: str | None,
        query: str,
    ) -> list[dict]:
        explicit_candidates = self.repository.filter_products(
            category_id=tag,
            category_name=category_name,
        )
        if explicit_candidates:
            return explicit_candidates

        inferred_category = None
        if category_name:
            inferred_category = self.repository.resolve_category(category_name)
        if not inferred_category and query:
            inferred_category = self.repository.resolve_category(query)
        if inferred_category:
            inferred_candidates = self.repository.filter_products(
                category_id=tag or inferred_category["category_id"],
                category_name=inferred_category["category_name"],
            )
            if inferred_candidates:
                return inferred_candidates

        if tag or category_name:
            return self.repository.load_products()
        return explicit_candidates

    def _sort_ranked(self, items: list[dict]) -> list[dict]:
        return sorted(
            items,
            key=lambda item: (-float(item["score"]), int(item["source_index"])),
        )

    def _rank_semantic_candidates(self, candidates: list[dict], user_desc: str) -> list[dict]:
        ranked: list[dict] = []
        for item in candidates:
            combined_text = " ".join(
                [
                    item["product_name"],
                    item["category_name"],
                    item["description"],
                ]
            )
            score = 0.0
            score += similarity_score(user_desc, item["product_name"]) * 2.0
            score += similarity_score(user_desc, combined_text) * 1.5
            score += token_overlap_score(user_desc, combined_text) * 5.0
            if item["in_stock"]:
                score += 0.25
            ranked.append({**item, "score": round(score, 4)})
        return self._sort_ranked(ranked)

    def _rerank_with_llm(
        self,
        ranked_candidates: list[dict],
        user_desc: str,
        top_k: int,
        category_name: str | None,
    ) -> list[dict]:
        if not self.llm_factory or not self.llm_factory.is_configured:
            return []

        chat_model = self.llm_factory.create_chat_model(temperature=0.0)
        if chat_model is None:
            return []

        indexed_candidates = ranked_candidates[:20]
        candidate_blocks = [
            self._summarize_candidate(item, index)
            for index, item in enumerate(indexed_candidates, start=1)
        ]
        prompt = (
            "你是库存匹配助手。请根据用户需求，从以下候选产品中选出最匹配的 "
            f"{top_k} 款。\n"
            "要求：\n"
            f"1. 只考虑候选列表中的产品\n2. 返回最匹配的 {top_k} 个产品编号\n"
            "3. 如果没有匹配的，返回空列表\n"
            '4. 严格按 JSON 格式输出: {"indices":[1,2]}\n'
            "5. 也可以直接回复编号如 1,3\n6. 不要输出解释\n\n"
            f"产品分类: {(category_name or indexed_candidates[0]['category_name']).strip()}\n"
            f"用户需求: {user_desc.strip()}\n\n"
            "候选产品:\n"
            + "\n".join(candidate_blocks)
        )
        try:
            response = chat_model.invoke(prompt)
        except Exception:
            return []

        indices = self._extract_indices(str(getattr(response, "content", response)), len(indexed_candidates))
        if not indices:
            return []

        reranked: list[dict] = []
        for offset, index in enumerate(indices):
            item = dict(indexed_candidates[index - 1])
            item["score"] = round(100.0 - offset, 4)
            reranked.append(item)
        return reranked

    def _summarize_candidate(self, item: dict, index: int) -> str:
        description = str(item.get("description", "")).strip()[:160]
        stock_status = str(item.get("stock_status", "")).strip() or "未知"
        return (
            f"{index}. 名称: {item['product_name']} | 分类: {item['category_name']} | "
            f"库存: {stock_status} | 描述: {description}"
        )

    def _extract_indices(self, raw_text: str, max_index: int) -> list[int]:
        text = raw_text.strip()
        if not text:
            return []

        if "```" in text:
            text = re.sub(r"```(?:json)?", "", text).replace("```", "").strip()
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = None

        values: list[int] = []
        if isinstance(parsed, dict) and isinstance(parsed.get("indices"), list):
            values = [self._coerce_index(item) for item in parsed["indices"]]
        else:
            values = [self._coerce_index(item) for item in re.findall(r"\d+", text)]

        filtered: list[int] = []
        for value in values:
            if 1 <= value <= max_index and value not in filtered:
                filtered.append(value)
        return filtered

    def _coerce_index(self, value: object) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return -1
