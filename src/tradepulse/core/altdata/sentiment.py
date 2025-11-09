"""Sentiment stream aggregation for alternative datasets."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Mapping

import numpy as np
import pandas as pd


@dataclass(slots=True)
class SentimentSignal:
    """Represents a single sentiment datapoint from an alternative feed."""

    timestamp: datetime
    source: str
    score: float
    volume: float = 1.0
    metadata: Mapping[str, float] | None = None


class SentimentFeatureBuilder:
    """Produce aggregated sentiment factors suitable for model ingestion."""

    def __init__(self, *, clip: float = 5.0) -> None:
        self._clip = max(0.0, float(clip))

    def _prepare(self, signals: Iterable[SentimentSignal]) -> pd.DataFrame:
        rows = []
        for signal in signals:
            ts = pd.Timestamp(signal.timestamp)
            if ts.tzinfo is None:
                ts = ts.tz_localize("UTC")
            else:
                ts = ts.tz_convert("UTC")
            rows.append(
                {
                    "timestamp": ts.floor("s"),
                    "source": signal.source,
                    "score": float(np.clip(signal.score, -self._clip, self._clip)),
                    "volume": float(max(signal.volume, 0.0)),
                }
            )
        if not rows:
            return pd.DataFrame(
                columns=["timestamp", "source", "score", "volume"]
            ).set_index("timestamp")
        frame = pd.DataFrame(rows)
        return frame.set_index("timestamp").sort_index()

    def aggregate(
        self, signals: Iterable[SentimentSignal], freq: str = "1min"
    ) -> pd.DataFrame:
        """Return a resampled view containing weighted sentiment statistics."""

        frame = self._prepare(signals)
        if frame.empty:
            return pd.DataFrame(
                columns=["sentiment_vwap", "sentiment_momentum", "sources"]
            )

        grouped = frame.resample(freq)
        weight_sum = grouped["volume"].sum().replace(0.0, np.nan)
        weighted_score = grouped.apply(
            lambda batch: float((batch["score"] * batch["volume"]).sum()),
        )
        vwap = (weighted_score / weight_sum).fillna(0.0).rename("sentiment_vwap")
        momentum = (
            grouped["score"].mean().diff().fillna(0.0).rename("sentiment_momentum")
        )
        sources = grouped["source"].nunique().rename("sources").fillna(0).astype(int)
        return pd.concat([vwap, momentum, sources], axis=1).fillna(0.0)

    def latest(self, signals: Iterable[SentimentSignal]) -> dict[str, float]:
        """Compute a latest snapshot used for dashboards or heuristics."""

        frame = self._prepare(signals)
        if frame.empty:
            return {"sentiment_vwap": 0.0, "sentiment_momentum": 0.0, "sources": 0.0}
        recent = frame.iloc[-50:]
        weights = recent["volume"].replace(0.0, 1.0)
        vwap = float((recent["score"] * weights).sum() / weights.sum())
        momentum = float(
            recent["score"].iloc[-5:].mean() - recent["score"].iloc[:5].mean()
        )
        return {
            "sentiment_vwap": vwap,
            "sentiment_momentum": momentum,
            "sources": float(recent["source"].nunique()),
        }


__all__ = ["SentimentSignal", "SentimentFeatureBuilder"]
