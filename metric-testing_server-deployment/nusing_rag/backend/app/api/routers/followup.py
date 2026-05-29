from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.dependencies import get_device_followup_service, get_session_store
from app.device_followup.service import DeviceFollowupService
from app.schemas.followup import FollowupAnswerRequest
from app.session_store.service import SessionStoreService

router = APIRouter(prefix='/followup', tags=['followup'])


@router.get('/question')
def get_followup_question(
    session_id: str = Query(...),
    device_tag: str = Query(...),
    followup_service: DeviceFollowupService = Depends(get_device_followup_service),
    session_store: SessionStoreService = Depends(get_session_store),
) -> dict | None:
    session = session_store.get_session(session_id)
    session.device_tag = device_tag
    session_store.save_session(session)
    return followup_service.get_question(device_tag)


@router.post('/answer')
def answer_followup(
    request: FollowupAnswerRequest,
    followup_service: DeviceFollowupService = Depends(get_device_followup_service),
    session_store: SessionStoreService = Depends(get_session_store),
) -> dict:
    session = session_store.get_session(request.session_id)
    result = followup_service.answer(
        request.device_tag,
        request.answer,
        nested_input=request.nested_input,
    )
    session.followup_results.append(result)
    session_store.save_session(session)
    return result
