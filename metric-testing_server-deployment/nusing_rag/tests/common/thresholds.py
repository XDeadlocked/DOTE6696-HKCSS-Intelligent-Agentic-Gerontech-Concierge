from __future__ import annotations

import math
from typing import TypedDict


class ThresholdRow(TypedDict):
    metric: str
    operator: str
    expected: float
    level: str
    actual: float
    result: str


ThresholdSpec = tuple[str, str, float, str]


def passes_threshold(actual: float, operator: str, expected: float) -> bool:
    if operator == ">=":
        return actual >= expected
    if operator == "<=":
        return actual <= expected
    if operator == "=":
        return math.isclose(actual, expected, abs_tol=1e-9)
    raise ValueError(f"Unsupported threshold operator: {operator}")


def evaluate_thresholds(
    metrics: dict[str, float | int],
    threshold_specs: list[ThresholdSpec],
) -> tuple[str, list[ThresholdRow], list[str], list[str]]:
    threshold_rows: list[ThresholdRow] = []
    failed_blocking: list[str] = []
    failed_warning: list[str] = []

    for metric_name, operator, expected, level in threshold_specs:
        actual = float(metrics[metric_name])
        passed = passes_threshold(actual, operator, expected)
        result = "PASS"
        if not passed and level == "blocking":
            result = "FAIL"
            failed_blocking.append(
                f"{metric_name}={actual:.4f} ({operator} {expected:.2f})"
            )
        elif not passed and level == "warning":
            result = "WARN"
            failed_warning.append(
                f"{metric_name}={actual:.4f} ({operator} {expected:.2f})"
            )

        threshold_rows.append(
            {
                "metric": metric_name,
                "operator": operator,
                "expected": expected,
                "level": level,
                "actual": actual,
                "result": result,
            }
        )

    status = "FAIL" if failed_blocking else "WARN" if failed_warning else "PASS"
    return status, threshold_rows, failed_blocking, failed_warning


def build_threshold_table(rows: list[ThresholdRow]) -> str:
    lines = [
        "| Metric | Threshold | Level | Actual | Result |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        lines.append(
            f"| `{row['metric']}` | `{row['operator']} {row['expected']:.2f}` | "
            f"{row['level']} | `{row['actual']:.4f}` | {row['result']} |"
        )
    return "\n".join(lines)
