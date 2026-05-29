from __future__ import annotations

from enum import Enum

from pydantic import BaseModel


class IntentType(str, Enum):
    nursing = "护理咨询"
    problem_solving = "产品-问题解决型"
    browsing = "产品-浏览了解型"
    unclear = "意图不清"
    reject = "拒答"


class IntentClassifyRequest(BaseModel):
    session_id: str | None = None
    user_input: str


class IntentResult(BaseModel):
    intent: IntentType | str
    is_safe: bool = True
    message: str = "识别完成"
    confidence: float | None = None
