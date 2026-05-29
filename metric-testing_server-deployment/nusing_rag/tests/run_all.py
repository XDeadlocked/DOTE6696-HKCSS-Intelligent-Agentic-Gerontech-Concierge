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
from app.core.config import get_settings
from app.session_store.service import build_session_store
from tests.common.io import ensure_dir
from tests.common.reporting import write_latest_report, write_module_summary
from tests.common.visualization import save_bar_chart


def main() -> int:
    reports_dir = ROOT / "reports" / "latest"
    charts_dir = ensure_dir(reports_dir / "charts")

    app = create_app()
    with TestClient(app) as client:
        health_response = client.get("/health")

    session_store = build_session_store(get_settings())
    session = session_store.create_session()
    session_store.bind_websocket(session.session_id, "assessment", "conn-1")
    bound = session_store.get_session(session.session_id)

    chart_path = save_bar_chart(
        charts_dir / "phase_a_smoke.png",
        labels=["health", "session_store"],
        values=[1.0 if health_response.status_code == 200 else 0.0, 1.0],
        title="Phase A Smoke Checks",
        ylabel="Score",
    )

    write_module_summary(
        reports_dir,
        module_name="phase_a",
        metrics={
            "health_status_code": health_response.status_code,
            "session_bindings": len(bound.websocket_bindings.get("assessment", [])),
            "session_backend": session_store.backend_name,
        },
        status="PASS" if health_response.status_code == 200 else "FAIL",
        chart_paths=[f"charts/{chart_path.name}"],
        notes=["Phase A verifies app startup, health route, session store, and report output."],
    )

    write_latest_report(
        reports_dir,
        module_results=[
            {
                "module": "phase_a",
                "status": "PASS" if health_response.status_code == 200 else "FAIL",
                "details": f"health={health_response.status_code}, backend={session_store.backend_name}",
            }
        ],
        chart_paths=[f"charts/{chart_path.name}"],
    )

    print(f"Phase A report generated at: {reports_dir}")
    return 0 if health_response.status_code == 200 else 1


if __name__ == "__main__":
    raise SystemExit(main())
