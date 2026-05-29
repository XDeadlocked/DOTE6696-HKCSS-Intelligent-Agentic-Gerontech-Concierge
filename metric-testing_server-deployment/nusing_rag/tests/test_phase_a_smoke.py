from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.main import create_app
from app.session_store.service import build_session_store
from app.core.config import get_settings
from tests.common.reporting import write_module_summary
from tests.common.visualization import save_bar_chart


def test_health_endpoint() -> None:
    app = create_app()
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert "session_backend" in payload


def test_session_store_lifecycle() -> None:
    service = build_session_store(get_settings())
    session = service.create_session()
    service.bind_websocket(session.session_id, "assessment", "conn-1")

    restored = service.get_session(session.session_id)
    assert restored.websocket_bindings["assessment"] == ["conn-1"]

    service.unbind_websocket(session.session_id, "assessment", "conn-1")
    restored = service.get_session(session.session_id)
    assert "assessment" not in restored.websocket_bindings


def test_reporting_outputs(tmp_path: Path) -> None:
    chart_path = save_bar_chart(
        tmp_path / "charts" / "module_scores.png",
        labels=["phase_a"],
        values=[1.0],
        title="Phase A Smoke",
        ylabel="Score",
    )
    summary_path = write_module_summary(
        tmp_path,
        module_name="phase_a",
        metrics={"health_check": 1.0, "session_store": 1.0},
        status="PASS",
        chart_paths=[f"charts/{chart_path.name}"],
        notes=["Smoke validation for Phase A base infrastructure."],
    )
    assert summary_path.exists()
    assert chart_path.exists()
