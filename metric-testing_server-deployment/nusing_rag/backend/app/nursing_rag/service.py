from __future__ import annotations

import re
from typing import Any

from app.core.llm_client import LLMClientFactory

from .repository import NursingKnowledgeRepository, extract_keywords, normalize_text


MEDICAL_REJECTION = (
    "抱歉，我無法提供醫療診斷、治療及用藥相關建議，請您諮詢專業醫生或復康護士，獲取專業醫療指導。"
)
KNOWLEDGE_FALLBACK = (
    "抱歉，目前的護理知識庫中暫未收錄關於此問題的資料。建議您諮詢專業醫生或復康護士。"
)
SAFETY_SUFFIX = "溫馨提示：以上建議僅供長者護理參考，不替代專業醫療意見。"
UNAVAILABLE_MESSAGE = "抱歉，此服務暫不可用。"
NURSING_RELEVANCE_THRESHOLD = 0.25
LOW_RELEVANCE_THRESHOLD = 0.10
NURSING_CONSULT_SYSTEM_PROMPT = """# 角色：專業長者護理顧問
# 核心任務：你是一名專業的護理顧問，基於提供的【參考知識】解答用戶的長者護理、輔具使用規範及健康照護問題。
# 回答要求：
1. 必須使用繁體中文（香港用語）輸出所有內容。
2. 優先依據【參考知識】作答。如果參考知識不夠完整但問題屬於安全的長者照護範疇（如輔具使用、體位擺放、日常護理注意事項），請大膽基於護理常識做補充，不要因為知識庫不完整就拒絕回答。
3. 只有當用戶問題完全超出長者照護範疇（例如詢問不相關的科技、娛樂、旅遊等），才輸出：抱歉，目前的護理知識庫中暫未收錄關於此問題的資料。建議您諮詢專業醫生或復康護士。
4. 不提供疾病診斷、治療方案、藥物建議。
5. 不進行商業推銷，只提供護理和輔具使用建議。
6. 輸出簡潔、清晰、可執行，不要添加寒暄和額外免責聲明。
# 排版格式要求（重要）：
- 每個段落之間必須使用空行分隔，確保閱讀清晰。
- 若回答包含多個要點，請使用「- 」或「1. 」開頭的列表格式，每項單獨一行。
- 使用 **粗體** 標註關鍵術語或重要提醒。
- 不要使用代碼塊（```），直接輸出純文字格式。
- 段落不要太長，每 2-3 句換一個段落。
"""
NURSING_CONSULT_USER_TEMPLATE = """【参考知识】
{context}

【用户问题】
{user_input}

请严格基于参考知识回答。"""

LOW_CONFIDENCE_USER_TEMPLATE = """【参考知识（相关度较低，请更加谨慎地使用）】
{context}

【用户问题】
{user_input}

参考知识相关度较低。如果参考知识确实无法支持完整回答，请输出：抱歉，目前的护理知识库中暂未收录关于此问题的资料。建议您咨询专业医生或复康护士。"""


def split_sentences(text: str) -> list[str]:
    raw_parts = re.split(r"[。！？!?；;]\s*", normalize_text(text))
    return [part.strip(" ，,") for part in raw_parts if part.strip()]


def normalize_markdown_whitespace(text: str) -> str:
    lines = text.split("\n")
    cleaned = []
    for line in lines:
        stripped = line.strip()
        if stripped:
            cleaned.append(stripped)
    result = "\n".join(cleaned).strip()
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result


def lexical_overlap_ratio(left: str, right: str) -> float:
    left_keywords = set(extract_keywords(left))
    right_keywords = set(extract_keywords(right))
    if not left_keywords:
        return 0.0
    return len(left_keywords & right_keywords) / len(left_keywords)


