"""Unit tests for merged daily series priority rules."""

from __future__ import annotations

from datetime import date, datetime, timezone

from app.managers.series_merge_manager import SeriesMergeManager
from app.storage.duckdb_repository import DuckDbRepository, RawObservation


def test_yahoo_futures_beats_seed_for_same_series_date(tmp_path) -> None:
    db_path = tmp_path / "merge.duckdb"
    repository = DuckDbRepository(db_path)
    fetched_at = datetime.now(timezone.utc)
    obs_date = date(2024, 3, 15)

    repository.upsert_raw_observations(
        [
            RawObservation("seed", "corn_usd_per_bushel", obs_date, 4.0, fetched_at),
            RawObservation(
                "yahoo_futures",
                "corn_usd_per_bushel",
                obs_date,
                4.75,
                fetched_at,
            ),
        ]
    )

    merged_rows = SeriesMergeManager(repository).rebuild_merged_daily(
        start_date=obs_date,
        end_date=obs_date,
    )

    assert len(merged_rows) == 1
    assert merged_rows[0].corn_usd_per_bushel == 4.75
    repository.close()
