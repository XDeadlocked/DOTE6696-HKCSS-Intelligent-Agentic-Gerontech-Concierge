from __future__ import annotations

from pydantic import BaseModel


class FollowupQuestion(BaseModel):
    session_id: str
    device_tag: str
    question: str
    options: list[str]


class FollowupAnswerRequest(BaseModel):
    session_id: str
    device_tag: str
    answer: str
    nested_input: str | None = None


class FollowupResult(BaseModel):
    session_id: str
    device_tag: str
    recommendation: str | None = None
    redirect_to_human: bool = False
