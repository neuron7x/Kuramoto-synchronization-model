# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Validation pipeline for GeoSync Pro."""

from __future__ import annotations

from typing import Dict, Iterable, Tuple

import numpy as np
import pandas as pd

from ..estimation.belief import VolBelief
from ..estimation.ekf import EMHEKF
from ..models.emh import EMHSSM, Params, State
from ..policy.mpc import Controller, MPCConfig
from ..risk.cvar import CVARGate


def simulate_steps(steps: int = 500, seed: int = 42) -> Iterable[Dict[str, float]]:
    rng = np.random.default_rng(seed)
    for t in range(steps):
        vol = float(np.clip(0.5 + 0.5 * np.sin(t / 30) + 0.2 * rng.standard_normal(), 0, 1))
        dd = float(np.clip(rng.beta(2, 5) * (0.5 + 0.5 * np.sin(t / 40)), 0, 1))
        liq = float(np.clip(1 - vol + 0.1 * rng.standard_normal(), 0, 1))
        reg = float(vol > 0.8) * 0.7 + 0.3
        reward = float(0.02 * (1 - vol) - 0.03 * (dd > 0.7))
        var_breach = bool(vol > 0.9 or dd > 0.75)
        yield dict(dd=dd, vol=vol, liq=liq, reg=reg, reward=reward, var_breach=var_breach)


def run_validation(steps: int = 500) -> Tuple[pd.DataFrame, Dict[str, float]]:
    p = Params()
    model = EMHSSM(p, State())
    model.belief = VolBelief()
    ekf = EMHEKF(model)
    ctrl = Controller(MPCConfig(horizon=5, temp=1.0))
    gate = CVARGate(alpha=0.95, limit=0.03, lookback=50)

    rows = []
    rets = []
    for obs in simulate_steps(steps):
        snap = model.step(obs)
        xhat = ekf.step(obs)
        mode = snap["mode"]
        D = snap["D"]

        action, extra = ctrl.decide(xhat, mode, D)

        alloc_scale = gate.update(obs["reward"])
        alloc_main = extra["alloc_main"] * alloc_scale
        alloc_alt = extra["alloc_alt"] * alloc_scale

        rets.append(obs["reward"])
        rows.append(
            {
                **xhat,
                **snap,
                **extra,
                "alloc_scale": alloc_scale,
                "alloc_main_scaled": alloc_main,
                "alloc_alt_scaled": alloc_alt,
                "action": action,
            }
        )

    df = pd.DataFrame(rows)
    q05 = float(np.quantile(rets, 0.05)) if rets else 0.0
    tail = [r for r in rets if r <= q05]
    tail_es95 = float(-np.mean(tail)) if tail else 0.0
    metrics = {
        "mean_reward": float(np.mean(rets)) if rets else 0.0,
        "std_reward": float(np.std(rets)) if rets else 0.0,
        "tail_ES95": tail_es95,
        "prop_RED": float(np.mean(df["mode"] == "RED")) if not df.empty else 0.0,
        "prop_increase_risk_in_RED": (
            float(np.mean((df["mode"] == "RED") & (df["action"] == "increase_risk")))
            if not df.empty
            else 0.0
        ),
        "avg_alloc_scale": float(np.mean(df["alloc_scale"])) if not df.empty else 0.0,
    }
    return df, metrics
