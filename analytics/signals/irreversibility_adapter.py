"""Adapter helpers exposing the Irreversibility-Gated Signal to pipelines."""
from __future__ import annotations

from typing import Dict, Optional

import pandas as pd

from analytics.signals.irreversibility import (
    IGSConfig,
    IGSMetrics,
    StreamingIGS,
    compute_igs_features,
)


class IGSFeatureProvider:
    """Feature provider that can be registered with existing pipelines."""

    def __init__(self, cfg: Dict[str, object] | IGSConfig | None = None) -> None:
        if cfg is None:
            self.cfg = IGSConfig()
        elif isinstance(cfg, IGSConfig):
            self.cfg = cfg
        else:
            self.cfg = IGSConfig(**cfg)
        self._streaming_engines: dict[str, StreamingIGS] = {}

    def compute_batch(self, price_series: pd.Series) -> pd.DataFrame:
        """Return IGS features for a price series containing strictly positive prices."""
        return compute_igs_features(price_series, self.cfg)

    def compute_from_df(self, frame: pd.DataFrame, price_column: str = "close") -> pd.DataFrame:
        if price_column not in frame.columns:
            raise ValueError(f"DataFrame must contain '{price_column}' column")
        return self.compute_batch(frame[price_column])

    def streaming_update(self, instrument: str, timestamp: pd.Timestamp, price: float) -> Optional[IGSMetrics]:
        if instrument not in self._streaming_engines:
            self._streaming_engines[instrument] = StreamingIGS(self.cfg)
        return self._streaming_engines[instrument].update(timestamp, price)


__all__ = ["IGSFeatureProvider"]
