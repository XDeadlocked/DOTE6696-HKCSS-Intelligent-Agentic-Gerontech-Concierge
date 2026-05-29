from __future__ import annotations

from pydantic import BaseModel, Field


class InventorySearchRequest(BaseModel):
    session_id: str
    query: str
    top_k: int = 5
    tag: str | None = None
    category_name: str | None = None
    mode: str = "semantic_rerank"


class InventoryItem(BaseModel):
    product_name: str
    category_name: str | None = None
    score: float | None = None
    stock_status: str | None = None


class InventorySearchResponse(BaseModel):
    query: str
    items: list[InventoryItem] = Field(default_factory=list)
