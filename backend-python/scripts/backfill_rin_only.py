"""
One-shot: seed the D6 RIN weekly series into an existing DB without
re-hitting Yahoo.

Casual: adds RIN data to your live-data DB without triggering Yahoo again.

Use this after adding the RIN column to a database that already has Yahoo +
EIA observations you don't want to lose. It:
  1. Opens the DB (schema init runs the idempotent ALTER for the RIN column).
  2. Generates the SeedDataProvider observations but keeps only the RIN rows.
  3. Upserts them into raw_observations.
  4. Rebuilds merged_daily (RIN column auto-populates via the existing merge).
  5. Recomputes computed_margins so the new RIN revenue lands immediately.

Safe to re-run. Yahoo/EIA rows are untouched.
"""

from __future__ import annotations

from pathlib import Path

from app.managers.crush_margin_calculator import CrushMarginCalculator
from app.managers.seed_data_provider import SeedDataProvider
from app.managers.series_merge_manager import SERIES_D6_RIN, SeriesMergeManager
from app.managers.z_score_manager import ZScoreManager
from app.models.crush_model_config import CrushModelConfig
from app.storage.duckdb_repository import ComputedMarginRow, DuckDbRepository


def main() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    db_path = repo_root / "backend-python" / "data" / "ethanol_dashboard.duckdb"
    print(f"Opening {db_path}")
    repository = DuckDbRepository(db_path)

    # 1. Generate all seed observations, keep only D6 RIN.
    provider = SeedDataProvider()
    all_obs = provider.build_observations()
    rin_obs = [o for o in all_obs if o.series_id == SERIES_D6_RIN]
    print(f"Generated {len(rin_obs)} weekly D6 RIN observations")

    # 2. Upsert only the RIN rows. Yahoo/EIA rows untouched.
    inserted = repository.upsert_raw_observations(rin_obs)
    print(f"Upserted {inserted} raw_observations rows")

    # 3. Rebuild merged_daily so the RIN column populates via LOCF.
    merge_manager = SeriesMergeManager(repository)
    merged = merge_manager.rebuild_merged_daily()
    print(f"Rebuilt merged_daily: {len(merged)} rows")

    # 4. Recompute margins so the RIN revenue lands in every historical row.
    config = CrushModelConfig.default()
    calculator = CrushMarginCalculator(config)
    z_score_manager = ZScoreManager()

    margin_points: list[tuple] = []
    per_day: list[tuple] = []
    for row in merged:
        result = calculator.calculate(row)
        if result is None:
            continue
        margin_points.append((row.obs_date, result.margin_per_bushel))
        per_day.append(
            (row.obs_date, result.margin_per_bushel, result.corn_oil_included)
        )

    annotated = z_score_manager.annotate_series(
        margin_points, window_type="rolling", lookback_days=1825
    )
    annotation_by_date = {item[0]: item for item in annotated}

    computed_rows = []
    for obs_date, margin_per_bushel, corn_oil_included in per_day:
        _, _, z_score, signal_label = annotation_by_date.get(
            obs_date, (obs_date, margin_per_bushel, None, "normal")
        )
        computed_rows.append(
            ComputedMarginRow(
                obs_date=obs_date,
                margin_per_bushel=margin_per_bushel,
                margin_per_gallon=margin_per_bushel
                / config.ethanol_gallons_per_bushel,
                z_score=z_score,
                signal_label=signal_label,
                corn_oil_included=corn_oil_included,
            )
        )
    count = repository.replace_computed_margins(computed_rows)
    print(f"Recomputed {count} margin rows (now includes RIN revenue)")

    repository.close()
    print("Done. Restart the backend to pick up the new data.")


if __name__ == "__main__":
    main()
