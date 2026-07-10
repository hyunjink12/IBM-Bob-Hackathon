"""Orchestrates ingestion, merge, margin math, z-scores, and warnings."""

from __future__ import annotations

import uuid
from datetime import date

from app.clients.eia_client import EiaClient
from app.clients.yahoo_futures_client import YahooFuturesClient
from app.managers.crush_margin_calculator import CrushMarginCalculator
from app.managers.seed_data_provider import SeedDataProvider
from app.managers.series_merge_manager import SeriesMergeManager
from app.managers.warning_signal_manager import WarningSignalManager
from app.managers.z_score_manager import ZScoreManager
from app.models.crush_model_config import CrushModelConfig
from app.storage.duckdb_repository import ComputedMarginRow, DuckDbRepository


class MarketDataIngestionManager:
    """
    Daily pipeline: fetch → merge → margins → z-scores → warnings.

    Casual: the overnight job that refreshes the whole dashboard.

    Tries live EIA and Yahoo futures first, then seeds when the database is
    empty or downloads fail. Recomputes derived tables every run so config
    changes propagate without manual SQL.
    """

    def __init__(
        self,
        repository: DuckDbRepository,
        crush_config: CrushModelConfig,
        eia_client: EiaClient,
        futures_client: YahooFuturesClient | None = None,
        seed_provider: SeedDataProvider | None = None,
    ) -> None:
        self._repository = repository
        self._crush_config = crush_config
        self._eia_client = eia_client
        self._futures_client = futures_client or YahooFuturesClient()
        self._seed_provider = seed_provider or SeedDataProvider()
        self._merge_manager = SeriesMergeManager(repository)
        self._margin_calculator = CrushMarginCalculator(crush_config)
        self._z_score_manager = ZScoreManager()
        self._warning_manager = WarningSignalManager(repository)

    def should_refresh_live_data_on_startup(self) -> bool:
        """
        Decide whether to re-run ingestion when the database already has rows.

        Casual: refresh Yahoo + EIA on every boot; tests stick to seed only.

        Without this, a first-run seed sticks around forever even after live
        clients are wired up. Yahoo futures and EIA both upsert on each pipeline
        run, so we refresh whenever we are not in the test environment.
        """
        return self._should_fetch_live_futures()

    def run_full_pipeline(
        self,
        *,
        window_type: str = "rolling",
        lookback_days: int = 1825,
    ) -> dict[str, int | str]:
        """
        Execute the full ingestion and recompute pipeline.

        Returns counts and status for logging/health endpoints.
        """
        run_id = str(uuid.uuid4())
        started_at = DuckDbRepository.utc_now()
        self._repository.record_ingestion_run(run_id, started_at, status="running")
        errors: list[str] = []

        try:
            raw_count = self._ingest_raw_data(errors)
            merged_rows = self._merge_manager.rebuild_merged_daily()
            margin_count = self._recompute_margins(
                merged_rows,
                window_type=window_type,
                lookback_days=lookback_days,
            )
            self._repository.record_ingestion_run(
                run_id,
                started_at,
                status="ok",
                finished_at=DuckDbRepository.utc_now(),
                errors="; ".join(errors) if errors else None,
            )
            return {
                "run_id": run_id,
                "raw_observations": raw_count,
                "merged_days": len(merged_rows),
                "computed_margins": margin_count,
                "status": "ok",
            }
        except Exception as exc:
            self._repository.record_ingestion_run(
                run_id,
                started_at,
                status="error",
                finished_at=DuckDbRepository.utc_now(),
                errors=str(exc),
            )
            raise

    def _ingest_raw_data(self, errors: list[str]) -> int:
        observations = []
        if self._repository.count_merged_daily_rows() == 0:
            observations.extend(self._seed_provider.build_observations())

        if self._should_fetch_live_futures():
            try:
                observations.extend(self._futures_client.fetch_all(period="5y"))
            except Exception as exc:
                errors.append(f"futures: {exc}")

        if self._eia_client.is_configured:
            try:
                observations.extend(self._eia_client.fetch_ethanol_weekly())
            except Exception as exc:
                errors.append(f"eia: {exc}")

        if not observations and self._repository.count_merged_daily_rows() == 0:
            observations.extend(self._seed_provider.build_observations())

        if observations:
            return self._repository.upsert_raw_observations(observations)
        return 0

    def _recompute_margins(
        self,
        merged_rows: list,
        *,
        window_type: str,
        lookback_days: int,
    ) -> int:
        margin_points: list[tuple[date, float]] = []
        per_day_results: list[tuple[date, float, bool]] = []

        for row in merged_rows:
            result = self._margin_calculator.calculate(row)
            if result is None:
                continue
            margin_points.append((row.obs_date, result.margin_per_bushel))
            per_day_results.append(
                (row.obs_date, result.margin_per_bushel, result.corn_oil_included)
            )

        annotated = self._z_score_manager.annotate_series(
            margin_points,
            window_type=window_type,
            lookback_days=lookback_days,
        )
        annotation_by_date = {item[0]: item for item in annotated}

        computed_rows: list[ComputedMarginRow] = []
        for obs_date, margin_per_bushel, corn_oil_included in per_day_results:
            _, _, z_score, signal_label = annotation_by_date.get(
                obs_date,
                (obs_date, margin_per_bushel, None, "normal"),
            )
            computed_rows.append(
                ComputedMarginRow(
                    obs_date=obs_date,
                    margin_per_bushel=margin_per_bushel,
                    margin_per_gallon=margin_per_bushel / self._crush_config.ethanol_gallons_per_bushel,
                    z_score=z_score,
                    signal_label=signal_label,
                    corn_oil_included=corn_oil_included,
                )
            )

        count = self._repository.replace_computed_margins(computed_rows)

        # Evaluate warnings against the latest day that actually has a margin —
        # merged_rows[-1] and computed_rows[-1] can diverge when the tip day is
        # missing prices (weekend/holiday) and margins stop earlier.
        self._evaluate_latest_warnings(merged_rows, computed_rows)
        return count

    def _evaluate_latest_warnings(
        self,
        merged_rows: list,
        computed_rows: list[ComputedMarginRow],
    ) -> None:
        """
        Run warning rules for the newest day with both merge + margin rows.

        Casual: only alert on a day we can actually score.
        """
        if not merged_rows or not computed_rows:
            return

        margin_by_date = {row.obs_date: row for row in computed_rows}
        for merged_row in reversed(merged_rows):
            margin_row = margin_by_date.get(merged_row.obs_date)
            if margin_row is None:
                continue
            self._warning_manager.evaluate_and_store(
                merged_row,
                margin_row,
                merged_rows,
                computed_rows,
            )
            return

    def _should_fetch_live_futures(self) -> bool:
        """Skip slow Yahoo pulls during automated tests."""
        from app.core.dependencies import get_settings

        return get_settings().env != "test"
