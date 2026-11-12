import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class ResearchConfig:
    initial_capital: float = 1_000_000
    surprise_threshold: float = 0.10
    forecast_max_age_days: int = 270
    hold_sessions: int = 10
    entry_ttl_sessions: int = 3
    liquidity_sessions: int = 60
    min_traded_fraction: float = 0.80
    min_average_volume_mad: float = 1_000_000
    max_stale_sessions: int = 3
    large_return_flag: float = 0.25
    fee_rate: float = 0.0077
    slippage_rate: float = 0.001
    stock_cap: float = 0.05
    sector_cap: float = 0.20
    gross_cap: float = 0.30
    participation_rate: float = 0.01
    drawdown_trigger: float = 0.05
    minimum_events: int = 30
    minimum_issuers: int = 10
    minimum_release_years: int = 3
    bootstrap_samples: int = 5000
    random_seed: int = 7051

    def validate(self):
        for k, v in asdict(self).items():
            if not math.isfinite(v) or v <= 0:
                raise ValueError(f"{k} must be positive and finite")
        for k in (
            "surprise_threshold",
            "min_traded_fraction",
            "large_return_flag",
            "fee_rate",
            "slippage_rate",
            "stock_cap",
            "sector_cap",
            "gross_cap",
            "participation_rate",
            "drawdown_trigger",
        ):
            if getattr(self, k) >= 1:
                raise ValueError(f"{k} must be below 1")
        if not self.stock_cap <= self.sector_cap <= self.gross_cap <= 1:
            raise ValueError("Require stock <= sector <= gross <= 1")
        for k in (
            "forecast_max_age_days",
            "hold_sessions",
            "entry_ttl_sessions",
            "liquidity_sessions",
            "max_stale_sessions",
            "minimum_events",
            "minimum_issuers",
            "minimum_release_years",
            "bootstrap_samples",
            "random_seed",
        ):
            if not isinstance(getattr(self, k), int):
                raise ValueError(f"{k} must be an integer")
        return self


def load_config(path: Path):
    return ResearchConfig(**json.loads(path.read_text(encoding="utf-8"))).validate()
