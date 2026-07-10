"""Unit tests for seed-data provenance detection."""

from datetime import date, datetime, timezone
from pathlib import Path

from app.managers.seed_data_status_manager import SeedDataStatusManager
from app.storage.duckdb_repository import DuckDbRepository, RawObservation


def _repo(tmp_path: Path) -> DuckDbRepository:
    return DuckDbRepository(tmp_path / "seed_status.duckdb")


def test_reports_seed_when_only_seed_rows_exist(tmp_path: Path) -> None:
    """Casual: empty live feeds → banner should fire."""
    repository = _repo(tmp_path)
    fetched_at = datetime.now(timezone.utc)
    repository.upsert_raw_observations(
        [
            RawObservation(
                "seed",
                "corn_usd_per_bushel",
                date(2026, 7, 1),
                4.5,
                fetched_at,
            ),
            RawObservation(
                "seed",
                "ethanol_usd_per_gallon",
                date(2026, 7, 1),
                1.8,
                fetched_at,
            ),
        ]
    )

    status = SeedDataStatusManager(repository).get_status()

    assert status["using_seed_data"] is True
    assert "corn_usd_per_bushel" in status["seeded_series"]
    assert status["message"] is not None


def test_live_yahoo_and_eia_clear_seed_warning(tmp_path: Path) -> None:
    """Casual: when live feeds exist for every live-capable series, hide the banner."""
    repository = _repo(tmp_path)
    fetched_at = datetime.now(timezone.utc)
    obs_date = date(2026, 7, 1)
    repository.upsert_raw_observations(
        [
            RawObservation("seed", "corn_usd_per_bushel", obs_date, 4.0, fetched_at),
            RawObservation(
                "yahoo_futures", "corn_usd_per_bushel", obs_date, 4.2, fetched_at
            ),
            RawObservation("seed", "ethanol_usd_per_gallon", obs_date, 1.7, fetched_at),
            RawObservation(
                "yahoo_futures", "ethanol_usd_per_gallon", obs_date, 1.9, fetched_at
            ),
            RawObservation("seed", "rbob_usd_per_gallon", obs_date, 2.0, fetched_at),
            RawObservation(
                "yahoo_futures", "rbob_usd_per_gallon", obs_date, 2.1, fetched_at
            ),
            RawObservation("seed", "nat_gas_usd_per_mmbtu", obs_date, 2.5, fetched_at),
            RawObservation(
                "yahoo_futures", "nat_gas_usd_per_mmbtu", obs_date, 2.6, fetched_at
            ),
            RawObservation("seed", "ethanol_stocks_mmbbl", obs_date, 20.0, fetched_at),
            RawObservation("eia", "ethanol_stocks_mmbbl", obs_date, 21.0, fetched_at),
            RawObservation(
                "seed", "ethanol_production_mbpd", obs_date, 1000.0, fetched_at
            ),
            RawObservation(
                "eia", "ethanol_production_mbpd", obs_date, 1010.0, fetched_at
            ),
            # Seed-only series must not keep the banner on forever.
            RawObservation(
                "seed", "ddgs_usd_per_short_ton", obs_date, 160.0, fetched_at
            ),
        ]
    )

    status = SeedDataStatusManager(repository).get_status()

    assert status["using_seed_data"] is False
    assert status["seeded_series"] == []
    assert status["message"] is None


def test_seed_tip_date_does_not_false_alarm_when_yahoo_exists(tmp_path: Path) -> None:
    """Casual: seed through today + older Yahoo should not trip the banner."""
    repository = _repo(tmp_path)
    fetched_at = datetime.now(timezone.utc)
    repository.upsert_raw_observations(
        [
            RawObservation(
                "yahoo_futures",
                "corn_usd_per_bushel",
                date(2026, 7, 9),
                4.2,
                fetched_at,
            ),
            RawObservation(
                "seed",
                "corn_usd_per_bushel",
                date(2026, 7, 10),
                4.0,
                fetched_at,
            ),
            RawObservation(
                "yahoo_futures",
                "ethanol_usd_per_gallon",
                date(2026, 7, 9),
                1.9,
                fetched_at,
            ),
            RawObservation(
                "yahoo_futures",
                "rbob_usd_per_gallon",
                date(2026, 7, 9),
                2.1,
                fetched_at,
            ),
            RawObservation(
                "yahoo_futures",
                "nat_gas_usd_per_mmbtu",
                date(2026, 7, 9),
                2.6,
                fetched_at,
            ),
            RawObservation(
                "eia",
                "ethanol_stocks_mmbbl",
                date(2026, 7, 8),
                21.0,
                fetched_at,
            ),
            RawObservation(
                "eia",
                "ethanol_production_mbpd",
                date(2026, 7, 8),
                1010.0,
                fetched_at,
            ),
        ]
    )

    status = SeedDataStatusManager(repository).get_status()

    assert status["using_seed_data"] is False
