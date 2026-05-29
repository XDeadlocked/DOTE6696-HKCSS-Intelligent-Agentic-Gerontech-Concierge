from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.inventory_search.service import InventorySearchService
from tests.common.dataset_generators import load_fixture_json
from tests.common.io import ensure_dir, write_csv_rows
from tests.common.reporting import write_module_summary
from tests.common.thresholds import build_threshold_table, evaluate_thresholds
from tests.common.visualization import save_bar_chart


def _rank_of_first_relevant(names: list[str], relevant: set[str]) -> int | None:
    for index, name in enumerate(names, start=1):
        if name in relevant:
            return index
    return None


def _ndcg_at_k(rank: int | None, k: int) -> float:
    if rank is None or rank > k:
        return 0.0
    return 1.0 / math.log2(rank + 1)


class _FakeResponse:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeChatModel:
    def __init__(self, content: str) -> None:
        self.content = content

    def invoke(self, _prompt):
        return _FakeResponse(self.content)


class _FakeFactory:
    def __init__(self, content: str) -> None:
        self.is_configured = True
        self._model = _FakeChatModel(content)

    def create_chat_model(self, temperature: float = 0.0):
        return self._model


class _FakeRepository:
    def __init__(self) -> None:
        self._items = [
            {
                "product_name": "普通助行杖",
                "category_name": "智能看护",
                "category_id": "watch",
                "description": "用于日常步行辅助",
                "stock_status": "有货",
                "in_stock": True,
                "source_index": 0,
            },
            {
                "product_name": "智能提醒手表",
                "category_name": "智能看护",
                "category_id": "watch",
                "description": "支持提醒吃药、定位与紧急呼叫",
                "stock_status": "有货",
                "in_stock": True,
                "source_index": 1,
            },
        ]

    def filter_products(self, category_id=None, category_name=None):
        return [
            item
            for item in self._items
            if (not category_id or item["category_id"] == category_id)
            and (not category_name or item["category_name"] == category_name)
        ]

    def resolve_category(self, _query: str):
        return {"category_id": "watch", "category_name": "智能看护"}

    def load_products(self):
        return list(self._items)


