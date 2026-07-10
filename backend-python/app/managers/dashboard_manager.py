"""Builds dashboard API payloads from persisted series."""

from __future__ import annotations

from datetime import date, timedelta

from app.managers.crush_margin_calculator import CrushMarginCalculator
from app.managers.inventory_stress_manager import InventoryStressManager
from app.managers.seed_data_status_manager import SeedDataStatusManager
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
    ) -> dict:
        """Panel 2 payload with margin series and current signal."""
        start_date, end_date = self._resolve_date_range(range_token)
        margins = self._repository.fetch_computed_margins(start_date, end_date)
        latest = margins[-1] if margins else None
        return {
            "range": range_token,
            "window_type": window_type,
            "lookback_days": lookback_days,
            "current": self._margin_snapshot(latest),
            "series": [
                {
                    "date": row.obs_date.isoformat(),
                    "margin_per_bushel": row.margin_per_bushel,
                    "margin_per_gallon": row.margin_per_gallon,
                    "z_score": row.z_score,
                    "signal_label": row.signal_label,
                }
                for row in margins
            ],
        }

    def get_spread(self, *, range_token: str = "1Y") -> dict:
        """
        Panel 3 payload with the CME-standard ethanol crush spread.

        Casual: 2.8 gallons of ethanol out for every bushel of corn in.

        `crush_spread_usd_per_bushel` = 2.8 × ethanol_$/gal − corn_$/bu, both
        legs surfaced so the UI can show which side is driving the move.
        """
        start_date, end_date = self._resolve_date_range(range_token)
        merged_rows = self._repository.fetch_merged_daily(start_date, end_date)
        series = []
        for row in merged_rows:
            spread = self._margin_calculator.calculate_spread(row)
            if spread is None:
                continue
            series.append(
                {
                    "date": row.obs_date.isoformat(),
                    "crush_spread_usd_per_bushel": spread.spread_usd_per_bushel,
                    "ethanol_leg_usd_per_bushel": spread.ethanol_leg_usd_per_bushel,
                    "corn_leg_usd_per_bushel": spread.corn_leg_usd_per_bushel,
                }
            )
        return {"range": range_token, "series": series}

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

    def get_panel5_placeholder(self) -> dict:
        """Panel 5 placeholder until content is defined."""
        return {
            "status": "placeholder",
            "message": "Panel 5 content TBD — slot reserved for RBOB blending or WASDE deep-dive.",
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
