"""Domain models describing macroeconomic indicators and data points."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

import pandas as pd

__all__ = ["MacroIndicatorConfig", "MacroDataSet"]


@dataclass(slots=True)
class MacroIndicatorConfig:
    """Configuration describing a macroeconomic indicator to be ingested."""

    code: str
    name: str
    category: str
    source: str
    target_frequency: str = "M"
    release_lag: timedelta = timedelta(days=0)
    transformations: dict[str, Any] = field(default_factory=dict)
    consensus_indicator: str | None = None


@dataclass(slots=True)
class MacroDataSet:
    """Container for raw macroeconomic observations."""

    indicator: MacroIndicatorConfig
    frame: pd.DataFrame

    def ensure_sorted(self) -> pd.DataFrame:
        """Return the dataset sorted by release date."""

        if self.frame.empty:
            return self.frame
        return self.frame.sort_values(["release_date", "period_end"]).reset_index(
            drop=True
        )
