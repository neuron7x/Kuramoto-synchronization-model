from __future__ import annotations

from typing import Dict, Mapping, Tuple

import numpy as np

from ..core.params import PolicyModeConfig


class BasalGangliaController:
    """Softmax Q policy with Go/No-Go gating."""

    def __init__(
        self,
        temp: float = 1.0,
        tau_E_amber: float = 0.3,
        mode_configs: Mapping[str, PolicyModeConfig] | None = None,
    ):
        self.temp = float(temp)
        self.tau_E_amber = float(tau_E_amber)
        self._mode_configs = (
            {mode.upper(): cfg for mode, cfg in mode_configs.items()}
            if mode_configs
            else {}
        )

    def _resolve_mode_config(self, mode: str) -> PolicyModeConfig:
        mode_key = mode.upper()
        if mode_key in self._mode_configs:
            return self._mode_configs[mode_key]
        default_gating = self.tau_E_amber if mode_key == "AMBER" else 0.0
        return PolicyModeConfig(temp=self.temp, gating=default_gating)

    def decide(
        self, state: Dict[str, float], mode: str, RPE: float
    ) -> Tuple[str, Dict[str, float]]:
        mode_key = mode.upper()
        mode_cfg = self._resolve_mode_config(mode_key)
        _H = float(  # noqa: F841 - extracted for completeness
            state.get("H", state.get("H_est", 0.5))
        )
        M = float(state.get("M", state.get("M_est", 0.8)))
        E = float(state.get("E", state.get("E_est", 0.1)))
        S = float(state.get("S", state.get("S_est", 0.0)))

        Q = {
            "increase_risk": S
            + 0.2 * M
            - 0.3 * (mode_key == "AMBER")
            - 0.8 * (mode_key == "RED"),
            "decrease_risk": 0.4 * (mode_key == "AMBER")
            + 0.9 * (mode_key == "RED")
            + 0.1 * (1 - S),
            "switch_to_alt": 0.3 + 0.5 * E,
            "hedge": 0.2 + 0.6 * (mode_key != "GREEN") + 0.2 * (1 - M),
            "hold": 0.3 + 0.2 * M - 0.1 * S,
        }

        if mode_key == "RED":
            Q["increase_risk"] = -np.inf
        if mode_key != "RED" and mode_cfg.gating > 0.0:
            if E < mode_cfg.gating or RPE <= 0.0:
                Q["increase_risk"] = -np.inf

        keys = list(Q.keys())
        vals = np.array([Q[k] for k in keys], dtype=float)
        exps = np.exp((vals - np.max(vals)) / max(1e-6, mode_cfg.temp))
        probs = exps / np.sum(exps)
        action = keys[int(np.argmax(probs))]

        penalty = {"GREEN": 0.0, "AMBER": 0.2, "RED": 0.5}.get(mode_key, 0.0)
        alloc_main = float(np.clip(M * (0.5 + 0.5 * S) * (1.0 - penalty), 0.0, 1.0))
        alloc_alt = float(np.clip(0.6 * E + 0.4 * S, 0.0, 1.0))

        return action, {
            "alloc_main": alloc_main,
            "alloc_alt": alloc_alt,
            "Q_values": Q,
            "action_probs": {k: float(probs[i]) for i, k in enumerate(keys)},
        }
