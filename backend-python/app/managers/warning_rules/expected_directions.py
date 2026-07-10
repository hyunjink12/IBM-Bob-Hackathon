"""Directional expectations for each warning rule's forward-margin move."""

from __future__ import annotations

# Maps rule.signal_type → "up" or "down".
#   "up"   → forward margin should rise (bullish setup)
#   "down" → forward margin should fall (mean-revert lower)
#
# Used by the backtester to compute directional hit rate. A rule with a 40%
# hit rate at 30d is coincident, not predictive, at that horizon — that's
# honest information, not a bug.
EXPECTED_DIRECTIONS: dict[str, str] = {
    "bullish_margin_setup": "up",
    "stocks_building_rich_margin": "down",
    "weak_margin_high_production": "up",
}
