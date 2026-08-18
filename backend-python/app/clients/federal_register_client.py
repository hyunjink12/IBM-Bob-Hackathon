"""Federal Register API client — pulls recent EPA RFS regulatory documents."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timezone

import httpx

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RfsDocument:
    """One Federal Register document referencing the Renewable Fuel Standard."""

    document_number: str      # unique FR identifier
    publication_date: date
    doc_type: str             # "Rule" | "Notice" | "Proposed Rule" | ...
    title: str
    abstract: str
    html_url: str
    fetched_at: datetime


class FederalRegisterClient:
    """
    Fetches recent EPA-issued RFS-related documents from the Federal Register.

    Casual: our news feed for EPA RFS actions — free, structured, official.

    The Federal Register API is public and un-authed. We filter to documents
    published by the EPA whose full text mentions "renewable fuel standard".
    That catches every real RFS rulemaking (Set Rules, RVOs, SRE decisions,
    info-collection renewals) plus some tangentially-relevant EPA actions
    (GHG endangerment) that biofuels traders still watch.
    """

    BASE_URL = "https://www.federalregister.gov/api/v1/documents.json"
    SEARCH_TERM = '"renewable fuel standard"'
    AGENCY_SLUG = "environmental-protection-agency"
    DEFAULT_PER_PAGE = 15

    def __init__(self, per_page: int | None = None) -> None:
        self._per_page = per_page or self.DEFAULT_PER_PAGE

    @property
    def is_configured(self) -> bool:
        """Always true — the API needs no auth."""
        return True

    def fetch_recent(self) -> list[RfsDocument]:
        """
        Pull the most recent RFS-related EPA documents from the Federal Register.

        Returns newest first. Empty list on network error (ingest continues).
        """
        params = {
            "conditions[agencies][]": self.AGENCY_SLUG,
            "conditions[term]": self.SEARCH_TERM,
            "order": "newest",
            "per_page": self._per_page,
            # Only fields we actually store — keeps the response small.
            "fields[]": [
                "document_number",
                "publication_date",
                "type",
                "title",
                "abstract",
                "html_url",
            ],
        }
        try:
            response = httpx.get(self.BASE_URL, params=params, timeout=30.0)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            _logger.warning("Federal Register fetch failed: %s", exc)
            return []

        fetched_at = datetime.now(timezone.utc)
        payload = response.json()
        documents: list[RfsDocument] = []
        for row in payload.get("results", []) or []:
            try:
                documents.append(
                    RfsDocument(
                        document_number=str(row.get("document_number", "")).strip(),
                        publication_date=date.fromisoformat(row["publication_date"]),
                        doc_type=str(row.get("type", "") or "").strip(),
                        title=str(row.get("title", "") or "").strip(),
                        abstract=str(row.get("abstract", "") or "").strip(),
                        html_url=str(row.get("html_url", "") or "").strip(),
                        fetched_at=fetched_at,
                    )
                )
            except (KeyError, ValueError, TypeError) as exc:
                _logger.warning("Skipping unparseable Federal Register row: %s", exc)
                continue
        return documents
