"""Unit tests for Yahoo Finance futures client."""

from __future__ import annotations

from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch

import pandas as pd

from app.clients.yahoo_futures_client import (
    FuturesSymbolSpec,
    YahooFuturesClient,
    _cents_to_dollars_per_bushel,
)


def test_corn_transform_matches_colab_scaling() -> None:
    assert _cents_to_dollars_per_bushel(450.0) == 4.5


@patch("app.clients.yahoo_futures_client.yf.Ticker")
def test_fetch_symbol_applies_transform_and_tags_source(mock_ticker_cls: MagicMock) -> None:
    history = pd.DataFrame(
        {"Close": [450.0, 455.0]},
        index=pd.to_datetime(["2024-01-02", "2024-01-03"]),
    )
    mock_ticker_cls.return_value.history.return_value = history

    spec = FuturesSymbolSpec("ZC=F", "corn_usd_per_bushel", _cents_to_dollars_per_bushel)
    observations = YahooFuturesClient().fetch_symbol(spec, period="5y")

    mock_ticker_cls.assert_called_once_with("ZC=F")
    mock_ticker_cls.return_value.history.assert_called_once_with(
        period="5y",
        auto_adjust=False,
    )
    assert len(observations) == 2
    assert observations[0].source == "yahoo_futures"
    assert observations[0].series_id == "corn_usd_per_bushel"
    assert observations[0].obs_date == date(2024, 1, 2)
    assert observations[0].value == 4.5


@patch("app.clients.yahoo_futures_client.yf.Ticker")
def test_fetch_symbol_returns_empty_on_yfinance_error(mock_ticker_cls: MagicMock) -> None:
    mock_ticker_cls.return_value.history.side_effect = RuntimeError("network down")

    spec = FuturesSymbolSpec("EH=F", "ethanol_usd_per_gallon")
    observations = YahooFuturesClient().fetch_symbol(spec)

    assert observations == []


@patch("app.clients.yahoo_futures_client.yf.Ticker")
def test_fetch_all_uses_colab_tickers(mock_ticker_cls: MagicMock) -> None:
    def _history_side_effect(*, period: str, auto_adjust: bool) -> pd.DataFrame:
        return pd.DataFrame(
            {"Close": [1.0]},
            index=pd.to_datetime(["2024-06-01"]),
        )

    mock_ticker_cls.return_value.history.side_effect = lambda **kwargs: _history_side_effect(
        period=kwargs["period"],
        auto_adjust=kwargs["auto_adjust"],
    )

    observations = YahooFuturesClient().fetch_all(period="5y")

    assert mock_ticker_cls.call_count == 4
    called_tickers = {call.args[0] for call in mock_ticker_cls.call_args_list}
    assert called_tickers == {"ZC=F", "EH=F", "RB=F", "NG=F"}
    assert len(observations) == 4
    assert all(obs.fetched_at.tzinfo == timezone.utc for obs in observations)
