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
        """
        Load the repo-default crush model config.

        Resolution order:
        1. APP_CRUSH_MODEL_PATH env var (Docker/Railway sets /app/config/crush_model.json)
        2. Repo root ../config/crush_model.json (local dev — backend-python/app/models/x.py → parents[3])
        3. /app/config/crush_model.json (Docker image layout fallback)

        The env var path is required on Railway because parents[3] resolves to
        `/` inside the /app/app/models/ container layout, which has no config/
        directory. The Dockerfile sets APP_CRUSH_MODEL_PATH so this "just works"
        without call sites needing to plumb settings through.
        """
        import os
        env_path = os.environ.get("APP_CRUSH_MODEL_PATH")
        if env_path:
            path = Path(env_path)
            if path.exists():
                return cls.from_json_file(path)

        repo_root_candidate = Path(__file__).resolve().parents[3] / "config" / "crush_model.json"
        if repo_root_candidate.exists():
            return cls.from_json_file(repo_root_candidate)

        docker_candidate = Path("/app/config/crush_model.json")
        if docker_candidate.exists():
            return cls.from_json_file(docker_candidate)

        raise FileNotFoundError(
            f"crush_model.json not found in any expected location: "
            f"APP_CRUSH_MODEL_PATH={env_path!r}, tried {repo_root_candidate} "
            f"and {docker_candidate}"
        )

    def ddgs_revenue_per_bushel(self, ddgs_usd_per_short_ton: float) -> float:
        """Convert DDGS $/short ton into coproduct revenue per bushel of corn."""
        ddgs_usd_per_pound = ddgs_usd_per_short_ton / self.ddgs_pounds_per_short_ton
        return ddgs_usd_per_pound * self.ddgs_pounds_per_bushel
