"""CFTC Commitments of Traders (COT) client — Disaggregated futures-only, CBOT Corn."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone

import httpx


@dataclass(frozen=True)
class CotReport:
    """
    One weekly COT print for a single contract.

    Casual: how many contracts each trader category was long / short as of
    Tuesday of the release week.

    All positions are contract counts, not dollar notional. Managed money is
    the "speculator" category traders read as directional positioning; producer
    and swap dealer sit on the hedger side.
    """

    contract_market_code: str
    contract_market_name: str
    report_date: date
    fetched_at: datetime

    open_interest: int
    producer_long: int
    producer_short: int
    swap_long: int
    swap_short: int
    managed_money_long: int
    managed_money_short: int
    other_reportable_long: int
    other_reportable_short: int

    @property
    def managed_money_net(self) -> int:
        """Managed-money spec net position (long − short)."""
        return self.managed_money_long - self.managed_money_short

    @property
    def producer_net(self) -> int:
        """Producer / commercial hedger net position."""
        return self.producer_long - self.producer_short


class CftcCotClient:
    """
    Fetches CBOT Corn Disaggregated futures-only COT via CFTC's Socrata API.

    Casual: hits the government's public COT dataset for corn spec positioning.

    No API key required for standard read volume. Endpoint returns JSON records
    per contract per report_date; we filter to CBOT Corn (code 002602) and
    hand back sorted CotReport objects.
    """

    # Disaggregated futures-only historical dataset.
    # Schema: https://publicreporting.cftc.gov/resource/72hh-3qpy.json
    BASE_URL = "https://publicreporting.cftc.gov/resource/72hh-3qpy.json"

    # CFTC contract market code for CBOT Corn (futures).
    CBOT_CORN_CODE = "002602"

    def __init__(self, timeout_seconds: float = 30.0) -> None:
        self._timeout = timeout_seconds

    @property
    def is_configured(self) -> bool:
        """No credentials required — always available."""
        return True

    def fetch_cbot_corn(self, *, limit: int = 260) -> list[CotReport]:
        """
        Pull the most recent `limit` weekly reports for CBOT Corn futures.

        260 weeks ≈ 5 years, matching the dashboard's z-score lookback.
        """
        params = {
            "cftc_contract_market_code": self.CBOT_CORN_CODE,
            "$order": "report_date_as_yyyy_mm_dd DESC",
            "$limit": str(limit),
        }
        response = httpx.get(self.BASE_URL, params=params, timeout=self._timeout)
        response.raise_for_status()
        payload = response.json()

        fetched_at = datetime.now(timezone.utc)
        reports: list[CotReport] = []
        for row in payload:
            report = self._parse_row(row, fetched_at)
            if report is not None:
                reports.append(report)
        # Return oldest-first for consistency with EIA client conventions.
        reports.sort(key=lambda r: r.report_date)
        return reports

    @staticmethod
    def _parse_row(row: dict, fetched_at: datetime) -> CotReport | None:
        """
        Convert one Socrata record into a CotReport, or None if malformed.

        Casual: turn a raw JSON row into our typed COT print.

        Socrata returns Long_All / Short_All column style; the disaggregated
        dataset uses snake_case field names like `m_money_positions_long_all`.
        """
        try:
            report_date_str = row.get("report_date_as_yyyy_mm_dd")
            if not report_date_str:
                return None
            report_date = _parse_iso_date(report_date_str)
            # Field-name inconsistency in the CFTC Socrata dataset:
            #   producer / other_reportable → no `_all` suffix
            #   swap / managed_money       → `_all` suffix
            # (swap short/spread additionally have a stray double underscore.)
            return CotReport(
                contract_market_code=row.get("cftc_contract_market_code", ""),
                contract_market_name=row.get("contract_market_name", ""),
                report_date=report_date,
                fetched_at=fetched_at,
                open_interest=_int(row.get("open_interest_all")),
                producer_long=_int(row.get("prod_merc_positions_long")),
                producer_short=_int(row.get("prod_merc_positions_short")),
                swap_long=_int(row.get("swap_positions_long_all")),
                swap_short=_int(row.get("swap__positions_short_all")),
                managed_money_long=_int(row.get("m_money_positions_long_all")),
                managed_money_short=_int(row.get("m_money_positions_short_all")),
                other_reportable_long=_int(row.get("other_rept_positions_long")),
                other_reportable_short=_int(row.get("other_rept_positions_short")),
            )
        except (ValueError, TypeError):
            return None


def _parse_iso_date(raw: str) -> date:
    """Strip time part if Socrata returns 'YYYY-MM-DDT00:00:00.000'."""
    return date.fromisoformat(raw[:10])


def _int(value) -> int:
    """Coerce Socrata's string-numeric fields to int; missing → 0."""
    if value in (None, ""):
        return 0
    return int(float(value))
