"""Unit tests for inventory / production stress snapshots."""

from datetime import date, timedelta

import pytest

from app.managers.inventory_stress_manager import InventoryStressManager
from app.storage.duckdb_repository import ComputedMarginRow, MergedDailyRow


def _history(
    length: int,
    *,
    stocks_start: float = 20.0,
    stocks_step: float = 0.0,
    production: float = 1000.0,
) -> list[MergedDailyRow]:
    rows = []
    for index in range(length):
        rows.append(
            MergedDailyRow(
                obs_date=date(2024, 1, 1) + timedelta(days=index),
                corn_usd_per_bushel=5.0,
                ethanol_usd_per_gallon=1.8,
                ddgs_usd_per_short_ton=150.0,
                rbob_usd_per_gallon=2.0,
                nat_gas_usd_per_mmbtu=2.5,
                ethanol_stocks_mmbbl=stocks_start + index * stocks_step,
                ethanol_production_mbpd=production,
                corn_oil_usd_per_pound=0.4,
                wasde_corn_for_ethanol_mbu=5400.0,
            )
        )
    return rows


def _margin(signal_label: str = "normal") -> ComputedMarginRow:
    return ComputedMarginRow(
        obs_date=date(2024, 6, 1),
        margin_per_bushel=0.5,
        margin_per_gallon=0.18,
        z_score=0.1,
        signal_label=signal_label,
        corn_oil_included=True,
    )


@pytest.mark.unit
def test_snapshot_includes_stocks_and_production_levels() -> None:
    """Casual: calm markets still get real numbers, not a blank panel."""
    manager = InventoryStressManager()
    history = _history(60, stocks_start=22.0, production=1050.0)

    snapshot = manager.build_snapshot(history, _margin("normal"), 0)

    assert snapshot["stocks_mmbbl"] == pytest.approx(22.0)
    assert snapshot["production_mbpd"] == pytest.approx(1050.0)
    assert snapshot["margin_signal_label"] == "normal"
    assert snapshot["status"] == "calm"
    assert "No inventory" in snapshot["status_message"]


@pytest.mark.unit
def test_stocks_building_marks_watch_status() -> None:
    """Casual: rising tanks flip the badge to watch even without alert cards."""
    manager = InventoryStressManager()
    # ~0.1/day over 60 days => well above the 2% / 28-day build threshold.
    history = _history(60, stocks_start=20.0, stocks_step=0.1)

    snapshot = manager.build_snapshot(history, _margin("normal"), 0)

    assert snapshot["stocks_change_28d_pct"] is not None
    assert snapshot["stocks_change_28d_pct"] > 0.02
    assert snapshot["status"] == "watch"


@pytest.mark.unit
def test_active_warnings_mark_alert_status() -> None:
    """Casual: any fired warning card means alert."""
    manager = InventoryStressManager()
    history = _history(40)

    snapshot = manager.build_snapshot(history, _margin("rich"), 2)

    assert snapshot["status"] == "alert"
    assert "2 active warning" in snapshot["status_message"]
