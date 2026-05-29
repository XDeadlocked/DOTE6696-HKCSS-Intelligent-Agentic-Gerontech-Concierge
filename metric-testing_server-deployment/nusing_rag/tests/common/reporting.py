from __future__ import annotations

from pathlib import Path

from tabulate import tabulate

from tests.common.io import ensure_dir, write_csv_rows, write_json


def write_module_summary(
    report_dir: Path,
    module_name: str,
    metrics: dict[str, float | int | str],
    status: str,
    chart_paths: list[str] | None = None,
    notes: list[str] | None = None,
    metric_definitions: dict[str, str] | None = None,
    extra_sections: list[tuple[str, str]] | None = None,
) -> Path:
    ensure_dir(report_dir)
    metrics_table = tabulate(
        [[key, value] for key, value in metrics.items()],
        headers=["Metric", "Value"],
        tablefmt="github",
    )
    lines = [
        f"# {module_name}",
        "",
        f"- Status: `{status}`",
        "",
        "## Metrics",
        "",
        metrics_table,
    ]
    if metric_definitions:
        definition_table = tabulate(
            [[key, value] for key, value in metric_definitions.items()],
            headers=["Metric", "Calculation"],
            tablefmt="github",
        )
        lines.extend(["", "## Metric Definitions", "", definition_table])
    if extra_sections:
        for title, content in extra_sections:
            lines.extend(["", f"## {title}", "", content])
    if chart_paths:
        lines.extend(["", "## Charts", ""])
        lines.extend([f"![{Path(chart).stem}]({chart})" for chart in chart_paths])
    if notes:
        lines.extend(["", "## Notes", ""])
        lines.extend([f"- {note}" for note in notes])

    summary_path = report_dir / "summary.md"
    summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    write_json(report_dir / "metrics.json", metrics)
    return summary_path


def build_confusion_matrix_markdown(
    labels: list[str],
    matrix: list[list[int]],
) -> str:
    headers = ["Actual \\ Predicted", *labels]
    rows = [[labels[index], *row] for index, row in enumerate(matrix)]
    return tabulate(rows, headers=headers, tablefmt="github")


def write_latest_report(
    report_dir: Path,
    module_results: list[dict[str, object]],
    chart_paths: list[str] | None = None,
) -> Path:
    ensure_dir(report_dir)
    write_csv_rows(report_dir / "summary.csv", module_results)
    table = tabulate(
        [
            [item["module"], item["status"], item.get("details", "")]
            for item in module_results
        ],
        headers=["Module", "Status", "Details"],
        tablefmt="github",
    )
    lines = [
        "# Phase A Report",
        "",
        "## Summary",
        "",
        table,
    ]
    if chart_paths:
        lines.extend(["", "## Charts", ""])
        lines.extend([f"![{Path(chart).stem}]({chart})" for chart in chart_paths])

    report_path = report_dir / "report.md"
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    summary_lines = ["# Phase A Summary", ""]
    summary_lines.extend(
        [f"- `{item['module']}`: `{item['status']}`" for item in module_results]
    )
    (report_dir / "summary.md").write_text(
        "\n".join(summary_lines) + "\n",
        encoding="utf-8",
    )
    return report_path
