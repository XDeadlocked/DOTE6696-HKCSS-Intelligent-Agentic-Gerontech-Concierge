from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.device_followup.service import DeviceFollowupService
from tests.common.dataset_generators import load_fixture_json
from tests.common.io import ensure_dir, write_csv_rows
from tests.common.reporting import write_module_summary
from tests.common.thresholds import build_threshold_table, evaluate_thresholds
from tests.common.visualization import save_bar_chart


def test_device_followup_fixture_regression() -> None:
    service = DeviceFollowupService()
    fixture = load_fixture_json("device_followup", "device_followup_cases.json")

    report_dir = ensure_dir(ROOT / "reports" / "latest" / "device_followup")
    chart_dir = ensure_dir(report_dir / "charts")

    case_rows: list[dict[str, object]] = []

    initial_pass = 0
    for case in fixture["initial_cases"]:
        result = service.answer(case["tag"], case["choice_label"])
        expected_behavior = case["expected_behavior"]
        predicted_behavior = result["status"] if result["status"] != "recommendation" else "recommend"
        if result["status"] == "no_product":
            predicted_behavior = "no_product"
        if result["status"] == "redirect":
            predicted_behavior = "redirect"
        passed = predicted_behavior == expected_behavior
        if expected_behavior == "recommend":
            passed = passed and result.get("recommend") == case["expected_recommend"]
        initial_pass += int(passed)
        case_rows.append(
            {
                "case_id": case["case_id"],
                "task": "initial",
                "expected": expected_behavior,
                "predicted": predicted_behavior,
                "passed": passed,
            }
        )

    nested_pass = 0
    for case in fixture["nested_cases"]:
        result = service.answer(case["tag"], case["choice_label"], nested_input=case["sub_choice_label"])
        passed = (
            result["status"] == "recommendation"
            and result.get("recommend") == case["expected_recommend"]
        )
        nested_pass += int(passed)
        case_rows.append(
            {
                "case_id": case["case_id"],
                "task": "nested",
                "expected": case["expected_recommend"],
                "predicted": result.get("recommend"),
                "passed": passed,
            }
        )

    fallback_pass = 0
    for case in fixture["fallback_cases"]:
        result = service.answer(case["tag"], case["free_text"])
        passed = result["status"] == "inventory_search"
        fallback_pass += int(passed)
        case_rows.append(
            {
                "case_id": case["case_id"],
                "task": "fallback",
                "expected": case["expected_behavior"],
                "predicted": result["status"],
                "passed": passed,
            }
        )

    metrics = {
        "followup_routing_accuracy": round(initial_pass / max(len(fixture["initial_cases"]), 1), 4),
        "nested_branch_accuracy": round(nested_pass / max(len(fixture["nested_cases"]), 1), 4),
        "fallback_inventory_trigger_rate": round(fallback_pass / max(len(fixture["fallback_cases"]), 1), 4),
    }
    threshold_specs = [
        ("followup_routing_accuracy", "=", 1.00, "blocking"),
        ("nested_branch_accuracy", "=", 1.00, "blocking"),
        ("fallback_inventory_trigger_rate", ">=", 0.95, "warning"),
    ]
    status, threshold_rows, failed_blocking, failed_warning = evaluate_thresholds(
        metrics,
        threshold_specs,
    )

    write_csv_rows(report_dir / "cases.csv", case_rows)
    chart = save_bar_chart(
        chart_dir / "device_followup_scores.png",
        labels=list(metrics.keys()),
        values=[float(value) for value in metrics.values()],
        title="Device Followup Metrics",
        ylabel="Score",
    )
    write_module_summary(
        report_dir=report_dir,
        module_name="device_followup",
        metrics=metrics,
        status=status,
        chart_paths=[f"charts/{chart.name}"],
        notes=[
            "Covers recommend, nested, no-product, redirect, and fallback flows.",
            "Blocking metrics fail the regression immediately; warning metrics are surfaced as WARN in the report.",
            (
                "Warning threshold misses: "
                + ", ".join(f"`{item}`" for item in failed_warning)
                if failed_warning
                else "Warning thresholds: all satisfied."
            ),
        ],
        metric_definitions={
            "followup_routing_accuracy": "followup_routing_accuracy = correctly_routed_first_level_cases / total_initial_cases",
            "nested_branch_accuracy": "nested_branch_accuracy = correctly_resolved_nested_cases / total_nested_cases",
            "fallback_inventory_trigger_rate": "fallback_inventory_trigger_rate = successful_inventory_fallbacks / total_fallback_cases",
        },
        extra_sections=[
            ("Threshold Checks", build_threshold_table(threshold_rows)),
        ],
    )

    assert not failed_blocking, "Blocking thresholds failed: " + "; ".join(
        failed_blocking
    )
