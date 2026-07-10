"""Point-in-time backtest for warning rules against historical margin history."""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import date, timedelta

from app.managers.warning_rules.base_rule import WarningRule
from app.managers.warning_rules.bullish_margin_setup_rule import BullishMarginSetupRule
from app.managers.warning_rules.expected_directions import EXPECTED_DIRECTIONS
from app.managers.warning_rules.stocks_building_rich_margin_rule import (
    StocksBuildingRichMarginRule,
)
from app.managers.warning_rules.weak_margin_high_production_rule import (
    WeakMarginHighProductionRule,
)
from app.storage.duckdb_repository import (
    ComputedMarginRow,
    DuckDbRepository,
    MergedDailyRow,
)


@dataclass(frozen=True)
class FiringOutcome:
    """One historical firing plus its forward-return outcomes."""

    trigger_date: date
    margin_at_trigger: float
    forward_moves: dict[int, float | None]  # {7: -0.12, 30: -0.42, 60: -0.31}


@dataclass(frozen=True)
class RuleBacktestReport:
    """Aggregate track record for one warning rule."""

    signal_type: str
    expected_direction: str
    horizons_days: tuple[int, ...]
    fire_count: int
    firings: list[FiringOutcome] = field(default_factory=list)
    median_move_by_horizon: dict[int, float | None] = field(default_factory=dict)
    p25_move_by_horizon: dict[int, float | None] = field(default_factory=dict)
    p75_move_by_horizon: dict[int, float | None] = field(default_factory=dict)
    hit_rate_by_horizon: dict[int, float | None] = field(default_factory=dict)


