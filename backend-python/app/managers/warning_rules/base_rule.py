"""Base class for dashboard warning rules."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from app.storage.duckdb_repository import ComputedMarginRow, MergedDailyRow


@dataclass(frozen=True)
class WarningSignal:
    """One trader-facing warning card."""

    signal_type: str
    severity: str
    message: str
    suggested_trade: str
    metadata: dict[str, Any]


class WarningRule(ABC):
    """Interface for a single warning rule evaluated on latest market state."""

    @property
    @abstractmethod
    def signal_type(self) -> str:
        """Stable identifier for the rule."""

    @abstractmethod
    def evaluate(
        self,
        latest_row: MergedDailyRow,
        margin_row: ComputedMarginRow,
        history: list[MergedDailyRow],
        margin_history: list[ComputedMarginRow],
    ) -> WarningSignal | None:
        """Return a warning when conditions are met, else None."""
