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
            suggested_trade VARCHAR,
            metadata_json VARCHAR,
            PRIMARY KEY (obs_date, signal_type)
        )
        """,
        # Idempotent migration for databases seeded before suggested_trade existed.
        """
        ALTER TABLE warning_signals ADD COLUMN IF NOT EXISTS suggested_trade VARCHAR
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
        """
        CREATE TABLE IF NOT EXISTS briefings (
            id INTEGER PRIMARY KEY,
            as_of DATE,
            generated_at TIMESTAMPTZ NOT NULL,
            text VARCHAR NOT NULL,
            cache_key VARCHAR
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS cot_reports (
            contract_market_code VARCHAR NOT NULL,
            report_date DATE NOT NULL,
            fetched_at TIMESTAMPTZ NOT NULL,
            contract_market_name VARCHAR,
            open_interest BIGINT,
            producer_long BIGINT,
            producer_short BIGINT,
            swap_long BIGINT,
            swap_short BIGINT,
            managed_money_long BIGINT,
            managed_money_short BIGINT,
            other_reportable_long BIGINT,
            other_reportable_short BIGINT,
            PRIMARY KEY (contract_market_code, report_date)
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
                    obs_date, signal_type, severity, message, suggested_trade, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    obs_date,
                    signal["signal_type"],
                    signal["severity"],
                    signal["message"],
                    signal.get("suggested_trade"),
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
            SELECT signal_type, severity, message, suggested_trade, metadata_json
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
                "suggested_trade": row[3],
                "metadata_json": row[4],
            }
            for row in rows
        ]

    def fetch_raw_observations_by_series(
        self,
        series_id: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[RawObservation]:
        """Raw observations for a single series within the given date range."""
        query = "SELECT source, series_id, obs_date, value, fetched_at FROM raw_observations WHERE series_id = ?"
        params: list[Any] = [series_id]
        if start_date:
            query += " AND obs_date >= ?"
            params.append(start_date)
        if end_date:
            query += " AND obs_date <= ?"
            params.append(end_date)
        query += " ORDER BY obs_date"
        rows = self._fetchall(query, params)
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
    def _cot_row_to_dict(row: tuple[Any, ...]) -> dict[str, Any]:
        """Convert a cot_reports SELECT row into the dashboard-friendly dict shape."""
        return {
            "contract_market_code": row[0],
            "report_date": row[1],
            "fetched_at": row[2],
            "contract_market_name": row[3],
            "open_interest": row[4],
            "producer_long": row[5],
            "producer_short": row[6],
            "swap_long": row[7],
            "swap_short": row[8],
            "managed_money_long": row[9],
            "managed_money_short": row[10],
            "other_reportable_long": row[11],
            "other_reportable_short": row[12],
        }

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

    def upsert_cot_reports(self, reports: list) -> int:
        """
        Insert or replace weekly COT reports keyed on (contract, report_date).

        `reports` is a list of app.clients.cftc_cot_client.CotReport objects,
        typed loose here to avoid a circular import into a low-level module.
        """
        if not reports:
            return 0
        rows = [
            (
                r.contract_market_code,
                r.report_date,
                r.fetched_at,
                r.contract_market_name,
                r.open_interest,
                r.producer_long,
                r.producer_short,
                r.swap_long,
                r.swap_short,
                r.managed_money_long,
                r.managed_money_short,
                r.other_reportable_long,
                r.other_reportable_short,
            )
            for r in reports
        ]
        self._executemany(
            """
            INSERT INTO cot_reports (
                contract_market_code, report_date, fetched_at, contract_market_name,
                open_interest,
                producer_long, producer_short,
                swap_long, swap_short,
                managed_money_long, managed_money_short,
                other_reportable_long, other_reportable_short
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (contract_market_code, report_date) DO UPDATE SET
                fetched_at = excluded.fetched_at,
                contract_market_name = excluded.contract_market_name,
                open_interest = excluded.open_interest,
                producer_long = excluded.producer_long,
                producer_short = excluded.producer_short,
                swap_long = excluded.swap_long,
                swap_short = excluded.swap_short,
                managed_money_long = excluded.managed_money_long,
                managed_money_short = excluded.managed_money_short,
                other_reportable_long = excluded.other_reportable_long,
                other_reportable_short = excluded.other_reportable_short
            """,
            rows,
        )
        return len(rows)

    def fetch_latest_cot_report(self, contract_market_code: str) -> dict[str, Any] | None:
        """Return the newest COT report for a contract, or None if absent."""
        row = self._fetchone(
            """
            SELECT contract_market_code, report_date, fetched_at, contract_market_name,
                   open_interest,
                   producer_long, producer_short,
                   swap_long, swap_short,
                   managed_money_long, managed_money_short,
                   other_reportable_long, other_reportable_short
            FROM cot_reports
            WHERE contract_market_code = ?
            ORDER BY report_date DESC
            LIMIT 1
            """,
            [contract_market_code],
        )
        return self._cot_row_to_dict(row) if row else None

    def fetch_cot_reports(
        self,
        contract_market_code: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[dict[str, Any]]:
        """Return all COT reports for a contract within the date range, oldest first."""
        query = """
            SELECT contract_market_code, report_date, fetched_at, contract_market_name,
                   open_interest,
                   producer_long, producer_short,
                   swap_long, swap_short,
                   managed_money_long, managed_money_short,
                   other_reportable_long, other_reportable_short
            FROM cot_reports
            WHERE contract_market_code = ?
        """
        params: list[Any] = [contract_market_code]
        if start_date:
            query += " AND report_date >= ?"
            params.append(start_date)
        if end_date:
            query += " AND report_date <= ?"
            params.append(end_date)
        query += " ORDER BY report_date"
        rows = self._fetchall(query, params)
        return [self._cot_row_to_dict(row) for row in rows]

    def fetch_prior_cot_report(
        self,
        contract_market_code: str,
        before_report_date: date,
    ) -> dict[str, Any] | None:
        """Return the newest COT report strictly older than the given date."""
        row = self._fetchone(
            """
            SELECT contract_market_code, report_date, fetched_at, contract_market_name,
                   open_interest,
                   producer_long, producer_short,
                   swap_long, swap_short,
                   managed_money_long, managed_money_short,
                   other_reportable_long, other_reportable_short
            FROM cot_reports
            WHERE contract_market_code = ? AND report_date < ?
            ORDER BY report_date DESC
            LIMIT 1
            """,
            [contract_market_code, before_report_date],
        )
        return self._cot_row_to_dict(row) if row else None

    def upsert_briefing(
        self,
        as_of: str | None,
        text: str,
        cache_key: str | None,
    ) -> None:
        """Replace the single stored briefing row (we only keep the latest)."""
        self._run("DELETE FROM briefings")
        self._run(
            """
            INSERT INTO briefings (id, as_of, generated_at, text, cache_key)
            VALUES (1, ?, ?, ?, ?)
            """,
            [as_of, self.utc_now(), text, cache_key],
        )

    def fetch_latest_briefing(self) -> dict[str, Any] | None:
        """Return the stored briefing row, or None if the table is empty."""
        row = self._fetchone(
            "SELECT as_of, generated_at, text, cache_key FROM briefings WHERE id = 1"
        )
        if row is None:
            return None
        return {
            "as_of": row[0].isoformat() if row[0] else None,
            "generated_at": row[1].isoformat() if row[1] else None,
            "text": row[2],
            "cache_key": row[3],
        }

    def fetch_backtest_summary(self) -> list[dict[str, Any]]:
        """
        Return a lightweight backtest summary suitable for prompt context.

        Pulls fire_count and the most recent 30-day hit-rate / median move
        stored alongside warning signals. If the backtester has not been
        materialised to DB, returns an empty list — the briefing manager
        will simply omit that section of context.
        """
        # We don't persist full backtest output to a table; return empty so
        # briefing_manager can still call this without error. The caller can
        # optionally supply richer context by overriding the method.
        return []

    @staticmethod
    def utc_now() -> datetime:
        """Timezone-aware UTC now helper."""
        return datetime.now(timezone.utc)
