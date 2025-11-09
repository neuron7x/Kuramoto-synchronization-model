"""On-chain analytics feature helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Mapping

import numpy as np
import pandas as pd


@dataclass(slots=True)
class OnChainMetric:
    """Represents a single on-chain datapoint aligned to a timestamp."""

    timestamp: datetime
    metric: str
    value: float
    chain: str | None = None
    metadata: Mapping[str, float] | None = None


class OnChainFeatureBuilder:
    """Compose on-chain metrics into a wide feature matrix."""

    def __init__(self, *, fill: float = 0.0) -> None:
        self._fill = float(fill)

    def _to_frame(self, metrics: Iterable[OnChainMetric]) -> pd.DataFrame:
        rows = []
        for metric in metrics:
            ts = pd.Timestamp(metric.timestamp)
            if ts.tzinfo is None:
                ts = ts.tz_localize("UTC")
            else:
                ts = ts.tz_convert("UTC")
            rows.append(
                {
                    "timestamp": ts.floor("s"),
                    "metric": metric.metric,
                    "value": float(metric.value),
                }
            )
        if not rows:
            return pd.DataFrame(columns=["timestamp", "metric", "value"]).set_index(
                "timestamp"
            )
        frame = pd.DataFrame(rows)
        return frame.set_index("timestamp").sort_index()

    def to_features(
        self, metrics: Iterable[OnChainMetric], freq: str = "5min"
    ) -> pd.DataFrame:
        """Return a resampled feature matrix with first differences."""

        frame = self._to_frame(metrics)
        if frame.empty:
            return pd.DataFrame()

        pivot = frame.pivot_table(
            index="timestamp", columns="metric", values="value", aggfunc="mean"
        )
        resampled = pivot.resample(freq).mean().ffill().fillna(self._fill)
        deltas = resampled.diff().fillna(0.0)
        deltas.columns = [f"{col}_delta" for col in deltas.columns]
        return pd.concat([resampled, deltas], axis=1).fillna(self._fill)

    def rolling_volatility(
        self, metrics: Iterable[OnChainMetric], window: int = 12
    ) -> pd.Series:
        """Compute rolling volatility for each metric and average across columns."""

        features = self.to_features(metrics)
        if features.empty:
            return pd.Series(dtype=float)
        numeric = features.select_dtypes(include=[np.number])
        return (
            numeric.rolling(window=window, min_periods=1).std().mean(axis=1).fillna(0.0)
        )


__all__ = ["OnChainMetric", "OnChainFeatureBuilder"]
