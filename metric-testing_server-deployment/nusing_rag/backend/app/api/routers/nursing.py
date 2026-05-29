from __future__ import annotations

from fastapi import APIRouter, Depends

from app.dependencies import get_nursing_rag_service, get_session_store
from app.nursing_rag.service import NursingRagService, SAFETY_SUFFIX
from app.schemas.nursing import NursingQuestionRequest
from app.session_store.service import SessionStoreService

router = APIRouter(prefix='/nursing', tags=['nursing'])


@router.post('/ask')
def ask_nursing_question(
    request: NursingQuestionRequest,
    nursing_rag: NursingRagService = Depends(get_nursing_rag_service),
    session_store: SessionStoreService = Depends(get_session_store),
) -> dict:
    session = session_store.get_session(request.session_id)
    result = nursing_rag.answer(request.question)
    session.current_flow = 'nursing_rag'
    session.nursing_qa_history.append(
        {'question': request.question, 'answer': result['answer'], 'contexts': result['contexts']}
    )
    session_store.save_session(session)
    return {
        'answer': str(result['answer']),
        'is_fallback': result['status'] != 'answered',
    }
