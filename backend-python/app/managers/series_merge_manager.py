"""Merge raw observations into a calendar-daily panel with forward-filled weekly data."""

from __future__ import annotations

from datetime import date, timedelta

from app.storage.duckdb_repository import DuckDbRepository, MergedDailyRow, RawObservation


# Logical series ids used across clients, merge, and overview.
SERIES_CORN = "corn_usd_per_bushel"
SERIES_ETHANOL = "ethanol_usd_per_gallon"
SERIES_DDGS = "ddgs_usd_per_short_ton"
SERIES_RBOB = "rbob_usd_per_gallon"
SERIES_NAT_GAS = "nat_gas_usd_per_mmbtu"
SERIES_ETHANOL_STOCKS = "ethanol_stocks_mmbbl"
SERIES_ETHANOL_PRODUCTION = "ethanol_production_mbpd"
SERIES_CORN_OIL = "corn_oil_usd_per_pound"
SERIES_WASDE_CORN_ETHANOL = "wasde_corn_for_ethanol_mbu"
SERIES_D6_RIN = "d6_rin_usd_per_gallon"

WEEKLY_SERIES = {SERIES_ETHANOL_STOCKS, SERIES_ETHANOL_PRODUCTION, SERIES_D6_RIN}
MONTHLY_SERIES = {SERIES_WASDE_CORN_ETHANOL}


class SeriesMergeManager:
    """
    Builds one row per calendar day from heterogeneous raw feeds.

    Casual: lines up daily futures with weekly EIA numbers.

    Uses calendar-daily index with forward-fill for weekly EIA and monthly WASDE
    so charts stay continuous. Flags release days via metadata on the API layer.
    """

    # yahoo_futures is the live Yahoo client source tag (not "yahoo").
    # epa_emts is the EPA RIN CSV file-drop client. All live sources outrank seed.
    SOURCE_PRIORITY = {"eia": 3, "epa_emts": 3, "yahoo_futures": 2, "seed": 1}

    def __init__(self, repository: DuckDbRepository) -> None:
        self._repository = repository

    @classmethod
    def source_priority(cls, source: str) -> int:
        """
        Rank a raw feed so live beats synthetic seed.

        Casual: higher number wins when two sources share a date.
        """
        return cls.SOURCE_PRIORITY.get(source, 0)

    def rebuild_merged_daily(
        self,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[MergedDailyRow]:
        """
        Rebuild merged_daily from raw_observations.

        When dates are omitted, uses the min/max available in raw data.
        """
        series_map = self._load_raw_series_map()
        if not series_map:
            return []

        all_dates: set[date] = set()
        for observations in series_map.values():
            all_dates.update(obs.obs_date for obs in observations)

        if not all_dates:
            return []

        resolved_start = start_date or min(all_dates)
        resolved_end = end_date or max(all_dates)
        calendar_dates = self._calendar_dates(resolved_start, resolved_end)

        merged_rows: list[MergedDailyRow] = []
        for obs_date in calendar_dates:
            merged_rows.append(
                MergedDailyRow(
                    obs_date=obs_date,
                    corn_usd_per_bushel=self._value_on_date(
                        series_map.get(SERIES_CORN, []), obs_date, forward_fill=True
                    ),
                    ethanol_usd_per_gallon=self._value_on_date(
                        series_map.get(SERIES_ETHANOL, []), obs_date, forward_fill=True
                    ),
                    ddgs_usd_per_short_ton=self._value_on_date(
                        series_map.get(SERIES_DDGS, []), obs_date, forward_fill=True
                    ),
                    rbob_usd_per_gallon=self._value_on_date(
                        series_map.get(SERIES_RBOB, []), obs_date, forward_fill=True
                    ),
                    nat_gas_usd_per_mmbtu=self._value_on_date(
                        series_map.get(SERIES_NAT_GAS, []), obs_date, forward_fill=True
                    ),
                    ethanol_stocks_mmbbl=self._value_on_date(
                        series_map.get(SERIES_ETHANOL_STOCKS, []),
                        obs_date,
                        forward_fill=True,
                    ),
                    ethanol_production_mbpd=self._value_on_date(
                        series_map.get(SERIES_ETHANOL_PRODUCTION, []),
                        obs_date,
                        forward_fill=True,
                    ),
                    corn_oil_usd_per_pound=self._value_on_date(
                        series_map.get(SERIES_CORN_OIL, []), obs_date, forward_fill=True
                    ),
                    wasde_corn_for_ethanol_mbu=self._value_on_date(
                        series_map.get(SERIES_WASDE_CORN_ETHANOL, []),
                        obs_date,
                        forward_fill=True,
                    ),
                    d6_rin_usd_per_gallon=self._value_on_date(
                        series_map.get(SERIES_D6_RIN, []),
                        obs_date,
                        forward_fill=True,
                    ),
                )
            )

        self._repository.replace_merged_daily(merged_rows)
        return merged_rows

    def _load_raw_series_map(self) -> dict[str, list[RawObservation]]:
        """
        Group raw rows by series, preferring live feeds over synthetic seed rows.

        Casual: if EIA and seed both have a Wednesday, trust EIA.

        ``raw_observations`` stores one row per (source, series_id, date). After
        the first bootstrap, seed and EIA can overlap on the same calendar day;
        the merge should keep the higher-trust source so the UI reflects live
        weekly stocks/production instead of stale demo numbers.
        """
        observations = self._repository.fetch_all_raw_observations()
        best_by_series_date: dict[tuple[str, date], RawObservation] = {}

        for observation in observations:
            key = (observation.series_id, observation.obs_date)
            existing = best_by_series_date.get(key)
            if existing is None or self.source_priority(
                observation.source
            ) > self.source_priority(existing.source):
                best_by_series_date[key] = observation

        series_map: dict[str, list[RawObservation]] = {}
        for observation in best_by_series_date.values():
            series_map.setdefault(observation.series_id, []).append(observation)

        for series_id in series_map:
            series_map[series_id].sort(key=lambda item: item.obs_date)
        return series_map

    @staticmethod
    def _calendar_dates(start_date: date, end_date: date) -> list[date]:
        dates: list[date] = []
        cursor = start_date
        while cursor <= end_date:
            dates.append(cursor)
            cursor += timedelta(days=1)
        return dates

    @staticmethod
    def _value_on_date(
        observations: list[RawObservation],
        obs_date: date,
        *,
        forward_fill: bool = False,
    ) -> float | None:
        if not observations:
            return None

        exact_matches = [obs.value for obs in observations if obs.obs_date == obs_date]
        if exact_matches:
            return exact_matches[-1]

        if not forward_fill:
            return None

        prior = [obs for obs in observations if obs.obs_date <= obs_date]
        if not prior:
            return None
        return prior[-1].value
