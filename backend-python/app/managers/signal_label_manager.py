"""Map z-scores to trader-facing signal labels."""

from __future__ import annotations


class SignalLabelManager:
    """
    Converts a z-score into Rich / Elevated / Normal / Soft / Weak.

    Casual: tells you if today's margin is weird compared to history.

    Thresholds match the dashboard spec with explicit transition bands between
    ±1 and ±1.5 so traders see 'elevated' or 'soft' before extremes.
    """

    def label_for_z_score(self, z_score: float) -> str:
        """Return the five-tier signal label for a z-score."""
        if z_score > 1.5:
            return "rich"
        if z_score > 1.0:
            return "elevated"
        if z_score >= -1.0:
            return "normal"
        if z_score >= -1.5:
            return "soft"
        return "weak"
