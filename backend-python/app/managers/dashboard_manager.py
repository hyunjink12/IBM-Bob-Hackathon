"""Builds dashboard API payloads from persisted series."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from app.managers.crush_margin_calculator import CrushMarginCalculator
from app.managers.inventory_stress_manager import InventoryStressManager
from app.managers.seed_data_status_manager import SeedDataStatusManager
from app.managers.warning_backtester import (
    RuleBacktestReport,
    WarningRuleBacktester,
    report_to_dict,
)
from app.managers.series_merge_manager import (
    SERIES_CORN,
    SERIES_DDGS,
    SERIES_ETHANOL,
    SERIES_ETHANOL_PRODUCTION,
    SERIES_ETHANOL_STOCKS,
    SERIES_NAT_GAS,
    SERIES_RBOB,
    SERIES_WASDE_CORN_ETHANOL,
)
from app.managers.z_score_manager import ZScoreManager
from app.models.crush_model_config import CrushModelConfig
from app.storage.duckdb_repository import DuckDbRepository


_VALID_GRANULARITIES: frozenset[str] = frozenset({"daily", "weekly", "monthly"})


def _period_key(iso_date: str, granularity: str) -> tuple:
    """
    Bucket key for downsampling: (year, iso_week) or (year, month) or the date itself.

    Casual: which weekly/monthly bin does this row belong to?
    """
    obs_date = date.fromisoformat(iso_date)
    if granularity == "weekly":
        year, week, _ = obs_date.isocalendar()
        return ("weekly", year, week)
    if granularity == "monthly":
        return ("monthly", obs_date.year, obs_date.month)
    return ("daily", obs_date.toordinal())


def _downsample_series(
    series: list[dict[str, Any]],
    granularity: str,
) -> list[dict[str, Any]]:
    """
    Keep the last observation per period for weekly/monthly; pass-through for daily.

    Casual: one point per week/month = the Friday/month-end print, not an average.

    Uses "last obs of period" so what the chart shows on 2026-W28 is literally the
    daily row that landed on the last available day of that ISO week. This matches
    OHLC-style close-of-period convention traders read intuitively. Z-scores and
    signal labels are carried through unchanged — they were computed at daily
    cadence and remain the honest value at that checkpoint day.
    """
    if granularity == "daily" or not series:
        return series
    if granularity not in _VALID_GRANULARITIES:
        return series

    # Series is already date-ordered ascending from the SQL query, so the last
    # row we see per bucket key IS the last observation of that period.
    last_by_bucket: dict[tuple, dict[str, Any]] = {}
    for row in series:
        last_by_bucket[_period_key(row["date"], granularity)] = row
    return sorted(last_by_bucket.values(), key=lambda item: item["date"])


class DashboardManager:
    """
    Reads DuckDB and shapes JSON for the React dashboard.

    Casual: packages everything the frontend panels need.

    Keeps API routes thin by centralizing range filtering, spread math, and
    per-series staleness timestamps in one place.
    """

    OVERVIEW_SERIES = (
        ("corn", SERIES_CORN, "corn_usd_per_bushel", "$/bu", "CBOT corn futures"),
        ("ethanol", SERIES_ETHANOL, "ethanol_usd_per_gallon", "$/gal", "CME EH futures (Chicago Ethanol Platts)"),
        ("ddgs", SERIES_DDGS, "ddgs_usd_per_short_ton", "$/short ton", "DDGS coproduct"),
        ("nat_gas", SERIES_NAT_GAS, "nat_gas_usd_per_mmbtu", "$/MMBtu", "Henry Hub proxy"),
        ("rbob", SERIES_RBOB, "rbob_usd_per_gallon", "$/gal", "RBOB gasoline futures"),
        (
            "ethanol_stocks",
            SERIES_ETHANOL_STOCKS,
            "ethanol_stocks_mmbbl",
            "MMbbl",
            "EIA weekly ethanol stocks",
        ),
        (
            "ethanol_production",
            SERIES_ETHANOL_PRODUCTION,
            "ethanol_production_mbpd",
            "Mbpd",
            "EIA weekly ethanol production",
        ),
    )

    def __init__(
        self,
        repository: DuckDbRepository,
        crush_config: CrushModelConfig,
        seed_status_manager: SeedDataStatusManager | None = None,
        inventory_stress_manager: InventoryStressManager | None = None,
        backtester: WarningRuleBacktester | None = None,
    ) -> None:
        self._repository = repository
        self._margin_calculator = CrushMarginCalculator(crush_config)
        self._z_score_manager = ZScoreManager()
        self._seed_status_manager = seed_status_manager or SeedDataStatusManager(
            repository
        )
        self._inventory_stress_manager = (
            inventory_stress_manager or InventoryStressManager()
        )
        self._backtester = backtester or WarningRuleBacktester(repository)
        self._backtest_cache: tuple[str | None, list[RuleBacktestReport]] | None = None

    def get_overview(self) -> dict:
        """Panel 1 payload with latest values, timestamps, and seed provenance."""
        latest = self._repository.fetch_latest_merged_daily()
        metrics = []
        for key, series_id, field_name, unit, description in self.OVERVIEW_SERIES:
            value = getattr(latest, field_name, None) if latest else None
            last_updated = self._repository.get_series_last_updated(series_id)
            metrics.append(
                {
                    "key": key,
                    "label": key.replace("_", " ").title(),
                    "value": value,
                    "unit": unit,
                    "description": description,
                    "last_updated": last_updated.isoformat() if last_updated else None,
                }
            )

        wasde = self._build_wasde_summary(latest)
        return {
            "as_of": latest.obs_date.isoformat() if latest else None,
            "metrics": metrics,
            "wasde": wasde,
            "data_provenance": self._seed_status_manager.get_status(),
        }

    def get_margins(
        self,
        *,
        range_token: str = "1Y",
        window_type: str = "rolling",
        lookback_days: int = 1825,
        granularity: str = "daily",
    ) -> dict:
        """
        Panel 2 payload with margin series and current signal.

        `granularity` in {"daily","weekly","monthly"} downsamples to the last
        observation of each period. Z-scores and signal labels are the underlying
        daily values on the checkpoint day — not recomputed at coarser cadence.
        """
        start_date, end_date = self._resolve_date_range(range_token)
        margins = self._repository.fetch_computed_margins(start_date, end_date)
        latest = margins[-1] if margins else None
        series = [
            {
                "date": row.obs_date.isoformat(),
                "margin_per_bushel": row.margin_per_bushel,
                "margin_per_gallon": row.margin_per_gallon,
                "z_score": row.z_score,
                "signal_label": row.signal_label,
            }
            for row in margins
        ]
        return {
            "range": range_token,
            "window_type": window_type,
            "lookback_days": lookback_days,
            "granularity": granularity,
            "current": self._margin_snapshot(latest),
            "series": _downsample_series(series, granularity),
        }

    def get_spread(
        self,
        *,
        range_token: str = "1Y",
        granularity: str = "daily",
    ) -> dict:
        """
        Panel 3 payload with the CME-standard ethanol crush spread.

        Casual: 2.8 gallons of ethanol out for every bushel of corn in.

        `crush_spread_usd_per_bushel` = 2.8 × ethanol_$/gal − corn_$/bu, both
        legs surfaced so the UI can show which side is driving the move. Series
        rows carry the same rolling-z-score / rich-normal-weak label the crush
        margin panel uses so the abstract's "rich or cheap" reading is explicit.
        """
        start_date, end_date = self._resolve_date_range(range_token)
        merged_rows = self._repository.fetch_merged_daily(start_date, end_date)

        spread_points: list[tuple] = []  # (obs_date, spread_val, eth_leg, corn_leg)
        for row in merged_rows:
            spread = self._margin_calculator.calculate_spread(row)
            if spread is None:
                continue
            spread_points.append(
                (
                    row.obs_date,
                    spread.spread_usd_per_bushel,
                    spread.ethanol_leg_usd_per_bushel,
                    spread.corn_leg_usd_per_bushel,
                )
            )

        annotated = self._z_score_manager.annotate_series(
            [(obs_date, spread_val) for obs_date, spread_val, _, _ in spread_points]
        )

        series = []
        for (obs_date, spread_val, eth_leg, corn_leg), (_, _, z_score, signal_label) in zip(
            spread_points, annotated
        ):
            series.append(
                {
                    "date": obs_date.isoformat(),
                    "crush_spread_usd_per_bushel": spread_val,
                    "ethanol_leg_usd_per_bushel": eth_leg,
                    "corn_leg_usd_per_bushel": corn_leg,
                    "z_score": z_score,
                    "signal_label": signal_label,
                }
            )
        current = series[-1] if series else None
        return {
            "range": range_token,
            "granularity": granularity,
            "series": _downsample_series(series, granularity),
            "current": current,
        }

    def get_warnings(self) -> dict:
        """
        Panel 4 payload with stress snapshot plus active warning cards.

        Casual: always send stocks/production context, not just empty alerts.

        Calm markets used to return only ``warnings: []``, which made the UI
        look broken. The stress snapshot keeps levels and deltas visible even
        when no rule-based cards fire.

        Warning cards are keyed to the latest day that has a computed margin
        (same rule as ingest), which can lag the tip merged calendar day on
        weekends/holidays when prices are missing.
        """
        latest = self._repository.fetch_latest_merged_daily()
        if latest is None:
            return {
                "as_of": None,
                "warnings": [],
                "stress": self._inventory_stress_manager.build_snapshot(
                    [], None, 0
                ),
            }

        history = self._repository.fetch_merged_daily()
        latest_margin = self._repository.fetch_latest_computed_margin()
        warning_date = (
            latest_margin.obs_date if latest_margin is not None else latest.obs_date
        )
        warnings = self._repository.fetch_warning_signals_for_date(warning_date)
        stress = self._inventory_stress_manager.build_snapshot(
            history,
            latest_margin,
            len(warnings),
        )
        return {
            "as_of": latest.obs_date.isoformat(),
            "warnings": warnings,
            "stress": stress,
        }

    def get_latest_ingest_cache_key(self) -> str | None:
        """Return the ISO timestamp of the last finished ingestion run, or None."""
        latest_ingest = self._repository.get_latest_ingestion_run()
        if latest_ingest and latest_ingest.get("finished_at"):
            return latest_ingest["finished_at"].isoformat()
        return None

    def get_backtest(self) -> dict:
        """
        Backtest reports for each warning rule, cached per ingestion run.

        Casual: 'if this rule had fired historically, what happened next?'

        Cached in-memory keyed on the latest ingestion timestamp, so we don't
        replay 5Y of history on every dashboard page load. Invalidates
        automatically after a new ingest.
        """
        cache_key = self.get_latest_ingest_cache_key()
        if self._backtest_cache is None or self._backtest_cache[0] != cache_key:
            reports = self._backtester.run()
            self._backtest_cache = (cache_key, reports)
        _, reports = self._backtest_cache
        return {
            "reports": [report_to_dict(report) for report in reports],
        }

    def _build_wasde_summary(self, latest) -> dict:
        """WASDE table-row summary with latest value and month-over-month delta."""
        if latest is None or latest.wasde_corn_for_ethanol_mbu is None:
            return {
                "value_mbu": None,
                "report_month": None,
                "delta_mbu": None,
                "last_updated": None,
            }

        history = self._repository.fetch_merged_daily()
        prior = None
        for row in reversed(history[:-1]):
            if row.wasde_corn_for_ethanol_mbu is not None:
                prior = row
                break

        delta = None
        if prior is not None:
            delta = latest.wasde_corn_for_ethanol_mbu - prior.wasde_corn_for_ethanol_mbu

        last_updated = self._repository.get_series_last_updated(SERIES_WASDE_CORN_ETHANOL)
        return {
            "value_mbu": latest.wasde_corn_for_ethanol_mbu,
            "report_month": latest.obs_date.strftime("%Y-%m"),
            "delta_mbu": delta,
            "last_updated": last_updated.isoformat() if last_updated else None,
        }

    def _resolve_date_range(self, range_token: str) -> tuple[date | None, date | None]:
        days = self._z_score_manager.parse_range_to_days(range_token)
        end_date = date.today()
        if days is None:
            return None, end_date
        return end_date - timedelta(days=days), end_date

    @staticmethod
    def _margin_snapshot(latest) -> dict | None:
        if latest is None:
            return None
        return {
            "date": latest.obs_date.isoformat(),
            "margin_per_bushel": latest.margin_per_bushel,
            "margin_per_gallon": latest.margin_per_gallon,
            "z_score": latest.z_score,
            "signal_label": latest.signal_label,
            "corn_oil_included": latest.corn_oil_included,
        }
