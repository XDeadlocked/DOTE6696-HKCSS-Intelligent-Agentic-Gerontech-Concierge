from __future__ import annotations

import math
import re
import sys
import time
from functools import lru_cache
from pathlib import Path

from ragas import EvaluationDataset, evaluate
from ragas.metrics import Faithfulness, ResponseRelevancy, SimpleCriteriaScore
from ragas.metrics.base import MetricOutputType, MetricType
from rouge_score import rouge_scorer

ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import get_settings
from app.core.embedding_model import get_embedding_function
from app.core.llm_client import LLMClientFactory
from app.nursing_rag.service import NursingRagService
from tests.common.dataset_generators import load_fixture_json
from tests.common.io import ensure_dir, write_csv_rows
from tests.common.metrics import average, safe_round
from tests.common.ragas_eval import build_openrouter_evaluator
from tests.common.reporting import write_module_summary
from tests.common.thresholds import build_threshold_table, evaluate_thresholds
from tests.common.visualization import save_bar_chart


def _normalize_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "")).strip()


def _overlap_ratio(expected: str, actual: str) -> float:
    expected_tokens = {
        token
        for token in re.split(r"[，,。；;：:\s/()\[\]【】\-]+", _normalize_text(expected))
        if len(token) >= 2
    }
    if not expected_tokens:
        return 0.0
    actual_text = _normalize_text(actual)
    hits = sum(1 for token in expected_tokens if token in actual_text)
    return hits / len(expected_tokens)


def _percentile_95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, math.ceil(len(ordered) * 0.95) - 1)
    return ordered[index]


def _safe_float(value: object) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return 0.0
    if math.isnan(score):
        return 0.0
    return score


@lru_cache(maxsize=1)
def _get_local_embeddings():
    return get_embedding_function()


def _cosine_similarity(left: str, right: str) -> float:
    if not _normalize_text(left) or not _normalize_text(right):
        return 0.0
    embeddings = _get_local_embeddings()
    left_vector, right_vector = embeddings.embed_documents([left, right])
    dot = sum(x * y for x, y in zip(left_vector, right_vector))
    left_norm = math.sqrt(sum(x * x for x in left_vector))
    right_norm = math.sqrt(sum(x * x for x in right_vector))
    if not left_norm or not right_norm:
        return 0.0
    return dot / (left_norm * right_norm)


def _build_live_service() -> NursingRagService:
    settings = get_settings()
    llm_factory = LLMClientFactory(settings)
    if not llm_factory.is_configured:
        raise RuntimeError(
            "backend/.env must provide OPENROUTER_API_KEY so nursing_rag can be evaluated with the live generation path."
        )
    return NursingRagService(llm_factory=llm_factory)


def _build_completeness_metric() -> SimpleCriteriaScore:
    return SimpleCriteriaScore(
        name="response_completeness",
        definition=(
            "Score from 0 to 1 whether the response fully answers the user's question, "
            "covers the key actionable points in the reference answer, and avoids omitting "
            "important guidance supported by the retrieved contexts."
        ),
        required_columns={
            MetricType.SINGLE_TURN: {
                "user_input",
                "response",
                "reference",
                "retrieved_contexts",
            }
        },
        output_type=MetricOutputType.CONTINUOUS,
        strictness=1,
    )


def _run_online_judge(
    cases: list[dict[str, object]],
) -> tuple[list[dict[str, float]], dict[str, float], str]:
    evaluator_llm, settings = build_openrouter_evaluator()
    embeddings = _get_local_embeddings()
    dataset = EvaluationDataset.from_list(
        [
            {
                "user_input": str(case["question"]),
                "response": str(case["answer"]),
                "reference": str(case["ground_truth"]),
                "retrieved_contexts": list(case["contexts"]),
            }
            for case in cases
        ]
    )
    results = evaluate(
        dataset=dataset,
        metrics=[
            Faithfulness(),
            ResponseRelevancy(),
            _build_completeness_metric(),
        ],
        llm=evaluator_llm,
        embeddings=embeddings,
        raise_exceptions=False,
        show_progress=False,
        batch_size=4,
    )
    dataframe = results.to_pandas()
    score_rows: list[dict[str, float]] = []
    groundedness_scores: list[float] = []
    answer_relevance_scores: list[float] = []
    completeness_scores: list[float] = []

    for row in dataframe.to_dict(orient="records"):
        groundedness = _safe_float(row.get("faithfulness"))
        answer_relevance = _safe_float(row.get("answer_relevancy"))
        completeness = _safe_float(row.get("response_completeness"))
        groundedness_scores.append(groundedness)
        answer_relevance_scores.append(answer_relevance)
        completeness_scores.append(completeness)
        score_rows.append(
            {
                "groundedness_judge": groundedness,
                "answer_relevance_judge": answer_relevance,
                "response_completeness_judge": completeness,
            }
        )

    return (
        score_rows,
        {
            "groundedness_judge_score": average(groundedness_scores),
            "answer_relevance_judge_score": average(answer_relevance_scores),
            "response_completeness_judge_score": average(completeness_scores),
        },
        settings["evaluation_model"],
    )


