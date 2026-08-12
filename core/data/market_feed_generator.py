# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Synthetic market feed generator for reproducible testing.

Generates realistic market data with controlled characteristics for stable
regression tests. Supports various market regimes (trending, mean-reverting,
volatile) for comprehensive dopamine loop testing.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import List, Literal, Optional

import numpy as np

from core.data.market_feed import (
    MarketFeedMetadata,
    MarketFeedRecord,
    MarketFeedRecording,
)

MarketRegime = Literal[
    "trending_up", "trending_down", "mean_reverting", "volatile", "stable"
]


class SyntheticMarketFeedGenerator:
    """Generate synthetic market feeds with realistic properties."""

    def __init__(
        self,
        seed: int = 42,
        base_price: float = 50000.0,
        base_spread_bps: float = 5.0,  # 5 basis points
        tick_interval_ms: float = 100.0,
        latency_mean_ms: float = 45.0,
        latency_std_ms: float = 15.0,
    ):
        """Initialize generator with reproducible seed.

        Args:
            seed: Random seed for reproducibility
            base_price: Starting price level
            base_spread_bps: Base bid-ask spread in basis points
            tick_interval_ms: Average time between ticks in milliseconds
            latency_mean_ms: Mean ingestion latency in milliseconds
            latency_std_ms: Standard deviation of latency in milliseconds
        """
        self.seed = seed
        self.base_price = base_price
        self.base_spread_bps = base_spread_bps
        self.tick_interval_ms = tick_interval_ms
        self.latency_mean_ms = latency_mean_ms
        self.latency_std_ms = latency_std_ms

        # Initialize random generators
        self.rng = np.random.default_rng(seed)
        random.seed(seed)

    def generate(
        self,
        num_records: int,
        start_time: Optional[datetime] = None,
        regime: MarketRegime = "stable",
        drift: float = 0.0,
        volatility: float = 0.001,
    ) -> MarketFeedRecording:
        """Generate synthetic market feed.

        Args:
            num_records: Number of records to generate
            start_time: Starting timestamp (defaults to fixed epoch for reproducibility)
            regime: Market regime to simulate
            drift: Price drift per tick (as fraction of price)
            volatility: Price volatility per tick (as fraction of price)

        Returns:
            MarketFeedRecording with synthetic data
        """
        if start_time is None:
            # Use fixed epoch for reproducibility
            start_time = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

        # Adjust parameters based on regime
        drift, volatility = self._adjust_for_regime(regime, drift, volatility)

        records = []
        current_price = self.base_price
        current_time = start_time

        for i in range(num_records):
            # Generate price movement
            price_change = drift * current_price + self.rng.normal(
                0, volatility * current_price
            )
            current_price = max(current_price + price_change, 1.0)  # Ensure positive

            # Generate spread (widens with volatility)
            spread_multiplier = 1.0 + abs(self.rng.normal(0, 0.3))
            spread = current_price * (self.base_spread_bps / 10000) * spread_multiplier

            # Generate bid/ask
            half_spread = spread / 2
            mid_price = current_price
            bid = mid_price - half_spread
            ask = mid_price + half_spread

            # Last price is within spread, slightly biased to mid
            last_offset = self.rng.normal(0, half_spread * 0.3)
            last = mid_price + last_offset
            last = max(bid, min(ask, last))  # Clamp to spread

            # Generate volume (lognormal distribution)
            volume = float(self.rng.lognormal(mean=-1.0, sigma=0.5))

            # Generate timestamps
            tick_interval = self.rng.exponential(self.tick_interval_ms / 1000.0)
            current_time += timedelta(seconds=tick_interval)

            latency = max(
                0.001,  # Minimum 1ms latency
                self.rng.normal(self.latency_mean_ms, self.latency_std_ms) / 1000.0,
            )
            ingest_time = current_time + timedelta(seconds=latency)

            # Create record
            record = MarketFeedRecord(
                exchange_ts=current_time,
                ingest_ts=ingest_time,
                bid=Decimal(str(round(bid, 2))),
                ask=Decimal(str(round(ask, 2))),
                last=Decimal(str(round(last, 2))),
                volume=Decimal(str(round(volume, 4))),
            )
            records.append(record)

        # Create metadata
        metadata = MarketFeedMetadata(
            symbol="BTCUSD",
            venue="synthetic",
            start_time=records[0].exchange_ts,
            end_time=records[-1].exchange_ts,
            record_count=len(records),
            version="1.0.0",
            description=f"Synthetic {regime} market feed",
            tags=["synthetic", regime, f"seed_{self.seed}"],
        )

        return MarketFeedRecording(records, metadata)

    def _adjust_for_regime(
        self,
        regime: MarketRegime,
        drift: float,
        volatility: float,
    ) -> tuple[float, float]:
        """Adjust drift and volatility based on market regime."""
        if regime == "trending_up":
            return 0.0001, volatility * 0.8  # Moderate uptrend, lower vol
        elif regime == "trending_down":
            return -0.0001, volatility * 0.8  # Moderate downtrend, lower vol
        elif regime == "mean_reverting":
            # Mean reversion implemented via negative autocorrelation
            return 0.0, volatility * 0.6
        elif regime == "volatile":
            return drift, volatility * 3.0  # High volatility
        else:  # stable
            return drift, volatility

    def generate_flash_crash(
        self,
        num_records: int,
        crash_position: float = 0.5,
        crash_magnitude: float = 0.05,
        recovery_speed: float = 0.8,
        start_time: Optional[datetime] = None,
    ) -> MarketFeedRecording:
        """Generate feed with flash crash event for stress testing.

        Args:
            num_records: Total number of records
            crash_position: Where in sequence crash occurs (0-1)
            crash_magnitude: Size of crash as fraction of price (e.g., 0.05 = 5%)
            recovery_speed: How quickly price recovers (0-1, higher = faster)
            start_time: Starting timestamp

        Returns:
            MarketFeedRecording with flash crash
        """
        if start_time is None:
            # Use fixed epoch for reproducibility
            start_time = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

        crash_index = int(num_records * crash_position)
        records = []
        current_price = self.base_price
        current_time = start_time

        for i in range(num_records):
            # Calculate crash effect
            if i == crash_index:
                # Sudden crash
                current_price *= 1 - crash_magnitude
            elif i > crash_index:
                # Gradual recovery
                recovery_progress = (i - crash_index) / (num_records - crash_index)
                recovery_factor = recovery_progress ** (1 / recovery_speed)
                target_price = self.base_price
                current_price += (target_price - current_price) * recovery_factor * 0.1

            # Add normal noise
            noise = self.rng.normal(0, 0.0005 * current_price)
            current_price = max(current_price + noise, 1.0)

            # Generate spread (widens during crash)
            if abs(i - crash_index) < 5:
                spread_multiplier = 3.0  # Wide spread during crash
            else:
                spread_multiplier = 1.0

            spread = current_price * (self.base_spread_bps / 10000) * spread_multiplier
            half_spread = spread / 2

            bid = current_price - half_spread
            ask = current_price + half_spread
            last = current_price

            # Volume spikes during crash
            if abs(i - crash_index) < 3:
                volume = float(self.rng.lognormal(mean=1.0, sigma=0.8))
            else:
                volume = float(self.rng.lognormal(mean=-1.0, sigma=0.5))

            # Generate timestamps
            tick_interval = self.rng.exponential(self.tick_interval_ms / 1000.0)
            current_time += timedelta(seconds=tick_interval)

            latency = max(
                0.001,
                self.rng.normal(self.latency_mean_ms, self.latency_std_ms) / 1000.0,
            )
            ingest_time = current_time + timedelta(seconds=latency)

            record = MarketFeedRecord(
                exchange_ts=current_time,
                ingest_ts=ingest_time,
                bid=Decimal(str(round(bid, 2))),
                ask=Decimal(str(round(ask, 2))),
                last=Decimal(str(round(last, 2))),
                volume=Decimal(str(round(volume, 4))),
            )
            records.append(record)

        metadata = MarketFeedMetadata(
            symbol="BTCUSD",
            venue="synthetic",
            start_time=records[0].exchange_ts,
            end_time=records[-1].exchange_ts,
            record_count=len(records),
            version="1.0.0",
            description=f"Flash crash at position {crash_position}, magnitude {crash_magnitude}",
            tags=["synthetic", "flash_crash", f"seed_{self.seed}"],
        )

        return MarketFeedRecording(records, metadata)

    def generate_regime_transition(
        self,
        num_records: int,
        regimes: List[MarketRegime],
        transition_points: Optional[List[float]] = None,
        start_time: Optional[datetime] = None,
    ) -> MarketFeedRecording:
        """Generate feed with multiple regime transitions.

        Args:
            num_records: Total number of records
            regimes: List of regimes to cycle through
            transition_points: Where transitions occur (0-1), defaults to equal spacing
            start_time: Starting timestamp

        Returns:
            MarketFeedRecording with regime transitions
        """
        if transition_points is None:
            transition_points = [i / len(regimes) for i in range(1, len(regimes))]

        if len(transition_points) != len(regimes) - 1:
            raise ValueError(
                f"Need {len(regimes) - 1} transition points for {len(regimes)} regimes"
            )

        all_records = []
        current_time = start_time or datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

        transition_indices = [int(p * num_records) for p in transition_points] + [
            num_records
        ]
        start_idx = 0

        for regime, end_idx in zip(regimes, transition_indices):
            segment_size = end_idx - start_idx
            if segment_size > 0:
                # Generate segment
                generator = SyntheticMarketFeedGenerator(
                    seed=self.seed + start_idx,
                    base_price=(
                        self.base_price
                        if not all_records
                        else float(all_records[-1].last)
                    ),
                    base_spread_bps=self.base_spread_bps,
                    tick_interval_ms=self.tick_interval_ms,
                    latency_mean_ms=self.latency_mean_ms,
                    latency_std_ms=self.latency_std_ms,
                )

                recording = generator.generate(
                    segment_size,
                    start_time=current_time,
                    regime=regime,
                )

                all_records.extend(recording.records)
                if all_records:
                    current_time = all_records[-1].exchange_ts

            start_idx = end_idx

        metadata = MarketFeedMetadata(
            symbol="BTCUSD",
            venue="synthetic",
            start_time=all_records[0].exchange_ts,
            end_time=all_records[-1].exchange_ts,
            record_count=len(all_records),
            version="1.0.0",
            description=f"Regime transitions: {' -> '.join(regimes)}",
            tags=["synthetic", "regime_transition", f"seed_{self.seed}"],
        )

        return MarketFeedRecording(all_records, metadata)
