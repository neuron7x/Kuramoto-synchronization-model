"""Action selection policy for NeuroTrade Pro."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Tuple

from ..models.emh import clamp


@dataclass
class MPCConfig:
    """Policy configuration."""

    horizon: int = 5
    temp: float = 1.0


class Controller:
    """Softmax policy with Go/No-Go gating."""

    def __init__(self, cfg: MPCConfig | None = None) -> None:
        self.cfg = cfg or MPCConfig()

    def decide(
        self, state: Dict[str, float], mode: str, D: float
    ) -> Tuple[str, Dict[str, float]]:
        _H = state["H"]  # noqa: F841 - extracted for state completeness
        M = state["M"]
        E = state["E"]
        S = state["S"]
        q = {
            "increase_risk": S
            + 0.2 * M
            - 0.3 * (mode == "AMBER")
            - 0.8 * (mode == "RED"),
            "decrease_risk": 0.4 * (mode == "AMBER")
            + 0.9 * (mode == "RED")
            + 0.1 * (1 - S),
            "switch_to_alt": 0.3 + 0.5 * E,
            "hedge": 0.2 + 0.6 * (mode != "GREEN") + 0.2 * (1 - M),
            "hold": 0.3 + 0.2 * M - 0.1 * S,
        }
        if mode == "RED":
            q["increase_risk"] = -1e3
        if mode == "AMBER" and E < 0.3:
            q["increase_risk"] = -1e3

        keys = list(q.keys())
        vals = [q[k] for k in keys]
        m = max(vals)
        exps = [math.exp((v - m) / max(1e-6, self.cfg.temp)) for v in vals]
        Z = sum(exps)
        probs = {k: exps[i] / Z for i, k in enumerate(keys)}
        action = max(probs.items(), key=lambda kv: kv[1])[0]

        penalty = {"GREEN": 0.0, "AMBER": 0.2, "RED": 0.5}[mode]
        alloc_main = clamp(M * (0.5 + 0.5 * S) * (1.0 - penalty))
        alloc_alt = clamp(0.6 * E + 0.4 * S)
        return action, dict(
            alloc_main=alloc_main, alloc_alt=alloc_alt, action_probs=probs
        )
