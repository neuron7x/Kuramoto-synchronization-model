"""Basal ganglia-inspired policy selection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple

import numpy as np


@dataclass
class PolicyConfig:
    """Policy temperature and gating thresholds."""

    temp: float = 1.0
    tau_E_amber: float = 0.30

    def __post_init__(self) -> None:
        self.temp = float(self.temp)
        self.tau_E_amber = float(self.tau_E_amber)


class BasalGangliaController:
    """Softmax policy with Go/No-Go gating invariants."""

    def __init__(self, cfg: PolicyConfig = PolicyConfig()):
        self.cfg = cfg

    def decide(self, state: Dict[str, float], mode: str, rpe: float) -> Tuple[str, Dict[str, float]]:
        H = float(state.get("H", 0.0))
        M = float(state.get("M", 0.0))
        E = float(state.get("E", 0.0))
        S = float(state.get("S", 0.0))
        q = {
            "increase_risk": S + 0.2 * M - 0.3 * (mode == "AMBER") - 0.8 * (mode == "RED"),
            "decrease_risk": 0.4 * (mode == "AMBER") + 0.9 * (mode == "RED") + 0.1 * (1 - S),
            "switch_to_alt": 0.3 + 0.5 * E,
            "hedge": 0.2 + 0.6 * (mode != "GREEN") + 0.2 * (1 - M),
            "hold": 0.3 + 0.2 * M - 0.1 * S,
        }
        if mode == "RED":
            q["increase_risk"] = -np.inf
        if mode == "AMBER" and (E <= self.cfg.tau_E_amber or rpe <= 0.0):
            q["increase_risk"] = -np.inf

        keys = list(q.keys())
        vals = np.array([q[k] for k in keys], float)
        probs = np.exp((vals - np.max(vals)) / max(1e-6, self.cfg.temp))
        probs /= probs.sum()
        action = keys[int(np.argmax(probs))]

        penalty = {"GREEN": 0.0, "AMBER": 0.2, "RED": 0.5}.get(mode, 0.0)
        alloc_main = float(np.clip(M * (0.5 + 0.5 * S) * (1.0 - penalty), 0.0, 1.0))
        alloc_alt = float(np.clip(0.6 * E + 0.4 * S, 0.0, 1.0))
        return action, {
            "alloc_main": alloc_main,
            "alloc_alt": alloc_alt,
            "action_probs": {k: float(probs[i]) for i, k in enumerate(keys)},
        }
