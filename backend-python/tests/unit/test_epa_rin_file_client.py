"""Unit tests for EpaRinFileClient CSV parsing + filtering rules."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.clients.epa_rin_file_client import EpaRinFileClient


_CSV_HEADER = (
    "Transfer Date by Week,Transfer Year,RIN Year,"
    "Fuel (D Code),QAP Service Type,RIN Price\n"
)


@pytest.mark.unit
def test_returns_empty_when_file_missing(tmp_path: Path) -> None:
    client = EpaRinFileClient(csv_path=tmp_path / "nonexistent.csv")
    assert client.is_configured is False
    assert client.fetch() == []


@pytest.mark.unit
def test_keeps_only_current_vintage_unverified_d6(tmp_path: Path) -> None:
    """Filter: RIN Year == Transfer Year AND QAP Service Type == Unverified AND Fuel == D6."""
    csv_path = tmp_path / "rin.csv"
    csv_path.write_text(
        _CSV_HEADER
        # Keep: current-vintage Unverified D6
        + '"6/22/2026","2026","2026","D6","Unverified","$1.99"\n'
        # Drop: prior-vintage
        + '"6/22/2026","2026","2025","D6","Unverified","$2.01"\n'
        # Drop: Q-RIN
        + '"6/22/2026","2026","2026","D6","Q-RIN","$1.95"\n'
        # Drop: D4 (biodiesel), not corn ethanol
        + '"6/22/2026","2026","2026","D4","Unverified","$1.50"\n'
    )
    observations = EpaRinFileClient(csv_path=csv_path).fetch()
    assert len(observations) == 1
    assert observations[0].value == pytest.approx(1.99)
    assert observations[0].source == "epa_emts"
    assert observations[0].series_id == "d6_rin_usd_per_gallon"


@pytest.mark.unit
def test_parses_date_and_price_formats(tmp_path: Path) -> None:
    csv_path = tmp_path / "rin.csv"
    csv_path.write_text(
        _CSV_HEADER
        + '"7/5/2010","2010","2010","D6","Unverified","$0.02"\n'
        + '"1/1/2018","2018","2018","D6","Unverified","$0.87"\n'
    )
    observations = EpaRinFileClient(csv_path=csv_path).fetch()
    assert len(observations) == 2
    assert {obs.obs_date.isoformat() for obs in observations} == {"2010-07-05", "2018-01-01"}


@pytest.mark.unit
def test_skips_unparseable_rows_without_crashing(tmp_path: Path) -> None:
    csv_path = tmp_path / "rin.csv"
    csv_path.write_text(
        _CSV_HEADER
        + '"6/22/2026","2026","2026","D6","Unverified","$1.99"\n'
        + '"bad-date","2026","2026","D6","Unverified","$1.50"\n'
        + '"6/29/2026","2026","2026","D6","Unverified","not-a-price"\n'
    )
    observations = EpaRinFileClient(csv_path=csv_path).fetch()
    assert len(observations) == 1
    assert observations[0].value == pytest.approx(1.99)
