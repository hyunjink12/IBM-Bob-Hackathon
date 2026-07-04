"""Parallel dashboard API calls — same pattern as the React client."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.app_settings import AppSettings
from app.main import create_app


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    db_path = tmp_path / "parallel.duckdb"
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
def test_parallel_dashboard_endpoints(client: TestClient) -> None:
    """All five dashboard routes should respond when hit at once."""
    paths = (
        "/api/dashboard/overview",
        "/api/dashboard/margins?range=1Y&windowType=rolling&lookbackDays=1825",
        "/api/dashboard/spread?range=1Y",
        "/api/dashboard/warnings",
        "/api/dashboard/panel5",
    )

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(client.get, path) for path in paths]
        responses = [future.result(timeout=10) for future in as_completed(futures)]

    assert len(responses) == 5
    assert all(response.status_code == 200 for response in responses)
