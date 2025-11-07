"""Hybrid Bayesian online change-point detection."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class BOCPDState:
    run_length: int = 0
    mean: float = 0.0
    var: float = 1e-6
    count: int = 0


class BOCPD:
    def __init__(self, hazard: float, z_limit: float) -> None:
        self.hazard = float(hazard)
        self.z_limit = float(z_limit)
        self.state = BOCPDState()

    def reset(self) -> None:
        self.state = BOCPDState()

    def update(self, x: float) -> int:
        st = self.state
        st.count += 1
        var = max(st.var, 1e-6)
        z_score = abs(x - st.mean) / (var**0.5)
        hazard_trigger = self.hazard > 0 and st.run_length > 0 and hazard_event(self.hazard)
        if z_score > self.z_limit or hazard_trigger:
            st.run_length = 0
            st.mean = x
            st.var = 1e-6
            st.count = 1
        else:
            st.run_length += 1
            delta = x - st.mean
            st.mean += delta / st.count
            delta2 = x - st.mean
            st.var = max(1e-6, st.var + delta * delta2)
        return st.run_length


def hazard_event(prob: float) -> bool:
    from random import random

    return random() < prob


__all__ = ["BOCPD"]
