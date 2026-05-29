from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.main import create_app
from tests.common.io import ensure_dir, write_csv_rows
from tests.common.metrics import average
from tests.common.reporting import write_module_summary
from tests.common.visualization import save_bar_chart


def test_phase_e_api_and_websocket_integration() -> None:
    app = create_app()

    report_dir = ensure_dir(ROOT / "reports" / "latest" / "phase_e")
    chart_dir = ensure_dir(report_dir / "charts")
    case_rows: list[dict[str, object]] = []

    health_scores: list[float] = []
    rest_scores: list[float] = []
    websocket_scores: list[float] = []
    session_scores: list[float] = []

    with TestClient(app) as client:
        health_response = client.get("/api/v1/health")
        health_ok = (
            health_response.status_code == 200
            and health_response.json()["status"] == "ok"
        )
        health_scores.append(float(health_ok))
        case_rows.append(
            {
                "case_id": "health",
                "channel": "rest",
                "expected": "200 ok",
                "actual": health_response.status_code,
                "passed": health_ok,
            }
        )

        create_response = client.post("/api/v1/sessions")
        assert create_response.status_code == 200
        session_id = create_response.json()["session_id"]

        session_summary = client.get(f"/api/v1/sessions/{session_id}")
        summary_ok = session_summary.status_code == 200 and session_summary.json()["session_id"] == session_id
        session_scores.append(float(summary_ok))
        case_rows.append(
            {
                "case_id": "session_summary",
                "channel": "rest",
                "expected": session_id,
                "actual": session_summary.json().get("session_id"),
                "passed": summary_ok,
            }
        )

        intent_response = client.post(
            "/api/v1/intent/classify",
            json={"session_id": session_id, "user_input": "你们有什么轮椅"},
        )
        intent_ok = (
            intent_response.status_code == 200
            and intent_response.json()["intent"] == "产品-浏览了解型"
        )
        rest_scores.append(float(intent_ok))
        case_rows.append(
            {
                "case_id": "intent",
                "channel": "rest",
                "expected": "产品-浏览了解型",
                "actual": intent_response.json().get("intent"),
                "passed": intent_ok,
            }
        )

        assessment_start = client.post(
            "/api/v1/assessment/start",
            json={"session_id": session_id},
        )
        assessment_question = assessment_start.json()
        assessment_start_ok = (
            assessment_start.status_code == 200
            and assessment_question["status"] == "question"
            and bool(assessment_question.get("options"))
        )
        rest_scores.append(float(assessment_start_ok))
        case_rows.append(
            {
                "case_id": "assessment_start",
                "channel": "rest",
                "expected": "question",
                "actual": assessment_question.get("status"),
                "passed": assessment_start_ok,
            }
        )

        first_option = assessment_question["options"][0]
        assessment_answer = client.post(
            "/api/v1/assessment/answer",
            json={"session_id": session_id, "user_input": first_option},
        )
        assessment_answer_ok = assessment_answer.status_code == 200 and assessment_answer.json()["status"] in {
            "question",
            "recommendation",
            "completed",
        }
        rest_scores.append(float(assessment_answer_ok))
        case_rows.append(
            {
                "case_id": "assessment_answer",
                "channel": "rest",
                "expected": "question|recommendation|completed",
                "actual": assessment_answer.json().get("status"),
                "passed": assessment_answer_ok,
            }
        )

        products_response = client.get("/api/v1/products", params={"query": "你们有什么轮椅", "page_size": 5})
        products_json = products_response.json()
        products_ok = products_response.status_code == 200 and len(products_json["items"]) > 0
        rest_scores.append(float(products_ok))
        case_rows.append(
            {
                "case_id": "products_list",
                "channel": "rest",
                "expected": "items > 0",
                "actual": len(products_json.get("items", [])),
                "passed": products_ok,
            }
        )

        detail_name = products_json["items"][0]["product_name"]
        detail_response = client.get("/api/v1/products/detail", params={"query": detail_name})
        detail_ok = detail_response.status_code == 200 and detail_response.json()["product_name"] == detail_name
        rest_scores.append(float(detail_ok))
        case_rows.append(
            {
                "case_id": "product_detail",
                "channel": "rest",
                "expected": detail_name,
                "actual": detail_response.json().get("product_name"),
                "passed": detail_ok,
            }
        )

        followup_question = client.get(
            "/api/v1/followup/question",
            params={"session_id": session_id, "device_tag": "1"},
        )
        question_json = followup_question.json()
        followup_question_ok = followup_question.status_code == 200 and question_json["tag"] == "1"
        rest_scores.append(float(followup_question_ok))
        case_rows.append(
            {
                "case_id": "followup_question",
                "channel": "rest",
                "expected": "1",
                "actual": question_json.get("tag"),
                "passed": followup_question_ok,
            }
        )

        followup_answer = client.post(
            "/api/v1/followup/answer",
            json={"session_id": session_id, "device_tag": "1", "answer": "1"},
        )
        followup_ok = followup_answer.status_code == 200 and followup_answer.json()["status"] == "recommendation"
        rest_scores.append(float(followup_ok))
        case_rows.append(
            {
                "case_id": "followup_answer",
                "channel": "rest",
                "expected": "recommendation",
                "actual": followup_answer.json().get("status"),
                "passed": followup_ok,
            }
        )

        inventory_response = client.post(
            "/api/v1/inventory/search",
            json={
                "session_id": session_id,
                "query": "我想找輪椅",
                "category_name": "輪椅",
                "top_k": 3,
                "mode": "semantic_rerank",
            },
        )
        inventory_ok = inventory_response.status_code == 200 and len(inventory_response.json()["items"]) > 0
        rest_scores.append(float(inventory_ok))
        case_rows.append(
            {
                "case_id": "inventory_search",
                "channel": "rest",
                "expected": "items > 0",
                "actual": len(inventory_response.json().get("items", [])),
                "passed": inventory_ok,
            }
        )

        nursing_response = client.post(
            "/api/v1/nursing/ask",
            json={"session_id": session_id, "question": "如何帮助老人吞咽"},
        )
        nursing_ok = nursing_response.status_code == 200 and bool(nursing_response.json()["answer"])
        rest_scores.append(float(nursing_ok))
        case_rows.append(
            {
                "case_id": "nursing_ask",
                "channel": "rest",
                "expected": "non-empty answer",
                "actual": bool(nursing_response.json().get("answer")),
                "passed": nursing_ok,
            }
        )

        updated_summary = client.get(f"/api/v1/sessions/{session_id}")
        updated_json = updated_summary.json()
        persistence_ok = (
            updated_summary.status_code == 200
            and updated_json["followup_count"] >= 1
            and updated_json["nursing_turns"] >= 1
        )
        session_scores.append(float(persistence_ok))
        case_rows.append(
            {
                "case_id": "session_persistence",
                "channel": "rest",
                "expected": "followup>=1,nursing>=1",
                "actual": f"followup={updated_json['followup_count']},nursing={updated_json['nursing_turns']}",
                "passed": persistence_ok,
            }
        )

        ws_session_id = client.post("/api/v1/sessions").json()["session_id"]
        with client.websocket_connect(f"/ws/assessment/{ws_session_id}") as websocket:
            websocket.send_json({"type": "start"})
            first_event = websocket.receive_json()
            first_event_ok = first_event["type"] == "question" and bool(first_event["data"].get("options"))
            websocket_scores.append(float(first_event_ok))
            case_rows.append(
                {
                    "case_id": "ws_assessment_start",
                    "channel": "websocket",
                    "expected": "question",
                    "actual": first_event.get("type"),
                    "passed": first_event_ok,
                }
            )

            ws_option = first_event["data"]["options"][0]
            websocket.send_json({"type": "answer", "user_input": ws_option})
            second_event = websocket.receive_json()
            second_ok = second_event["type"] in {"question", "completed"}
            websocket_scores.append(float(second_ok))
            case_rows.append(
                {
                    "case_id": "ws_assessment_answer",
                    "channel": "websocket",
                    "expected": "question|completed",
                    "actual": second_event.get("type"),
                    "passed": second_ok,
                }
            )

        ws_nursing_id = client.post("/api/v1/sessions").json()["session_id"]
        with client.websocket_connect(f"/ws/nursing/{ws_nursing_id}") as websocket:
            websocket.send_json({"type": "question", "question": "如何帮助老人吞咽"})
            chunk_event = websocket.receive_json()
            done_event = None
            while True:
                maybe_event = websocket.receive_json()
                if maybe_event["type"] == "done":
                    done_event = maybe_event
                    break
            ws_nursing_ok = (
                chunk_event["type"] == "answer_chunk"
                and done_event is not None
                and done_event["type"] == "done"
            )
            websocket_scores.append(float(ws_nursing_ok))
            case_rows.append(
                {
                    "case_id": "ws_nursing",
                    "channel": "websocket",
                    "expected": "answer_chunk + done",
                    "actual": f"{chunk_event.get('type')} -> {done_event.get('type') if done_event else None}",
                    "passed": ws_nursing_ok,
                }
            )

    metrics = {
        "health_endpoint_success_rate": average(health_scores),
        "rest_contract_success_rate": average(rest_scores),
        "websocket_contract_success_rate": average(websocket_scores),
        "session_persistence_rate": average(session_scores),
    }

    write_csv_rows(report_dir / "cases.csv", case_rows)
    chart = save_bar_chart(
        chart_dir / "phase_e_scores.png",
        labels=list(metrics.keys()),
        values=[float(value) for value in metrics.values()],
        title="Phase E Integration Metrics",
        ylabel="Score",
    )
    write_module_summary(
        report_dir=report_dir,
        module_name="phase_e",
        metrics=metrics,
        status="PASS",
        chart_paths=[f"charts/{chart.name}"],
        notes=[
            "Covers REST endpoints for session, intent, assessment, products, followup, inventory, and nursing.",
            "Covers websocket flows for assessment and nursing with real session binding.",
        ],
        metric_definitions={
            "health_endpoint_success_rate": "health_endpoint_success_rate = successful_health_checks / total_health_checks",
            "rest_contract_success_rate": "rest_contract_success_rate = successful_rest_contract_cases / total_rest_contract_cases",
            "websocket_contract_success_rate": "websocket_contract_success_rate = successful_websocket_contract_cases / total_websocket_contract_cases",
            "session_persistence_rate": "session_persistence_rate = successful_session_state_checks / total_session_state_checks",
        },
    )

    assert metrics["health_endpoint_success_rate"] >= 1.0
    assert metrics["rest_contract_success_rate"] >= 0.95
    assert metrics["websocket_contract_success_rate"] >= 0.95
    assert metrics["session_persistence_rate"] >= 1.0
