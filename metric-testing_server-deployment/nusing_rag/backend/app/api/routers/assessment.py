from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.dependencies import get_logic_rule_service, get_session_store
from app.logic_rule.service import LogicRuleRuntimeState, LogicRuleService
from app.session_store.service import SessionStoreService

router = APIRouter(prefix='/assessment', tags=['assessment'])


class AssessmentStartRequest(BaseModel):
    session_id: str


class AssessmentAnswerRequest(BaseModel):
    session_id: str
    user_input: str = ""
    selected_options: list[str] | None = None


def _state_from_session(session) -> LogicRuleRuntimeState:
    return LogicRuleRuntimeState(
        current_node=session.current_node_id or '',
        pending_branches=list(session.logic_pending_branches),
        collected_recommendations=[str(item) for item in session.selected_answers],
        qa_history=list(session.logic_rule_qa_history),
        is_complete=session.logic_is_complete,
    )


def _sync_session(session, runtime: LogicRuleRuntimeState) -> None:
    session.current_flow = 'assessment'
    session.current_node_id = runtime.current_node or None
    session.logic_pending_branches = list(runtime.pending_branches)
    session.selected_answers = list(runtime.collected_recommendations)
    session.logic_rule_qa_history = list(runtime.qa_history)
    session.logic_is_complete = runtime.is_complete


@router.post('/start')
def start_assessment(
    request: AssessmentStartRequest,
    logic_rule: LogicRuleService = Depends(get_logic_rule_service),
    session_store: SessionStoreService = Depends(get_session_store),
) -> dict:
    session = session_store.get_session(request.session_id)
    runtime = logic_rule.start_session()
    _sync_session(session, runtime)
    session_store.save_session(session)
    question = logic_rule.get_current_question(runtime)
    return {'status': 'question', **(question or {})}


@router.post('/answer')
def answer_assessment(
    request: AssessmentAnswerRequest,
    logic_rule: LogicRuleService = Depends(get_logic_rule_service),
    session_store: SessionStoreService = Depends(get_session_store),
) -> dict:
    session = session_store.get_session(request.session_id)
    if session.current_flow != 'assessment' or not session.current_node_id:
        raise HTTPException(status_code=409, detail='assessment_not_started')
    runtime = _state_from_session(session)
    result = logic_rule.submit_answer(runtime, request.user_input, selected_options=request.selected_options)
    _sync_session(session, runtime)
    session_store.save_session(session)

    recommendations = logic_rule.get_recommendations(runtime)
    serialized_recommendations = [asdict(item) for item in recommendations]
    if result['status'] == 'next_question':
        return {'status': 'question', **(result.get('question') or {})}
    if result['status'] == 'reprompt':
        return {'status': 'reprompt', 'reason': result.get('reason', 'unclear_input')}
    return {
        'status': 'completed' if runtime.is_complete else 'recommendation',
        'recommendations': serialized_recommendations,
        'question': logic_rule.get_current_question(runtime),
    }
