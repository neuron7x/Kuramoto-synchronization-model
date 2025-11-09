"""News ingestion and sentiment enrichment utilities."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Iterable, Sequence

import numpy as np
import pandas as pd

_WORD_PATTERN = re.compile(r"[a-zA-Z]+")

_DEFAULT_POSITIVE = {
    "beat",
    "growth",
    "surge",
    "record",
    "upgrade",
    "bullish",
    "innovation",
    "optimistic",
    "outperform",
}

_DEFAULT_NEGATIVE = {
    "fraud",
    "downgrade",
    "scandal",
    "loss",
    "lawsuit",
    "bearish",
    "default",
    "dilution",
    "recession",
}


@dataclass(slots=True)
class NewsItem:
    """Canonical structure describing a single news event."""

    timestamp: datetime
    headline: str
    source: str | None = None
    body: str | None = None
    tags: Sequence[str] | None = None
    sentiment: float | None = None


class NewsSentimentAnalyzer:
    """Lightweight lexicon-based sentiment scorer for financial headlines."""

    def __init__(
        self,
        *,
        positive_tokens: Sequence[str] | None = None,
        negative_tokens: Sequence[str] | None = None,
        emphasis_multiplier: float = 1.5,
    ) -> None:
        self._positive = {
            token.lower() for token in (positive_tokens or _DEFAULT_POSITIVE)
        }
        self._negative = {
            token.lower() for token in (negative_tokens or _DEFAULT_NEGATIVE)
        }
        self._emphasis_multiplier = max(1.0, emphasis_multiplier)

    def _tokenise(self, text: str) -> list[str]:
        return [match.group(0).lower() for match in _WORD_PATTERN.finditer(text or "")]

    def score(self, text: str, *, boost_tokens: Sequence[str] | None = None) -> float:
        tokens = self._tokenise(text)
        if not tokens:
            return 0.0
        boost = {token.lower() for token in (boost_tokens or ())}
        positive = negative = 0.0
        for token in tokens:
            weight = self._emphasis_multiplier if token in boost else 1.0
            if token in self._positive:
                positive += weight
            elif token in self._negative:
                negative += weight
        total = positive + negative
        if total == 0:
            return 0.0
        return float((positive - negative) / total)

    def annotate(self, item: NewsItem) -> NewsItem:
        if item.sentiment is not None:
            return item
        score = self.score(item.headline + " " + (item.body or ""))
        return replace(item, sentiment=score)


class NewsFeatureBuilder:
    """Aggregate news events into feature tensors suitable for modelling."""

    def __init__(self, analyzer: NewsSentimentAnalyzer | None = None) -> None:
        self._analyzer = analyzer or NewsSentimentAnalyzer()

    def _ensure_frame(self, items: Iterable[NewsItem]) -> pd.DataFrame:
        enriched = []
        for item in items:
            annotated = self._analyzer.annotate(item)
            ts = pd.Timestamp(annotated.timestamp)
            if ts.tzinfo is None:
                ts = ts.tz_localize("UTC")
            else:
                ts = ts.tz_convert("UTC")
            enriched.append(
                {
                    "timestamp": ts.floor("s"),
                    "headline": annotated.headline,
                    "source": annotated.source or "unknown",
                    "sentiment": float(annotated.sentiment or 0.0),
                }
            )
        if not enriched:
            return pd.DataFrame(
                columns=["timestamp", "headline", "source", "sentiment"]
            ).set_index("timestamp")
        frame = pd.DataFrame(enriched)
        frame = frame.set_index("timestamp").sort_index()
        return frame

    def aggregate(self, items: Iterable[NewsItem], freq: str = "5min") -> pd.DataFrame:
        """Return aggregated features for ``items`` resampled to ``freq``."""

        frame = self._ensure_frame(items)
        if frame.empty:
            return pd.DataFrame(
                columns=[
                    "news_count",
                    "sentiment_mean",
                    "sentiment_std",
                    "source_diversity",
                ]
            )

        grouped = frame.resample(freq)
        sentiment_mean = (
            grouped["sentiment"].mean().fillna(0.0).rename("sentiment_mean")
        )
        sentiment_std = grouped["sentiment"].std().fillna(0.0).rename("sentiment_std")
        counts = grouped.size().rename("news_count").astype(int)
        diversity = (
            grouped["source"].nunique().fillna(0).astype(int).rename("source_diversity")
        )

        features = pd.concat([counts, sentiment_mean, sentiment_std, diversity], axis=1)
        features["sentiment_mean"] = features["sentiment_mean"].astype(float)
        features["sentiment_std"] = features["sentiment_std"].replace(
            [np.nan, math.inf, -math.inf], 0.0
        )
        return features.fillna(0.0)

    def latest_snapshot(self, items: Iterable[NewsItem]) -> dict[str, float]:
        """Return a snapshot summarising the most recent sentiment."""

        frame = self._ensure_frame(items)
        if frame.empty:
            return {
                "news_count": 0.0,
                "sentiment_mean": 0.0,
                "sentiment_std": 0.0,
                "source_diversity": 0.0,
            }
        latest = frame.iloc[-10:]
        return {
            "news_count": float(len(latest)),
            "sentiment_mean": float(latest["sentiment"].mean()),
            "sentiment_std": float(latest["sentiment"].std() or 0.0),
            "source_diversity": float(latest["source"].nunique()),
        }


__all__ = ["NewsItem", "NewsSentimentAnalyzer", "NewsFeatureBuilder"]
