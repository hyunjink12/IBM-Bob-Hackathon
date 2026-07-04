"""FastAPI application entrypoint."""

import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.dashboard_router import create_admin_router, create_dashboard_router
from app.api.health_router import create_health_router
from app.api.hello_router import create_hello_router
from app.core.app_settings import AppSettings
from app.core.dependencies import (
    build_dashboard_manager,
    build_ingestion_manager,
    configure_runtime,
    ensure_data_bootstrapped,
    get_repository,
)
from app.managers.health_check_manager import HealthCheckManager
from app.managers.hello_manager import HelloManager

_logger = logging.getLogger(__name__)


def _run_startup_data_refresh() -> None:
    """
    Kick off bootstrap/refresh without blocking the ASGI event loop.

    Casual: load prices in the background so page refresh still works.
    """
    try:
        ensure_data_bootstrapped()
    except Exception:
        _logger.exception("Startup data refresh failed")


def _build_lifespan(settings: AppSettings):
    """
    Build a lifespan handler that bootstraps data on startup.

    Casual: tests wait for seed data; dev runs refresh in a background thread.
    """

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        if settings.env == "test":
            _run_startup_data_refresh()
        else:
            refresh_thread = threading.Thread(
                target=_run_startup_data_refresh,
                name="startup-data-refresh",
                daemon=True,
            )
            refresh_thread.start()
        yield

    return lifespan


def create_app(settings: AppSettings | None = None) -> FastAPI:
    """
    Build the FastAPI app with routers and middleware.

    Casual: sets up the API server object uvicorn runs.

    Uses a factory so tests (and future scripts) can inject settings without
    mutating process-wide environment variables.
    """
    resolved_settings = settings or AppSettings()
    configure_runtime(resolved_settings)

    def data_freshness() -> dict:
        repository = get_repository()
        latest_ingest = repository.get_latest_ingestion_run()
        latest_margin = repository.fetch_latest_computed_margin()
        return {
            "last_ingestion": latest_ingest,
            "latest_margin_date": (
                latest_margin.obs_date.isoformat() if latest_margin else None
            ),
        }

    health_manager = HealthCheckManager(
        service_name="corn-ethanol-backend",
        environment=resolved_settings.env,
        data_freshness_provider=data_freshness,
    )
    hello_manager = HelloManager()
    dashboard_manager = build_dashboard_manager()
    ingestion_manager = build_ingestion_manager()

    app = FastAPI(
        title=resolved_settings.api_title,
        version=resolved_settings.api_version,
        lifespan=_build_lifespan(resolved_settings),
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "*",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(create_health_router(health_manager))
    app.include_router(create_hello_router(hello_manager))
    app.include_router(create_dashboard_router(dashboard_manager))
    app.include_router(
        create_admin_router(ingestion_manager, resolved_settings.admin_token)
    )

    @app.get("/")
    def read_root() -> dict[str, str]:
        """Friendly landing route when you open the API in a browser."""
        return {
            "message": "Corn Ethanol Arb Monitor API",
            "docs": "/docs",
            "health": "/api/health",
            "dashboard": "/api/dashboard/overview",
        }

    return app


app = create_app()
