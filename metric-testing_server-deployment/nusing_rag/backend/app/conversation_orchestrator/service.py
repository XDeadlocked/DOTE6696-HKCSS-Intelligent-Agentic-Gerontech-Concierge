from __future__ import annotations

from typing import Any

from app.core.llm_client import LLMClientFactory
from app.intent_router.service import IntentRouterService
from app.logic_rule.service import LogicRuleService
from app.product_catalog.service import ProductCatalogService
from app.inventory_search.service import InventorySearchService
from app.nursing_rag.service import NursingRagService
from app.schemas.intent import IntentType
from app.session_store.service import SessionStoreService, build_session_store
from app.core.config import get_settings


class ConversationOrchestratorService:
    def __init__(
        self,
        intent_router: IntentRouterService | None = None,
        logic_rule: LogicRuleService | None = None,
        product_catalog: ProductCatalogService | None = None,
        inventory_search: InventorySearchService | None = None,
        nursing_rag: NursingRagService | None = None,
        session_store: SessionStoreService | None = None,
        llm_factory: LLMClientFactory | None = None,
    ) -> None:
        self.intent_router = intent_router or IntentRouterService(llm_factory=llm_factory)
        self.logic_rule = logic_rule or LogicRuleService()
        self.product_catalog = product_catalog or ProductCatalogService()
        self.inventory_search = inventory_search or InventorySearchService(llm_factory=llm_factory)
        self.nursing_rag = nursing_rag or NursingRagService(llm_factory=llm_factory)
        self.session_store = session_store or build_session_store(get_settings())

    def handle_user_input(self, user_input: str, session_id: str | None = None) -> dict[str, Any]:
        state = (
            self.session_store.get_session(session_id)
            if session_id
            else self.session_store.create_session()
        )
        state.history_messages.append({"role": "user", "content": user_input})  # type: ignore[arg-type]

        intent_result = self.intent_router.classify_intent(user_input)
        state.intent = str(intent_result.intent)

        if intent_result.intent == IntentType.reject:
            result = {
                "session_id": state.session_id,
                "route": ["intent_router"],
                "final_module": "intent_router",
                "response_type": "blocked",
                "output": intent_result.message,
            }
            state.current_flow = "blocked"
            self._append_assistant_message(state, intent_result.message)
            self.session_store.save_session(state)
            return result

        if intent_result.intent == IntentType.nursing:
            rag_result = self.nursing_rag.answer(user_input)
            state.current_flow = "nursing_rag"
            state.nursing_qa_history.append(
                {
                    "question": user_input,
                    "answer": rag_result["answer"],
                    "contexts": rag_result["contexts"],
                }
            )
            self._append_assistant_message(state, str(rag_result["answer"]))
            self.session_store.save_session(state)
            return {
                "session_id": state.session_id,
                "route": ["intent_router", "nursing_rag"],
                "final_module": "nursing_rag",
                "response_type": "rag_answer",
                "output": rag_result["answer"],
                "contexts": rag_result["contexts"],
            }

        if intent_result.intent == IntentType.browsing:
            catalog_result = self.product_catalog.browse_category(query=user_input, page=1, page_size=5)
            category = catalog_result["category"]
            items = catalog_result["items"]
            state.current_flow = "product_catalog"
            state.browse_selected_category = category.category_name if category else None
            state.browse_viewed_products = [item.product_name for item in items]
            summary = {
                "category": category.category_name if category else None,
                "items": [item.model_dump() for item in items],
            }
            self._append_assistant_message(state, f"已返回 {len(items)} 个产品浏览结果。")
            self.session_store.save_session(state)
            return {
                "session_id": state.session_id,
                "route": ["intent_router", "product_catalog"],
                "final_module": "product_catalog",
                "response_type": "catalog_list",
                "output": summary,
            }

        if intent_result.intent == IntentType.problem_solving:
            logic_state = self.logic_rule.start_session()
            question_payload = self.logic_rule.get_current_question(logic_state)
            inventory_result = self.inventory_search.search(
                query=user_input,
                top_k=5,
                mode="semantic_rerank",
            )
            followup_result = {
                "status": "inventory_search",
                "trigger_inventory_search": True,
                "tag": "",
                "category": "",
                "user_choice": user_input,
            }
            state.current_flow = "inventory_search"
            if question_payload:
                state.logic_rule_qa_history.append(question_payload)
            state.followup_results.append(followup_result)
            state.collected_recommendations = [item.model_dump() for item in inventory_result.items[:3]]
            self._append_assistant_message(state, f"已返回 {len(inventory_result.items)} 个推荐结果。")
            self.session_store.save_session(state)
            return {
                "session_id": state.session_id,
                "route": ["intent_router", "logic_rule", "device_followup", "inventory_search"],
                "final_module": "inventory_search",
                "response_type": "product_recommendation",
                "output": {
                    "question": question_payload,
                    "followup": followup_result,
                    "items": [item.model_dump() for item in inventory_result.items],
                },
            }

        self._append_assistant_message(state, "未能识别明确意图")
        self.session_store.save_session(state)
        return {
            "session_id": state.session_id,
            "route": ["intent_router"],
            "final_module": "intent_router",
            "response_type": "clarification",
            "output": "未能识别明确意图",
        }

    def _append_assistant_message(self, state: Any, content: str) -> None:
        state.history_messages.append({"role": "assistant", "content": content})  # type: ignore[arg-type]
