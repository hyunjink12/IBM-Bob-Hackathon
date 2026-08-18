"""EPA D6 RIN weekly price ingestion from a locally-dropped CSV export."""

from __future__ import annotations

import csv
import logging
from datetime import date, datetime, timezone
from pathlib import Path

from app.storage.duckdb_repository import RawObservation

_logger = logging.getLogger(__name__)


class EpaRinFileClient:
    """
    Reads D6 RIN weekly prices from an EPA EMTS 'Export Table' CSV on disk.

    Casual: turns EPA's downloaded CSV into raw observations the app can ingest.

    EPA publishes RIN prices through a JavaScript-rendered Qlik dashboard at
    ``epa.gov/fuels-registration-reporting-and-compliance-help/rin-trades-
    and-price-information``. There is no clean HTTP endpoint; the workflow is
    manual: select all Transfer Years, Fuel D6, click Export Table, drop the
    CSV at the path this client watches. The next ingest run picks it up.

    Canonical weekly price: current-vintage Unverified. RIN Year must equal
    Transfer Year (same-vintage), and QAP Service Type must be 'Unverified'
    (the more liquid of the two QAP categories; Q-RIN is the smaller
    quality-assured pool). That combination matches the "D6 RIN price"
    number industry commentary quotes.
    """

    # Filename carries the vintage year so mentors looking at the volume or
    # the repo can see at a glance which EPA snapshot is loaded. Update to
    # `rin_prices_2027.csv` etc. when the calendar year rolls over and drop
    # the new CSV alongside — override via APP_EPA_RIN_CSV_PATH if needed.
    DEFAULT_PATH = Path("data/epa/rin_prices_2026.csv")
    SOURCE = "epa_emts"
    LOGICAL_ID = "d6_rin_usd_per_gallon"

    def __init__(self, csv_path: Path | None = None) -> None:
        self._csv_path = Path(csv_path) if csv_path else self.DEFAULT_PATH

    @property
    def is_configured(self) -> bool:
        """True when the expected CSV file exists on disk."""
        return self._csv_path.exists()

    def fetch(self) -> list[RawObservation]:
        """
        Parse the CSV and emit one RawObservation per canonical weekly D6 price.

        Returns an empty list (with a warning) if the file is missing, so the
        ingest pipeline can fall through to seed data without crashing.
        """
        if not self.is_configured:
            _logger.info(
                "EPA RIN CSV not found at %s — RIN will fall back to seed data",
                self._csv_path,
            )
            return []

        observations: list[RawObservation] = []
        fetched_at = datetime.now(timezone.utc)

        with self._csv_path.open(encoding="utf-8-sig") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                # Skip anything that isn't current-vintage Unverified D6.
                if row.get("Fuel (D Code)", "").strip() != "D6":
                    continue
                if row.get("QAP Service Type", "").strip() != "Unverified":
                    continue
                if row.get("RIN Year", "").strip() != row.get("Transfer Year", "").strip():
                    continue

                raw_date = row.get("Transfer Date by Week", "").strip()
                raw_price = row.get("RIN Price", "").strip()
                if not raw_date or not raw_price:
                    continue

                try:
                    obs_date = datetime.strptime(raw_date, "%m/%d/%Y").date()
                    price = float(raw_price.replace("$", "").replace(",", ""))
                except (ValueError, TypeError):
                    _logger.warning(
                        "Skipping unparseable EPA RIN row: date=%r price=%r",
                        raw_date,
                        raw_price,
                    )
                    continue

                observations.append(
                    RawObservation(
                        source=self.SOURCE,
                        series_id=self.LOGICAL_ID,
                        obs_date=obs_date,
                        value=price,
                        fetched_at=fetched_at,
                    )
                )

        _logger.info(
            "Parsed %d weekly D6 RIN observations from %s",
            len(observations),
            self._csv_path,
        )
        return observations
