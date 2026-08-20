"""Synthetic historical seed data when live feeds are unavailable."""

from __future__ import annotations

import math
import random
from datetime import date, datetime, timedelta, timezone

from app.storage.duckdb_repository import RawObservation


class SeedDataProvider:
    """
    Generates realistic synthetic market history for local demo.

    Casual: fake but plausible prices so the dashboard works on day one.

    Used when the database is empty or live pulls fail. Values are deterministic
    enough for tests (fixed seed) while still looking like a real market panel.
    """

    def __init__(self, seed: int = 42) -> None:
        self._random = random.Random(seed)

    def build_observations(
        self,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[RawObservation]:
        """Build ~5 years of synthetic observations for all core series."""
        end = end_date or date.today()
        start = start_date or (end - timedelta(days=1825))
        fetched_at = datetime.now(timezone.utc)

        observations: list[RawObservation] = []
        day_count = (end - start).days + 1

        corn = 4.8
        ethanol = 1.85
        ddgs = 165.0
        rbob = 2.35
        nat_gas = 2.75
        corn_oil = 0.38
        stocks = 24.0
        production = 1050.0
        wasde = 5400.0

        for offset in range(day_count):
            obs_date = start + timedelta(days=offset)
            noise = math.sin(offset / 17.0) + self._random.uniform(-0.02, 0.02)

            corn += self._random.uniform(-0.04, 0.04) + 0.002 * noise
            ethanol += self._random.uniform(-0.02, 0.02) + 0.001 * noise
            # DDGS + corn oil are cash/OTC markets with no free live feed —
            # we're not paying for DTN/Barchart, so we pin them to a static
            # realistic level instead of random-walking. Fake daily variation
            # would falsely imply signal and pollute the plant margin series.
            # Static values are disclosed in the MethodologyFooter.
            ddgs = 165.0
            corn_oil = 0.38
            rbob += self._random.uniform(-0.03, 0.03)
            nat_gas += self._random.uniform(-0.05, 0.05)

            observations.extend(
                self._daily_observations(
                    obs_date,
                    fetched_at,
                    corn=max(corn, 3.0),
                    ethanol=max(ethanol, 1.2),
                    ddgs=max(ddgs, 100.0),
                    rbob=max(rbob, 1.5),
                    nat_gas=max(nat_gas, 1.5),
                    corn_oil=max(corn_oil, 0.2),
                )
            )

            if obs_date.weekday() == 2:
                stocks += self._random.uniform(-0.2, 0.25)
                production += self._random.uniform(-15, 15)
                observations.extend(
                    self._weekly_observations(
                        obs_date,
                        fetched_at,
                        stocks=max(stocks, 15.0),
                        production=max(production, 900.0),
                    )
                )

            # D6 RIN prices intentionally NOT seeded here. Real EPA weekly data
            # lands via EpaRinFileClient; when the CSV is absent, RIN simply
            # stays None on merged_daily rather than showing fabricated values.
            # The margin calculator handles missing RIN gracefully (rin_included
            # falls back to False and the regulatory D6 RIN value drops out).

            if obs_date.day == 12:
                wasde += self._random.uniform(-40, 40)
                observations.append(
                    RawObservation(
                        source="seed",
                        series_id="wasde_corn_for_ethanol_mbu",
                        obs_date=obs_date,
                        value=max(wasde, 4800.0),
                        fetched_at=fetched_at,
                    )
                )

        return observations

    @staticmethod
    def _daily_observations(
        obs_date: date,
        fetched_at: datetime,
        *,
        corn: float,
        ethanol: float,
        ddgs: float,
        rbob: float,
        nat_gas: float,
        corn_oil: float,
    ) -> list[RawObservation]:
        return [
            RawObservation("seed", "corn_usd_per_bushel", obs_date, corn, fetched_at),
            RawObservation("seed", "ethanol_usd_per_gallon", obs_date, ethanol, fetched_at),
            RawObservation("seed", "ddgs_usd_per_short_ton", obs_date, ddgs, fetched_at),
            RawObservation("seed", "rbob_usd_per_gallon", obs_date, rbob, fetched_at),
            RawObservation("seed", "nat_gas_usd_per_mmbtu", obs_date, nat_gas, fetched_at),
            RawObservation("seed", "corn_oil_usd_per_pound", obs_date, corn_oil, fetched_at),
        ]

    @staticmethod
    def _weekly_observations(
        obs_date: date,
        fetched_at: datetime,
        *,
        stocks: float,
        production: float,
    ) -> list[RawObservation]:
        return [
            RawObservation(
                "seed", "ethanol_stocks_mmbbl", obs_date, stocks, fetched_at
            ),
            RawObservation(
                "seed", "ethanol_production_mbpd", obs_date, production, fetched_at
            ),
        ]
