from __future__ import annotations

import asyncio
import math
from dataclasses import dataclass

import numpy as np

from .features import EWEntropy, EWEntropyConfig, ema_update, ewvar_update

Float = np.float32


@dataclass
class AMMConfig:
    ema_span: int = 32  # forecast EMA span
    vol_lambda: float = 0.94  # EWMA variance decay
    alpha: float = 1.2  # precision scale
    beta: float = 0.6  # entropy penalty
    lambda_sync: float = 0.7  # Kuramoto gain
    eta_ricci: float = 0.5  # Ricci exponential gain
    k_gain0: float = 2.0  # initial tanh gain
    theta0: float = 0.0  # initial threshold
    rho: float = 0.04  # target burst level
    lam_S: float = 0.92  # synaptic decay
    eta_k: float = 0.01  # homeostasis rate (gain)
    eta_theta: float = 0.001  # homeostasis rate (threshold)
    pi_min: float = 1e-2
    pi_max: float = 1e3
    eps: float = 1e-8
    # entropy estimator config
    ent_bins: int = 32
    ent_xmin: float = -0.05
    ent_xmax: float = 0.05
    ent_decay: float = 0.975


class AdaptiveMarketMind:
    """Adaptive Market Mind (AMM): precision-weighted prediction error with
    Kuramoto- and Ricci-modulated precision, plus homeostatic gain control.
    Streaming O(1), float32-stable. Async-friendly via aupdate()."""

    def __init__(
        self, cfg: AMMConfig, use_internal_entropy: bool = True, R_bar: float = 0.5
    ) -> None:
        self.cfg = cfg
        self._ema = Float(0.0)
        self._var = Float(0.0)
        self._S = Float(0.0)
        self._k = Float(cfg.k_gain0)
        self._theta = Float(cfg.theta0)
        self._init = False
        self._R_bar = Float(R_bar)
        self._ent = (
            EWEntropy(
                EWEntropyConfig(
                    bins=cfg.ent_bins,
                    xmin=cfg.ent_xmin,
                    xmax=cfg.ent_xmax,
                    decay=cfg.ent_decay,
                )
            )
            if use_internal_entropy
            else None
        )
        self._alock = asyncio.Lock()

    @property
    def gain(self) -> float:
        return float(self._k)

    @property
    def threshold(self) -> float:
        return float(self._theta)

    @property
    def pulse(self) -> float:
        return float(self._S)

    def _precision(self, sigma2: float, H: float, R: float, kappa: float) -> float:
        pi0 = Float(self.cfg.alpha / (sigma2 + self.cfg.eps)) * Float(
            math.exp(-self.cfg.beta * float(H))
        )
        gamma = Float(1.0 + self.cfg.lambda_sync * (Float(R) - self._R_bar))
        hric = Float(math.exp(self.cfg.eta_ricci * Float(kappa)))
        pi = float(pi0 * gamma * hric)
        return float(min(max(pi, self.cfg.pi_min), self.cfg.pi_max))

    def update(
        self, x_t: float, R_t: float, kappa_t: float, H_t: float | None = None
    ) -> dict:
        x = Float(x_t)
        R = Float(R_t)
        kappa = Float(kappa_t)

        if not self._init:
            self._ema = Float(x)
            self._var = Float(1e-6)
            self._S = Float(0.0)
            self._init = True

        ema = self._ema = ema_update(self._ema, x, self.cfg.ema_span)
        pe = Float(x - ema)

        self._var = ewvar_update(self._var, pe, self.cfg.vol_lambda, self.cfg.eps)
        sigma2 = float(self._var)

        if self._ent is not None and H_t is None:
            H = self._ent.update(float(x))
        else:
            H = float(H_t) if H_t is not None else 0.0

        pi = self._precision(sigma2, H, R, kappa)
        delta = Float(pi) * pe
        a = Float(math.tanh(float(self._k) * float(delta)))

        burst = Float(max(0.0, float(a) - float(self._theta)))
        self._S = Float(self.cfg.lam_S) * self._S + Float(1.0 - self.cfg.lam_S) * burst

        self._k = Float(
            float(self._k) * math.exp(self.cfg.eta_k * (float(self._S) - self.cfg.rho))
        )
        self._theta = Float(
            float(self._theta) + self.cfg.eta_theta * (float(self._S) - self.cfg.rho)
        )

        return {
            "amm_pulse": float(self._S),
            "amm_precision": float(pi),
            "amm_valence": 0.0 if abs(float(a)) < 1e-7 else (1.0 if a > 0 else -1.0),
            "pred": float(ema),
            "pe": float(pe),
            "entropy": float(H),
        }

    async def aupdate(
        self,
        x_t: float,
        R_t: float,
        kappa_t: float,
        H_t: float | None = None,
        offload: bool = False,
    ) -> dict:
        """Async-friendly оновлення."""
        async with self._alock:
            if offload:
                loop = asyncio.get_running_loop()
                return await loop.run_in_executor(
                    None, lambda: self.update(x_t, R_t, kappa_t, H_t)
                )
            return self.update(x_t, R_t, kappa_t, H_t)

    @staticmethod
    def batch(
        cfg: AMMConfig,
        x: np.ndarray,
        R: np.ndarray,
        kappa: np.ndarray,
        H: np.ndarray | None = None,
    ) -> dict:
        n = len(x)
        amm = AdaptiveMarketMind(cfg, use_internal_entropy=H is None)
        out = {
            k: np.zeros(n, dtype=Float)
            for k in (
                "amm_pulse",
                "amm_precision",
                "amm_valence",
                "pred",
                "pe",
                "entropy",
            )
        }
        for i in range(n):
            ctxH = None if H is None else float(H[i])
            o = amm.update(float(x[i]), float(R[i]), float(kappa[i]), ctxH)
            out["amm_pulse"][i] = Float(o["amm_pulse"])
            out["amm_precision"][i] = Float(o["amm_precision"])
            out["amm_valence"][i] = Float(o["amm_valence"])
            out["pred"][i] = Float(o["pred"])
            out["pe"][i] = Float(o["pe"])
            out["entropy"][i] = Float(o["entropy"])
        return out
