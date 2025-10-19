"""
IGS Feature Provider adapter for pipelines and backtests.
"""

from __future__ import annotations
from typing import Dict, Any, Optional, Callable
import pandas as pd
from analytics.signals.irreversibility import IGSConfig, StreamingIGS, compute_igs_features

class IGSFeatureProvider:
    def __init__(self, cfg: Dict[str, Any] | IGSConfig, external_adapt_measure: Optional[Callable] = None):
        self.cfg = IGSConfig(**cfg) if isinstance(cfg, dict) else cfg
        self._streaming: Dict[str, StreamingIGS] = {}
        self._external_adapt_measure = external_adapt_measure

    def compute_batch(self, price_series: pd.Series) -> pd.DataFrame:
        return compute_igs_features(price_series, self.cfg)

    def compute_from_df(self, df: pd.DataFrame) -> pd.DataFrame:
        if "close" not in df.columns:
            raise ValueError("DataFrame must contain 'close' column")
        return self.compute_batch(df["close"])

    def streaming_update(self, instrument: str, timestamp, price: float):
        if instrument not in self._streaming:
            self._streaming[instrument] = StreamingIGS(self.cfg, external_adaptation_measure=self._external_adapt_measure)
        return self._streaming[instrument].update(timestamp, price)
