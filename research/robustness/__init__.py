# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Robustness primitives — read-only statistical battery.

Contains three strategy-agnostic primitive modules:

- :mod:`cpcv` — Combinatorial Purged Cross-Validation splits,
  Probability of Backtest Overfitting (PBO), Probabilistic Sharpe Ratio
  (PSR). Lopez de Prado (2018) *Advances in Financial ML*.
- :mod:`null_audit` — block-bootstrap null falsification families.
- :mod:`stability` — parameter jitter stability.

All primitives are *pure functions* on numpy/pandas inputs. No writes.
No I/O. No strategy coupling. Protocol-level orchestration lives in
:mod:`research.robustness.protocols`.
"""

from __future__ import annotations

from .cpcv import (
    cpcv_splits,
    estimate_pbo,
    probabilistic_sharpe_ratio,
    probabilistic_sharpe_ratio_hac,
    rolling_probabilistic_sharpe,
)
from .null_audit import NullAuditResult, run_null_falsification_audit
from .stability import JitterStabilityResult, parameter_jitter_stability

__all__ = [
    "JitterStabilityResult",
    "NullAuditResult",
    "cpcv_splits",
    "estimate_pbo",
    "parameter_jitter_stability",
    "probabilistic_sharpe_ratio",
    "probabilistic_sharpe_ratio_hac",
    "rolling_probabilistic_sharpe",
    "run_null_falsification_audit",
]
