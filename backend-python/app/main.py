"""FastAPI application entrypoint."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health_router import create_health_router
from app.api.hello_router import create_hello_router
from app.core.app_settings import AppSettings
from app.managers.health_check_manager import HealthCheckManager
from app.managers.hello_manager import HelloManager


def create_app(settings: AppSettings | None = None) -> FastAPI:
    """
    Build the FastAPI app with routers and middleware.

    Casual: sets up the API server object uvicorn runs.

    Uses a factory so tests (and future scripts) can inject settings without
    mutating process-wide environment variables.
    """
    resolved_settings = settings or AppSettings()
    health_manager = HealthCheckManager(
        service_name="corn-ethanol-backend",
        environment=resolved_settings.env,
    )
    hello_manager = HelloManager()

    app = FastAPI(
        title=resolved_settings.api_title,
        version=resolved_settings.api_version,
    )

    # Allow the Vite dev server (localhost:5173) to call the API during local dev.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(create_health_router(health_manager))
    app.include_router(create_hello_router(hello_manager))

    @app.get("/")
    def read_root() -> dict[str, str]:
        """Friendly landing route when you open the API in a browser."""
        return {
            "message": "Corn Ethanol Arb Monitor API",
            "docs": "/docs",
            "health": "/api/health",
        }

    return app


# Uvicorn import string: `uvicorn app.main:app`
app = create_app()
