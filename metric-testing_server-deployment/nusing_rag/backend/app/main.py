from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.router import api_router
from app.api.websocket import router as websocket_router
from app.core.config import get_settings
from app.core.exceptions import AppError, SessionNotFoundError
from app.core.llm_client import LLMClientFactory
from app.core.app_logging import configure_logging, get_logger
from app.session_store.service import build_session_store, build_cleanup_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
    logger = get_logger(__name__)

    app.state.settings = settings
    app.state.llm_factory = LLMClientFactory(settings)
    app.state.session_store = build_session_store(settings)
    app.state.cleanup_scheduler = build_cleanup_scheduler(
        app.state.session_store, hour=3, minute=0
    )
    if app.state.cleanup_scheduler:
        await app.state.cleanup_scheduler.start()

    logger.info(
        "Application resources initialized",
        extra={
            "session_ttl_minutes": settings.session_ttl_minutes,
            "llm_configured": app.state.llm_factory.is_configured,
        },
    )
    yield
    if app.state.cleanup_scheduler:
        await app.state.cleanup_scheduler.stop()
    logger.info("Application shutdown complete")


def create_app() -> FastAPI:
    settings = get_settings()
    frontend_dir = Path(__file__).resolve().parents[2] / "frontend"
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        lifespan=lifespan,
    )
    app.include_router(api_router, prefix=settings.api_v1_prefix)
    app.include_router(websocket_router)
    if frontend_dir.exists():
        app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")

    @app.exception_handler(SessionNotFoundError)
    async def handle_session_not_found(
        request: Request,
        exc: SessionNotFoundError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content={"detail": str(exc), "error_type": "session_not_found"},
        )

    @app.exception_handler(AppError)
    async def handle_application_error(
        request: Request,
        exc: AppError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "detail": str(exc),
                "error_type": exc.code,
                "details": exc.details,
            },
        )

    return app


app = create_app()

# if __name__ == "__main__":
#     import uvicorn
#     app = create_app()

#     uvicorn.run(app, host="0.0.0.0", port=8000)
