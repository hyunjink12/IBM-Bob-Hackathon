"""Integration test for ingestion pipeline with seed data."""

from pathlib import Path

import pytest

from app.core.app_settings import AppSettings
from app.core.dependencies import build_ingestion_manager, configure_runtime
from app.storage.duckdb_repository import DuckDbRepository


@pytest.mark.integration
def test_ingestion_pipeline_populates_margins(tmp_path: Path) -> None:
    db_path = tmp_path / "pipeline.duckdb"
    configure_runtime(
        AppSettings(
            env="test",
            duckdb_path=str(db_path),
            crush_model_path=str(
                Path(__file__).resolve().parents[3] / "config" / "crush_model.json"
            ),
        )
    )
    result = build_ingestion_manager().run_full_pipeline()
    repository = DuckDbRepository(db_path)

    assert result["status"] == "ok"
    assert repository.count_merged_daily_rows() > 0
    assert repository.fetch_latest_computed_margin() is not None
    repository.close()
