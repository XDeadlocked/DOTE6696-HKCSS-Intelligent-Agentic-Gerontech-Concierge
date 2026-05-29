from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: str
    content: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SessionState(BaseModel):
    session_id: str
    current_flow: str = "idle"
    current_node_id: str | None = None
    intent: str | None = None
    selected_answers: list[str] = Field(default_factory=list)
    device_tag: str | None = None
    logic_pending_branches: list[str] = Field(default_factory=list)
    logic_is_complete: bool = False
    history_messages: list[ChatMessage] = Field(default_factory=list)
    logic_rule_qa_history: list[dict[str, object]] = Field(default_factory=list)
    collected_recommendations: list[dict[str, object]] = Field(default_factory=list)
    browse_selected_category: str | None = None
    browse_viewed_products: list[str] = Field(default_factory=list)
    nursing_qa_history: list[dict[str, object]] = Field(default_factory=list)
    followup_results: list[dict[str, object]] = Field(default_factory=list)
    websocket_bindings: dict[str, list[str]] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @classmethod
    def new(cls, session_id: str | None = None) -> "SessionState":
        return cls(session_id=session_id or str(uuid4()))


class SessionCreateResponse(BaseModel):
    session_id: str
    expires_in_seconds: int


class SessionSummary(BaseModel):
    session_id: str
    current_flow: str
    current_node_id: str | None = None
    intent: str | None = None
    browse_selected_category: str | None = None
    browse_viewed_products: list[str] = Field(default_factory=list)
    nursing_turns: int = 0
    logic_turns: int = 0
    followup_count: int = 0
