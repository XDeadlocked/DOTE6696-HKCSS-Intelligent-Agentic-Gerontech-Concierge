from __future__ import annotations

from pydantic import BaseModel, Field


class ProductCategorySummary(BaseModel):
    category_id: str
    category_name: str
    product_count: int = 0


class ProductSummary(BaseModel):
    product_id: str | None = None
    product_name: str
    category_id: str | None = None
    category_name: str | None = None
    description: str | None = None


class ProductDetail(ProductSummary):
    sales_price: str | None = None
    stock_status: str | None = None
    dimensions: dict[str, str] = Field(default_factory=dict)
