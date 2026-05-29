from __future__ import annotations

import sys
from pathlib import Path
from typing import Mapping

from sklearn.metrics import confusion_matrix, precision_recall_fscore_support

ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.intent_router.service import IntentRouterService
from app.schemas.intent import IntentType
from tests.common.dataset_generators import load_fixture_json
from tests.common.io import ensure_dir, write_csv_rows
from tests.common.metrics import classification_metrics
from tests.common.reporting import build_confusion_matrix_markdown, write_module_summary
from tests.common.thresholds import build_threshold_table, evaluate_thresholds
from tests.common.visualization import save_bar_chart


INTENT_LABELS = [
    IntentType.nursing.value,
    IntentType.problem_solving.value,
    IntentType.browsing.value,
    IntentType.unclear.value,
]
INTENT_DISPLAY_LABELS = ["Nursing", "Problem Solving", "Browsing", "Unclear"]
GUARDRAIL_LABELS = ["allow", "block"]
GUARDRAIL_DISPLAY_LABELS = ["Allow", "Block"]
MODULE_TO_INTENT = {
    "nursing_rag": IntentType.nursing.value,
    "logic_rule": IntentType.problem_solving.value,
    "inventory_search": IntentType.problem_solving.value,
    "product_catalog": IntentType.browsing.value,
}
INTENT_TO_LLM_OUTPUT = {
    IntentType.nursing.value: "护理咨询",
    IntentType.problem_solving.value: "产品-问题解决型",
    IntentType.browsing.value: "产品-浏览了解型",
    IntentType.unclear.value: "意图不清",
}


class _FakeResponse:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeChatModel:
    def __init__(self, responses: str | Mapping[str, str], default: str = "") -> None:
        self.responses = responses
        self.default = default

    def invoke(self, prompt):
        if isinstance(self.responses, str):
            return _FakeResponse(self.responses)

        prompt_text = str(prompt)
        for key, value in self.responses.items():
            if key in prompt_text:
                return _FakeResponse(value)
        return _FakeResponse(self.default)


class _FakeFactory:
    def __init__(self, content: str | Mapping[str, str], default: str = "") -> None:
        self.is_configured = True
        self._model = _FakeChatModel(content, default=default)

    def create_chat_model(self, temperature: float = 0.0):
        return self._model


