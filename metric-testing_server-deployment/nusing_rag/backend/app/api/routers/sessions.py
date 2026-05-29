from __future__ import annotations

from fastapi import APIRouter, Depends

from app.dependencies import get_session_store
from app.schemas.session import SessionCreateResponse, SessionSummary
from app.session_store.service import SessionStoreService

router = APIRouter(prefix='/sessions', tags=['sessions'])


@router.post('', response_model=SessionCreateResponse)
def create_session(
    session_store: SessionStoreService = Depends(get_session_store),
) -> SessionCreateResponse:
    state = session_store.create_session()
    return SessionCreateResponse(
        session_id=state.session_id,
        expires_in_seconds=session_store.ttl_seconds,
    )


@router.get('/{session_id}', response_model=SessionSummary)
def get_session_summary(
    session_id: str,
    session_store: SessionStoreService = Depends(get_session_store),
) -> SessionSummary:
    state = session_store.get_session(session_id)
    return SessionSummary(
        session_id=state.session_id,
        current_flow=state.current_flow,
        current_node_id=state.current_node_id,
        intent=state.intent,
        browse_selected_category=state.browse_selected_category,
        browse_viewed_products=list(state.browse_viewed_products),
        nursing_turns=len(state.nursing_qa_history),
        logic_turns=len(state.logic_rule_qa_history),
        followup_count=len(state.followup_results),
    )
