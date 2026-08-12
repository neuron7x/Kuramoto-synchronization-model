# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations


def ism(dH_dt: float, E_topo: float, eta: float = 1.0) -> float:
    if E_topo == 0:
        return 0.0
    return float(eta * dH_dt / E_topo)
