from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.dependencies import get_product_catalog_service
from app.product_catalog.service import ProductCatalogService

router = APIRouter(prefix='/products', tags=['products'])


@router.get('/categories')
def list_categories(
    product_catalog: ProductCatalogService = Depends(get_product_catalog_service),
) -> list[dict]:
    return [item.model_dump() for item in product_catalog.list_categories()]


@router.get('')
def list_products(
    query: str | None = None,
    category_id: str | None = None,
    category_name: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=50),
    in_stock_only: bool = False,
    product_catalog: ProductCatalogService = Depends(get_product_catalog_service),
) -> dict:
    result = product_catalog.browse_category(
        query=query,
        category_id=category_id,
        category_name=category_name,
        page=page,
        page_size=page_size,
        in_stock_only=in_stock_only,
    )
    category = result['category']
    return {
        'category': category.model_dump() if category else None,
        'page': result['page'],
        'page_size': result['page_size'],
        'total_items': result['total_items'],
        'total_pages': result['total_pages'],
        'items': [item.model_dump() for item in result['items']],
    }


@router.get('/detail')
def get_product_detail(
    query: str,
    product_catalog: ProductCatalogService = Depends(get_product_catalog_service),
) -> dict | None:
    detail = product_catalog.get_product_detail(query)
    return detail.model_dump() if detail else None
