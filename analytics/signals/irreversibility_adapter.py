"""Adapters exposing Irreversibility-Gated Signal utilities to pipelines."""
from __future__ import annotations

from typing import Dict, Iterable, Mapping, Optional

import pandas as pd

from .irreversibility import IGSConfig, IGSMetrics, StreamingIGS, compute_igs_features, igs_directional_signal

__all__ = ["IGSFeatureProvider", "igs_directional_signal"]


class IGSFeatureProvider:
    """Wrapper bridging the IGS core with the TradePulse pipeline ecosystem."""

    def __init__(self, cfg: Mapping[str, object] | IGSConfig | None = None) -> None:
        if cfg is None:
            self.cfg = IGSConfig()
        elif isinstance(cfg, IGSConfig):
            self.cfg = cfg
        else:
            self.cfg = IGSConfig(**dict(cfg))
        self._streaming: Dict[str, StreamingIGS] = {}

    def compute_batch(self, price_series: pd.Series) -> pd.DataFrame:
        """Compute IGS features for a single instrument in batch mode."""

        return compute_igs_features(price_series, self.cfg)

    def compute_from_frame(
        self,
        frame: pd.DataFrame,
        price_column: str = "close",
    ) -> pd.DataFrame:
        """Compute features from a DataFrame that contains a price column."""

        if price_column not in frame.columns:
            raise KeyError(f"DataFrame must contain '{price_column}' column")
        price_series = frame[price_column].astype(float)
        return self.compute_batch(price_series)

    def streaming_update(self, instrument: str, timestamp: pd.Timestamp, price: float) -> Optional[IGSMetrics]:
        """Update (or create) the streaming engine for ``instrument``."""

        if instrument not in self._streaming:
            self._streaming[instrument] = StreamingIGS(self.cfg)
        return self._streaming[instrument].update(timestamp, price)

    def instruments(self) -> Iterable[str]:
        """Return known streaming instruments."""

        return tuple(self._streaming.keys())

    def reset_streaming(self) -> None:
        """Remove all cached streaming engines."""

        self._streaming.clear()
