from __future__ import annotations

from fastapi import APIRouter

from app.api.routers.assessment import router as assessment_router
from app.api.routers.followup import router as followup_router
from app.api.routers.health import router as health_router
from app.api.routers.intent import router as intent_router
from app.api.routers.inventory import router as inventory_router
from app.api.routers.nursing import router as nursing_router
from app.api.routers.products import router as products_router
from app.api.routers.sessions import router as sessions_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(sessions_router)
api_router.include_router(intent_router)
api_router.include_router(assessment_router)
api_router.include_router(products_router)
api_router.include_router(nursing_router)
api_router.include_router(followup_router)
api_router.include_router(inventory_router)
