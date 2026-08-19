"""FastAPI routers for dashboard and admin endpoints."""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query, status

from app.managers.briefing_manager import BriefingManager
from app.managers.dashboard_manager import DashboardManager
from app.managers.market_data_ingestion_manager import MarketDataIngestionManager

_logger = logging.getLogger(__name__)

# Minimum seconds between real ingests when the /refresh endpoint is poked.
# Protects Yahoo/EIA/CFTC from being hammered when a mentor spam-clicks the
# Refresh button. Tuned to match the "reasonable retry" cadence — anything
# faster wouldn't produce different data anyway (Yahoo prints at market cadence).
_REFRESH_COOLDOWN_SECONDS = 60


def create_dashboard_router(
    dashboard_manager: DashboardManager,
    briefing_manager: BriefingManager,
    ingestion_manager: MarketDataIngestionManager,
) -> APIRouter:
    """Build dashboard read endpoints consumed by the React client."""
    router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])
    # Concurrent /refresh calls should not stampede the ingestion pipeline;
    # a mutex serialises them and lets the second one immediately see the
    # first's completed run without doing a redundant fetch.
    refresh_lock = threading.Lock()

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

    @router.get("/eia-releases")
    def read_eia_releases(
        range: str = Query(default="1Y", alias="range"),
    ) -> dict:
        return dashboard_manager.get_eia_releases(range_token=range)

    @router.get("/tape")
    def read_situational_tape() -> dict:
        return dashboard_manager.get_situational_tape()

    @router.get("/cot-positioning")
    def read_cot_positioning(
        range: str = Query(default="1Y", alias="range"),
    ) -> dict:
        return dashboard_manager.get_cot_positioning(range_token=range)

    @router.get("/backtest")
    def read_backtest() -> dict:
        return dashboard_manager.get_backtest()

    @router.get("/briefing")
    def read_briefing() -> dict:
        """
        Granite-generated natural-language signal briefing.

        Cached per ingest run; regenerated automatically after new data lands.
        Returns ``text: null`` and ``unavailable_reason`` when watsonx.ai is
        not configured — the frontend hides the strip gracefully.
        """
        cache_key = dashboard_manager.get_latest_ingest_cache_key()
        return briefing_manager.get_or_generate(ingest_cache_key=cache_key)

    @router.post("/ask")
    def answer_preset_question(
        question_id: str = Body(..., embed=True),
    ) -> dict:
        """
        Answer one of the preset Granite questions scoped to dashboard data.

        Accepts ``{"question_id": "eia_interpretation" | "cot_interpretation" | "margin_drivers"}``.
        Always freshly generated — no cache — so the user sees up-to-date prose.
        """
        return briefing_manager.answer_preset_question(question_id)

    @router.post("/refresh")
    def trigger_refresh() -> dict:
        """
        Public "poke ingest" endpoint wired to the Refresh button.

        Runs the full ingestion pipeline only if the last successful ingest
        finished more than ``_REFRESH_COOLDOWN_SECONDS`` ago; otherwise
        returns immediately with the cached last-run metadata. Rate limiting
        is server-side (not per-IP) because the risk being managed is
        upstream API throttling of Yahoo/EIA/CFTC, not our own bandwidth.
        """
        latest = ingestion_manager.repository.get_latest_ingestion_run()
        now = datetime.now(timezone.utc)

        def _seconds_since(finished_at):
            if finished_at is None:
                return None
            if finished_at.tzinfo is None:
                finished_at = finished_at.replace(tzinfo=timezone.utc)
            return (now - finished_at).total_seconds()

        def _cooldown_response(age_seconds, reason):
            return {
                "status": "cached",
                "reason": reason,
                "last_run": latest,
                "seconds_since_last_run": age_seconds,
                "cooldown_seconds": _REFRESH_COOLDOWN_SECONDS,
            }

        if latest is not None:
            age = _seconds_since(latest.get("finished_at"))
            if age is not None and age < _REFRESH_COOLDOWN_SECONDS:
                return _cooldown_response(
                    age,
                    f"last ingest finished {int(age)}s ago; cooldown "
                    f"{_REFRESH_COOLDOWN_SECONDS}s to avoid upstream throttling",
                )

        # Serialize concurrent refresh requests — the first through the lock
        # runs the pipeline; anyone else waiting picks up the fresh result
        # without duplicating outbound calls to Yahoo/EIA/CFTC.
        with refresh_lock:
            latest = ingestion_manager.repository.get_latest_ingestion_run()
            if latest is not None:
                age = _seconds_since(latest.get("finished_at"))
                if age is not None and age < _REFRESH_COOLDOWN_SECONDS:
                    return _cooldown_response(age, "another refresh completed while waiting")
            try:
                report = ingestion_manager.run_full_pipeline()
            except Exception as exc:
                _logger.exception("Refresh-triggered ingest failed")
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"ingest failed: {type(exc).__name__}",
                ) from exc
        return {
            "status": "ran",
            "report": report,
        }

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
