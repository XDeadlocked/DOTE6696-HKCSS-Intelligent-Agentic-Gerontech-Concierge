from __future__ import annotations

from pydantic import BaseModel


class SessionStoreStats(BaseModel):
    backend: str
    active_sessions: int
