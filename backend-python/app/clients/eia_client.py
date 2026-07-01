"""EIA Open Data API client for ethanol production and stocks."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone

import httpx

from app.storage.duckdb_repository import RawObservation


@dataclass(frozen=True)
class EiaSeriesSpec:
    """One EIA series to pull."""

    series_id: str
    logical_id: str


class EiaClient:
    """
    Fetches weekly ethanol production and inventory from EIA.

    Casual: grabs the government's ethanol tank and run-rate numbers.

    Uses the public EIA API v2. When no API key is configured, returns an
    empty list so ingestion can fall back to seeded data without crashing.
    """

    BASE_URL = "https://api.eia.gov/v2"

    ETHANOL_PRODUCTION = EiaSeriesSpec(
        series_id="PET.W_EPOOXE_YOP_NUS_MBBLD",
        logical_id="ethanol_production_mbpd",
    )
    ETHANOL_STOCKS = EiaSeriesSpec(
        series_id="PET.W_EPOOXE_SAE_NUS_MBBL",
        logical_id="ethanol_stocks_mmbbl",
    )

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key.strip()

    @property
    def is_configured(self) -> bool:
        """True when an API key is available."""
        return bool(self._api_key)

    def fetch_series(self, spec: EiaSeriesSpec, *, length: int = 5000) -> list[RawObservation]:
        """Download one EIA series as raw observations."""
        if not self.is_configured:
            return []

        url = f"{self.BASE_URL}/seriesid/{spec.series_id}"
        params = {"api_key": self._api_key, "length": length}
        response = httpx.get(url, params=params, timeout=30.0)
        response.raise_for_status()
        payload = response.json()

        fetched_at = datetime.now(timezone.utc)
        observations: list[RawObservation] = []
        response_data = payload.get("response", {}).get("data", [])
        for item in response_data:
            period = item.get("period")
            value = item.get("value")
            if period is None or value in (None, ""):
                continue
            observations.append(
                RawObservation(
                    source="eia",
                    series_id=spec.logical_id,
                    obs_date=date.fromisoformat(str(period)),
                    value=float(value),
                    fetched_at=fetched_at,
                )
            )
        return observations

    def fetch_ethanol_weekly(self) -> list[RawObservation]:
        """Fetch both ethanol production and stocks series."""
        observations: list[RawObservation] = []
        observations.extend(self.fetch_series(self.ETHANOL_PRODUCTION))
        observations.extend(self.fetch_series(self.ETHANOL_STOCKS))
        return observations
