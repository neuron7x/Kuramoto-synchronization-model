# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Leakage gate for the Kuramoto OOS path.

``core/kuramoto/oos_validation`` historically split train/val/test as
contiguous slices with no embargo. At horizon 1 that is admissible, but a
multi-step (overlapping-label) horizon then leaks the train/test boundary into
the OOS error with no guard. These tests pin the gate: a multi-step horizon
without a covering embargo is refused, an embargo opens a real purge gap, and
the horizon-1 default still reproduces the contiguous split (zero blast radius).
"""

from __future__ import annotations

import numpy as np
import pytest

from core.kuramoto.contracts import PhaseMatrix
from core.kuramoto.oos_validation import OOSConfig, temporal_split


def _phases(t: int = 100, n: int = 3) -> PhaseMatrix:
    rng = np.random.default_rng(0)
    theta = np.mod(rng.uniform(0.0, 2 * np.pi, size=(t, n)), np.nextafter(2 * np.pi, 0.0))
    return PhaseMatrix(
        theta=theta,
        timestamps=np.arange(t, dtype=np.float64),
        asset_ids=tuple(f"a{i}" for i in range(n)),
        extraction_method="hilbert",
        frequency_band=(1e-6, 0.5),
    )


def test_multistep_horizon_without_embargo_is_refused() -> None:
    with pytest.raises(ValueError, match="embargo"):
        OOSConfig(horizon=3)


def test_multistep_horizon_with_covering_embargo_is_allowed() -> None:
    cfg = OOSConfig(horizon=3, embargo=2)
    assert cfg.embargo == 2


def test_negative_embargo_refused() -> None:
    with pytest.raises(ValueError, match="embargo must be"):
        OOSConfig(embargo=-1)


def test_horizon_one_default_is_contiguous() -> None:
    """Zero blast radius: the historical contiguous split is preserved."""
    train, val, test = temporal_split(_phases(100), train_frac=0.6, val_frac=0.2)
    assert train.stop == val.start
    assert val.stop == test.start


def test_embargo_opens_a_real_purge_gap() -> None:
    train, val, test = temporal_split(_phases(100), train_frac=0.6, val_frac=0.2, embargo=5)
    assert val.start == train.stop + 5
    assert test.start == val.stop + 5
    # the embargoed observations belong to no split → genuinely purged
    assert val.start - train.stop == 5
