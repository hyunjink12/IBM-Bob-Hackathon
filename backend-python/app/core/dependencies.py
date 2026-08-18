"""Application dependency wiring for repositories and managers."""

from __future__ import annotations

from pathlib import Path

from app.clients.eia_client import EiaClient
from app.clients.epa_rin_file_client import EpaRinFileClient
from app.clients.watsonx_client import WatsonxClient
from app.core.app_settings import AppSettings
from app.managers.briefing_manager import BriefingManager
from app.managers.dashboard_manager import DashboardManager
from app.managers.market_data_ingestion_manager import MarketDataIngestionManager
from app.models.crush_model_config import CrushModelConfig
from app.storage.duckdb_repository import DuckDbRepository

_runtime_settings: AppSettings | None = None
_repository: DuckDbRepository | None = None


def _backend_root() -> Path:
    """Repo path for `backend-python/`, used to resolve relative defaults."""
    return Path(__file__).resolve().parents[2]


def resolve_data_dir(settings: AppSettings) -> Path:
    """
    Root directory for persistent state (DuckDB + EPA file-drop).

    When APP_DATA_DIR is set (Railway volume, Docker mount), use it verbatim.
    Otherwise fall back to `backend-python/data` for local dev.
    """
    if settings.data_dir:
        return Path(settings.data_dir).expanduser().resolve()
    return _backend_root() / "data"


def resolve_duckdb_path(settings: AppSettings) -> Path:
    """DuckDB file path, honoring explicit override then falling back to data_dir."""
    if settings.duckdb_path:
        db_path = Path(settings.duckdb_path).expanduser()
        return db_path.resolve() if db_path.is_absolute() else (_backend_root() / db_path).resolve()
    return resolve_data_dir(settings) / "ethanol_dashboard.duckdb"


def resolve_epa_rin_csv_path(settings: AppSettings) -> Path:
    """EPA D6 RIN CSV path, honoring override then falling back to data_dir/epa."""
    if settings.epa_rin_csv_path:
        csv_path = Path(settings.epa_rin_csv_path).expanduser()
        return csv_path.resolve() if csv_path.is_absolute() else (_backend_root() / csv_path).resolve()
    return resolve_data_dir(settings) / "epa" / "rin_prices_2026.csv"


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
        db_path = resolve_duckdb_path(settings)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        _repository = DuckDbRepository(db_path)
    return _repository


_EPA_SEED_DIR = Path("/app/seed_data/epa")


def build_ingestion_manager() -> MarketDataIngestionManager:
    """Construct the ingestion pipeline with configured clients."""
    settings = get_settings()
    crush_config = resolve_crush_config(settings)
    epa_csv_path = resolve_epa_rin_csv_path(settings)
    # Ensure the EPA drop directory exists so mentors can `scp` a CSV in
    # without first creating the folder.
    epa_csv_path.parent.mkdir(parents=True, exist_ok=True)
    # First-boot seed: if the volume's EPA CSV is missing, copy the snapshot
    # baked into the image at build time. Lets a fresh Railway deploy come up
    # with real RIN prices before the user runs their first weekly CSV update.
    if not epa_csv_path.exists() and _EPA_SEED_DIR.exists():
        import shutil
        for seed_file in _EPA_SEED_DIR.iterdir():
            target = epa_csv_path.parent / seed_file.name
            if not target.exists():
                shutil.copy2(seed_file, target)
    return MarketDataIngestionManager(
        repository=get_repository(),
        crush_config=crush_config,
        eia_client=EiaClient(settings.eia_api_key),
        epa_rin_client=EpaRinFileClient(csv_path=epa_csv_path),
    )


def _build_shared_backtester() -> "WarningRuleBacktester":
    """Build a backtester wired to the shared repository."""
    from app.managers.warning_backtester import WarningRuleBacktester
    return WarningRuleBacktester(get_repository())


def build_dashboard_manager() -> DashboardManager:
    """Construct the dashboard read model with the shared backtester."""
    settings = get_settings()
    return DashboardManager(
        repository=get_repository(),
        crush_config=resolve_crush_config(settings),
        backtester=_build_shared_backtester(),
    )


def build_watsonx_client() -> WatsonxClient:
    """Construct the watsonx.ai client from settings."""
    settings = get_settings()
    return WatsonxClient(
        api_key=settings.watsonx_api_key,
        project_id=settings.watsonx_project_id,
        base_url=settings.watsonx_url,
        model_id=settings.watsonx_model_id,
    )


def build_briefing_manager() -> BriefingManager:
    """Construct the Granite briefing manager with the shared backtester."""
    return BriefingManager(
        repository=get_repository(),
        watsonx_client=build_watsonx_client(),
        backtester=_build_shared_backtester(),
    )


def ensure_data_bootstrapped() -> None:
    """
    Seed an empty database or refresh live Yahoo/EIA feeds on startup,
    then warm up the Granite briefing cache so the first page load doesn't wait.

    Casual: first launch seeds data; later launches pull fresh futures (and EIA
    when a key is set) so the dashboard is not stuck on synthetic numbers.

    Runs synchronously — call from a background thread during API startup so
    uvicorn can accept dashboard requests while Yahoo/EIA pulls finish.
    """
    repository = get_repository()
    ingestion_manager = build_ingestion_manager()
    is_empty = repository.count_merged_daily_rows() == 0
    should_refresh_eia = ingestion_manager.should_refresh_live_data_on_startup()
    if is_empty or should_refresh_eia:
        ingestion_manager.run_full_pipeline()

    # Warm up the briefing after ingest so the first dashboard request hits
    # the DB cache rather than blocking on a Granite API call. Manager derives
    # its own cache key from the latest ingestion run.
    briefing_manager = build_briefing_manager()
    if briefing_manager.is_available:
        briefing_manager.get_or_generate()
