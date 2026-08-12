# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""The deprecated conservation-law aliases must keep working bit-for-bit.

Until every in-tree caller is migrated to the canonical ``*_proxy`` names,
the aliases ``compute_market_energy`` / ``compute_market_momentum`` /
``check_energy_conservation`` / ``check_momentum_conservation`` MUST:

1. Emit a ``DeprecationWarning``.
2. Return numerically identical output to their ``*_proxy`` replacements.

This guards the audit-2026-04-30 zero-behaviour-change contract.
"""

from __future__ import annotations

import warnings

import numpy as np
import pytest

from core.physics.conservation import (
    check_energy_conservation,
    check_momentum_conservation,
    check_proxy_drift,
    compute_flow_momentum_proxy,
    compute_market_energy,
    compute_market_momentum,
    compute_volatility_energy_proxy,
)


def test_compute_market_energy_alias_matches_proxy() -> None:
    """NON_PHYSICS: deprecated-alias equivalence + DeprecationWarning.

    This is a migration/refactor contract, not a physics witness: it asserts the
    alias returns bit-identical output to its ``*_proxy`` replacement and warns.
    It makes no claim about any registered conservation invariant (INV-TH1/TH2),
    so grounding it to an INV would be a category error per Rule Zero.
    """
    prices = np.array([100.0, 102.0, 105.0, 104.0, 107.0])
    volumes = np.array([1000.0, 800.0, 1200.0, 900.0, 1100.0])
    expected = compute_volatility_energy_proxy(prices, volumes)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", DeprecationWarning)
        observed = compute_market_energy(prices, volumes)
    assert observed == pytest.approx(expected, rel=0, abs=0)
    assert any(issubclass(w.category, DeprecationWarning) for w in caught)


def test_compute_market_momentum_alias_matches_proxy() -> None:
    """NON_PHYSICS: deprecated-alias equivalence + DeprecationWarning.

    Migration/refactor contract only — asserts alias == ``*_proxy`` output and
    warns; no registered physics invariant is witnessed.
    """
    prices = np.array([100.0, 102.0, 105.0])
    volumes = np.array([10.0, 20.0, 30.0])
    expected = compute_flow_momentum_proxy(prices, volumes)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", DeprecationWarning)
        observed = compute_market_momentum(prices, volumes)
    assert observed == pytest.approx(expected, rel=0, abs=0)
    assert any(issubclass(w.category, DeprecationWarning) for w in caught)


def test_check_energy_conservation_alias_matches_drift() -> None:
    """NON_PHYSICS: deprecated-alias equivalence to ``check_proxy_drift``.

    Migration/refactor contract only — asserts the alias routes to
    ``check_proxy_drift`` identically and warns; not a conservation-law witness.
    """
    expected = check_proxy_drift(100.0, 100.5, tolerance=0.01)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", DeprecationWarning)
        observed = check_energy_conservation(100.0, 100.5, tolerance=0.01)
    assert observed == expected
    assert any(issubclass(w.category, DeprecationWarning) for w in caught)


def test_check_momentum_conservation_alias_matches_drift() -> None:
    """NON_PHYSICS: deprecated-alias equivalence to ``check_proxy_drift``.

    Migration/refactor contract only — asserts the alias routes to
    ``check_proxy_drift`` identically and warns; not a conservation-law witness.
    """
    expected = check_proxy_drift(50.0, 50.5, tolerance=0.02)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", DeprecationWarning)
        observed = check_momentum_conservation(50.0, 50.5, tolerance=0.02)
    assert observed == expected
    assert any(issubclass(w.category, DeprecationWarning) for w in caught)
