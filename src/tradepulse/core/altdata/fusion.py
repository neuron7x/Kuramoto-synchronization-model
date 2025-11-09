"""Feature fusion utilities combining market and alternative data."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import pandas as pd


@dataclass(frozen=True)
class FusionConfig:
    """Configuration describing how alternative data should be fused."""

    join_horizon: str = "5min"
    forward_fill: bool = True
    dropna: bool = True
    prefixes: Mapping[str, str] | None = None


class AltDataFusionEngine:
    """Combine heterogeneous alternative datasets into market-aligned features."""

    def __init__(self, config: FusionConfig | None = None) -> None:
        self._config = config or FusionConfig()

    def _prepare(self, frame: pd.DataFrame | None, prefix: str) -> pd.DataFrame:
        if frame is None or frame.empty:
            return pd.DataFrame()
        data = frame.copy()
        data.index = pd.to_datetime(data.index, utc=True)
        if self._config.join_horizon:
            data = data.resample(self._config.join_horizon).last()
        if self._config.forward_fill:
            data = data.ffill()
        if prefix:
            data = data.add_prefix(prefix)
        return data

    def fuse(
        self,
        market_features: pd.DataFrame,
        *,
        news_features: pd.DataFrame | None = None,
        sentiment_features: pd.DataFrame | None = None,
        onchain_features: pd.DataFrame | None = None,
    ) -> pd.DataFrame:
        """Merge market features with optional alternative data feature frames."""

        prefixes = dict(self._config.prefixes or {})
        market = self._prepare(market_features, prefix=prefixes.get("market", ""))
        news = self._prepare(news_features, prefix=prefixes.get("news", "news_"))
        sentiment = self._prepare(
            sentiment_features, prefix=prefixes.get("sentiment", "sentiment_")
        )
        onchain = self._prepare(
            onchain_features, prefix=prefixes.get("onchain", "onchain_")
        )

        frames = [
            frame for frame in (market, news, sentiment, onchain) if not frame.empty
        ]
        if not frames:
            return pd.DataFrame()

        combined = pd.concat(frames, axis=1).sort_index()
        if self._config.dropna:
            combined = combined.dropna(how="all")
        return combined

    def validate_alignment(self, fused: pd.DataFrame) -> bool:
        """Return ``True`` when the fused frame is chronologically aligned."""

        if fused.empty:
            return True
        index = fused.index
        if not isinstance(index, pd.DatetimeIndex):
            raise TypeError("fused features must be indexed by timestamps")
        return index.is_monotonic_increasing


__all__ = ["FusionConfig", "AltDataFusionEngine"]
