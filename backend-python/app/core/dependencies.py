"""Application dependency wiring for repositories and managers."""

from __future__ import annotations

from pathlib import Path

from app.clients.eia_client import EiaClient
from app.core.app_settings import AppSettings
from app.managers.dashboard_manager import DashboardManager
from app.managers.market_data_ingestion_manager import MarketDataIngestionManager
from app.models.crush_model_config import CrushModelConfig
from app.storage.duckdb_repository import DuckDbRepository

_runtime_settings: AppSettings | None = None
_repository: DuckDbRepository | None = None


def configure_runtime(settings: AppSettings) -> None:
    """Set process-wide settings and reset cached repository."""
    global _runtime_settings, _repository
    _runtime_settings = settings
    if _repository is not None:
        _repository.close()
    _repository = None


def get_settings() -> AppSettings:
    """Return active settings for this process."""
    return _runtime_settings or AppSettings()


def resolve_crush_config(settings: AppSettings) -> CrushModelConfig:
    """Load crush model JSON using settings path when provided."""
    config_path = Path(settings.crush_model_path)
    if not config_path.is_absolute():
        backend_root = Path(__file__).resolve().parents[2]
        config_path = (backend_root / config_path).resolve()
    return CrushModelConfig.from_json_file(config_path)


def get_repository() -> DuckDbRepository:
    """Shared DuckDB repository for the process."""
    global _repository
    if _repository is None:
        settings = get_settings()
        db_path = Path(settings.duckdb_path)
        if not db_path.is_absolute():
            backend_root = Path(__file__).resolve().parents[2]
            db_path = (backend_root / db_path).resolve()
        _repository = DuckDbRepository(db_path)
    return _repository


def build_ingestion_manager() -> MarketDataIngestionManager:
    """Construct the ingestion pipeline with configured clients."""
    settings = get_settings()
    crush_config = resolve_crush_config(settings)
    return MarketDataIngestionManager(
        repository=get_repository(),
        crush_config=crush_config,
        eia_client=EiaClient(settings.eia_api_key),
    )


def build_dashboard_manager() -> DashboardManager:
    """Construct the dashboard read model."""
    settings = get_settings()
    return DashboardManager(
        repository=get_repository(),
        crush_config=resolve_crush_config(settings),
    )


def ensure_data_bootstrapped() -> None:
    """
    Run ingestion once when the database has no merged rows.

    Casual: first launch seeds data so the UI isn't empty.
    """
    repository = get_repository()
    if repository.count_merged_daily_rows() == 0:
        build_ingestion_manager().run_full_pipeline()
