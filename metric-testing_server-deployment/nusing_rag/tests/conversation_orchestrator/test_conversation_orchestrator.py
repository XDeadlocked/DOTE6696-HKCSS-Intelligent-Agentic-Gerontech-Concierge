from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.conversation_orchestrator.service import ConversationOrchestratorService
from tests.common.dataset_generators import load_fixture_json
from tests.common.io import ensure_dir, write_csv_rows
from tests.common.metrics import average, safe_round
from tests.common.reporting import write_module_summary
from tests.common.thresholds import build_threshold_table, evaluate_thresholds
from tests.common.visualization import save_bar_chart


def _is_subsequence(expected: list[str], actual: list[str]) -> bool:
    if not expected:
        return True
    cursor = 0
    for item in actual:
        if item == expected[cursor]:
            cursor += 1
            if cursor == len(expected):
                return True
    return False


def test_conversation_orchestrator_scenarios() -> None:
    service = ConversationOrchestratorService()
    fixture = load_fixture_json("conversation_orchestrator", "orchestrator_scenarios.json")

    report_dir = ensure_dir(ROOT / "reports" / "latest" / "conversation_orchestrator")
    chart_dir = ensure_dir(report_dir / "charts")

    case_rows: list[dict[str, object]] = []
    route_scores: list[float] = []
    e2e_scores: list[float] = []
    sequence_scores: list[float] = []
    session_scores: list[float] = []
    resilience_scores: list[float] = []

    for case in fixture["scenarios"]:
        result = service.handle_user_input(case["user_input"])
        route = result["route"]
        expected_route = case["expected_route"]
        route_ok = float(route == expected_route)
        e2e_ok = float(
            result["final_module"] == case["expected_final_module"]
            and result["response_type"] == case["expected_response_type"]
        )
        sequence_ok = float(route and route[0] == "intent_router" and route[-1] == result["final_module"])
        session_ok = float(bool(result["session_id"]))

        route_scores.append(route_ok)
        e2e_scores.append(e2e_ok)
        sequence_scores.append(sequence_ok)
        session_scores.append(session_ok)

        case_rows.append(
            {
                "scenario_id": case["scenario_id"],
                "user_input": case["user_input"],
                "expected_route": " -> ".join(expected_route),
                "actual_route": " -> ".join(route),
                "expected_final_module": case["expected_final_module"],
                "actual_final_module": result["final_module"],
                "expected_response_type": case["expected_response_type"],
                "actual_response_type": result["response_type"],
                "route_match": bool(route_ok),
                "e2e_success": bool(e2e_ok),
                "sequence_valid": bool(sequence_ok),
                "session_consistent": bool(session_ok),
            }
        )

    for case in fixture.get("llm_resilience_scenarios", []):
        result = service.handle_user_input(case["user_input"])
        route = result["route"]
        subsequence_ok = float(_is_subsequence(case["expected_route"], route))
        resilience_ok = float(
            subsequence_ok
            and result["final_module"] == case["expected_final_module"]
            and bool(result["session_id"])
            and result["output"] is not None
        )
        resilience_scores.append(resilience_ok)
        case_rows.append(
            {
                "scenario_id": case["scenario_id"],
                "user_input": case["user_input"],
                "task": "llm_resilience",
                "expected_route": " -> ".join(case["expected_route"]),
                "actual_route": " -> ".join(route),
                "expected_final_module": case["expected_final_module"],
                "actual_final_module": result["final_module"],
                "expected_response_type": case["expected_response_type"],
                "actual_response_type": result["response_type"],
                "route_match": bool(subsequence_ok),
                "e2e_success": bool(resilience_ok),
                "sequence_valid": bool(route and route[0] == "intent_router"),
                "session_consistent": bool(result["session_id"]),
            }
        )

    metrics = {
        "route_accuracy": average(route_scores),
        "end_to_end_success_rate": average(e2e_scores),
        "event_sequence_validity": average(sequence_scores),
        "session_consistency_rate": average(session_scores),
        "llm_resilience_success_rate": average(resilience_scores),
    }
    threshold_specs = [
        ("route_accuracy", ">=", 0.95, "blocking"),
        ("end_to_end_success_rate", ">=", 0.90, "blocking"),
        ("event_sequence_validity", "=", 1.00, "blocking"),
        ("session_consistency_rate", "=", 1.00, "blocking"),
        ("llm_resilience_success_rate", ">=", 0.95, "warning"),
    ]
    status, threshold_rows, failed_blocking, failed_warning = evaluate_thresholds(
        metrics,
        threshold_specs,
    )

    write_csv_rows(report_dir / "cases.csv", case_rows)
    chart = save_bar_chart(
        chart_dir / "conversation_orchestrator_scores.png",
        labels=list(metrics.keys()),
        values=[float(value) for value in metrics.values()],
        title="Conversation Orchestrator Metrics",
        ylabel="Score",
    )
    write_module_summary(
        report_dir=report_dir,
        module_name="conversation_orchestrator",
        metrics=metrics,
        status=status,
        chart_paths=[f"charts/{chart.name}"],
        notes=[
            "Scenarios cover blocked inputs, nursing consultation, product browsing, and problem-solving recommendation flows.",
            "Session consistency checks that each orchestration result is bound to a persisted session identifier.",
            "LLM resilience scenarios verify that orchestration still reaches the expected downstream module when an LLM path degrades.",
            "Blocking metrics fail the regression immediately; warning metrics are surfaced as WARN in the report.",
            (
                "Warning threshold misses: "
                + ", ".join(f"`{item}`" for item in failed_warning)
                if failed_warning
                else "Warning thresholds: all satisfied."
            ),
        ],
        metric_definitions={
            "route_accuracy": "route_accuracy = scenarios_with_exact_expected_route / total_scenarios",
            "end_to_end_success_rate": "end_to_end_success_rate = scenarios_with_expected_final_module_and_response_type / total_scenarios",
            "event_sequence_validity": "event_sequence_validity = scenarios_where_route_starts_with_intent_router_and_ends_with_final_module / total_scenarios",
            "session_consistency_rate": "session_consistency_rate = scenarios_with_non_empty_session_id / total_scenarios",
            "llm_resilience_success_rate": "llm_resilience_success_rate = resilience_scenarios_with_expected_route_subsequence_and_final_module / total_resilience_scenarios",
        },
        extra_sections=[
            ("Threshold Checks", build_threshold_table(threshold_rows)),
        ],
    )

    assert not failed_blocking, "Blocking thresholds failed: " + "; ".join(
        failed_blocking
    )
