from __future__ import annotations

from dataclasses import dataclass

import numpy as np

Float = np.float32


def ema_update(prev: float, x: float, span: int) -> float:
    """One-step EMA update (float32, O(1))."""
    alpha = Float(2.0 / (1.0 + span))
    return Float((1.0 - alpha) * Float(prev) + alpha * Float(x))


def ewvar_update(prev_var: float, pe: float, lam: float, eps: float = 1e-12) -> float:
    """EWMA variance update for residuals (float32, O(1))."""
    lam = Float(lam)
    return Float(
        lam * Float(prev_var) + (1.0 - lam) * (Float(pe) * Float(pe)) + Float(eps)
    )


@dataclass
class EWEntropyConfig:
    bins: int = 32
    xmin: float = -0.05
    xmax: float = 0.05
    decay: float = 0.975
    eps: float = 1e-12


class EWEntropy:
    """Exponentially-weighted discrete Shannon entropy over fixed bins.
    Streaming, O(1), float32."""

    def __init__(self, cfg: EWEntropyConfig):
        self.cfg = cfg
        self._counts = np.full(cfg.bins, Float(1e-6), dtype=Float)  # small prior
        self._sum = Float(np.sum(self._counts))
        self._p = self._counts / self._sum
        self._H = Float(0.0)
        self._update_entropy()

    def _bin_index(self, x: float) -> int:
        r = (Float(x) - self.cfg.xmin) / (self.cfg.xmax - self.cfg.xmin + 1e-12)
        idx = int(np.floor(float(r) * self.cfg.bins))
        return max(0, min(self.cfg.bins - 1, idx))

    def _update_entropy(self) -> None:
        p = self._p + Float(self.cfg.eps)
        self._H = Float(-np.sum(p * np.log(p)))

    def update(self, x: float) -> float:
        self._counts *= Float(self.cfg.decay)
        self._counts[self._bin_index(x)] += Float(1.0)
        self._sum = Float(np.sum(self._counts))
        self._p = self._counts / self._sum
        self._update_entropy()
        return float(self._H)

    @property
    def value(self) -> float:
        return float(self._H)
