"""Free futures price client using Yahoo Finance symbols."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone

import yfinance as yf

from app.storage.duckdb_repository import RawObservation


@dataclass(frozen=True)
class FuturesSymbolSpec:
    """Maps a Yahoo ticker to our logical series id."""

    ticker: str
    logical_id: str


class YahooFuturesClient:
    """
    Pulls front-month style futures proxies from Yahoo Finance.

    Casual: free(ish) CME-ish prices when you don't have a Bloomberg terminal.

    Yahoo is unofficial and can break; ingestion falls back to seeded history
    when downloads fail. Symbols are continuous-style proxies suitable for a
    hackathon dashboard, not institutional execution.
    """

    SYMBOLS: tuple[FuturesSymbolSpec, ...] = (
        FuturesSymbolSpec("ZC=F", "corn_usd_per_bushel"),
        FuturesSymbolSpec("EH=F", "ethanol_usd_per_gallon"),
        FuturesSymbolSpec("RB=F", "rbob_usd_per_gallon"),
        FuturesSymbolSpec("NG=F", "nat_gas_usd_per_mmbtu"),
    )

    def fetch_all(self, *, period: str = "5y") -> list[RawObservation]:
        """Download all configured futures symbols."""
        observations: list[RawObservation] = []
        for spec in self.SYMBOLS:
            observations.extend(self.fetch_symbol(spec, period=period))
        return observations

    def fetch_symbol(self, spec: FuturesSymbolSpec, *, period: str = "5y") -> list[RawObservation]:
        """Download one symbol history as raw observations."""
        fetched_at = datetime.now(timezone.utc)
        try:
            history = yf.Ticker(spec.ticker).history(period=period, auto_adjust=False)
        except Exception:
            return []

        if history.empty:
            return []

        observations: list[RawObservation] = []
        for timestamp, row in history.iterrows():
            close_price = row.get("Close")
            if close_price is None:
                continue
            value = float(close_price)
            if spec.logical_id == "corn_usd_per_bushel":
                # Yahoo corn futures are cents per bushel.
                value = value / 100.0
            observations.append(
                RawObservation(
                    source="yahoo_futures",
                    series_id=spec.logical_id,
                    obs_date=timestamp.date(),
                    value=value,
                    fetched_at=fetched_at,
                )
            )
        return observations
