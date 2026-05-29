from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AssessmentQuestion(BaseModel):
    session_id: str
    node_id: str
    question: str
    options: list[str] = Field(default_factory=list)
    allows_free_text: bool = False


class AssessmentAnswerRequest(BaseModel):
    session_id: str
    answer: str
    answer_index: int | None = None


class AssessmentWsEvent(BaseModel):
    event: str
    payload: dict[str, Any] = Field(default_factory=dict)
