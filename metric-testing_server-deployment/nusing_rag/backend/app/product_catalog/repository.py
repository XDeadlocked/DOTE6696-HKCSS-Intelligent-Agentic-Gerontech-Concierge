from __future__ import annotations

import csv
import html
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.core.config import get_settings


def _normalize_text(value: str | None) -> str:
    text = html.unescape("" if value is None else str(value))
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _normalize_key(value: str | None) -> str:
    return _normalize_text(value).lower()


def _format_price(value: Any) -> str | None:
    if value in (None, "", 0, 0.0):
        return None
    if isinstance(value, (int, float)):
        return f"{float(value):.2f}"
    text = _normalize_text(str(value))
    return text or None


class ProductCatalogRepository:
    def __init__(
        self,
        product_csv_path: Path | None = None,
        product_json_path: Path | None = None,
    ) -> None:
        settings = get_settings()
        self.product_csv_path = product_csv_path or settings.product_csv_path
        self.product_json_path = product_json_path or settings.product_json_path

    @lru_cache(maxsize=1)
    def load_products(self) -> list[dict[str, Any]]:
        with self.product_csv_path.open("r", encoding="utf-8-sig") as csv_file:
            master_rows = list(csv.DictReader(csv_file))

        import json

        with self.product_json_path.open("r", encoding="utf-8") as json_file:
            detail_rows = json.load(json_file)

        detail_map = {
            _normalize_key(item.get("Name")): item
            for item in detail_rows
            if isinstance(item, dict)
        }

        products: list[dict[str, Any]] = []
        for index, row in enumerate(master_rows):
            product_name = _normalize_text(row.get("product_name"))
            detail = detail_map.get(_normalize_key(product_name), {})

            detail_description = (
                _normalize_text(detail.get("eCommerce Description"))
                or _normalize_text(detail.get("Product/Description"))
            )
            base_description = _normalize_text(row.get("description"))
            merged_description = detail_description or base_description

            products.append(
                {
                    "source_index": index,
                    "product_id": product_name or f"product-{index + 1}",
                    "product_name": product_name,
                    "category_id": _normalize_text(row.get("category_id")),
                    "category_name": _normalize_text(row.get("category_name")),
                    "description": merged_description,
                    "base_description": base_description,
                    "detail_description": detail_description,
                    "sales_price": _format_price(detail.get("Sales Price")),
                    "stock_status": _normalize_text(row.get("stock_status")),
                    "in_stock": str(row.get("in_stock", "")).strip().lower() == "true",
                    "quantity_on_hand": detail.get("Quantity On Hand"),
                    "net_weight": _normalize_text(
                        detail.get("Net Weight") or row.get("net_weight")
                    ),
                    "dimensions": {
                        "height": _normalize_text(
                            detail.get("Dimension Height") or row.get("dimension_height")
                        ),
                        "length": _normalize_text(
                            detail.get("Dimension Length") or row.get("dimension_length")
                        ),
                        "width": _normalize_text(
                            detail.get("Dimension Width") or row.get("dimension_width")
                        ),
                    },
                    "video_url": _normalize_text(detail.get("Introduction Video URL")),
                }
            )
        return products

    def list_categories(self) -> list[dict[str, Any]]:
        counts: dict[tuple[str, str], int] = {}
        for product in self.load_products():
            key = (product["category_id"], product["category_name"])
            counts[key] = counts.get(key, 0) + 1

        return [
            {
                "category_id": category_id,
                "category_name": category_name,
                "product_count": count,
            }
            for (category_id, category_name), count in sorted(
                counts.items(),
                key=lambda item: item[0][1],
            )
        ]

    def resolve_category(self, query: str) -> dict[str, Any] | None:
        normalized_query = _normalize_key(query)
        if not normalized_query:
            return None

        for category in sorted(
            self.list_categories(),
            key=lambda item: len(item["category_name"]),
            reverse=True,
        ):
            category_name = _normalize_key(category["category_name"])
            if category_name and (
                category_name in normalized_query or normalized_query in category_name
            ):
                return category
        return None

    def list_products(
        self,
        category_id: str | None = None,
        category_name: str | None = None,
        page: int = 1,
        page_size: int = 10,
        in_stock_only: bool = False,
    ) -> dict[str, Any]:
        filtered = self.filter_products(
            category_id=category_id,
            category_name=category_name,
            in_stock_only=in_stock_only,
        )
        page = max(page, 1)
        page_size = max(page_size, 1)
        total_items = len(filtered)
        total_pages = (total_items + page_size - 1) // page_size if total_items else 0
        start = (page - 1) * page_size
        end = start + page_size
        return {
            "page": page,
            "page_size": page_size,
            "total_items": total_items,
            "total_pages": total_pages,
            "items": filtered[start:end],
        }

    def filter_products(
        self,
        category_id: str | None = None,
        category_name: str | None = None,
        in_stock_only: bool = False,
    ) -> list[dict[str, Any]]:
        normalized_category_id = _normalize_text(category_id)
        normalized_category_name = _normalize_text(category_name)

        items = self.load_products()
        if normalized_category_id:
            items = [
                item
                for item in items
                if item["category_id"] == normalized_category_id
            ]
        if not items and normalized_category_name:
            items = [
                item
                for item in self.load_products()
                if item["category_name"] == normalized_category_name
            ]
        elif normalized_category_name:
            items = [
                item
                for item in items
                if item["category_name"] == normalized_category_name
            ]
        if in_stock_only:
            items = [item for item in items if item["in_stock"]]
        return items

    def get_product_detail(self, query: str) -> dict[str, Any] | None:
        normalized_query = _normalize_text(query)
        if not normalized_query:
            return None

        extracted_name = self._extract_detail_name(normalized_query)
        normalized_name = _normalize_key(extracted_name)
        products = self.load_products()

        exact = next(
            (
                item
                for item in products
                if _normalize_key(item["product_name"]) == normalized_name
            ),
            None,
        )
        if exact:
            return exact

        partial = next(
            (
                item
                for item in products
                if normalized_name in _normalize_key(item["product_name"])
                or _normalize_key(item["product_name"]) in normalized_name
            ),
            None,
        )
        if partial:
            return partial

        return max(
            products,
            key=lambda item: self._sequence_score(
                normalized_name,
                _normalize_key(item["product_name"]),
            ),
            default=None,
        )

    def _extract_detail_name(self, query: str) -> str:
        patterns = [
            r"我想看(.+?)的詳情",
            r"我想看(.+?)详情",
            r"查看(.+?)的詳情",
            r"查看(.+?)详情",
        ]
        for pattern in patterns:
            match = re.search(pattern, query)
            if match:
                return match.group(1).strip()
        return query

    def _sequence_score(self, left: str, right: str) -> float:
        if not left or not right:
            return 0.0
        from difflib import SequenceMatcher

        return SequenceMatcher(None, left, right).ratio()
