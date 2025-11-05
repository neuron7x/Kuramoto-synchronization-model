"""Regime detection for adaptive plasticity."""

from enum import Enum
from typing import Dict, Optional
from .metrics import Telemetry


class Regime(Enum):
    """Market/system regime classification."""

    CALM = "CALM"
    TREND = "TREND"
    VOLATILE = "VOLATILE"
    SHOCK = "SHOCK"


class RegimeDetector:
    """Detect current regime based on telemetry and thresholds."""

    def __init__(
        self, thresholds: Dict[str, Dict[str, float]], hysteresis_vol: float = 0.03
    ):
        """Initialize regime detector.

        Args:
            thresholds: Regime classification thresholds
            hysteresis_vol: Hysteresis buffer to prevent regime oscillation
        """
        self.thresholds = thresholds
        self.hysteresis_vol = hysteresis_vol
        self._last_regime: Optional[Regime] = None

    def detect(self, t: Telemetry, last: Optional[Regime] = None) -> Regime:
        """Detect regime from telemetry.

        Priority order: SHOCK > VOLATILE > TREND > CALM

        Args:
            t: Current telemetry
            last: Previous regime for hysteresis

        Returns:
            Detected regime
        """
        # Check SHOCK conditions first (highest priority)
        shock_t = self.thresholds.get("SHOCK", {})
        if t.p99 > shock_t.get("latency_p99_max", 20.0) or t.jitter > shock_t.get(
            "jitter_p99_max", 10.0
        ):
            self._last_regime = Regime.SHOCK
            return Regime.SHOCK

        # Apply hysteresis if we have previous regime
        vol_with_hyst = t.vol_index
        if last == Regime.VOLATILE:
            vol_with_hyst += self.hysteresis_vol
        elif last == Regime.CALM or last == Regime.TREND:
            vol_with_hyst -= self.hysteresis_vol

        # Check volatility-based regimes
        calm_t = self.thresholds.get("CALM", {})
        trend_t = self.thresholds.get("TREND", {})

        if vol_with_hyst < calm_t.get("vol_index_max", 0.3):
            regime = Regime.CALM
        elif vol_with_hyst < trend_t.get("vol_index_max", 0.6):
            regime = Regime.TREND
        else:
            regime = Regime.VOLATILE

        self._last_regime = regime
        return regime