class _FakeResponse:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeChatModel:
    def __init__(self, content: str) -> None:
        self.content = content

    def invoke(self, _messages):
        return _FakeResponse(self.content)


class _FakeFactory:
    def __init__(self, content: str) -> None:
        self.is_configured = True
        self._model = _FakeChatModel(content)

    def create_chat_model(self, temperature: float = 0.0):
        return self._model


class _FakeRepository:
    def search(self, _question: str, top_k: int = 3):
        return [
            {
                "rowid": 1,
                "score": 0.42,
                "content": "协助长者翻身前先说明动作，并保护肩膀和髋部，再缓慢侧身，避免猛拉。",
                "title": "翻身协助",
            }
        ][:top_k]


def test_nursing_rag_evalset_regression() -> None:
    service = _build_live_service()
    fixture = load_fixture_json("nursing_rag", "nursing_rag_evalset.json")
    evalset = fixture["evalset"]
    medical_reject_cases = fixture["medical_reject_cases"]
    knowledge_fallback_cases = fixture["knowledge_fallback_cases"]
    judge_cases = fixture["judge_cases"]

    report_dir = ensure_dir(ROOT / "reports" / "latest" / "nursing_rag")
    chart_dir = ensure_dir(report_dir / "charts")
    scorer = rouge_scorer.RougeScorer(["rougeL"], use_stemmer=False)

    case_rows: list[dict[str, object]] = []
    retrieval_non_empty: list[float] = []
    reference_support_scores: list[float] = []
    answer_relevancy_scores: list[float] = []
    faithfulness_scores: list[float] = []
    rouge_scores: list[float] = []
    answer_latencies_ms: list[float] = []

    for case in evalset:
        start = time.perf_counter()
        result = service.answer(case["question"], top_k=3)
        answer_latencies_ms.append((time.perf_counter() - start) * 1000)
        retrievals = result["retrievals"]
        contexts = result["contexts"]
        answer = _normalize_text(result["answer"])

        retrieved_rowids = [item["rowid"] for item in retrievals]
        retrieval_non_empty.append(float(bool(retrievals)))

        joined_context = "\n".join(contexts)
        reference_support = _overlap_ratio(case["reference_context"], joined_context)
        answer_relevancy = _cosine_similarity(case["ground_truth"], answer)
        faithfulness = _cosine_similarity(answer, joined_context)
        rouge_l = scorer.score(case["ground_truth"], answer)["rougeL"].fmeasure

        reference_support_scores.append(reference_support)
        answer_relevancy_scores.append(answer_relevancy)
        faithfulness_scores.append(faithfulness)
        rouge_scores.append(rouge_l)

        case_rows.append(
            {
                "case_id": case["case_id"],
                "question": case["question"],
                "reference_rowid": case["reference_rowid"],
                "top_rowid": retrieved_rowids[0] if retrieved_rowids else None,
                "retrieval_non_empty": bool(retrievals),
                "reference_support_proxy": safe_round(reference_support),
                "answer_relevancy_proxy": safe_round(answer_relevancy),
                "faithfulness_proxy": safe_round(faithfulness),
                "rouge_l_f1": safe_round(rouge_l),
            }
        )

    medical_reject_pass = 0
    for case in medical_reject_cases:
        start = time.perf_counter()
        result = service.answer(case["question"], top_k=3)
        answer_latencies_ms.append((time.perf_counter() - start) * 1000)
        answer = _normalize_text(result["answer"])
        passed = (
            result["status"] in {"medical_reject", "no_result"}
            and "专业医生" in answer
            and ("复康护士" in answer or "康复护士" in answer)
        )
        medical_reject_pass += int(passed)
        case_rows.append(
            {
                "case_id": case["case_id"],
                "question": case["question"],
                "task": "medical_reject",
                "expected_behavior": case["expected_behavior"],
                "predicted_status": result["status"],
                "passed": passed,
            }
        )

    knowledge_fallback_pass = 0
    for case in knowledge_fallback_cases:
        start = time.perf_counter()
        result = service.answer(case["question"], top_k=3)
        answer_latencies_ms.append((time.perf_counter() - start) * 1000)
        answer = _normalize_text(result["answer"])
        passed = (
            result["status"] == "no_result"
            and "暂未收录" in answer
            and ("复康护士" in answer or "康复护士" in answer)
        )
        knowledge_fallback_pass += int(passed)
        case_rows.append(
            {
                "case_id": case["case_id"],
                "question": case["question"],
                "task": "knowledge_fallback",
                "expected_behavior": case["expected_behavior"],
                "predicted_status": result["status"],
                "passed": passed,
            }
        )

    judge_payloads: list[dict[str, object]] = []
    for case in judge_cases:
        start = time.perf_counter()
        result = service.answer(case["question"], top_k=3)
        answer_latencies_ms.append((time.perf_counter() - start) * 1000)
        judge_payloads.append(
            {
                "case_id": case["case_id"],
                "question": case["question"],
                "ground_truth": case["ground_truth"],
                "answer": _normalize_text(result["answer"]),
                "contexts": list(result["contexts"]),
            }
        )

    judge_rows, judge_metrics, evaluator_model = _run_online_judge(judge_payloads)
    for case, score_row in zip(judge_cases, judge_rows, strict=True):
        groundedness = score_row["groundedness_judge"]
        answer_relevance = score_row["answer_relevance_judge"]
        completeness = score_row["response_completeness_judge"]
        case_rows.append(
            {
                "case_id": case["case_id"],
                "question": case["question"],
                "task": "judge_review",
                "groundedness_judge": safe_round(groundedness),
                "answer_relevance_judge": safe_round(answer_relevance),
                "response_completeness_judge": safe_round(completeness),
                "passed": groundedness >= 0.8 and answer_relevance >= 0.8 and completeness >= 0.75,
            }
        )

    metrics = {
        "retrieval_non_empty_rate": average(retrieval_non_empty),
        "reference_support_proxy": average(reference_support_scores),
        "answer_relevancy_proxy": average(answer_relevancy_scores),
        "faithfulness_proxy": average(faithfulness_scores),
        "rouge_l_f1": average(rouge_scores),
        "medical_reject_accuracy": round(
            medical_reject_pass / max(len(medical_reject_cases), 1),
            4,
        ),
        "knowledge_fallback_accuracy": round(
            knowledge_fallback_pass / max(len(knowledge_fallback_cases), 1),
            4,
        ),
        "groundedness_judge_score": judge_metrics["groundedness_judge_score"],
        "answer_relevance_judge_score": judge_metrics["answer_relevance_judge_score"],
        "response_completeness_judge_score": judge_metrics["response_completeness_judge_score"],
        "p95_latency_ms": safe_round(_percentile_95(answer_latencies_ms)),
    }
    threshold_specs = [
        ("retrieval_non_empty_rate", ">=", 0.95, "blocking"),
        ("faithfulness_proxy", ">=", 0.60, "blocking"),
        ("medical_reject_accuracy", "=", 1.00, "blocking"),
        ("knowledge_fallback_accuracy", ">=", 0.95, "blocking"),
        ("reference_support_proxy", ">=", 0.20, "warning"),
        ("answer_relevancy_proxy", ">=", 0.40, "warning"),
        ("groundedness_judge_score", ">=", 0.75, "warning"),
        ("answer_relevance_judge_score", ">=", 0.85, "warning"),
        ("response_completeness_judge_score", ">=", 0.80, "warning"),
    ]
    threshold_rows: list[dict[str, object]] = []
    status, threshold_rows, failed_blocking, failed_warning = evaluate_thresholds(
        metrics,
        threshold_specs,
    )

    write_csv_rows(report_dir / "cases.csv", case_rows)
    chart = save_bar_chart(
        chart_dir / "nursing_rag_scores.png",
        labels=list(metrics.keys()),
        values=[float(value) for value in metrics.values()],
        title="Nursing RAG Metrics",
        ylabel="Score",
    )
    write_module_summary(
        report_dir=report_dir,
        module_name="nursing_rag",
        metrics=metrics,
        status=status,
        chart_paths=[f"charts/{chart.name}"],
        notes=[
            "Retrieval uses Chroma persisted vectors with the shared embedding function from app.core.",
            "Answer generation uses the live business path with the backend OpenRouter configuration when contexts are available.",
            "Medical reject and knowledge fallback fixtures are evaluated separately from normal-answer samples.",
            f"Judge metrics are executed with ragas over OpenRouter using evaluator model `{evaluator_model}` and local HuggingFace embeddings.",
            "Blocking metrics fail the regression immediately; warning metrics are still executed and surfaced as WARN in the report.",
            (
                "Warning threshold misses: "
                + ", ".join(f"`{item}`" for item in failed_warning)
                if failed_warning
                else "Warning thresholds: all satisfied."
            ),
        ],
        metric_definitions={
            "retrieval_non_empty_rate": "retrieval_non_empty_rate = cases_with_non_empty_retrievals / total_cases",
            "reference_support_proxy": "reference_support_proxy = mean(keyword_overlap(reference_context, retrieved_contexts))",
            "answer_relevancy_proxy": "answer_relevancy_proxy = mean(cosine_similarity(local_embedding(ground_truth), local_embedding(generated_answer)))",
            "faithfulness_proxy": "faithfulness_proxy = mean(cosine_similarity(local_embedding(generated_answer), local_embedding(retrieved_contexts)))",
            "rouge_l_f1": "rouge_l_f1 = mean(ROUGE-L F1 between ground_truth and generated_answer)",
            "medical_reject_accuracy": "medical_reject_accuracy = correctly_rejected_medical_cases / total_medical_reject_cases",
            "knowledge_fallback_accuracy": "knowledge_fallback_accuracy = correctly_fallback_cases / total_knowledge_fallback_cases",
            "groundedness_judge_score": "groundedness_judge_score = mean(ragas Faithfulness(answer, retrieved_contexts))",
            "answer_relevance_judge_score": "answer_relevance_judge_score = mean(ragas ResponseRelevancy(question, answer))",
            "response_completeness_judge_score": "response_completeness_judge_score = mean(ragas SimpleCriteriaScore(question, answer, reference, retrieved_contexts))",
            "p95_latency_ms": "p95_latency_ms = 95th percentile of end-to-end service.answer latency in milliseconds",
        },
        extra_sections=[
            ("Threshold Checks", build_threshold_table(threshold_rows)),
        ],
    )

    assert not failed_blocking, "Blocking thresholds failed: " + "; ".join(
        failed_blocking
    )


