from __future__ import annotations

from app.schemas.product import ProductCategorySummary, ProductDetail, ProductSummary

from .repository import ProductCatalogRepository


class ProductCatalogService:
    def __init__(self, repository: ProductCatalogRepository | None = None) -> None:
        self.repository = repository or ProductCatalogRepository()

    def list_categories(self) -> list[ProductCategorySummary]:
        return [
            ProductCategorySummary.model_validate(item)
            for item in self.repository.list_categories()
        ]

    def resolve_category(self, query: str) -> ProductCategorySummary | None:
        resolved = self.repository.resolve_category(query)
        if not resolved:
            return None
        return ProductCategorySummary.model_validate(resolved)

    def browse_category(
        self,
        query: str | None = None,
        category_id: str | None = None,
        category_name: str | None = None,
        page: int = 1,
        page_size: int = 10,
        in_stock_only: bool = False,
    ) -> dict[str, object]:
        resolved = None
        if query and not category_id and not category_name:
            resolved = self.repository.resolve_category(query)
            if resolved:
                category_id = resolved["category_id"]
                category_name = resolved["category_name"]

        result = self.repository.list_products(
            category_id=category_id,
            category_name=category_name,
            page=page,
            page_size=page_size,
            in_stock_only=in_stock_only,
        )
        items = [
            ProductSummary(
                product_id=item["product_id"],
                product_name=item["product_name"],
                category_id=item["category_id"],
                category_name=item["category_name"],
                description=item["description"],
            )
            for item in result["items"]
        ]
        return {
            "category": (
                ProductCategorySummary.model_validate(resolved)
                if resolved
                else ProductCategorySummary(
                    category_id=category_id or "",
                    category_name=category_name or "",
                    product_count=result["total_items"],
                )
                if category_id or category_name
                else None
            ),
            "page": result["page"],
            "page_size": result["page_size"],
            "total_items": result["total_items"],
            "total_pages": result["total_pages"],
            "items": items,
        }

    def get_product_detail(self, query: str) -> ProductDetail | None:
        detail = self.repository.get_product_detail(query)
        if not detail:
            return None
        return ProductDetail(
            product_id=detail["product_id"],
            product_name=detail["product_name"],
            category_id=detail["category_id"],
            category_name=detail["category_name"],
            description=detail["description"] or None,
            sales_price=detail["sales_price"],
            stock_status=detail["stock_status"] or None,
            dimensions=detail["dimensions"],
        )
