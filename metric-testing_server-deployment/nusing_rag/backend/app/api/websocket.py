from __future__ import annotations

from dataclasses import asdict
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.exceptions import SessionNotFoundError
from app.logic_rule.service import LogicRuleRuntimeState, LogicRuleService
from app.nursing_rag.service import NursingRagService

router = APIRouter(tags=['websocket'])


def _ws_event(event_type: str, session_id: str, data: dict) -> dict:
    return {
        'type': event_type,
        'session_id': session_id,
        'trace_id': str(uuid.uuid4()),
        'data': data,
    }


def _runtime_from_session(session) -> LogicRuleRuntimeState:
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


def _get_logic_rule_service(websocket: WebSocket) -> LogicRuleService:
    return LogicRuleService()


def _get_nursing_rag_service(websocket: WebSocket) -> NursingRagService:
    return NursingRagService(llm_factory=websocket.app.state.llm_factory)


@router.websocket('/ws/assessment/{session_id}')
async def assessment_ws(websocket: WebSocket, session_id: str) -> None:
    await websocket.accept()
    session_store = websocket.app.state.session_store
    logic_rule_service = _get_logic_rule_service(websocket)
    try:
        session_store.bind_websocket(session_id, 'assessment', str(id(websocket)))
    except SessionNotFoundError:
        await websocket.send_json(_ws_event('error', session_id, {'message': 'session_not_found'}))
        await websocket.close(code=1008)
        return
    try:
        while True:
            payload = await websocket.receive_json()
            event_type = payload.get('type')
            session = session_store.get_session(session_id)
            if event_type == 'start':
                runtime = logic_rule_service.start_session()
                _sync_session(session, runtime)
                session_store.save_session(session)
                await websocket.send_json(
                    _ws_event('question', session_id, logic_rule_service.get_current_question(runtime) or {})
                )
                continue
            if event_type != 'answer':
                await websocket.send_json(_ws_event('error', session_id, {'message': 'unsupported_event'}))
                continue

            runtime = _runtime_from_session(session) if session.current_node_id else logic_rule_service.start_session()
            selected_options = payload.get('selected_options', None)
            if selected_options and isinstance(selected_options, list):
                result = logic_rule_service.submit_answer(runtime, "", selected_options=selected_options)
            else:
                result = logic_rule_service.submit_answer(runtime, str(payload.get('user_input', '')))
            _sync_session(session, runtime)
            session_store.save_session(session)

            if result['status'] == 'reprompt':
                await websocket.send_json(_ws_event('error', session_id, {'message': 'unclear_input'}))
                continue
            if runtime.is_complete:
                recommendations = [asdict(item) for item in logic_rule_service.get_recommendations(runtime)]
                await websocket.send_json(_ws_event('completed', session_id, {'recommendations': recommendations}))
                continue
            question = logic_rule_service.get_current_question(runtime)
            if question:
                await websocket.send_json(_ws_event('question', session_id, question))
            else:
                recommendations = [asdict(item) for item in logic_rule_service.get_recommendations(runtime)]
                await websocket.send_json(_ws_event('completed', session_id, {'recommendations': recommendations}))
    except WebSocketDisconnect:
        session_store.unbind_websocket(session_id, 'assessment', str(id(websocket)))


@router.websocket('/ws/nursing/{session_id}')
async def nursing_ws(websocket: WebSocket, session_id: str) -> None:
    await websocket.accept()
    session_store = websocket.app.state.session_store
    nursing_rag_service = _get_nursing_rag_service(websocket)
    try:
        session_store.bind_websocket(session_id, 'nursing', str(id(websocket)))
    except SessionNotFoundError:
        await websocket.send_json(_ws_event('error', session_id, {'message': 'session_not_found'}))
        await websocket.close(code=1008)
        return
    try:
        while True:
            payload = await websocket.receive_json()
            if payload.get('type') != 'question':
                await websocket.send_json(_ws_event('error', session_id, {'message': 'unsupported_event'}))
                continue
            question = str(payload.get('question', '')).strip()
            await websocket.send_json(_ws_event('thinking_start', session_id, {}))
            result = nursing_rag_service.answer(question)
            session = session_store.get_session(session_id)
            session.current_flow = 'nursing_rag'
            session.nursing_qa_history.append(
                {'question': question, 'answer': result['answer'], 'contexts': result['contexts']}
            )
            session_store.save_session(session)

            await websocket.send_json(_ws_event('thinking_done', session_id, {}))

            chunks = [chunk.strip() for chunk in str(result['answer']).split('；') if chunk.strip()]
            if not chunks:
                chunks = [str(result['answer'])]
            for chunk in chunks:
                await websocket.send_json(_ws_event('answer_chunk', session_id, {'content': chunk}))
            await websocket.send_json(
                _ws_event(
                    'done',
                    session_id,
                    {},
                )
            )
    except WebSocketDisconnect:
        session_store.unbind_websocket(session_id, 'nursing', str(id(websocket)))
