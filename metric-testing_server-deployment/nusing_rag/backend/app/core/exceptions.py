from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class AppError(Exception):
    message: str
    code: str = "app_error"
    status_code: int = 400
    details: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return self.message


class ConfigError(AppError):
    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            message=message,
            code="config_error",
            status_code=500,
            details=details or {},
        )


class NotFoundError(AppError):
    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            message=message,
            code="not_found",
            status_code=404,
            details=details or {},
        )


class SessionNotFoundError(NotFoundError):
    def __init__(self, session_id: str) -> None:
        super().__init__(
            message=f"Session '{session_id}' not found",
            details={"session_id": session_id},
        )


class ExternalServiceUnavailable(AppError):
    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            message=message,
            code="external_service_unavailable",
            status_code=503,
            details=details or {},
        )
