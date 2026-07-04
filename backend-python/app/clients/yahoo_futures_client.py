"""Free futures price client using Yahoo Finance symbols."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone

import yfinance as yf

from app.storage.duckdb_repository import RawObservation

_logger = logging.getLogger(__name__)


def _identity(value: float) -> float:
    """Pass-through transform for symbols already in target units."""
    return value


def _cents_to_dollars_per_bushel(value: float) -> float:
    """Yahoo corn futures quote in cents/bushel → dollars/bushel."""
    return value / 100.0


@dataclass(frozen=True)
class FuturesSymbolSpec:
    """
    Maps a Yahoo ticker to our logical series id plus a unit transform.

    Casual: one futures symbol and how to turn its close into our schema.

    Mirrors the Colab notebook pattern:
    ``tickers = {"ZC=F": ("corn_usd_per_bushel", lambda x: x / 100.0), ...}``
    so each symbol owns its own ``yf.Ticker(...).history()`` call and scaling.
    """

    ticker: str
    logical_id: str
    transform: Callable[[float], float] = field(default=_identity)


class YahooFuturesClient:
    """
    Pulls front-month style futures proxies from Yahoo Finance.

    Casual: free(ish) CME-ish prices when you don't have a Bloomberg terminal.

    Yahoo is unofficial and can break; ingestion falls back to seeded history
    when downloads fail. Symbols are continuous-style proxies suitable for a
    hackathon dashboard, not institutional execution.

  Each symbol is fetched independently (same as the Colab notebook) via
  ``yf.Ticker(ticker).history(period=..., auto_adjust=False)``, Close column
  only, then the per-symbol transform is applied before persisting.
    """

    # Colab-aligned ticker map: ZC=F corn (÷100), EH/RB/NG pass-through.
    SYMBOLS: tuple[FuturesSymbolSpec, ...] = (
        FuturesSymbolSpec("ZC=F", "corn_usd_per_bushel", _cents_to_dollars_per_bushel),
        FuturesSymbolSpec("EH=F", "ethanol_usd_per_gallon", _identity),
        FuturesSymbolSpec("RB=F", "rbob_usd_per_gallon", _identity),
        FuturesSymbolSpec("NG=F", "nat_gas_usd_per_mmbtu", _identity),
    )

    def fetch_all(self, *, period: str = "5y") -> list[RawObservation]:
        """
        Download all configured futures symbols.

        Casual: loop every ticker and stitch the observations together.

        Per-symbol failures are logged and skipped so one bad symbol does not
        block the rest (same resilience pattern as the Colab try/except loop).
        """
        observations: list[RawObservation] = []
        for spec in self.SYMBOLS:
            observations.extend(self.fetch_symbol(spec, period=period))
        return observations

    def fetch_symbol(self, spec: FuturesSymbolSpec, *, period: str = "5y") -> list[RawObservation]:
        """
        Download one symbol history as raw observations.

        Casual: yfinance history → Close column → unit fix → DB rows.

        Uses ``auto_adjust=False`` so Close matches the Colab notebook and
        keeps corn cents/bushel scaling predictable.
        """
        fetched_at = datetime.now(timezone.utc)
        try:
            history = yf.Ticker(spec.ticker).history(period=period, auto_adjust=False)
        except Exception as exc:
            _logger.warning("Error fetching %s: %s", spec.ticker, exc)
            return []

        if history.empty:
            _logger.warning("No data found for %s (Yahoo Finance)", spec.ticker)
            return []

        if "Close" not in history.columns:
            _logger.warning("No Close column for %s (Yahoo Finance)", spec.ticker)
            return []

        observations: list[RawObservation] = []
        for timestamp, row in history.iterrows():
            close_price = row.get("Close")
            if close_price is None:
                continue
            try:
                value = spec.transform(float(close_price))
            except (TypeError, ValueError):
                continue
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
