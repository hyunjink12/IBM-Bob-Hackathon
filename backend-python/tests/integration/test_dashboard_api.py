"""Integration tests for dashboard API."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.app_settings import AppSettings
from app.main import create_app


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    db_path = tmp_path / "test.duckdb"
    settings = AppSettings(
        env="test",
        duckdb_path=str(db_path),
        crush_model_path=str(
            Path(__file__).resolve().parents[3] / "config" / "crush_model.json"
        ),
    )
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client


@pytest.mark.integration
def test_health_endpoint(client: TestClient) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert "data_freshness" in payload


@pytest.mark.integration
def test_dashboard_overview_after_bootstrap(client: TestClient) -> None:
    response = client.get("/api/dashboard/overview")
    assert response.status_code == 200
    payload = response.json()
    assert payload["as_of"] is not None
    assert len(payload["metrics"]) >= 7
    assert payload["data_provenance"]["using_seed_data"] is True
    assert payload["data_provenance"]["message"]


@pytest.mark.integration
def test_dashboard_margins_series(client: TestClient) -> None:
    response = client.get("/api/dashboard/margins?range=1Y&windowType=rolling")
    assert response.status_code == 200
    payload = response.json()
    assert payload["current"] is not None
    assert len(payload["series"]) > 0


@pytest.mark.integration
def test_dashboard_warnings_and_panel5(client: TestClient) -> None:
    warnings = client.get("/api/dashboard/warnings")
    panel5 = client.get("/api/dashboard/panel5")
    assert warnings.status_code == 200
    assert panel5.status_code == 200
    assert panel5.json()["status"] == "placeholder"

    payload = warnings.json()
    assert payload["as_of"] is not None
    assert "warnings" in payload
    assert "stress" in payload
    stress = payload["stress"]
    assert stress["stocks_mmbbl"] is not None
    assert stress["production_mbpd"] is not None
    assert stress["status"] in {"calm", "watch", "stressed"}
    assert stress["status_message"]
