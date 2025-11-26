"""Two-state persistence filter for volatility regimes."""

from __future__ import annotations


class VolBelief:
    """Simple two-state belief filter for volatility regimes."""

    def __init__(
        self, p11: float = 0.95, p00: float = 0.95, thresh: float = 0.75
    ) -> None:
        self.p11 = float(p11)
        self.p00 = float(p00)
        self.thresh = float(thresh)
        self.b = 0.5

    def step(self, vol: float) -> float:
        vol = float(max(0.0, min(1.0, vol)))
        like_high = 0.9 if vol > self.thresh else 0.1
        like_low = 1.0 - like_high
        b_pred = self.b * self.p11 + (1.0 - self.b) * (1.0 - self.p00)
        num = like_high * b_pred
        den = num + like_low * (1.0 - b_pred)
        self.b = num / max(1e-9, den)
        return self.b
