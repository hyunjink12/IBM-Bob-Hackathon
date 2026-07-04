"""Live integration tests against the EIA Open Data API."""

from __future__ import annotations

import pytest

from app.clients.eia_client import EiaClient
from app.core.app_settings import AppSettings


@pytest.fixture
def eia_client() -> EiaClient:
    """Build an EIA client from real env settings (skips when no key)."""
    settings = AppSettings()
    if not settings.eia_api_key.strip():
        pytest.skip("APP_EIA_API_KEY is not set — skipping live EIA test")
    return EiaClient(settings.eia_api_key)


@pytest.mark.integration
@pytest.mark.live
def test_eia_production_series_returns_us_weekly_data(eia_client: EiaClient) -> None:
    """Production endpoint should return recent U.S. ethanol run-rate observations."""
    observations = eia_client.fetch_series(EiaClient.ETHANOL_PRODUCTION, length=10)

    assert len(observations) >= 5
    assert all(obs.series_id == "ethanol_production_mbpd" for obs in observations)
    assert all(obs.value > 0 for obs in observations)
    # Latest EIA weekly rows should be within the last few months.
    assert max(obs.obs_date for obs in observations).year >= 2025


@pytest.mark.integration
@pytest.mark.live
def test_eia_stocks_series_returns_us_weekly_data(eia_client: EiaClient) -> None:
    """Stocks endpoint should return recent U.S. ethanol inventory observations."""
    observations = eia_client.fetch_series(EiaClient.ETHANOL_STOCKS, length=10)

    assert len(observations) >= 5
    assert all(obs.series_id == "ethanol_stocks_mmbbl" for obs in observations)
    assert all(obs.value > 0 for obs in observations)
    assert max(obs.obs_date for obs in observations).year >= 2025


@pytest.mark.integration
@pytest.mark.live
def test_eia_fetch_ethanol_weekly_returns_both_series(eia_client: EiaClient) -> None:
    """Combined fetch should pull both production and stocks in one call."""
    observations = eia_client.fetch_ethanol_weekly()

    series_ids = {obs.series_id for obs in observations}
    assert "ethanol_production_mbpd" in series_ids
    assert "ethanol_stocks_mmbbl" in series_ids
    assert len(observations) >= 10