def test_inventory_search_fixture_regression() -> None:
    service = InventorySearchService()
    fixture = load_fixture_json("inventory_search", "inventory_search_cases.json")

    report_dir = ensure_dir(ROOT / "reports" / "latest" / "inventory_search")
    chart_dir = ensure_dir(report_dir / "charts")

    case_rows: list[dict[str, object]] = []

    exact_hit_at_1 = 0
    exact_mrr_total = 0.0
    for case in fixture["exact_match_cases"]:
        response = service.search(
            query=case["query"],
            category_name=case["expected_category_name"],
            top_k=5,
            mode="strict",
        )
        names = [item.product_name for item in response.items]
        rank = _rank_of_first_relevant(names, {case["expected_product_name"]})
        passed = rank == 1
        exact_hit_at_1 += int(passed)
        exact_mrr_total += 0.0 if rank is None else 1 / rank
        case_rows.append(
            {
                "case_id": case["case_id"],
                "task": "strict",
                "expected": case["expected_product_name"],
                "predicted": names[0] if names else None,
                "rank": rank,
                "passed": passed,
            }
        )

    semantic_hit_total = 0
    semantic_precision_total = 0.0
    semantic_recall_total = 0.0
    semantic_mrr_total = 0.0
    semantic_ndcg_total = 0.0
    for case in fixture["semantic_cases"]:
        top_k = case["top_k"]
        response = service.search(
            query=case["query"],
            category_name=case["expected_category_name"],
            top_k=top_k,
            mode="semantic_rerank",
        )
        names = [item.product_name for item in response.items]
        relevant = set(case["expected_relevant_products"])
        hits = sum(1 for name in names[:top_k] if name in relevant)
        rank = _rank_of_first_relevant(names, relevant)
        semantic_hit_total += int(hits > 0)
        semantic_precision_total += hits / max(top_k, 1)
        semantic_recall_total += hits / max(len(relevant), 1)
        semantic_mrr_total += 0.0 if rank is None else 1 / rank
        semantic_ndcg_total += _ndcg_at_k(rank, top_k)
        case_rows.append(
            {
                "case_id": case["case_id"],
                "task": "semantic_rerank",
                "expected": case["expected_product_name"],
                "predicted": names[0] if names else None,
                "rank": rank,
                "passed": hits > 0,
            }
        )

    llm_rerank_success = 0
    llm_rerank_fallbacks = 0
    llm_rerank_uplifts = 0
    for case in fixture["llm_rerank_cases"]:
        baseline_response = service.search(
            query=case["query"],
            category_name=case["expected_category_name"],
            top_k=case["top_k"],
            mode=case["mode"],
        )
        baseline_names = [item.product_name for item in baseline_response.items]
        baseline_top_1 = baseline_names[0] if baseline_names else None

        candidates = service._get_candidates(
            tag=None,
            category_name=case["expected_category_name"],
            query=case["query"],
        )
        ranked_candidates = service._rank_semantic_candidates(candidates, user_desc=case["query"])
        expected_index = next(
            (
                index
                for index, item in enumerate(ranked_candidates[:20], start=1)
                if item["product_name"] == case["expected_product_name"]
            ),
            None,
        )
        llm_output = json.dumps({"indices": [expected_index]}) if expected_index else '{"indices":[]}'
        llm_service = InventorySearchService(llm_factory=_FakeFactory(llm_output))
        response = llm_service.search(
            query=case["query"],
            category_name=case["expected_category_name"],
            top_k=case["top_k"],
            mode=case["mode"],
        )
        names = [item.product_name for item in response.items]
        predicted = names[0] if names else None
        passed = predicted == case["expected_product_name"]
        llm_rerank_success += int(passed)
        llm_rerank_fallbacks += int(not passed and predicted == baseline_top_1)
        llm_rerank_uplifts += int(baseline_top_1 != case["expected_product_name"] and passed)
        case_rows.append(
            {
                "case_id": case["case_id"],
                "task": "llm_rerank",
                "expected": case["expected_product_name"],
                "predicted": predicted,
                "baseline_top_1": baseline_top_1,
                "passed": passed,
            }
        )

    llm_failure_recovery = 0
    llm_failure_attempts = 0
    for case in fixture["llm_fallback_cases"]:
        baseline_response = service.search(
            query=case["query"],
            category_name=case["expected_category_name"],
            top_k=5,
            mode=case["mode"],
        )
        baseline_top_1 = baseline_response.items[0].product_name if baseline_response.items else None
        candidates = service._get_candidates(
            tag=None,
            category_name=case["expected_category_name"],
            query=case["query"],
        )
        ranked_candidates = service._rank_semantic_candidates(candidates, user_desc=case["query"])
        expects_local_fallback = not bool(
            service._extract_indices(case["simulated_llm_output"], len(ranked_candidates[:20]))
        )
        llm_service = InventorySearchService(llm_factory=_FakeFactory(case["simulated_llm_output"]))
        response = llm_service.search(
            query=case["query"],
            category_name=case["expected_category_name"],
            top_k=5,
            mode=case["mode"],
        )
        predicted = response.items[0].product_name if response.items else None
        passed = predicted == baseline_top_1 if expects_local_fallback else bool(predicted)
        llm_failure_attempts += int(expects_local_fallback)
        llm_failure_recovery += int(passed and expects_local_fallback)
        case_rows.append(
            {
                "case_id": case["case_id"],
                "task": "llm_fallback",
                "expected": case["expected_product_name"],
                "predicted": predicted,
                "baseline_top_1": baseline_top_1,
                "expects_local_fallback": expects_local_fallback,
                "passed": passed,
            }
        )

    metrics = {
        "strict_hit_at_1": round(
            exact_hit_at_1 / max(len(fixture["exact_match_cases"]), 1),
            4,
        ),
        "strict_mrr": round(
            exact_mrr_total / max(len(fixture["exact_match_cases"]), 1),
            4,
        ),
        "semantic_hit_at_5": round(
            semantic_hit_total / max(len(fixture["semantic_cases"]), 1),
            4,
        ),
        "semantic_precision_at_5": round(
            semantic_precision_total / max(len(fixture["semantic_cases"]), 1),
            4,
        ),
        "semantic_recall_at_5": round(
            semantic_recall_total / max(len(fixture["semantic_cases"]), 1),
            4,
        ),
        "semantic_mrr": round(
            semantic_mrr_total / max(len(fixture["semantic_cases"]), 1),
            4,
        ),
        "semantic_ndcg_at_5": round(
            semantic_ndcg_total / max(len(fixture["semantic_cases"]), 1),
            4,
        ),
        "llm_rerank_success_rate": round(
            llm_rerank_success / max(len(fixture["llm_rerank_cases"]), 1),
            4,
        ),
        "llm_fallback_rate": round(
            llm_rerank_fallbacks / max(len(fixture["llm_rerank_cases"]), 1),
            4,
        ),
        "rerank_uplift_rate": round(
            llm_rerank_uplifts / max(len(fixture["llm_rerank_cases"]), 1),
            4,
        ),
        "llm_failure_recovery_rate": round(
            llm_failure_recovery / max(llm_failure_attempts, 1),
            4,
        ),
    }
    threshold_specs = [
        ("strict_hit_at_1", ">=", 0.98, "blocking"),
        ("strict_mrr", ">=", 0.95, "blocking"),
        ("semantic_hit_at_5", ">=", 0.95, "blocking"),
        ("semantic_recall_at_5", ">=", 0.95, "blocking"),
        ("semantic_ndcg_at_5", ">=", 0.80, "warning"),
        ("llm_rerank_success_rate", ">=", 0.90, "warning"),
        ("llm_fallback_rate", "<=", 0.10, "observability"),
        ("llm_failure_recovery_rate", ">=", 0.95, "warning"),
    ]
    status, threshold_rows, failed_blocking, failed_warning = evaluate_thresholds(
        metrics,
        threshold_specs,
    )

    write_csv_rows(report_dir / "cases.csv", case_rows)
    chart = save_bar_chart(
        chart_dir / "inventory_search_scores.png",
        labels=list(metrics.keys()),
        values=[float(value) for value in metrics.values()],
        title="Inventory Search Metrics",
        ylabel="Score",
    )
    write_module_summary(
        report_dir=report_dir,
        module_name="inventory_search",
        metrics=metrics,
        status=status,
        chart_paths=[f"charts/{chart.name}"],
        notes=[
            "Strict mode ranks exact product-name matches within category candidates.",
            "Semantic rerank mode uses category inference plus token and similarity scoring.",
            "LLM rerank metrics compare the LLM top-1 result against the local baseline top-1 result.",
            "Fallback cases validate that malformed LLM output returns to the local ranker result.",
            "Blocking metrics fail the regression immediately; warning metrics are surfaced as WARN in the report.",
            (
                "Warning threshold misses: "
                + ", ".join(f"`{item}`" for item in failed_warning)
                if failed_warning
                else "Warning thresholds: all satisfied."
            ),
        ],
        metric_definitions={
            "strict_hit_at_1": "strict_hit_at_1 = strict_cases_with_correct_top_1 / total_strict_cases",
            "strict_mrr": "strict_mrr = mean(1 / rank_of_expected_product) across strict cases",
            "semantic_hit_at_5": "semantic_hit_at_5 = semantic_cases_with_relevant_item_in_top_5 / total_semantic_cases",
            "semantic_precision_at_5": "semantic_precision_at_5 = mean(relevant_items_in_top_5 / 5) across semantic cases",
            "semantic_recall_at_5": "semantic_recall_at_5 = mean(relevant_items_in_top_5 / relevant_items_total) across semantic cases",
            "semantic_mrr": "semantic_mrr = mean(1 / rank_of_first_relevant_item) across semantic cases",
            "semantic_ndcg_at_5": "semantic_ndcg_at_5 = mean(DCG@5 / IDCG@5) across semantic cases",
            "llm_rerank_success_rate": "llm_rerank_success_rate = llm_rerank_cases_with_expected_top_1 / total_llm_rerank_cases",
            "llm_fallback_rate": "llm_fallback_rate = llm_rerank_cases_that_returned_local_baseline_due_to_llm_failure / total_llm_rerank_cases",
            "rerank_uplift_rate": "rerank_uplift_rate = llm_rerank_cases_where_llm_corrected_a_non_top_1_baseline / total_llm_rerank_cases",
            "llm_failure_recovery_rate": "llm_failure_recovery_rate = malformed_llm_cases_that_match_local_baseline / total_llm_fallback_cases",
        },
        extra_sections=[
            ("Threshold Checks", build_threshold_table(threshold_rows)),
        ],
    )

    assert not failed_blocking, "Blocking thresholds failed: " + "; ".join(
        failed_blocking
    )


def test_inventory_search_uses_llm_rerank_when_available() -> None:
    service = InventorySearchService(
        repository=_FakeRepository(),
        llm_factory=_FakeFactory('{"indices":[2,1]}'),
    )

    response = service.search(
        query="需要提醒吃药",
        category_name="智能看护",
        top_k=2,
        mode="semantic_rerank",
    )

    assert response.items[0].product_name == "普通助行杖"
