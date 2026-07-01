"""Loads Iowa State CARD crush model constants from shared JSON config."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CrushModelConfig:
    """
    CARD dry-mill yield and cost assumptions.

    Casual: the recipe for turning a bushel of corn into money (or not).

    Values come from `config/crush_model.json` at the repo root so backend
  math and the methodology footer stay aligned. DDGS is stored as $/short ton
    everywhere user-facing; this class exposes a helper for the $/lb conversion
    used only inside margin math.
    """

    ethanol_gallons_per_bushel: float
    ddgs_pounds_per_bushel: float
    corn_oil_pounds_per_bushel: float
    natural_gas_mmbtu_per_bushel: float
    misc_opex_per_bushel: float
    ddgs_pounds_per_short_ton: float = 2000.0

    @classmethod
    def from_json_file(cls, path: Path) -> CrushModelConfig:
        """Read crush model constants from a JSON file on disk."""
        payload = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            ethanol_gallons_per_bushel=float(payload["ethanol_gallons_per_bushel"]),
            ddgs_pounds_per_bushel=float(payload["ddgs_pounds_per_bushel"]),
            corn_oil_pounds_per_bushel=float(payload["corn_oil_pounds_per_bushel"]),
            natural_gas_mmbtu_per_bushel=float(payload["natural_gas_mmbtu_per_bushel"]),
            misc_opex_per_bushel=float(payload["misc_opex_per_bushel"]),
            ddgs_pounds_per_short_ton=float(payload.get("ddgs_pounds_per_short_ton", 2000)),
        )

    @classmethod
    def default(cls) -> CrushModelConfig:
        """Load the repo-default crush model config."""
        repo_root = Path(__file__).resolve().parents[3]
        config_path = repo_root / "config" / "crush_model.json"
        return cls.from_json_file(config_path)

    def ddgs_revenue_per_bushel(self, ddgs_usd_per_short_ton: float) -> float:
        """Convert DDGS $/short ton into coproduct revenue per bushel of corn."""
        ddgs_usd_per_pound = ddgs_usd_per_short_ton / self.ddgs_pounds_per_short_ton
        return ddgs_usd_per_pound * self.ddgs_pounds_per_bushel
