from __future__ import annotations

from fastapi import APIRouter, Request

from app.schemas.common import HealthResponse

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponse)
def health(request: Request) -> HealthResponse:
    settings = request.app.state.settings
    llm_factory = request.app.state.llm_factory
    return HealthResponse(
        status="ok",
        app_name=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
        session_backend=settings.session_backend,
        llm_configured=llm_factory.is_configured,
    )
