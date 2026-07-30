"""FastAPI routers for dashboard and admin endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status

from app.managers.dashboard_manager import DashboardManager
from app.managers.market_data_ingestion_manager import MarketDataIngestionManager


def create_dashboard_router(dashboard_manager: DashboardManager) -> APIRouter:
    """Build dashboard read endpoints consumed by the React client."""
    router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

    @router.get("/overview")
    def read_overview() -> dict:
        return dashboard_manager.get_overview()

    @router.get("/margins")
    def read_margins(
        range: str = Query(default="1Y", alias="range"),
        windowType: str = Query(default="rolling"),
        lookbackDays: int = Query(default=1825),
        granularity: str = Query(default="daily"),
    ) -> dict:
        return dashboard_manager.get_margins(
            range_token=range,
            window_type=windowType,
            lookback_days=lookbackDays,
            granularity=granularity,
        )

    @router.get("/spread")
    def read_spread(
        range: str = Query(default="1Y", alias="range"),
        granularity: str = Query(default="daily"),
    ) -> dict:
        return dashboard_manager.get_spread(range_token=range, granularity=granularity)

    @router.get("/warnings")
    def read_warnings() -> dict:
        return dashboard_manager.get_warnings()

    @router.get("/backtest")
    def read_backtest() -> dict:
        return dashboard_manager.get_backtest()

    return router


def create_admin_router(
    ingestion_manager: MarketDataIngestionManager,
    admin_token: str,
) -> APIRouter:
    """Build protected admin routes for manual ingestion."""
    router = APIRouter(prefix="/api/admin", tags=["admin"])

    def _verify_admin(authorization: str | None = Header(default=None)) -> None:
        if not admin_token:
            return
        expected = f"Bearer {admin_token}"
        if authorization != expected:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid admin token",
            )

    @router.post("/ingest")
    def trigger_ingest(_: None = Depends(_verify_admin)) -> dict:
        return ingestion_manager.run_full_pipeline()

    return router
