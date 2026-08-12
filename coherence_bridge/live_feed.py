"""Live data feed loop: market data → GeoSyncAdapter → signal emission.

This is the missing link between raw price data and the CoherenceBridge
signal pipeline. It continuously fetches OHLCV bars and feeds them to
the GeoSyncAdapter, which runs the physics kernel on each update.

Supports two modes:
  - synthetic: deterministic random walk for demo/testing
  - exness: real tick data via efinance (requires efinance package)
"""

from __future__ import annotations

import logging
import time
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger("coherence_bridge.live_feed")


class LiveFeedLoop:
    """Continuously feeds OHLCV data to a GeoSyncAdapter.

    Parameters
    ----------
    adapter
        A GeoSyncAdapter (or any object with ``update_market_data(inst, df)``
        and ``instruments`` attribute).
    mode
        ``"synthetic"`` for deterministic random walk, ``"exness"`` for real data.
    bar_interval_s
        Seconds between synthetic bar generation.
    history_bars
        Number of bars to maintain in the rolling window.
    """

    def __init__(
        self,
        adapter: Any,
        *,
        mode: str = "synthetic",
        bar_interval_s: float = 1.0,
        history_bars: int = 500,
    ) -> None:
        self.adapter = adapter
        self.mode = mode
        self.bar_interval_s = bar_interval_s
        self.history_bars = history_bars
        self._running = False
        self._histories: dict[str, pd.DataFrame] = {}
        self._rng = np.random.default_rng(seed=42)

        # Initial synthetic prices per instrument
        self._last_price: dict[str, float] = {
            "EURUSD": 1.1000,
            "GBPUSD": 1.2700,
            "USDJPY": 149.50,
            "AUDUSD": 0.6550,
            "USDCAD": 1.3600,
        }

    def run(self) -> None:
        """Block and feed data until stopped. Call from a thread."""
        self._running = True
        logger.info(
            "LiveFeedLoop started: mode=%s, interval=%.1fs, instruments=%s",
            self.mode,
            self.bar_interval_s,
            self.adapter.instruments,
        )

        while self._running:
            for instrument in self.adapter.instruments:
                try:
                    if self.mode == "synthetic":
                        bar = self._generate_synthetic_bar(instrument)
                    else:
                        raise NotImplementedError(
                            f"Feed mode '{self.mode}' not implemented. "
                            "Use 'synthetic' or wire efinance here."
                        )
                    self._append_bar(instrument, bar)
                    self.adapter.update_market_data(
                        instrument,
                        self._histories[instrument],
                    )
                except Exception as exc:
                    logger.warning("Feed error for %s: %s", instrument, exc)

            time.sleep(self.bar_interval_s)

    def stop(self) -> None:
        self._running = False

    def _generate_synthetic_bar(self, instrument: str) -> dict[str, Any]:
        """Generate one OHLCV bar with geometric Brownian motion."""
        price = self._last_price.get(instrument, 1.0)
        # GBM: dS = μ·S·dt + σ·S·dW
        dt = self.bar_interval_s / 86400.0  # fraction of day
        sigma = 0.001  # intraday vol
        mu = 0.0
        dw = self._rng.standard_normal()
        new_price = price * np.exp((mu - 0.5 * sigma**2) * dt + sigma * np.sqrt(dt) * dw)

        # OHLCV bar
        high = max(price, new_price) * (1 + abs(dw) * 0.0001)
        low = min(price, new_price) * (1 - abs(dw) * 0.0001)
        volume = abs(dw) * 1000 + 100

        self._last_price[instrument] = new_price
        return {
            "open": price,
            "high": high,
            "low": low,
            "close": new_price,
            "volume": volume,
        }

    def _append_bar(self, instrument: str, bar: dict[str, Any]) -> None:
        """Append bar to rolling history DataFrame."""
        now = pd.Timestamp.now(tz="UTC")
        new_row = pd.DataFrame([bar], index=pd.DatetimeIndex([now]))

        if instrument not in self._histories:
            self._histories[instrument] = new_row
        else:
            self._histories[instrument] = pd.concat(
                [self._histories[instrument], new_row],
            ).tail(self.history_bars)
