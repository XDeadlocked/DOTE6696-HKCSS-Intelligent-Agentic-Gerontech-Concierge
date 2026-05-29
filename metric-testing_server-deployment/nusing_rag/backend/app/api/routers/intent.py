from __future__ import annotations

from fastapi import APIRouter, Depends

from app.dependencies import get_intent_router, get_session_store
from app.intent_router.service import IntentRouterService
from app.schemas.intent import IntentClassifyRequest, IntentResult
from app.session_store.service import SessionStoreService

router = APIRouter(prefix='/intent', tags=['intent'])


@router.post('/classify', response_model=IntentResult)
def classify_intent(
    request: IntentClassifyRequest,
    intent_router: IntentRouterService = Depends(get_intent_router),
    session_store: SessionStoreService = Depends(get_session_store),
) -> IntentResult:
    result = intent_router.classify_intent(request.user_input)
    if request.session_id:
        state = session_store.get_session(request.session_id)
        state.intent = str(result.intent)
        state.history_messages.append({'role': 'user', 'content': request.user_input})
        state.history_messages.append({'role': 'assistant', 'content': result.message})
        session_store.save_session(state)
    return result
