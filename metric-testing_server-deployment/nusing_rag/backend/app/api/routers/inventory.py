from __future__ import annotations

from fastapi import APIRouter, Depends

from app.dependencies import get_inventory_search_service, get_session_store
from app.inventory_search.service import InventorySearchService
from app.schemas.inventory import InventorySearchRequest, InventorySearchResponse
from app.session_store.service import SessionStoreService

router = APIRouter(prefix='/inventory', tags=['inventory'])


@router.post('/search', response_model=InventorySearchResponse)
def search_inventory(
    request: InventorySearchRequest,
    inventory_search: InventorySearchService = Depends(get_inventory_search_service),
    session_store: SessionStoreService = Depends(get_session_store),
) -> InventorySearchResponse:
    session = session_store.get_session(request.session_id)
    result = inventory_search.search(
        query=request.query,
        tag=request.tag,
        category_name=request.category_name,
        top_k=request.top_k,
        mode=request.mode,
    )
    session.current_flow = 'inventory_search'
    session.collected_recommendations = [item.model_dump() for item in result.items]
    session_store.save_session(session)
    return result
