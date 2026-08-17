"""Detects when synthetic seed rows are still driving the dashboard."""

from __future__ import annotations

from app.managers.series_merge_manager import (
    SERIES_CORN,
    SERIES_D6_RIN,
    SERIES_ETHANOL,
    SERIES_ETHANOL_PRODUCTION,
    SERIES_ETHANOL_STOCKS,
    SERIES_NAT_GAS,
    SERIES_RBOB,
)
from app.storage.duckdb_repository import DuckDbRepository


class SeedDataStatusManager:
    """
    Figures out if fake seed data is still what the UI is showing.

    Casual: tells the frontend “hey, this is demo data.”

    A live-capable series counts as seeded only when it has *no* Yahoo/EIA
    rows at all. Seed history is often written through ``date.today()``, so
    checking the single newest winning row would false-alarm whenever futures
    lag by a day. Absence of any live source is the reliable “fallback mode”
    signal the banner needs.
    """

    # Only series that a live source is expected to replace.
    LIVE_FEED_SERIES = (
        SERIES_CORN,
        SERIES_ETHANOL,
        SERIES_NAT_GAS,
        SERIES_RBOB,
        SERIES_ETHANOL_STOCKS,
        SERIES_ETHANOL_PRODUCTION,
        SERIES_D6_RIN,
    )

    LIVE_SOURCES = frozenset({"eia", "yahoo_futures", "epa_emts"})

    def __init__(self, repository: DuckDbRepository) -> None:
        self._repository = repository

    def get_status(self) -> dict:
        """
        Build a provenance payload for the overview API / UI banner.

        Casual: true/false plus which series never got a live feed.
        """
        seeded_series = self._series_without_live_source()
        using_seed = len(seeded_series) > 0
        return {
            "using_seed_data": using_seed,
            "seeded_series": seeded_series,
            "message": (
                "Synthetic seed data is powering one or more dashboard series. "
                "Values are for demo only — not live market prices."
                if using_seed
                else None
            ),
        }

    def _series_without_live_source(self) -> list[str]:
        """
        List live-capable series that only have seed (or nothing) in raw storage.

        Casual: if Yahoo/EIA never landed for a series, it’s still on seed.
        """
        observations = self._repository.fetch_all_raw_observations()
        live_series: set[str] = set()
        present_series: set[str] = set()

        for observation in observations:
            if observation.series_id not in self.LIVE_FEED_SERIES:
                continue
            present_series.add(observation.series_id)
            if observation.source in self.LIVE_SOURCES:
                live_series.add(observation.series_id)

        # Only flag series that exist and never received a live row.
        return sorted(present_series - live_series)
