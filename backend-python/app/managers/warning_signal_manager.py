"""Evaluate all warning rules against latest market state."""

from __future__ import annotations

import json

from app.managers.warning_rules.base_rule import WarningRule, WarningSignal
from app.managers.warning_rules.bullish_margin_setup_rule import BullishMarginSetupRule
from app.managers.warning_rules.stocks_building_rich_margin_rule import (
    StocksBuildingRichMarginRule,
)
from app.managers.warning_rules.weak_margin_high_production_rule import (
    WeakMarginHighProductionRule,
)
from app.storage.duckdb_repository import ComputedMarginRow, DuckDbRepository, MergedDailyRow


class WarningSignalManager:
    """
    Runs all warning rules and persists active cards.

    Casual: spots weird combos like 'rich margins but inventories piling up'.

    Each rule is a small Python class (easy to unit test). YAML extraction can
    happen later if the rule count grows.
    """

    def __init__(self, repository: DuckDbRepository, rules: list[WarningRule] | None = None) -> None:
        self._repository = repository
        self._rules = rules or [
            StocksBuildingRichMarginRule(),
            WeakMarginHighProductionRule(),
            BullishMarginSetupRule(),
        ]

    def evaluate_and_store(
        self,
        latest_row: MergedDailyRow,
        margin_row: ComputedMarginRow,
        history: list[MergedDailyRow],
        margin_history: list[ComputedMarginRow],
    ) -> list[WarningSignal]:
        """Evaluate rules for the latest day and save results."""
        active_signals: list[WarningSignal] = []
        for rule in self._rules:
            signal = rule.evaluate(latest_row, margin_row, history, margin_history)
            if signal is not None:
                active_signals.append(signal)

        payload = [
            {
                "signal_type": signal.signal_type,
                "severity": signal.severity,
                "message": signal.message,
                "metadata_json": json.dumps(signal.metadata),
            }
            for signal in active_signals
        ]
        self._repository.replace_warning_signals(latest_row.obs_date, payload)
        return active_signals
