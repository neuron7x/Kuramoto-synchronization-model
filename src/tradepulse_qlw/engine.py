"""Main QLW engine for market dynamics analysis."""

from __future__ import annotations

import numpy as np
from scipy.signal import savgol_filter

from .config import QLWConfig
from .mdfa import gamma_from_h, hurst_mfdfa
from .pde_solver import NewmarkWaveSolver
from .risk.adaptive_tau import PIDTau
from .types import EngineResult


class QLWEngine:
    """
    QLW Engine: Damped Stochastic Wave Model for Liquidity Risk.

    Combines PDE solver, MF-DFA calibration, and adaptive risk control
    to model market dynamics as a wave field with forbidden zones.
    """

    def __init__(self, cfg: QLWConfig):
        self.cfg = cfg
        self.pid = PIDTau(
            target=cfg.pid_target, min_tau=cfg.tau_min, max_tau=cfg.tau_max
        )

    def _compute_c_series(self, pressures: np.ndarray) -> tuple[float, np.ndarray]:
        """Compute wave speed series from order flow pressures."""
        cfg = self.cfg
        c_t = np.empty(cfg.nt)
        alpha = cfg.c_ema_alpha
        c0 = cfg.c_min + (cfg.c_max - cfg.c_min) * np.clip(
            np.mean(pressures[: max(1, cfg.nt // 10)]), 0, 1
        )
        c_t[0] = c0
        for t in range(1, cfg.nt):
            c_t[t] = (1 - alpha) * c_t[t - 1] + alpha * (
                cfg.c_min + (cfg.c_max - cfg.c_min) * np.clip(pressures[t], 0, 1)
            )
        return float(np.mean(c_t)), c_t

    def calibrate_gamma(self, features_fmn: np.ndarray) -> tuple[float, dict]:
        """
        Calibrate damping coefficient via MF-DFA Hurst exponent.

        Parameters
        ----------
        features_fmn : np.ndarray
            Feature matrix (nt, n_features)

        Returns
        -------
        tuple[float, dict]
            Gamma value and metadata including Hurst statistics
        """
        arr = np.asarray(features_fmn, dtype=float)
        ts = arr.mean(axis=1) if arr.ndim == 2 else arr
        nt = len(ts)
        W = max(32, nt // 4)
        S = max(8, W // 4)
        Hs = [hurst_mfdfa(ts[i : i + W]) for i in range(0, nt - W + 1, S)]
        H_mean, H_std = float(np.mean(Hs)), float(np.std(Hs))
        lo, hi = self.cfg.gamma_lo, self.cfg.gamma_hi
        gamma = gamma_from_h(H_mean, lo, hi)
        return gamma, {"H_mean": H_mean, "H_std": H_std}

    def run(
        self,
        features_fmn: np.ndarray,
        orderbook: np.ndarray | None = None,
        delta_volume: np.ndarray | None = None,
    ) -> EngineResult:
        """
        Run the QLW engine on market data.

        Parameters
        ----------
        features_fmn : np.ndarray
            Feature matrix (nt, n_features)
        orderbook : np.ndarray, optional
            Order book data (nt, depth, 2) for bid/ask
        delta_volume : np.ndarray, optional
            Volume delta series

        Returns
        -------
        EngineResult
            Complete results including wave field, masks, and metadata
        """
        cfg = self.cfg
        fmn = np.asarray(features_fmn, dtype=float)
        nt = cfg.nt

        # Compute order flow pressures
        if orderbook is not None:
            pressures = (orderbook[:, :, 0].sum(1) - orderbook[:, :, 1].sum(1)) / (
                orderbook.sum((1, 2)) + 1e-12
            )
        elif delta_volume is not None:
            pressures = np.abs(np.asarray(delta_volume, dtype=float))
        else:
            pressures = np.zeros(nt)

        # Calibrate wave speed and damping
        c, c_t = self._compute_c_series(pressures)
        gamma, h_meta = self.calibrate_gamma(fmn)

        # Solve PDE
        solver = NewmarkWaveSolver(
            cfg.nx,
            nt,
            cfg.dx,
            cfg.dt,
            c=c,
            gamma=gamma,
            noise_sigma=cfg.noise_sigma,
            seed=cfg.seed,
            pml_width_frac=cfg.pml_width_frac,
            pml_gain=cfg.pml_gain,
            use_numba=cfg.use_numba,
            use_gpu=cfg.use_gpu,
        )
        psi = solver.solve()

        # Compute phase alignment
        price_ts = np.log(fmn.mean(1) + 1e-12)
        price_phase = np.unwrap(np.angle(np.fft.fft(price_ts)))
        price_phase = savgol_filter(price_phase, cfg.phase_smooth_len, 2)
        psi_phases = np.unwrap(np.angle(np.fft.fft(psi, axis=1)), axis=1)
        phase_diff = psi_phases.mean(1) - price_phase[:nt]
        R = np.cos(phase_diff)[:, None]  # (nt,1) for hotspot_k=1 baseline

        # Compute forbidden zones
        abs_psi = np.abs(psi)
        m = np.median(abs_psi)
        mad = np.median(np.abs(abs_psi - m)) + 1e-12

        if cfg.forbidden_mode == "quantile":
            tau = float(np.quantile(abs_psi, cfg.forbidden_quantile))
        elif cfg.forbidden_mode == "mad":
            tau = float(m + cfg.forbidden_k * mad)
        elif cfg.forbidden_mode == "pid":
            # Initial tau from MAD heuristic then close the loop
            tau = float(m + cfg.forbidden_k * mad)
            ratio = float((abs_psi > tau).mean())
            tau = self.pid.update(ratio, tau)
        else:
            tau = cfg.forbidden_threshold

        # Soft and hard masks
        soft = 1 / (1 + np.exp(-(abs_psi - tau) / mad))
        hard = soft > 0.9

        # Metadata
        from typing import Any

        meta: dict[str, Any] = {
            "dt": cfg.dt,
            "dx": cfg.dx,
            "c": c,
            "c_mean": float(np.mean(c_t)),
            "gamma": gamma,
            "cfl": c * cfg.dt / cfg.dx,
            "seed": cfg.seed,
            "eta_sigma": cfg.noise_sigma,
            "tau": tau,
            "pml_gain": cfg.pml_gain,
            "R_auc": float(np.trapezoid(np.abs(R).ravel())),
        }
        meta.update(h_meta)
        meta["hard_gate_trigger"] = hard.mean(axis=1) >= 0.15
        meta["soft_weight_penalty"] = float(1 - 0.5 * np.mean(soft > 0.9))
        meta["decision_impact"] = "TACL gate applied if trigger"

        return EngineResult(psi=psi, resonance=R, forbidden_mask=hard, soft_mask=soft, meta=meta)
