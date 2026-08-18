"""Builds dashboard API payloads from persisted series."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from app.clients.cftc_cot_client import CftcCotClient
from app.managers.crush_margin_calculator import CrushMarginCalculator
from app.managers.inventory_stress_manager import InventoryStressManager
from app.managers.release_schedule_manager import ReleaseScheduleManager
from app.managers.seed_data_status_manager import SeedDataStatusManager
from app.managers.warning_backtester import (
    RuleBacktestReport,
    WarningRuleBacktester,
    report_to_dict,
)
from app.managers.series_merge_manager import (
    SERIES_CORN,
    SERIES_D6_RIN,
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

    # (key, series_id, field_name, unit, description, display_label)
    # Explicit display_label avoids ``.title()`` producing awkward casings like
    # "Ddgs" / "Rbob" — commodity acronyms must render as market-standard.
    OVERVIEW_SERIES = (
        ("corn", SERIES_CORN, "corn_usd_per_bushel", "$/bu", "CBOT corn futures", "Corn"),
        ("ethanol", SERIES_ETHANOL, "ethanol_usd_per_gallon", "$/gal", "CME EH futures (Chicago Ethanol Platts)", "Ethanol"),
        ("ddgs", SERIES_DDGS, "ddgs_usd_per_short_ton", "$/short ton", "DDGS coproduct", "DDGS"),
        ("nat_gas", SERIES_NAT_GAS, "nat_gas_usd_per_mmbtu", "$/MMBtu", "Henry Hub proxy", "Natural Gas"),
        # RBOB intentionally NOT here — it isn't a direct crush model input. It
        # surfaces in `blending_economics` on the overview payload, where it
        # belongs conceptually (the ethanol substitute in the gasoline pool).
        (
            "ethanol_stocks",
            SERIES_ETHANOL_STOCKS,
            "ethanol_stocks_mmbbl",
            "MMbbl",
            "EIA weekly ethanol stocks",
            "Ethanol Stocks",
        ),
        (
            "ethanol_production",
            SERIES_ETHANOL_PRODUCTION,
            "ethanol_production_mbpd",
            "Mb/d",
            "EIA weekly ethanol production",
            "Ethanol Production",
        ),
        (
            "d6_rin",
            SERIES_D6_RIN,
            "d6_rin_usd_per_gallon",
            # Market instrument is a RIN, not a gallon. For corn ethanol the
            # ethanol-equivalent value is 1.0 so the numeric conversion is a
            # no-op, but the unit label must name the traded instrument. The
            # regulatory-value $/bu conversion lives in the composition panel.
            "$/RIN",
            "EPA D6 corn ethanol RIN (weekly)",
            "D6 RIN Price",
        ),
    )

    def __init__(
        self,
        repository: DuckDbRepository,
        crush_config: CrushModelConfig,
        seed_status_manager: SeedDataStatusManager | None = None,
        inventory_stress_manager: InventoryStressManager | None = None,
        backtester: WarningRuleBacktester | None = None,
        release_schedule_manager: ReleaseScheduleManager | None = None,
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
        self._release_schedule = release_schedule_manager or ReleaseScheduleManager()

    def get_overview(self) -> dict:
        """Panel 1 payload with latest values, timestamps, and seed provenance."""
        latest = self._repository.fetch_latest_merged_daily()
        metrics = []
        for key, series_id, field_name, unit, description, display_label in self.OVERVIEW_SERIES:
            value = getattr(latest, field_name, None) if latest else None
            last_updated = self._repository.get_series_last_updated(series_id)
            metrics.append(
                {
                    "key": key,
                    "label": display_label,
                    "value": value,
                    "unit": unit,
                    "description": description,
                    "last_updated": last_updated.isoformat() if last_updated else None,
                }
            )

        wasde = self._build_wasde_summary(latest)
        blending = self._build_blending_economics(latest)
        return {
            "as_of": latest.obs_date.isoformat() if latest else None,
            "metrics": metrics,
            "wasde": wasde,
            "blending_economics": blending,
            "data_provenance": self._seed_status_manager.get_status(),
        }

    # Placeholder regime bands for the blender's advantage spread.
    # $/gal; positive = ethanol favored, negative = ethanol resisted. See README
    # "Blending economics" section for the rationale + caveat that these are
    # not derived from a historical distribution.
    _BLENDING_INDIFFERENCE_BAND_USD = 0.30

    def _build_blending_economics(self, latest) -> dict | None:
        """
        Blender's advantage = RBOB − (physical ethanol − D6 RIN credit).

        Casual: how much cheaper is a gallon of ethanol vs a gallon of RBOB
        once you subtract the RIN a blender captures.

        The blender captures the D6 RIN when they blend the ethanol into
        gasoline, so their effective input cost is `ethanol_price − rin_price`.
        Positive advantage → refiners push blend rates up (to E10/E15 limits);
        negative → refiners resist blending beyond the RFS mandate.

        Returns None when any required price leg is missing on the merged row.
        Falls back gracefully to physical-only (RBOB − ethanol) when only the
        RIN is missing, with `rin_included=False` so the UI can flag it.
        """
        if latest is None:
            return None
        rbob = latest.rbob_usd_per_gallon
        ethanol = latest.ethanol_usd_per_gallon
        if rbob is None or ethanol is None:
            return None

        rin = latest.d6_rin_usd_per_gallon
        rin_included = rin is not None
        effective_ethanol_cost = ethanol - (rin or 0.0)
        blender_advantage = rbob - effective_ethanol_cost

        if blender_advantage > self._BLENDING_INDIFFERENCE_BAND_USD:
            regime_label = "Blenders favor ethanol"
            regime_direction = "favor_ethanol"
        elif blender_advantage < -self._BLENDING_INDIFFERENCE_BAND_USD:
            regime_label = "Blenders resist ethanol"
            regime_direction = "resist_ethanol"
        else:
            regime_label = "Blend indifference"
            regime_direction = "indifference"

        # 1-year percentile + weekly sparkline series of the same spread.
        # Both derive from the same historical pass — recompute once, use twice.
        percentile_1y, sample_size, sparkline = self._blender_advantage_history(
            latest.obs_date, lookback_days=365, current_value=blender_advantage
        )

        # RBOB rides in the blending payload (it isn't a crush model input, so
        # it's not in OVERVIEW_SERIES) — but the frontend still renders a
        # standard metric card for it. Expose the same last_updated timestamp
        # the metric grid uses so the stale badge stays consistent.
        rbob_last_updated = self._repository.get_series_last_updated(SERIES_RBOB)

        return {
            "as_of": latest.obs_date.isoformat(),
            "rbob_usd_per_gallon": round(rbob, 4),
            "rbob_last_updated": rbob_last_updated.isoformat() if rbob_last_updated else None,
            "ethanol_usd_per_gallon": round(ethanol, 4),
            "d6_rin_usd_per_gallon": round(rin, 4) if rin is not None else None,
            "effective_ethanol_cost_usd_per_gallon": round(effective_ethanol_cost, 4),
            "blender_advantage_usd_per_gallon": round(blender_advantage, 4),
            "regime_label": regime_label,
            "regime_direction": regime_direction,
            "rin_included": rin_included,
            "indifference_band_usd_per_gallon": self._BLENDING_INDIFFERENCE_BAND_USD,
            "percentile_1y_pct": percentile_1y,
            "percentile_sample_size": sample_size,
            "sparkline_1y": sparkline,
        }

    def _blender_advantage_history(
        self,
        as_of_date,
        *,
        lookback_days: int,
        current_value: float,
    ) -> tuple[int | None, int, list[dict]]:
        """
        Compute 1Y percentile + weekly-downsampled sparkline in one pass.

        Returns (percentile 0-100, sample_size, weekly_series).
        Percentile is None when history is too thin (< 30 valid days).
        Weekly series is downsampled last-observation-of-week so it fits
        cleanly in a small SVG (~52 points).
        """
        from datetime import timedelta
        start = as_of_date - timedelta(days=lookback_days)
        rows = self._repository.fetch_merged_daily(start, as_of_date)
        values: list[float] = []
        weekly_by_key: dict[tuple[int, int], tuple] = {}
        for row in rows:
            if row.rbob_usd_per_gallon is None or row.ethanol_usd_per_gallon is None:
                continue
            rin_val = row.d6_rin_usd_per_gallon or 0.0
            advantage = row.rbob_usd_per_gallon - (row.ethanol_usd_per_gallon - rin_val)
            values.append(advantage)
            # ISO year+week keeps chronological order without off-by-one at year rollover
            iso_year, iso_week, _ = row.obs_date.isocalendar()
            weekly_by_key[(iso_year, iso_week)] = (row.obs_date, advantage)

        if len(values) < 30:
            return None, len(values), []

        rank = sum(1 for v in values if v <= current_value)
        percentile = round(rank / len(values) * 100)
        weekly = [
            {"date": d.isoformat(), "value": round(v, 4)}
            for _, (d, v) in sorted(weekly_by_key.items())
        ]
        return percentile, len(values), weekly

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
        composition = self._build_margin_composition(latest)
        return {
            "range": range_token,
            "window_type": window_type,
            "lookback_days": lookback_days,
            "granularity": granularity,
            "current": self._margin_snapshot(latest),
            "composition": composition,
            "series": _downsample_series(series, granularity),
        }

    def _build_margin_composition(self, latest) -> dict | None:
        """
        Per-driver breakdown for the day matching `latest` computed margin.

        Casual: 'what's making up today's margin.'

        Groups drivers into `physical_components` (crush P&L levers that sum
        to plant_operating_margin) and `regulatory_components` (D6 RIN value,
        shown separately because it is a compliance-market value, not
        producer operating revenue). Legacy `components` list retained for
        backward-compat with any consumer still reading the flat array.
        """
        if latest is None:
            return None
        merged_rows = self._repository.fetch_merged_daily(
            latest.obs_date, latest.obs_date
        )
        if not merged_rows:
            return None
        comp = self._margin_calculator.decompose(merged_rows[0])
        if comp is None:
            return None
        physical = [
            {"label": "Ethanol revenue", "kind": "revenue", "value_per_bushel": comp.ethanol_revenue},
            {"label": "DDGS revenue", "kind": "revenue", "value_per_bushel": comp.ddgs_revenue},
            {
                "label": "Corn oil revenue",
                "kind": "revenue",
                "value_per_bushel": comp.corn_oil_revenue,
                "included": comp.corn_oil_included,
            },
            {"label": "Corn cost", "kind": "cost", "value_per_bushel": comp.corn_cost},
            {"label": "Natural gas cost", "kind": "cost", "value_per_bushel": comp.nat_gas_cost},
            {"label": "Misc opex", "kind": "cost", "value_per_bushel": comp.misc_opex_cost},
        ]
        regulatory = [
            {
                "label": "D6 RIN value (captured at blending)",
                "kind": "regulatory",
                "value_per_bushel": comp.d6_rin_value,
                "included": comp.rin_included,
                "tooltip": (
                    "Market value of the D6 RIN generated per gallon of ethanol "
                    "blended into gasoline, scaled up by the CARD dry-mill yield "
                    "(2.8 gal/bu). The RIN is captured by the blender/refiner at "
                    "the point of blending — the ethanol producer does not "
                    "receive this value directly. Pass-through from RIN prices "
                    "to producer/corn economics is empirically small (blend wall "
                    "and inelastic short-run production) and is out of scope for "
                    "this dashboard. Shown here for scale of the RFS compliance "
                    "market attached to qualifying corn ethanol production."
                ),
            },
        ]
        plant_operating_margin = sum(item["value_per_bushel"] for item in physical)
        return {
            "as_of": latest.obs_date.isoformat(),
            "margin_per_bushel": latest.margin_per_bushel,
            "plant_operating_margin_per_bushel": plant_operating_margin,
            "d6_rin_value_per_bushel": comp.d6_rin_value,
            "rin_included": comp.rin_included,
            "physical_components": physical,
            "regulatory_components": regulatory,
            "components": physical + regulatory,   # legacy flat list
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

    def get_eia_releases(self, *, range_token: str = "1Y") -> dict:
        """
        EIA Weekly Petroleum Status Report release events within the range.

        Casual: dot on the chart for every Wednesday the EIA prints stocks/production.

        Joins stocks + production raw observations by obs_date (both series are
        weekly Wednesday releases and share dates). WoW % change is computed
        against the immediately prior release, not a forward-filled daily value.
        """
        start_date, end_date = self._resolve_date_range(range_token)

        # Pull one release earlier than start_date so the first in-range release
        # has a WoW baseline. Cheap: EIA is weekly, ~7 days back is enough.
        wow_lookback = (start_date - timedelta(days=10)) if start_date else None
        stocks_rows = self._repository.fetch_raw_observations_by_series(
            SERIES_ETHANOL_STOCKS, wow_lookback, end_date
        )
        production_rows = self._repository.fetch_raw_observations_by_series(
            SERIES_ETHANOL_PRODUCTION, wow_lookback, end_date
        )
        production_by_date = {r.obs_date: r.value for r in production_rows}

        releases: list[dict] = []
        prior_stocks: float | None = None
        prior_production: float | None = None
        for row in stocks_rows:
            # EiaSeriesSpec.unit_scale=0.001 is already applied at ingest by
            # EiaClient — raw_observations.value for this series is already
            # in MMbbl. A second scaling here made a 25 MMbbl print render as
            # 0.03 MMbbl in the EIA-release chart tooltip.
            stocks_mmbbl = row.value
            production_mbpd = production_by_date.get(row.obs_date)

            stocks_wow_pct = (
                (stocks_mmbbl - prior_stocks) / prior_stocks
                if prior_stocks not in (None, 0)
                else None
            )
            production_wow_pct = (
                (production_mbpd - prior_production) / prior_production
                if production_mbpd is not None
                and prior_production not in (None, 0)
                else None
            )

            if start_date is None or row.obs_date >= start_date:
                releases.append(
                    {
                        "date": row.obs_date.isoformat(),
                        "stocks_mmbbl": round(stocks_mmbbl, 3),
                        "stocks_wow_pct": stocks_wow_pct,
                        "production_mbpd": production_mbpd,
                        "production_wow_pct": production_wow_pct,
                    }
                )
            prior_stocks = stocks_mmbbl
            if production_mbpd is not None:
                prior_production = production_mbpd

        return {"range": range_token, "releases": releases}

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

    def get_cot_positioning(self, *, range_token: str = "1Y") -> dict:
        """
        CBOT Corn COT positioning payload: history series + latest print + percentile.

        Casual: 'where are the specs sitting, and how stretched is that?'

        Managed-money net (long − short) is the spec directional signal traders
        watch. Percentile is computed over the full 5Y file so 'stretched'
        readings survive a shorter chart-range selection.
        """
        start_date, end_date = self._resolve_date_range(range_token)
        reports = self._repository.fetch_cot_reports(
            CftcCotClient.CBOT_CORN_CODE, start_date, end_date
        )
        full_history = self._repository.fetch_cot_reports(
            CftcCotClient.CBOT_CORN_CODE
        )

        # Index the full history so WoW deltas can be computed even for the
        # first in-range point (its "prior" is one week earlier — potentially
        # outside the range but still in DB).
        history_by_date = {r["report_date"]: r for r in full_history}
        sorted_dates = sorted(history_by_date.keys())
        prior_by_date: dict = {}
        for i, d in enumerate(sorted_dates):
            if i == 0:
                prior_by_date[d] = None
            else:
                prior_by_date[d] = history_by_date[sorted_dates[i - 1]]

        def _delta(current_value, prior_row, key):
            if prior_row is None or current_value is None:
                return None
            prior_value = prior_row.get(key)
            if prior_value is None:
                return None
            return current_value - prior_value

        series: list[dict] = []
        for r in reports:
            mm_net = r["managed_money_long"] - r["managed_money_short"]
            producer_net = r["producer_long"] - r["producer_short"]
            prior = prior_by_date.get(r["report_date"])
            prior_mm_net = None
            if prior is not None:
                prior_mm_net = prior["managed_money_long"] - prior["managed_money_short"]
            series.append(
                {
                    "date": r["report_date"].isoformat(),
                    "managed_money_long": r["managed_money_long"],
                    "managed_money_short": r["managed_money_short"],
                    "managed_money_net": mm_net,
                    "producer_net": producer_net,
                    "open_interest": r["open_interest"],
                    "managed_money_long_wow": _delta(
                        r["managed_money_long"], prior, "managed_money_long"
                    ),
                    "managed_money_short_wow": _delta(
                        r["managed_money_short"], prior, "managed_money_short"
                    ),
                    "managed_money_net_wow": (
                        mm_net - prior_mm_net if prior_mm_net is not None else None
                    ),
                    "open_interest_wow": _delta(
                        r["open_interest"], prior, "open_interest"
                    ),
                }
            )

        latest = full_history[-1] if full_history else None
        prior = full_history[-2] if len(full_history) >= 2 else None
        latest_snapshot = None
        if latest is not None:
            mm_net = latest["managed_money_long"] - latest["managed_money_short"]
            mm_net_wow = None
            if prior is not None:
                prior_net = prior["managed_money_long"] - prior["managed_money_short"]
                mm_net_wow = mm_net - prior_net
            percentile = self._compute_mm_net_percentile(full_history, mm_net)
            latest_snapshot = {
                "report_date": latest["report_date"].isoformat(),
                "managed_money_long": latest["managed_money_long"],
                "managed_money_short": latest["managed_money_short"],
                "managed_money_net": mm_net,
                "managed_money_net_wow": mm_net_wow,
                "producer_net": latest["producer_long"] - latest["producer_short"],
                "open_interest": latest["open_interest"],
                "mm_net_percentile_5y": percentile,
            }

        return {
            "range": range_token,
            "current": latest_snapshot,
            "series": series,
        }

    @staticmethod
    def _compute_mm_net_percentile(
        history: list[dict], latest_mm_net: int
    ) -> float | None:
        """Rank the latest MM net within the full 5Y COT history."""
        if not history:
            return None
        nets = sorted(
            r["managed_money_long"] - r["managed_money_short"] for r in history
        )
        # Rank position of the latest value (empirical CDF).
        below_or_equal = sum(1 for n in nets if n <= latest_mm_net)
        return round(below_or_equal / len(nets), 3)

    def get_situational_tape(self) -> dict:
        """
        Rolling top-of-page tape items — countdowns, active warnings, key prints.

        Casual: everything a trader wants glanceable at all times.

        Items are keyed by type so the frontend can style each distinctly:
        - "release_countdown": next scheduled EIA / WASDE / COT
        - "cot_print": latest managed-money net + WoW delta for CBOT Corn
        - "warning": each active rule-based signal
        - "stale": any market series older than 7 days
        - "ingest": last successful ingestion timestamp
        """
        items: list[dict] = []

        for release in self._release_schedule.upcoming_releases():
            items.append({"type": "release_countdown", **release.to_dict()})

        cot_item = self._build_cot_tape_item()
        if cot_item is not None:
            items.append(cot_item)

        latest_margin = self._repository.fetch_latest_computed_margin()
        if latest_margin is not None:
            warnings = self._repository.fetch_warning_signals_for_date(
                latest_margin.obs_date
            )
            for warning in warnings:
                items.append(
                    {
                        "type": "warning",
                        "signal_type": warning.get("signal_type"),
                        "severity": warning.get("severity"),
                        "message": warning.get("message"),
                    }
                )

        for stale_item in self._build_stale_tape_items():
            items.append(stale_item)

        latest_ingest = self._repository.get_latest_ingestion_run()
        if latest_ingest and latest_ingest.get("finished_at"):
            items.append(
                {
                    "type": "ingest",
                    "finished_at": latest_ingest["finished_at"].isoformat(),
                    "status": latest_ingest.get("status"),
                }
            )

        return {"items": items}

    def _build_cot_tape_item(self) -> dict | None:
        latest = self._repository.fetch_latest_cot_report(CftcCotClient.CBOT_CORN_CODE)
        if latest is None:
            return None
        mm_net = latest["managed_money_long"] - latest["managed_money_short"]

        prior = self._repository.fetch_prior_cot_report(
            CftcCotClient.CBOT_CORN_CODE, latest["report_date"]
        )
        mm_net_wow = None
        if prior is not None:
            prior_net = prior["managed_money_long"] - prior["managed_money_short"]
            mm_net_wow = mm_net - prior_net

        return {
            "type": "cot_print",
            "contract": "CBOT Corn",
            "report_date": latest["report_date"].isoformat(),
            "managed_money_net": mm_net,
            "managed_money_net_wow": mm_net_wow,
        }

    def _build_stale_tape_items(self) -> list[dict]:
        stale: list[dict] = []
        for key, series_id, _, _, _, display_label in self.OVERVIEW_SERIES:
            last_updated = self._repository.get_series_last_updated(series_id)
            if last_updated is None:
                continue
            age_days = (date.today() - last_updated.date()).days
            if age_days >= 7:
                stale.append(
                    {
                        "type": "stale",
                        "key": key,
                        "label": display_label,
                        "age_days": age_days,
                    }
                )
        return stale

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
        end_date = date.today()
        if range_token.upper() == "YTD":
            return date(end_date.year, 1, 1), end_date
        days = self._z_score_manager.parse_range_to_days(range_token)
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
