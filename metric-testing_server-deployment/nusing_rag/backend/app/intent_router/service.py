from __future__ import annotations

from app.core.llm_client import LLMClientFactory
from app.intent_router.classifier import HeuristicIntentClassifier
from app.intent_router.guardrail import GuardrailService
from app.intent_router.prompts import BLOCKED_RESPONSE, INTENT_CLASSIFY_PROMPT
from app.schemas.intent import IntentResult, IntentType


class IntentRouterService:
    """Intent routing service with deterministic guardrail-first logic."""

    def __init__(
        self,
        guardrail: GuardrailService | None = None,
        classifier: HeuristicIntentClassifier | None = None,
        llm_factory: LLMClientFactory | None = None,
    ) -> None:
        self.guardrail = guardrail or GuardrailService()
        self.classifier = classifier or HeuristicIntentClassifier()
        self.llm_factory = llm_factory

    def classify_intent(self, user_input: str) -> IntentResult:
        guardrail_result = self.guardrail.check(user_input)
        if guardrail_result.blocked:
            return IntentResult(
                intent=IntentType.reject,
                is_safe=False,
                message=guardrail_result.message or BLOCKED_RESPONSE,
                confidence=1.0,
            )

        llm_intent = self._classify_with_llm(user_input)
        if llm_intent is not None:
            return IntentResult(
                intent=llm_intent,
                is_safe=True,
                message="识别完成" if llm_intent != IntentType.unclear else "未能识别明确意图",
                confidence=0.95,
            )

        decision = self.classifier.classify(user_input)
        return IntentResult(
            intent=decision.intent,
            is_safe=True,
            message="识别完成" if decision.intent != IntentType.unclear else "未能识别明确意图",
            confidence=decision.confidence,
        )

    def _classify_with_llm(self, user_input: str) -> IntentType | None:
        if not self.llm_factory or not self.llm_factory.is_configured:
            return None

        chat_model = self.llm_factory.create_chat_model(temperature=0.0)
        if chat_model is None:
            return None

        prompt = INTENT_CLASSIFY_PROMPT.format(user_input=user_input.strip())
        try:
            response = chat_model.invoke(prompt)
        except Exception:
            return None

        output = str(getattr(response, "content", response)).strip()
        return self._parse_intent_output(output)

    def _parse_intent_output(self, output: str) -> IntentType | None:
        normalized = output.strip()
        if not normalized:
            return None
        if BLOCKED_RESPONSE in normalized:
            return IntentType.reject
        if "护理咨询" in normalized:
            return IntentType.nursing
        if "产品-问题解决型" in normalized:
            return IntentType.problem_solving
        if "产品-浏览了解型" in normalized:
            return IntentType.browsing
        if "意图不清" in normalized:
            return IntentType.unclear
        return None