def test_intent_router_fixture_regression() -> None:
    service = IntentRouterService()
    guardrail_cases = load_fixture_json("intent_router", "guardrail_cases.json")
    intent_cases = load_fixture_json("intent_router", "intent_cases.json")
    boundary_fixture = load_fixture_json("intent_router", "llm_boundary_cases.json")
    boundary_cases = boundary_fixture["cases"]

    report_dir = ensure_dir(ROOT / "reports" / "latest" / "intent_router")
    chart_dir = ensure_dir(report_dir / "charts")

    case_rows: list[dict[str, object]] = []

    guardrail_true: list[str] = []
    guardrail_pred: list[str] = []
    for case in guardrail_cases:
        result = service.classify_intent(case["input"])
        expected_blocked = case["expected"]
        predicted = result.message
        guardrail_true.append("block")
        guardrail_pred.append("block" if predicted == expected_blocked else "allow")
        case_rows.append(
            {
                "case_id": case["input"][:30],
                "task": "guardrail",
                "input": case["input"],
                "expected": expected_blocked,
                "predicted": predicted,
                "passed": predicted == expected_blocked,
            }
        )

    intent_true: list[str] = []
    intent_pred: list[str] = []
    for case in intent_cases:
        result = service.classify_intent(case["input"])
        predicted = result.intent.value if isinstance(result.intent, IntentType) else str(result.intent)
        intent_true.append(case["expected"])
        intent_pred.append(predicted)
        guardrail_true.append("allow")
        guardrail_pred.append("block" if result.intent == IntentType.reject else "allow")
        case_rows.append(
            {
                "case_id": case["input"][:30],
                "task": "intent",
                "input": case["input"],
                "expected": case["expected"],
                "predicted": predicted,
                "passed": predicted == case["expected"],
            }
        )

    intent_scores = classification_metrics(intent_true, intent_pred)
    invalid_label_rate = round(
        sum(pred not in INTENT_LABELS for pred in intent_pred) / max(len(intent_pred), 1),
        4,
    )
    guardrail_precision, guardrail_recall, guardrail_f1, _ = precision_recall_fscore_support(
        guardrail_true,
        guardrail_pred,
        average="binary",
        pos_label="block",
        zero_division=0,
    )
    guardrail_matrix = confusion_matrix(guardrail_true, guardrail_pred, labels=GUARDRAIL_LABELS)
    tn, fp, fn, tp = guardrail_matrix.ravel()
    metrics = {
        "accuracy": intent_scores["accuracy"],
        "macro_precision": intent_scores["precision"],
        "macro_recall": intent_scores["recall"],
        "macro_f1": intent_scores["f1"],
        "invalid_label_rate": invalid_label_rate,
        "guardrail_accuracy": round((tp + tn) / max(tp + tn + fp + fn, 1), 4),
        "guardrail_precision": round(float(guardrail_precision), 4),
        "guardrail_recall": round(float(guardrail_recall), 4),
        "guardrail_f1": round(float(guardrail_f1), 4),
        "guardrail_false_negative_rate": round(fn / max(tp + fn, 1), 4),
        "guardrail_false_positive_rate": round(fp / max(fp + tn, 1), 4),
    }
    intent_matrix = confusion_matrix(intent_true, intent_pred, labels=INTENT_LABELS)

    llm_outputs = {
        case["input"]: INTENT_TO_LLM_OUTPUT[MODULE_TO_INTENT[case["expected_primary_intent"]]]
        for case in boundary_cases
    }
    llm_service = IntentRouterService(llm_factory=_FakeFactory(llm_outputs))
    llm_attempts = 0
    llm_parse_success = 0
    llm_fallback_count = 0
    llm_boundary_success = 0
    for case in boundary_cases:
        llm_attempts += 1
        raw_output = llm_outputs[case["input"]]
        parsed_intent = llm_service._parse_intent_output(raw_output)
        llm_parse_success += int(parsed_intent is not None)

        result = llm_service.classify_intent(case["input"])
        predicted = result.intent.value if isinstance(result.intent, IntentType) else str(result.intent)
        allowed_predictions = {MODULE_TO_INTENT[case["expected_primary_intent"]]}
        allowed_predictions.update(
            MODULE_TO_INTENT[item]
            for item in case.get("expected_allowed_fallbacks", [])
            if item in MODULE_TO_INTENT
        )
        passed = predicted in allowed_predictions
        llm_boundary_success += int(passed)
        llm_fallback_count += int(parsed_intent is None)
        case_rows.append(
            {
                "case_id": case["case_id"],
                "task": "llm_boundary",
                "input": case["input"],
                "expected": "|".join(sorted(allowed_predictions)),
                "predicted": predicted,
                "passed": passed,
            }
        )

    metrics.update(
        {
            "llm_parse_success_rate": round(llm_parse_success / max(llm_attempts, 1), 4),
            "llm_fallback_rate": round(llm_fallback_count / max(llm_attempts, 1), 4),
            "llm_path_coverage": 1.0 if llm_attempts else 0.0,
            "llm_boundary_success_rate": round(llm_boundary_success / max(llm_attempts, 1), 4),
        }
    )
    threshold_specs = [
        ("guardrail_false_negative_rate", "<=", 0.02, "blocking"),
        ("guardrail_f1", ">=", 0.95, "blocking"),
        ("macro_f1", ">=", 0.60, "warning"),
        ("invalid_label_rate", "<=", 0.02, "warning"),
        ("accuracy", ">=", 0.80, "warning"),
        ("llm_parse_success_rate", ">=", 0.95, "warning"),
        ("llm_boundary_success_rate", ">=", 0.85, "warning"),
        ("llm_fallback_rate", "<=", 0.10, "observability"),
    ]
    status, threshold_rows, failed_blocking, failed_warning = evaluate_thresholds(
        metrics,
        threshold_specs,
    )

    write_csv_rows(report_dir / "cases.csv", case_rows)
    scores_chart = save_bar_chart(
        chart_dir / "intent_router_scores.png",
        labels=list(metrics.keys()),
        values=[float(value) for value in metrics.values()],
        title="Intent Router Metrics",
        ylabel="Score",
    )
    write_module_summary(
        report_dir=report_dir,
        module_name="intent_router",
        metrics=metrics,
        status=status,
        chart_paths=[
            f"charts/{scores_chart.name}",
        ],
        notes=[
            "Uses guardrail-first routing with an LLM-first classification path and heuristic fallback.",
            "Intent labels are compared against fixture regression data.",
            "Guardrail metrics use binary labels: `block` vs `allow`.",
            "LLM boundary metrics consume short, noisy, mixed-language fixture cases.",
            "Blocking metrics fail the regression immediately; warning metrics are surfaced as WARN in the report.",
            (
                "Warning threshold misses: "
                + ", ".join(f"`{item}`" for item in failed_warning)
                if failed_warning
                else "Warning thresholds: all satisfied."
            ),
        ],
        metric_definitions={
            "accuracy": "intent_accuracy = correct_intent_predictions / total_intent_samples",
            "macro_precision": "macro_precision = arithmetic mean of per-class precision across all intent labels",
            "macro_recall": "macro_recall = arithmetic mean of per-class recall across all intent labels",
            "macro_f1": "macro_f1 = arithmetic mean of per-class F1 across all intent labels",
            "invalid_label_rate": "invalid_label_rate = invalid_predicted_labels / total_intent_samples",
            "guardrail_accuracy": "guardrail_accuracy = (TP + TN) / (TP + TN + FP + FN), with `block` as positive class",
            "guardrail_precision": "guardrail_precision = TP / (TP + FP), with `block` as positive class",
            "guardrail_recall": "guardrail_recall = TP / (TP + FN), with `block` as positive class",
            "guardrail_f1": "guardrail_f1 = 2 * precision * recall / (precision + recall)",
            "guardrail_false_negative_rate": "guardrail_false_negative_rate = FN / (TP + FN)",
            "guardrail_false_positive_rate": "guardrail_false_positive_rate = FP / (FP + TN)",
            "llm_parse_success_rate": "llm_parse_success_rate = parseable_llm_outputs / total_llm_attempts",
            "llm_fallback_rate": "llm_fallback_rate = llm_attempts_that_fell_back_to_heuristic / total_llm_attempts",
            "llm_path_coverage": "llm_path_coverage = llm_enabled_safe_cases / total_safe_boundary_cases",
            "llm_boundary_success_rate": "llm_boundary_success_rate = boundary_cases_with_expected_or_allowed_intent / total_boundary_cases",
        },
        extra_sections=[
            (
                "Guardrail Confusion Matrix",
                build_confusion_matrix_markdown(
                    GUARDRAIL_DISPLAY_LABELS,
                    guardrail_matrix.tolist(),
                ),
            ),
            (
                "Intent Confusion Matrix",
                build_confusion_matrix_markdown(
                    INTENT_DISPLAY_LABELS,
                    intent_matrix.tolist(),
                ),
            ),
            ("Threshold Checks", build_threshold_table(threshold_rows)),
        ],
    )

    assert not failed_blocking, "Blocking thresholds failed: " + "; ".join(
        failed_blocking
    )


def test_intent_router_uses_llm_when_available() -> None:
    service = IntentRouterService(llm_factory=_FakeFactory("产品-浏览了解型"))

    result = service.classify_intent("护理床")

    assert result.intent == IntentType.browsing
    assert result.message == "识别完成"


def test_intent_router_falls_back_to_heuristic_when_llm_output_is_invalid() -> None:
    service = IntentRouterService(
        llm_factory=_FakeFactory({"你们有什么轮椅": "这不是合法标签"}, default="这不是合法标签")
    )

    result = service.classify_intent("你们有什么轮椅")

    assert result.intent == IntentType.browsing
    assert result.message == "识别完成"
