"""DuckDB persistence for raw observations, merged daily rows, and computed margins."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import duckdb


@dataclass(frozen=True)
class RawObservation:
    """One fetched market data point before merge."""

    source: str
    series_id: str
    obs_date: date
    value: float
    fetched_at: datetime


@dataclass(frozen=True)
class MergedDailyRow:
    """One calendar day with all inputs aligned (weekly series forward-filled)."""

    obs_date: date
    corn_usd_per_bushel: float | None
    ethanol_usd_per_gallon: float | None
    ddgs_usd_per_short_ton: float | None
    rbob_usd_per_gallon: float | None
    nat_gas_usd_per_mmbtu: float | None
    ethanol_stocks_mmbbl: float | None
    ethanol_production_mbpd: float | None
    corn_oil_usd_per_pound: float | None
    wasde_corn_for_ethanol_mbu: float | None


@dataclass(frozen=True)
class ComputedMarginRow:
    """Crush margin output for one day."""

    obs_date: date
    margin_per_bushel: float
    margin_per_gallon: float
    z_score: float | None
    signal_label: str
    corn_oil_included: bool


class DuckDbRepository:
    """
    Reads/writes dashboard data in DuckDB.

    Casual: our local filing cabinet for prices and margins.

    Keeps raw API pulls separate from merged/computed tables so a bad ingest
    can be replayed without corrupting crush math. Uses DuckDB for fast
    analytics on time series without standing up Postgres.
    """

    SCHEMA_STATEMENTS: tuple[str, ...] = (
        """
        CREATE TABLE IF NOT EXISTS raw_observations (
            source VARCHAR NOT NULL,
            series_id VARCHAR NOT NULL,
            obs_date DATE NOT NULL,
            value DOUBLE NOT NULL,
            fetched_at TIMESTAMPTZ NOT NULL,
            PRIMARY KEY (source, series_id, obs_date)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS merged_daily (
            obs_date DATE PRIMARY KEY,
            corn_usd_per_bushel DOUBLE,
            ethanol_usd_per_gallon DOUBLE,
            ddgs_usd_per_short_ton DOUBLE,
            rbob_usd_per_gallon DOUBLE,
            nat_gas_usd_per_mmbtu DOUBLE,
            ethanol_stocks_mmbbl DOUBLE,
            ethanol_production_mbpd DOUBLE,
            corn_oil_usd_per_pound DOUBLE,
            wasde_corn_for_ethanol_mbu DOUBLE
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS computed_margins (
            obs_date DATE PRIMARY KEY,
            margin_per_bushel DOUBLE NOT NULL,
            margin_per_gallon DOUBLE NOT NULL,
            z_score DOUBLE,
            signal_label VARCHAR NOT NULL,
            corn_oil_included BOOLEAN NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS warning_signals (
            obs_date DATE NOT NULL,
            signal_type VARCHAR NOT NULL,
            severity VARCHAR NOT NULL,
            message VARCHAR NOT NULL,
            metadata_json VARCHAR,
            PRIMARY KEY (obs_date, signal_type)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS ingestion_runs (
            run_id VARCHAR PRIMARY KEY,
            started_at TIMESTAMPTZ NOT NULL,
            finished_at TIMESTAMPTZ,
            status VARCHAR NOT NULL,
            errors VARCHAR
        )
        """,
    )

    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        # DuckDB connections are not thread-safe; FastAPI serves sync routes
        # from a thread pool, and the React client fires parallel /api calls.
        self._io_lock = threading.RLock()
        self._connection = duckdb.connect(str(self._database_path))
        self._initialize_schema()

    def _initialize_schema(self) -> None:
        for statement in self.SCHEMA_STATEMENTS:
            self._connection.execute(statement)

    def _fetchone(self, query: str, params: list[Any] | None = None):
        """Run SQL and return one row while holding the repository lock."""
        with self._io_lock:
            if params is None:
                return self._connection.execute(query).fetchone()
            return self._connection.execute(query, params).fetchone()

    def _fetchall(self, query: str, params: list[Any] | None = None) -> list[tuple[Any, ...]]:
        """Run SQL and return all rows while holding the repository lock."""
        with self._io_lock:
            if params is None:
                return self._connection.execute(query).fetchall()
            return self._connection.execute(query, params).fetchall()

    def _run(self, query: str, params: list[Any] | None = None) -> None:
        """Run a write statement under the repository lock."""
        with self._io_lock:
            if params is None:
                self._connection.execute(query)
            else:
                self._connection.execute(query, params)

    def _executemany(self, query: str, params_list: list[tuple[Any, ...]]) -> None:
        """Run a parameterized batch under the repository lock."""
        with self._io_lock:
            self._connection.executemany(query, params_list)

    def close(self) -> None:
        """Close the underlying DuckDB connection."""
        with self._io_lock:
            self._connection.close()

    def upsert_raw_observations(self, observations: list[RawObservation]) -> int:
        """Insert or replace raw market observations."""
        if not observations:
            return 0
        rows = [
            (
                obs.source,
                obs.series_id,
                obs.obs_date,
                obs.value,
                obs.fetched_at,
            )
            for obs in observations
        ]
        self._executemany(
            """
            INSERT INTO raw_observations (source, series_id, obs_date, value, fetched_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (source, series_id, obs_date) DO UPDATE SET
                value = excluded.value,
                fetched_at = excluded.fetched_at
            """,
            rows,
        )
        return len(rows)

    def get_series_last_updated(self, series_id: str) -> datetime | None:
        """Return the latest fetch time for a logical series id."""
        result = self._fetchone(
            """
            SELECT MAX(fetched_at) FROM raw_observations WHERE series_id = ?
            """,
            [series_id],
        )
        if result is None or result[0] is None:
            return None
        return result[0]

    def replace_merged_daily(self, rows: list[MergedDailyRow]) -> int:
        """Replace merged daily rows for the provided dates."""
        if not rows:
            return 0
        for row in rows:
            self._run(
                """
                INSERT INTO merged_daily (
                    obs_date, corn_usd_per_bushel, ethanol_usd_per_gallon,
                    ddgs_usd_per_short_ton, rbob_usd_per_gallon, nat_gas_usd_per_mmbtu,
                    ethanol_stocks_mmbbl, ethanol_production_mbpd,
                    corn_oil_usd_per_pound, wasde_corn_for_ethanol_mbu
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (obs_date) DO UPDATE SET
                    corn_usd_per_bushel = excluded.corn_usd_per_bushel,
                    ethanol_usd_per_gallon = excluded.ethanol_usd_per_gallon,
                    ddgs_usd_per_short_ton = excluded.ddgs_usd_per_short_ton,
                    rbob_usd_per_gallon = excluded.rbob_usd_per_gallon,
                    nat_gas_usd_per_mmbtu = excluded.nat_gas_usd_per_mmbtu,
                    ethanol_stocks_mmbbl = excluded.ethanol_stocks_mmbbl,
                    ethanol_production_mbpd = excluded.ethanol_production_mbpd,
                    corn_oil_usd_per_pound = excluded.corn_oil_usd_per_pound,
                    wasde_corn_for_ethanol_mbu = excluded.wasde_corn_for_ethanol_mbu
                """,
                [
                    row.obs_date,
                    row.corn_usd_per_bushel,
                    row.ethanol_usd_per_gallon,
                    row.ddgs_usd_per_short_ton,
                    row.rbob_usd_per_gallon,
                    row.nat_gas_usd_per_mmbtu,
                    row.ethanol_stocks_mmbbl,
                    row.ethanol_production_mbpd,
                    row.corn_oil_usd_per_pound,
                    row.wasde_corn_for_ethanol_mbu,
                ],
            )
        return len(rows)

    def replace_computed_margins(self, rows: list[ComputedMarginRow]) -> int:
        """Replace computed margin rows."""
        if not rows:
            return 0
        for row in rows:
            self._run(
                """
                INSERT INTO computed_margins (
                    obs_date, margin_per_bushel, margin_per_gallon,
                    z_score, signal_label, corn_oil_included
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT (obs_date) DO UPDATE SET
                    margin_per_bushel = excluded.margin_per_bushel,
                    margin_per_gallon = excluded.margin_per_gallon,
                    z_score = excluded.z_score,
                    signal_label = excluded.signal_label,
                    corn_oil_included = excluded.corn_oil_included
                """,
                [
                    row.obs_date,
                    row.margin_per_bushel,
                    row.margin_per_gallon,
                    row.z_score,
                    row.signal_label,
                    row.corn_oil_included,
                ],
            )
        return len(rows)

    def replace_warning_signals(
        self,
        obs_date: date,
        signals: list[dict[str, Any]],
    ) -> int:
        """Replace warning signals for a single observation date."""
        self._run(
            "DELETE FROM warning_signals WHERE obs_date = ?",
            [obs_date],
        )
        for signal in signals:
            self._run(
                """
                INSERT INTO warning_signals (
                    obs_date, signal_type, severity, message, metadata_json
                ) VALUES (?, ?, ?, ?, ?)
                """,
                [
                    obs_date,
                    signal["signal_type"],
                    signal["severity"],
                    signal["message"],
                    signal.get("metadata_json"),
                ],
            )
        return len(signals)

    def record_ingestion_run(
        self,
        run_id: str,
        started_at: datetime,
        status: str,
        finished_at: datetime | None = None,
        errors: str | None = None,
    ) -> None:
        """Log an ingestion run for health checks and debugging."""
        self._run(
            """
            INSERT INTO ingestion_runs (run_id, started_at, finished_at, status, errors)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (run_id) DO UPDATE SET
                finished_at = excluded.finished_at,
                status = excluded.status,
                errors = excluded.errors
            """,
            [run_id, started_at, finished_at, status, errors],
        )

    def get_latest_ingestion_run(self) -> dict[str, Any] | None:
        """Return metadata for the most recent ingestion run."""
        row = self._fetchone(
            """
            SELECT run_id, started_at, finished_at, status, errors
            FROM ingestion_runs
            ORDER BY started_at DESC
            LIMIT 1
            """
        )
        if row is None:
            return None
        return {
            "run_id": row[0],
            "started_at": row[1],
            "finished_at": row[2],
            "status": row[3],
            "errors": row[4],
        }

    def fetch_merged_daily(
        self,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[MergedDailyRow]:
        """Load merged daily rows ordered by date."""
        query = "SELECT * FROM merged_daily WHERE 1=1"
        params: list[Any] = []
        if start_date:
            query += " AND obs_date >= ?"
            params.append(start_date)
        if end_date:
            query += " AND obs_date <= ?"
            params.append(end_date)
        query += " ORDER BY obs_date"
        rows = self._fetchall(query, params)
        return [self._row_to_merged_daily(row) for row in rows]

    def fetch_computed_margins(
        self,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[ComputedMarginRow]:
        """Load computed margin rows ordered by date."""
        query = "SELECT * FROM computed_margins WHERE 1=1"
        params: list[Any] = []
        if start_date:
            query += " AND obs_date >= ?"
            params.append(start_date)
        if end_date:
            query += " AND obs_date <= ?"
            params.append(end_date)
        query += " ORDER BY obs_date"
        rows = self._fetchall(query, params)
        return [
            ComputedMarginRow(
                obs_date=row[0],
                margin_per_bushel=row[1],
                margin_per_gallon=row[2],
                z_score=row[3],
                signal_label=row[4],
                corn_oil_included=bool(row[5]),
            )
            for row in rows
        ]

    def fetch_latest_merged_daily(self) -> MergedDailyRow | None:
        """Return the newest merged daily row."""
        row = self._fetchone(
            "SELECT * FROM merged_daily ORDER BY obs_date DESC LIMIT 1"
        )
        if row is None:
            return None
        return self._row_to_merged_daily(row)

    def fetch_latest_computed_margin(self) -> ComputedMarginRow | None:
        """Return the newest computed margin row."""
        row = self._fetchone(
            "SELECT * FROM computed_margins ORDER BY obs_date DESC LIMIT 1"
        )
        if row is None:
            return None
        return ComputedMarginRow(
            obs_date=row[0],
            margin_per_bushel=row[1],
            margin_per_gallon=row[2],
            z_score=row[3],
            signal_label=row[4],
            corn_oil_included=bool(row[5]),
        )

    def fetch_warning_signals_for_date(self, obs_date: date) -> list[dict[str, Any]]:
        """Load active warning cards for a date."""
        rows = self._fetchall(
            """
            SELECT signal_type, severity, message, metadata_json
            FROM warning_signals
            WHERE obs_date = ?
            ORDER BY severity DESC, signal_type
            """,
            [obs_date],
        )
        return [
            {
                "signal_type": row[0],
                "severity": row[1],
                "message": row[2],
                "metadata_json": row[3],
            }
            for row in rows
        ]

    def fetch_all_raw_observations(self) -> list[RawObservation]:
        """Load all raw observations ordered by series and date."""
        rows = self._fetchall(
            """
            SELECT source, series_id, obs_date, value, fetched_at
            FROM raw_observations
            ORDER BY series_id, obs_date
            """
        )
        return [
            RawObservation(
                source=row[0],
                series_id=row[1],
                obs_date=row[2],
                value=row[3],
                fetched_at=row[4],
            )
            for row in rows
        ]

    def count_merged_daily_rows(self) -> int:
        """Return how many merged daily rows exist (used to detect empty DB)."""
        result = self._fetchone("SELECT COUNT(*) FROM merged_daily")
        return int(result[0]) if result else 0

    @staticmethod
    def _row_to_merged_daily(row: tuple[Any, ...]) -> MergedDailyRow:
        return MergedDailyRow(
            obs_date=row[0],
            corn_usd_per_bushel=row[1],
            ethanol_usd_per_gallon=row[2],
            ddgs_usd_per_short_ton=row[3],
            rbob_usd_per_gallon=row[4],
            nat_gas_usd_per_mmbtu=row[5],
            ethanol_stocks_mmbbl=row[6],
            ethanol_production_mbpd=row[7],
            corn_oil_usd_per_pound=row[8],
            wasde_corn_for_ethanol_mbu=row[9],
        )

    @staticmethod
    def utc_now() -> datetime:
        """Timezone-aware UTC now helper."""
        return datetime.now(timezone.utc)