class WarningRuleBacktester:
    """
    Replay warning rules day-by-day against margin history and grade each firing.

    Casual: "if this rule had fired historically, what happened next?"

    Two decisions worth understanding:

    1. **Point-in-time slicing.** Rules read `history` to compute rolling
       percentiles. If we passed the full history at every simulated day, the
       percentile bounds would include future data — lookahead bias. Each
       replay step gets `history[: i + 1]` so the rule sees only the past.
    2. **Event cooldown.** A rule that stays true for a week is one regime,
       not seven independent observations. Firings within `COOLDOWN_DAYS` of
       the previous firing for the same rule are dropped.
    """

    HORIZONS_DAYS: tuple[int, ...] = (7, 30, 60)
    MIN_WARMUP_DAYS = 200
    COOLDOWN_DAYS = 30

    def __init__(
        self,
        repository: DuckDbRepository,
        rules: list[WarningRule] | None = None,
        expected_directions: dict[str, str] | None = None,
    ) -> None:
        self._repository = repository
        self._rules = rules or [
            BullishMarginSetupRule(),
            StocksBuildingRichMarginRule(),
            WeakMarginHighProductionRule(),
        ]
        self._expected = expected_directions or EXPECTED_DIRECTIONS

    def run(self) -> list[RuleBacktestReport]:
        merged = self._repository.fetch_merged_daily()
        margins = self._repository.fetch_computed_margins()
        margin_by_date: dict[date, ComputedMarginRow] = {
            m.obs_date: m for m in margins
        }
        return [
            self._replay_rule(rule, merged, margins, margin_by_date)
            for rule in self._rules
        ]

    def _replay_rule(
        self,
        rule: WarningRule,
        merged: list[MergedDailyRow],
        margins: list[ComputedMarginRow],
        margin_by_date: dict[date, ComputedMarginRow],
    ) -> RuleBacktestReport:
        firings: list[FiringOutcome] = []
        last_fire_date: date | None = None

        for i in range(self.MIN_WARMUP_DAYS, len(merged)):
            row = merged[i]
            margin_row = margin_by_date.get(row.obs_date)
            if margin_row is None:
                continue

            # Point-in-time truncation — no lookahead bias.
            merged_slice = merged[: i + 1]
            margin_slice = [m for m in margins if m.obs_date <= row.obs_date]

            signal = rule.evaluate(row, margin_row, merged_slice, margin_slice)
            if signal is None:
                continue

            # Event cooldown — collapse consecutive firings within the same regime.
            if (
                last_fire_date is not None
                and (row.obs_date - last_fire_date).days < self.COOLDOWN_DAYS
            ):
                continue
            last_fire_date = row.obs_date

            firings.append(
                FiringOutcome(
                    trigger_date=row.obs_date,
                    margin_at_trigger=margin_row.margin_per_bushel,
                    forward_moves=self._forward_moves(
                        row.obs_date, margin_by_date, margin_row.margin_per_bushel
                    ),
                )
            )

        return self._summarize(rule, firings)

    def _forward_moves(
        self,
        trigger_date: date,
        margin_by_date: dict[date, ComputedMarginRow],
        margin_at_trigger: float,
    ) -> dict[int, float | None]:
        """Margin at trigger_date + horizon minus margin at trigger, per horizon."""
        moves: dict[int, float | None] = {}
        for horizon in self.HORIZONS_DAYS:
            future_date = trigger_date + timedelta(days=horizon)
            future_row = margin_by_date.get(future_date)
            # Walk back up to a week for weekends/holidays so we don't punch holes.
            for back in range(1, 8):
                if future_row is not None:
                    break
                future_row = margin_by_date.get(future_date - timedelta(days=back))
            moves[horizon] = (
                None
                if future_row is None
                else future_row.margin_per_bushel - margin_at_trigger
            )
        return moves

    def _summarize(
        self,
        rule: WarningRule,
        firings: list[FiringOutcome],
    ) -> RuleBacktestReport:
        expected = self._expected.get(rule.signal_type, "down")

        moves_by_horizon: dict[int, list[float]] = {h: [] for h in self.HORIZONS_DAYS}
        for firing in firings:
            for horizon, move in firing.forward_moves.items():
                if move is not None:
                    moves_by_horizon[horizon].append(move)

        median_h: dict[int, float | None] = {}
        p25_h: dict[int, float | None] = {}
        p75_h: dict[int, float | None] = {}
        hit_h: dict[int, float | None] = {}

        for horizon, moves in moves_by_horizon.items():
            if not moves:
                median_h[horizon] = p25_h[horizon] = p75_h[horizon] = hit_h[horizon] = None
                continue
            median_h[horizon] = statistics.median(moves)
            if len(moves) >= 4:
                quarters = statistics.quantiles(moves, n=4)
                p25_h[horizon] = quarters[0]
                p75_h[horizon] = quarters[2]
            else:
                p25_h[horizon] = None
                p75_h[horizon] = None
            direction_match = (
                (lambda m: m > 0) if expected == "up" else (lambda m: m < 0)
            )
            hit_h[horizon] = sum(1 for m in moves if direction_match(m)) / len(moves)

        return RuleBacktestReport(
            signal_type=rule.signal_type,
            expected_direction=expected,
            horizons_days=self.HORIZONS_DAYS,
            fire_count=len(firings),
            firings=firings,
            median_move_by_horizon=median_h,
            p25_move_by_horizon=p25_h,
            p75_move_by_horizon=p75_h,
            hit_rate_by_horizon=hit_h,
        )


def report_to_dict(report: RuleBacktestReport) -> dict:
    """Serialize a report for JSON API output."""
    return {
        "signal_type": report.signal_type,
        "expected_direction": report.expected_direction,
        "horizons_days": list(report.horizons_days),
        "fire_count": report.fire_count,
        "median_move_by_horizon": {
            str(h): v for h, v in report.median_move_by_horizon.items()
        },
        "p25_move_by_horizon": {
            str(h): v for h, v in report.p25_move_by_horizon.items()
        },
        "p75_move_by_horizon": {
            str(h): v for h, v in report.p75_move_by_horizon.items()
        },
        "hit_rate_by_horizon": {
            str(h): v for h, v in report.hit_rate_by_horizon.items()
        },
        "recent_firings": [
            {
                "trigger_date": f.trigger_date.isoformat(),
                "margin_at_trigger": f.margin_at_trigger,
                "forward_moves": {str(h): v for h, v in f.forward_moves.items()},
            }
            for f in report.firings[-5:]
        ],
    }