def test_nursing_rag_uses_llm_generation_when_available() -> None:
    service = NursingRagService(
        repository=_FakeRepository(),
        llm_factory=_FakeFactory("先安抚长者，再托住肩髋缓慢翻身，避免硬拉。"),
    )

    result = service.answer("如何帮助老人翻身？")

    assert result["status"] == "answered"
    assert "先安抚长者" in result["answer"]
    assert "溫馨提示" in result["answer"]


class _FakeFailingChatModel:
    def invoke(self, _messages):
        raise RuntimeError("simulated_llm_failure")


class _FakeFailingFactory:
    def __init__(self) -> None:
        self.is_configured = True
        self._model = _FakeFailingChatModel()

    def create_chat_model(self, temperature: float = 0.0):
        return self._model


class _FakeUnconfiguredFactory:
    def __init__(self) -> None:
        self.is_configured = False

    def create_chat_model(self, temperature: float = 0.0):
        return None


UNAVAILABLE_MESSAGE = "抱歉，此服務暫不可用。"


def test_nursing_rag_service_unavailable_when_llm_fails() -> None:
    service = NursingRagService(
        repository=_FakeRepository(),
        llm_factory=_FakeFailingFactory(),
    )

    result = service.answer("如何帮助老人翻身？")

    assert result["status"] == "service_unavailable"
    assert result["answer"] == UNAVAILABLE_MESSAGE


def test_nursing_rag_service_unavailable_when_llm_not_configured() -> None:
    service = NursingRagService(
        repository=_FakeRepository(),
        llm_factory=_FakeUnconfiguredFactory(),
    )

    result = service.answer("如何帮助老人翻身？")

    assert result["status"] == "service_unavailable"
    assert result["answer"] == UNAVAILABLE_MESSAGE


def test_nursing_rag_no_safety_suffix_when_service_unavailable() -> None:
    service = NursingRagService(
        repository=_FakeRepository(),
        llm_factory=_FakeFailingFactory(),
    )

    result = service.answer("如何帮助老人翻身？")

    assert "溫馨提示" not in result["answer"]
    assert result["answer"] == UNAVAILABLE_MESSAGE
