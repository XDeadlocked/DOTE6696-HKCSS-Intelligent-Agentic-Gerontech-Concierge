from __future__ import annotations

from pydantic import BaseModel


class NursingQuestionRequest(BaseModel):
    session_id: str
    question: str


class NursingAnswerChunk(BaseModel):
    session_id: str
    content: str
    done: bool = False
