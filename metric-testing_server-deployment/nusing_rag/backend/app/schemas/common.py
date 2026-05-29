from __future__ import annotations

from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    code: str
    message: str
    details: dict[str, object] = Field(default_factory=dict)


class HealthResponse(BaseModel):
    status: str
    app_name: str
    version: str
    environment: str
    session_backend: str
    llm_configured: bool
