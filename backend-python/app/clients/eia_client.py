"""EIA Open Data API client for ethanol production and stocks."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone

import httpx

from app.storage.duckdb_repository import RawObservation


@dataclass(frozen=True)
class EiaSeriesSpec:
    """
    One EIA v2 facet query to pull.

    Casual: describes which EIA table + filters to hit.

    Each spec maps to an EIA API v2 ``/data/`` route plus facet filters
    (product, process, duoarea) rather than the legacy ``/seriesid/`` shortcut,
    which no longer resolves for our ethanol series.
    """

    endpoint_path: str
    logical_id: str
    facets: dict[str, str]


class EiaClient:
    """
    Fetches weekly ethanol production and inventory from EIA.

    Casual: grabs the government's ethanol tank and run-rate numbers.

    Uses the public EIA API v2 facet endpoints (e.g. ``petroleum/pnp/wprode``).
    When no API key is configured, returns an empty list so ingestion can fall
    back to seeded data without crashing.
    """

    BASE_URL = "https://api.eia.gov/v2"

    # U.S. weekly oxygenate-plant production (MBBL/D) via petroleum/pnp/wprode.
    ETHANOL_PRODUCTION = EiaSeriesSpec(
        endpoint_path="petroleum/pnp/wprode/data",
        logical_id="ethanol_production_mbpd",
        facets={"product": "EPOOXE", "process": "YOP", "duoarea": "NUS"},
    )
    # U.S. weekly ending stocks (MMBBL) via petroleum/stoc/wstk.
    ETHANOL_STOCKS = EiaSeriesSpec(
        endpoint_path="petroleum/stoc/wstk/data",
        logical_id="ethanol_stocks_mmbbl",
        facets={"product": "EPOOXE", "process": "SAE", "duoarea": "NUS"},
    )

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key.strip()

    @property
    def is_configured(self) -> bool:
        """True when an API key is available."""
        return bool(self._api_key)

    def _build_request_params(self, spec: EiaSeriesSpec, *, length: int) -> dict[str, str | int]:
        """
        Build query params for an EIA v2 facet data request.

        Casual: turns our series spec into the URL knobs EIA expects.

        Mirrors the public API shape:
        ``frequency=weekly``, ``data[0]=value``, sorted by period descending,
        plus ``facets[facet][]`` entries for each filter on the spec.
        """
        params: dict[str, str | int] = {
            "frequency": "weekly",
            "data[0]": "value",
            "sort[0][column]": "period",
            "sort[0][direction]": "desc",
            "offset": 0,
            "length": length,
            "api_key": self._api_key,
        }
        for facet_name, facet_value in spec.facets.items():
            params[f"facets[{facet_name}][]"] = facet_value
        return params

    def fetch_series(self, spec: EiaSeriesSpec, *, length: int = 5000) -> list[RawObservation]:
        """Download one EIA series as raw observations."""
        if not self.is_configured:
            return []

        url = f"{self.BASE_URL}/{spec.endpoint_path}/"
        params = self._build_request_params(spec, length=length)
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