class NursingRagService:
    def __init__(
        self,
        repository: NursingKnowledgeRepository | None = None,
        llm_factory: LLMClientFactory | None = None,
    ) -> None:
        self.repository = repository or NursingKnowledgeRepository()
        self.llm_factory = llm_factory

    def retrieve(self, question: str, top_k: int = 3) -> list[dict[str, Any]]:
        return self.repository.search(question, top_k=top_k)

    def answer(self, question: str, top_k: int = 3) -> dict[str, Any]:
        if self._looks_like_medical_diagnosis(question):
            return {
                "answer": MEDICAL_REJECTION,
                "contexts": [],
                "retrievals": [],
                "status": "medical_reject",
            }

        retrievals = self.retrieve(question, top_k=top_k)
        if not retrievals or float(retrievals[0]["score"]) < LOW_RELEVANCE_THRESHOLD:
            return {
                "answer": KNOWLEDGE_FALLBACK,
                "contexts": [],
                "retrievals": retrievals,
                "status": "no_result",
            }

        contexts = [str(item["content"]) for item in retrievals]
        top_score = float(retrievals[0]["score"])
        low_confidence = top_score < NURSING_RELEVANCE_THRESHOLD
        answer_body = self._compose_answer(question, retrievals, low_confidence=low_confidence)

        if answer_body == UNAVAILABLE_MESSAGE:
            return {
                "answer": answer_body,
                "contexts": contexts,
                "retrievals": retrievals,
                "status": "service_unavailable",
            }

        return {
            "answer": f"{answer_body}\n\n{SAFETY_SUFFIX}",
            "contexts": contexts,
            "retrievals": retrievals,
            "status": "answered",
        }

    def _compose_answer(
        self,
        question: str,
        retrievals: list[dict[str, Any]],
        low_confidence: bool = False,
    ) -> str:
        llm_answer = self._compose_answer_with_llm(question, retrievals, low_confidence=low_confidence)
        if llm_answer:
            return llm_answer
        return UNAVAILABLE_MESSAGE

    def _compose_answer_with_llm(
        self,
        question: str,
        retrievals: list[dict[str, Any]],
        low_confidence: bool = False,
    ) -> str | None:
        if not self.llm_factory or not self.llm_factory.is_configured:
            return None

        chat_model = self.llm_factory.create_chat_model(temperature=0.1)
        if chat_model is None:
            return None

        context_text = "\n\n".join(
            f"参考 {index + 1}: {str(item['content']).strip()}"
            for index, item in enumerate(retrievals)
        )
        template = LOW_CONFIDENCE_USER_TEMPLATE if low_confidence else NURSING_CONSULT_USER_TEMPLATE
        prompt = template.format(
            context=context_text,
            user_input=question.strip(),
        )
        messages = [
            ("system", NURSING_CONSULT_SYSTEM_PROMPT),
            ("human", prompt),
        ]
        try:
            response = chat_model.invoke(messages)
        except Exception:
            return None

        answer = str(getattr(response, "content", response)).strip()
        if not answer:
            return None
        if KNOWLEDGE_FALLBACK in answer:
            return KNOWLEDGE_FALLBACK

        answer = self._strip_safety_lines(answer)
        answer = self._strip_safety_suffix(answer)
        answer = normalize_markdown_whitespace(answer)
        return answer or None

    def _strip_safety_suffix(self, text: str) -> str:
        stripped = text.strip()
        suffix_variants = [
            SAFETY_SUFFIX,
            "溫馨提示：以上建議僅供長者護理參考，不替代專業醫療意見，如有健康相關疑問，請及時諮詢醫護人員。",
            "温馨提示：以上建议仅供长者护理参考，不替代专业医疗意见，如有健康相关疑问，请及时咨询医护人员。",
        ]
        for suffix in suffix_variants:
            if stripped.endswith(suffix):
                stripped = stripped[: -len(suffix)].rstrip(" \n；;，,")
        return stripped

    def _strip_safety_lines(self, text: str) -> str:
        lines = text.split("\n")
        kept = [
            line
            for line in lines
            if not line.strip().startswith("温馨提示") and not line.strip().startswith("溫馨提示")
        ]
        return "\n".join(kept).strip()

    def _looks_like_medical_diagnosis(self, question: str) -> bool:
        markers = [
            "是甚麼病", "是什麼病", "是什么病",
            "吃甚麼藥", "吃什麼藥", "吃什么药",
            "治療", "治疗",
            "診斷", "诊断",
            "病因",
            "嚴不嚴重", "严不严重",
            "能活多久",
            "安眠藥", "安眠药",
        ]
        text = normalize_text(question)
        return any(marker in text for marker in markers)
