from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.logic_rule.service import LogicRuleService
from tests.common.dataset_generators import load_fixture_json
from tests.common.io import ensure_dir, write_csv_rows
from tests.common.reporting import write_module_summary
from tests.common.thresholds import build_threshold_table, evaluate_thresholds
from tests.common.visualization import save_bar_chart


def test_logic_rule_fixture_regression() -> None:
    service = LogicRuleService()
    fixture = load_fixture_json("logic_rule", "logic_rule_cases.json")

    report_dir = ensure_dir(ROOT / "reports" / "latest" / "logic_rule")
    chart_dir = ensure_dir(report_dir / "charts")

    case_rows: list[dict[str, object]] = []
    transition_pass = 0
    for case in fixture["transition_cases"]:
        next_nodes = service.engine.get_next_nodes(case["current_node"], case["selected_options"])
        passed = next_nodes == case["expected_next_nodes"]
        transition_pass += int(passed)
        case_rows.append(
            {
                "case_id": case["case_id"],
                "task": "transition",
                "expected": "|".join(case["expected_next_nodes"]),
                "predicted": "|".join(next_nodes),
                "passed": passed,
            }
        )

    invalid_pass = 0
    for case in fixture["invalid_input_cases"]:
        state = service.start_session()
        state.current_node = case["current_node"]
        result = service.submit_answer(state, case["invalid_user_input"])
        passed = result["status"] == "reprompt"
        invalid_pass += int(passed)
        case_rows.append(
            {
                "case_id": case["case_id"],
                "task": "invalid_input",
                "expected": case["expected_behavior"],
                "predicted": result["status"],
                "passed": passed,
            }
        )

    scenario_pass = 0
    for case in fixture["scenario_cases"]:
        state = service.start_session()
        for step in case["steps"]:
            state.current_node = step["node_id"]
            service.submit_answer(state, step["selected_options"][0])
        recommendations = service.get_recommendations(state)
        device_tags = [item.device_tag for item in recommendations]
        passed = case["expected_device_tag"] in device_tags
        scenario_pass += int(passed)
        case_rows.append(
            {
                "case_id": case["scenario_id"],
                "task": "scenario",
                "expected": case["expected_device_tag"],
                "predicted": ",".join(device_tags),
                "passed": passed,
            }
        )

    presentation_cases = fixture["presentation_cases"]
    question_cases = [case for case in presentation_cases if case["presentation_type"] == "question"]
    recommendation_cases = [case for case in presentation_cases if case["presentation_type"] == "recommendation"]
    presentation_service = LogicRuleService()

    question_present_success = 0
    recommendation_present_success = 0
    local_rule_exact_match_count = 0
    for case in question_cases:
        state = presentation_service.start_session()
        state.current_node = case["node_id"]
        payload = presentation_service.get_current_question(state)
        presented = str(payload["question"]) if payload else ""
        passed = bool(presented.strip())
        question_present_success += int(passed)
        local_rule_exact_match_count += int(presented == case["original_text"])
        case_rows.append(
            {
                "case_id": case["case_id"],
                "task": "question_presentation",
                "expected": case["expected_behavior"],
                "predicted": presented,
                "passed": passed,
            }
        )

    for case in recommendation_cases:
        state = presentation_service.start_session()
        state.collected_recommendations = [case["terminal_node"]]
        recommendations = presentation_service.get_recommendations(state)
        presented = recommendations[0].content if recommendations else ""
        passed = bool(presented.strip())
        recommendation_present_success += int(passed)
        local_rule_exact_match_count += int(presented == case["original_text"])
        case_rows.append(
            {
                "case_id": case["case_id"],
                "task": "recommendation_presentation",
                "expected": case["expected_behavior"],
                "predicted": presented,
                "passed": passed,
            }
        )

    metrics = {
        "node_transition_accuracy": round(transition_pass / max(len(fixture["transition_cases"]), 1), 4),
        "invalid_input_recovery_rate": round(invalid_pass / max(len(fixture["invalid_input_cases"]), 1), 4),
        "scenario_success_rate": round(scenario_pass / max(len(fixture["scenario_cases"]), 1), 4),
        "question_presentation_success_rate": round(
            question_present_success / max(len(question_cases), 1),
            4,
        ),
        "recommendation_presentation_success_rate": round(
            recommendation_present_success / max(len(recommendation_cases), 1),
            4,
        ),
        "local_rule_exact_match_rate": round(
            local_rule_exact_match_count / max(len(presentation_cases), 1),
            4,
        ),
    }
    threshold_specs = [
        ("node_transition_accuracy", "=", 1.00, "blocking"),
        ("scenario_success_rate", ">=", 0.95, "blocking"),
        ("invalid_input_recovery_rate", ">=", 0.95, "warning"),
        ("question_presentation_success_rate", ">=", 0.99, "warning"),
        ("recommendation_presentation_success_rate", ">=", 0.99, "warning"),
        ("local_rule_exact_match_rate", "=", 1.00, "observability"),
    ]
    status, threshold_rows, failed_blocking, failed_warning = evaluate_thresholds(
        metrics,
        threshold_specs,
    )

    write_csv_rows(report_dir / "cases.csv", case_rows)
    chart = save_bar_chart(
        chart_dir / "logic_rule_scores.png",
        labels=list(metrics.keys()),
        values=[float(value) for value in metrics.values()],
        title="Logic Rule Metrics",
        ylabel="Score",
    )
    write_module_summary(
        report_dir=report_dir,
        module_name="logic_rule",
        metrics=metrics,
        status=status,
        chart_paths=[f"charts/{chart.name}"],
        notes=[
            "Uses dictionary-based node transition instead of vector retrieval.",
            "Covers transitions, invalid input recovery, and full scenarios.",
            "Presentation metrics validate direct rendering from the local rule tree without LLM rewriting.",
            "Blocking metrics fail the regression immediately; warning metrics are surfaced as WARN in the report.",
            (
                "Warning threshold misses: "
                + ", ".join(f"`{item}`" for item in failed_warning)
                if failed_warning
                else "Warning thresholds: all satisfied."
            ),
        ],
        metric_definitions={
            "node_transition_accuracy": "node_transition_accuracy = correctly_matched_next_nodes / total_transition_cases",
            "invalid_input_recovery_rate": "invalid_input_recovery_rate = successful_reprompt_recoveries / total_invalid_input_cases",
            "scenario_success_rate": "scenario_success_rate = successful_end_to_end_scenarios / total_scenario_cases",
            "question_presentation_success_rate": "question_presentation_success_rate = non_empty_question_presentations / total_question_presentation_cases",
            "recommendation_presentation_success_rate": "recommendation_presentation_success_rate = non_empty_recommendation_presentations / total_recommendation_presentation_cases",
            "local_rule_exact_match_rate": "local_rule_exact_match_rate = presentations_equal_to_original_rule_text / total_presentation_cases",
        },
        extra_sections=[
            ("Threshold Checks", build_threshold_table(threshold_rows)),
        ],
    )

    assert not failed_blocking, "Blocking thresholds failed: " + "; ".join(
        failed_blocking
    )


def test_logic_rule_uses_local_rule_text_for_question_and_recommendation() -> None:
    service = LogicRuleService()
    state = service.start_session()

    question = service.get_current_question(state)
    recommend_id = next(iter(service.engine.recommend_nodes))
    state.collected_recommendations = [recommend_id]
    recommendations = service.get_recommendations(state)

    assert question is not None
    assert question["question"] == question["raw_question"]
    assert recommendations[0].content == service.engine.recommend_nodes[recommend_id]["content"]
