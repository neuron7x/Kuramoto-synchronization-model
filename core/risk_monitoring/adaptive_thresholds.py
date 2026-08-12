# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Adaptive Risk Threshold Calibration.

This module implements adaptive risk thresholds that adjust based on:
- Market volatility
- Trade volume
- Asset-specific behavior

The thresholds automatically tighten during unstable periods to minimize exposure.
"""

from __future__ import annotations

import logging
import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

import numpy as np
from numpy.typing import NDArray

__all__ = [
    "AdaptiveThresholdCalibrator",
    "ThresholdConfig",
    "CalibratedThresholds",
]

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class ThresholdConfig:
    """Configuration for adaptive threshold calibration.

    Attributes:
        base_position_limit: Base position limit as fraction of equity.
        base_daily_loss_limit: Base daily loss limit as fraction of equity.
        base_drawdown_limit: Base maximum drawdown limit as fraction.
        volatility_lookback: Number of periods for volatility calculation.
        volatility_scale_factor: Scaling factor for volatility adjustment.
        volume_lookback: Number of periods for volume calculation.
        volume_threshold_multiplier: Multiplier for volume-based threshold adjustment.
        min_threshold_multiplier: Minimum threshold multiplier (floor).
        max_threshold_multiplier: Maximum threshold multiplier (ceiling).
        adaptation_rate: Rate of threshold adaptation (0-1).
    """

    base_position_limit: float = 0.10  # 10% of equity
    base_daily_loss_limit: float = 0.05  # 5% of equity
    base_drawdown_limit: float = 0.15  # 15% max drawdown
    volatility_lookback: int = 20
    volatility_scale_factor: float = 2.0
    volume_lookback: int = 10
    volume_threshold_multiplier: float = 1.5
    min_threshold_multiplier: float = 0.3  # Never go below 30% of base
    max_threshold_multiplier: float = 1.5  # Can expand to 150% in calm markets
    adaptation_rate: float = 0.1

    def __post_init__(self) -> None:
        if self.base_position_limit <= 0 or self.base_position_limit > 1:
            raise ValueError("base_position_limit must be in (0, 1]")
        if self.base_daily_loss_limit <= 0 or self.base_daily_loss_limit > 1:
            raise ValueError("base_daily_loss_limit must be in (0, 1]")
        if self.base_drawdown_limit <= 0 or self.base_drawdown_limit > 1:
            raise ValueError("base_drawdown_limit must be in (0, 1]")
        if self.volatility_lookback < 2:
            raise ValueError("volatility_lookback must be >= 2")
        if self.min_threshold_multiplier <= 0:
            raise ValueError("min_threshold_multiplier must be positive")
        if self.max_threshold_multiplier < self.min_threshold_multiplier:
            raise ValueError("max_threshold_multiplier must be >= min_threshold_multiplier")
        if not 0 < self.adaptation_rate <= 1:
            raise ValueError("adaptation_rate must be in (0, 1]")

    def to_dict(self) -> dict[str, Any]:
        """Convert configuration to dictionary."""
        return {
            "base_position_limit": self.base_position_limit,
            "base_daily_loss_limit": self.base_daily_loss_limit,
            "base_drawdown_limit": self.base_drawdown_limit,
            "volatility_lookback": self.volatility_lookback,
            "volatility_scale_factor": self.volatility_scale_factor,
            "volume_lookback": self.volume_lookback,
            "volume_threshold_multiplier": self.volume_threshold_multiplier,
            "min_threshold_multiplier": self.min_threshold_multiplier,
            "max_threshold_multiplier": self.max_threshold_multiplier,
            "adaptation_rate": self.adaptation_rate,
        }


@dataclass(slots=True)
class CalibratedThresholds:
    """Calibrated risk thresholds after adaptation.

    Attributes:
        position_limit: Current position limit as fraction of equity.
        daily_loss_limit: Current daily loss limit as fraction of equity.
        drawdown_limit: Current drawdown limit as fraction.
        volatility_regime: Current volatility regime (low/normal/high).
        adaptation_factor: Current adaptation factor applied.
        last_updated: Timestamp of last calibration.
    """

    position_limit: float
    daily_loss_limit: float
    drawdown_limit: float
    volatility_regime: str = "normal"
    adaptation_factor: float = 1.0
    last_updated: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        """Convert thresholds to dictionary."""
        return {
            "position_limit": self.position_limit,
            "daily_loss_limit": self.daily_loss_limit,
            "drawdown_limit": self.drawdown_limit,
            "volatility_regime": self.volatility_regime,
            "adaptation_factor": self.adaptation_factor,
            "last_updated": self.last_updated.isoformat(),
        }


class AdaptiveThresholdCalibrator:
    """Calibrates risk thresholds adaptively based on market conditions.

    The calibrator maintains a rolling window of market data and adjusts
    thresholds based on observed volatility and volume patterns.

    Example:
        >>> calibrator = AdaptiveThresholdCalibrator()
        >>> calibrator.update(returns=returns, volumes=volumes)
        >>> thresholds = calibrator.get_thresholds()
        >>> print(f"Current position limit: {thresholds.position_limit:.2%}")
    """

    def __init__(
        self,
        config: ThresholdConfig | None = None,
        *,
        time_source: Callable[[], datetime] | None = None,
    ) -> None:
        """Initialize the calibrator.

        Args:
            config: Threshold configuration.
            time_source: Optional time source for testing.
        """
        self._config = config or ThresholdConfig()
        self._time = time_source or (lambda: datetime.now(timezone.utc))
        self._lock = threading.RLock()

        # Rolling data windows
        self._returns: deque[float] = deque(maxlen=self._config.volatility_lookback)
        self._volumes: deque[float] = deque(maxlen=self._config.volume_lookback)

        # Current state
        self._current_volatility: float = 0.0
        self._baseline_volatility: float | None = None
        self._current_adaptation_factor: float = 1.0
        self._volatility_regime: str = "normal"

        # Asset-specific adjustments
        self._asset_volatility: dict[str, float] = {}
        self._asset_volume_profile: dict[str, float] = {}

        LOGGER.info(
            "Adaptive threshold calibrator initialized",
            extra={"config": self._config.to_dict()},
        )

    @property
    def config(self) -> ThresholdConfig:
        """Get current configuration."""
        return self._config

    def update(
        self,
        *,
        returns: NDArray[np.float64] | list[float] | None = None,
        volumes: NDArray[np.float64] | list[float] | None = None,
        asset: str | None = None,
    ) -> CalibratedThresholds:
        """Update calibration with new market data.

        Args:
            returns: Array of recent returns.
            volumes: Array of recent volumes.
            asset: Optional asset identifier for asset-specific calibration.

        Returns:
            Updated calibrated thresholds.
        """
        with self._lock:
            # Update return history
            if returns is not None:
                for r in np.asarray(returns).flatten():
                    if np.isfinite(r):
                        self._returns.append(float(r))

            # Update volume history
            if volumes is not None:
                for v in np.asarray(volumes).flatten():
                    if np.isfinite(v) and v >= 0:
                        self._volumes.append(float(v))

            # Calculate current volatility
            self._update_volatility(asset)

            # Calculate adaptation factor
            self._update_adaptation_factor()

            # Determine volatility regime
            self._update_volatility_regime()

            return self.get_thresholds()

    def get_thresholds(self, asset: str | None = None) -> CalibratedThresholds:
        """Get current calibrated thresholds.

        Args:
            asset: Optional asset for asset-specific thresholds.

        Returns:
            Current calibrated thresholds.
        """
        with self._lock:
            factor = self._current_adaptation_factor

            # Apply asset-specific adjustment if available
            if asset and asset in self._asset_volatility:
                asset_vol = self._asset_volatility[asset]
                if self._baseline_volatility and self._baseline_volatility > 0:
                    asset_factor = asset_vol / self._baseline_volatility
                    factor = factor * min(max(asset_factor, 0.5), 2.0)

            # Clamp factor to configured bounds
            factor = max(
                self._config.min_threshold_multiplier,
                min(factor, self._config.max_threshold_multiplier),
            )

            return CalibratedThresholds(
                position_limit=self._config.base_position_limit * factor,
                daily_loss_limit=self._config.base_daily_loss_limit * factor,
                drawdown_limit=self._config.base_drawdown_limit * factor,
                volatility_regime=self._volatility_regime,
                adaptation_factor=factor,
                last_updated=self._time(),
            )

    def update_asset_profile(
        self,
        asset: str,
        *,
        volatility: float | None = None,
        avg_volume: float | None = None,
    ) -> None:
        """Update asset-specific profile.

        Args:
            asset: Asset identifier.
            volatility: Asset's typical volatility.
            avg_volume: Asset's average trading volume.
        """
        with self._lock:
            if volatility is not None and volatility > 0:
                self._asset_volatility[asset] = volatility
            if avg_volume is not None and avg_volume > 0:
                self._asset_volume_profile[asset] = avg_volume

    def reset(self) -> None:
        """Reset the calibrator to initial state."""
        with self._lock:
            self._returns.clear()
            self._volumes.clear()
            self._current_volatility = 0.0
            self._baseline_volatility = None
            self._current_adaptation_factor = 1.0
            self._volatility_regime = "normal"
            self._asset_volatility.clear()
            self._asset_volume_profile.clear()
            LOGGER.info("Adaptive threshold calibrator reset")

    def get_status(self) -> dict[str, Any]:
        """Get current calibrator status.

        Returns:
            Dictionary with status information.
        """
        with self._lock:
            thresholds = self.get_thresholds()
            return {
                "current_volatility": self._current_volatility,
                "baseline_volatility": self._baseline_volatility,
                "volatility_regime": self._volatility_regime,
                "adaptation_factor": self._current_adaptation_factor,
                "return_samples": len(self._returns),
                "volume_samples": len(self._volumes),
                "tracked_assets": len(self._asset_volatility),
                "thresholds": thresholds.to_dict(),
            }

    def _update_volatility(self, asset: str | None = None) -> None:
        """Calculate current volatility from return history."""
        if len(self._returns) < 2:
            return

        returns_array = np.array(list(self._returns))
        self._current_volatility = float(np.std(returns_array, ddof=1))

        # Update baseline if not set or if market is calm
        if self._baseline_volatility is None:
            self._baseline_volatility = self._current_volatility
        elif self._volatility_regime == "low":
            # Slowly adapt baseline during calm periods
            self._baseline_volatility = (
                0.95 * self._baseline_volatility + 0.05 * self._current_volatility
            )

        # Update asset-specific volatility
        if asset and len(self._returns) >= self._config.volatility_lookback:
            self._asset_volatility[asset] = self._current_volatility

    def _update_adaptation_factor(self) -> None:
        """Calculate adaptation factor based on volatility ratio."""
        if self._baseline_volatility is None or self._baseline_volatility <= 0:
            self._current_adaptation_factor = 1.0
            return

        # Calculate volatility ratio
        vol_ratio = self._current_volatility / self._baseline_volatility

        # Apply scaling: higher volatility = lower thresholds (more conservative)
        # Inverse relationship: when vol_ratio > 1, we want factor < 1
        target_factor = 1.0 / (1.0 + (vol_ratio - 1.0) * self._config.volatility_scale_factor)

        # Apply volume-based adjustment if we have volume data
        if len(self._volumes) >= 2:
            volumes_array = np.array(list(self._volumes))
            avg_volume = float(np.mean(volumes_array))
            recent_volume = float(np.mean(volumes_array[-3:]))

            if avg_volume > 0:
                volume_ratio = recent_volume / avg_volume
                # High volume during volatility is concerning
                if volume_ratio > self._config.volume_threshold_multiplier:
                    target_factor *= 0.8

        # Smooth adaptation
        self._current_adaptation_factor = (
            self._config.adaptation_rate * target_factor
            + (1 - self._config.adaptation_rate) * self._current_adaptation_factor
        )

        # Clamp to bounds
        self._current_adaptation_factor = max(
            self._config.min_threshold_multiplier,
            min(self._current_adaptation_factor, self._config.max_threshold_multiplier),
        )

    def _update_volatility_regime(self) -> None:
        """Determine current volatility regime."""
        if self._baseline_volatility is None or self._baseline_volatility <= 0:
            self._volatility_regime = "normal"
            return

        vol_ratio = self._current_volatility / self._baseline_volatility

        if vol_ratio < 0.7:
            self._volatility_regime = "low"
        elif vol_ratio > 1.5:
            self._volatility_regime = "high"
        else:
            self._volatility_regime = "normal"
