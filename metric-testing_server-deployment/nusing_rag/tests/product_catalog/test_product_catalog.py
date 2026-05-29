from __future__ import annotations

import html
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.product_catalog.service import ProductCatalogService
from tests.common.dataset_generators import load_fixture_json
from tests.common.io import ensure_dir, write_csv_rows
from tests.common.reporting import write_module_summary
from tests.common.thresholds import build_threshold_table, evaluate_thresholds
from tests.common.visualization import save_bar_chart


def _normalize_excerpt_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", html.unescape(value or "")).strip()


def test_product_catalog_fixture_regression() -> None:
    service = ProductCatalogService()
    fixture = load_fixture_json("product_catalog", "product_catalog_cases.json")

    report_dir = ensure_dir(ROOT / "reports" / "latest" / "product_catalog")
    chart_dir = ensure_dir(report_dir / "charts")

    case_rows: list[dict[str, object]] = []

    category_pass = 0
    for case in fixture["category_browse_cases"]:
        result = service.browse_category(query=case["query"], page=1, page_size=5)
        category = result["category"]
        items = result["items"]
        passed = bool(
            category
            and category.category_name == case["expected_category_name"]
            and category.category_id == case["expected_category_id"]
            and len(items) >= case["expected_min_results"]
        )
        category_pass += int(passed)
        case_rows.append(
            {
                "case_id": case["case_id"],
                "task": "category_browse",
                "expected": case["expected_category_name"],
                "predicted": category.category_name if category else None,
                "passed": passed,
            }
        )

    detail_pass = 0
    excerpt_pass_count = 0
    total_expected_fields = 0
    filled_expected_fields = 0
    for case in fixture["product_detail_cases"]:
        detail = service.get_product_detail(case["query"])
        field_values = {
            "product_name": detail.product_name if detail else None,
            "category_name": detail.category_name if detail else None,
            "description": detail.description if detail else None,
            "sales_price": detail.sales_price if detail else None,
        }
        excerpt = _normalize_excerpt_text(case["expected_description_excerpt"])
        description_text = _normalize_excerpt_text(detail.description if detail else None)
        excerpt_pass = not excerpt or excerpt in description_text
        excerpt_pass_count += int(excerpt_pass)
        passed = bool(
            detail
            and detail.product_name == case["expected_product_name"]
            and detail.category_name == case["expected_category_name"]
        )
        detail_pass += int(passed)

        expected_fields = case["expected_fields"]
        total_expected_fields += len(expected_fields)
        filled_expected_fields += sum(
            1 for field in expected_fields if field_values.get(field) not in (None, "")
        )

        case_rows.append(
            {
                "case_id": case["case_id"],
                "task": "product_detail",
                "expected": case["expected_product_name"],
                "predicted": detail.product_name if detail else None,
                "passed": passed,
            }
        )

    pagination_pass = 0
    for case in fixture["pagination_cases"]:
        result = service.browse_category(
            category_name=case["category_name"],
            page=case["page"],
            page_size=case["page_size"],
        )
        expected_item_count = min(
            case["page_size"],
            case["expected_total_items"],
        )
        passed = bool(
            result["total_items"] == case["expected_total_items"]
            and result["total_pages"] == case["expected_total_pages"]
            and len(result["items"]) == expected_item_count
        )
        pagination_pass += int(passed)
        case_rows.append(
            {
                "case_id": case["case_id"],
                "task": "pagination",
                "expected": case["expected_total_pages"],
                "predicted": result["total_pages"],
                "passed": passed,
            }
        )

    metrics = {
        "category_match_accuracy": round(
            category_pass / max(len(fixture["category_browse_cases"]), 1),
            4,
        ),
        "product_detail_exact_match_rate": round(
            detail_pass / max(len(fixture["product_detail_cases"]), 1),
            4,
        ),
        "description_excerpt_match_rate": round(
            excerpt_pass_count / max(len(fixture["product_detail_cases"]), 1),
            4,
        ),
        "detail_field_completeness": round(
            filled_expected_fields / max(total_expected_fields, 1),
            4,
        ),
        "pagination_correctness": round(
            pagination_pass / max(len(fixture["pagination_cases"]), 1),
            4,
        ),
        "null_field_rate": round(
            1 - (filled_expected_fields / max(total_expected_fields, 1)),
            4,
        ),
    }
    threshold_specs = [
        ("category_match_accuracy", ">=", 0.98, "blocking"),
        ("product_detail_exact_match_rate", ">=", 0.95, "blocking"),
        ("pagination_correctness", "=", 1.00, "blocking"),
        ("detail_field_completeness", ">=", 0.95, "warning"),
    ]
    status, threshold_rows, failed_blocking, failed_warning = evaluate_thresholds(
        metrics,
        threshold_specs,
    )

    write_csv_rows(report_dir / "cases.csv", case_rows)
    chart = save_bar_chart(
        chart_dir / "product_catalog_scores.png",
        labels=list(metrics.keys()),
        values=[float(value) for value in metrics.values()],
        title="Product Catalog Metrics",
        ylabel="Score",
    )
    write_module_summary(
        report_dir=report_dir,
        module_name="product_catalog",
        metrics=metrics,
        status=status,
        chart_paths=[f"charts/{chart.name}"],
        notes=[
            "Category browse cases resolve category from natural-language queries.",
            "Detail cases validate exact product retrieval and expected field presence.",
            "Blocking metrics fail the regression immediately; warning metrics are surfaced as WARN in the report.",
            (
                "Warning threshold misses: "
                + ", ".join(f"`{item}`" for item in failed_warning)
                if failed_warning
                else "Warning thresholds: all satisfied."
            ),
        ],
        metric_definitions={
            "category_match_accuracy": "category_match_accuracy = correctly_resolved_category_queries / total_category_browse_cases",
            "product_detail_exact_match_rate": "product_detail_exact_match_rate = exact_product_detail_hits / total_product_detail_cases",
            "description_excerpt_match_rate": "description_excerpt_match_rate = cases_with_expected_excerpt_found_in_description / total_product_detail_cases",
            "detail_field_completeness": "detail_field_completeness = non_empty_expected_fields / total_expected_fields",
            "pagination_correctness": "pagination_correctness = correct_pagination_cases / total_pagination_cases",
            "null_field_rate": "null_field_rate = empty_expected_fields / total_expected_fields",
        },
        extra_sections=[
            ("Threshold Checks", build_threshold_table(threshold_rows)),
        ],
    )

    assert not failed_blocking, "Blocking thresholds failed: " + "; ".join(
        failed_blocking
    )
