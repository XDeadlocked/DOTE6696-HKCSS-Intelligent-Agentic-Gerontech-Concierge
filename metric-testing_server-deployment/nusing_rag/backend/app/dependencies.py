from __future__ import annotations

from fastapi import Depends, Request

from app.conversation_orchestrator.service import ConversationOrchestratorService
from app.core.config import Settings
from app.core.llm_client import LLMClientFactory
from app.device_followup.service import DeviceFollowupService
from app.intent_router.service import IntentRouterService
from app.inventory_search.service import InventorySearchService
from app.logic_rule.service import LogicRuleService
from app.nursing_rag.service import NursingRagService
from app.product_catalog.service import ProductCatalogService
from app.session_store.service import SessionStoreService


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_session_store(request: Request) -> SessionStoreService:
    return request.app.state.session_store


def get_llm_factory(request: Request) -> LLMClientFactory:
    return request.app.state.llm_factory


def get_intent_router(
    llm_factory: LLMClientFactory = Depends(get_llm_factory),
) -> IntentRouterService:
    return IntentRouterService(llm_factory=llm_factory)


def get_logic_rule_service(
) -> LogicRuleService:
    return LogicRuleService()


def get_device_followup_service() -> DeviceFollowupService:
    return DeviceFollowupService()


def get_product_catalog_service() -> ProductCatalogService:
    return ProductCatalogService()


def get_inventory_search_service(
    llm_factory: LLMClientFactory = Depends(get_llm_factory),
) -> InventorySearchService:
    return InventorySearchService(llm_factory=llm_factory)


def get_nursing_rag_service(
    llm_factory: LLMClientFactory = Depends(get_llm_factory),
) -> NursingRagService:
    return NursingRagService(llm_factory=llm_factory)


def get_conversation_orchestrator(
    session_store: SessionStoreService = Depends(get_session_store),
    llm_factory: LLMClientFactory = Depends(get_llm_factory),
) -> ConversationOrchestratorService:
    return ConversationOrchestratorService(
        intent_router=IntentRouterService(llm_factory=llm_factory),
        logic_rule=LogicRuleService(),
        inventory_search=InventorySearchService(llm_factory=llm_factory),
        nursing_rag=NursingRagService(llm_factory=llm_factory),
        session_store=session_store,
    )
