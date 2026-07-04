"""Verify DuckDB repository survives parallel reads (mirrors React Promise.all)."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path

from app.storage.duckdb_repository import DuckDbRepository, MergedDailyRow


def test_parallel_reads_do_not_deadlock(tmp_path: Path) -> None:
    """Five concurrent dashboard-style reads should all finish quickly."""
    repository = DuckDbRepository(tmp_path / "concurrency.duckdb")
    repository.replace_merged_daily(
        [
            MergedDailyRow(
                obs_date=date(2026, 1, 1),
                corn_usd_per_bushel=4.5,
                ethanol_usd_per_gallon=1.8,
                ddgs_usd_per_short_ton=160.0,
                rbob_usd_per_gallon=2.2,
                nat_gas_usd_per_mmbtu=2.5,
                ethanol_stocks_mmbbl=24.0,
                ethanol_production_mbpd=1050.0,
                corn_oil_usd_per_pound=0.35,
                wasde_corn_for_ethanol_mbu=5400.0,
            )
        ]
    )

    tasks = (
        repository.fetch_latest_merged_daily,
        lambda: repository.fetch_merged_daily(),
        lambda: repository.fetch_computed_margins(),
        lambda: repository.count_merged_daily_rows(),
        lambda: repository.fetch_all_raw_observations(),
    )

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(task) for task in tasks]
        results = [future.result(timeout=5) for future in as_completed(futures)]

    assert len(results) == 5
    assert repository.fetch_latest_merged_daily() is not None
