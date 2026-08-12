# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Unit tests for the volatility / flow proxies in ``core.physics.conservation``.

The 2026-04-30 external audit demoted ``compute_market_energy`` and
friends from "conservation laws" to volatility / flow proxies. This file
exercises the canonical ``*_proxy`` names; the deprecated aliases keep
working but are covered separately by ``test_conservation_aliases.py``.
"""

import numpy as np
import pytest

from core.physics.conservation import (
    check_proxy_drift,
    compute_flow_momentum_proxy,
    compute_volatility_energy_proxy,
)


class TestProxyDrift:
    """The drift checker is a diagnostic, not a conservation law."""

    def test_drift_perfect(self) -> None:
        within, change = check_proxy_drift(100.0, 100.0)
        assert within is True
        assert change == 0.0

    def test_drift_within_tolerance(self) -> None:
        within, change = check_proxy_drift(100.0, 100.5, tolerance=0.01)
        assert within is True
        assert abs(change - 0.005) < 1e-10

    def test_drift_violation(self) -> None:
        within, change = check_proxy_drift(100.0, 110.0, tolerance=0.01)
        assert within is False
        assert abs(change - 0.1) < 1e-10

    def test_drift_perfect_for_momentum_inputs(self) -> None:
        """Same checker handles flow-momentum drift — there is no separate function."""
        within, change = check_proxy_drift(50.0, 50.0)
        assert within is True
        assert change == 0.0


class TestVolatilityEnergyProxy:
    """``compute_volatility_energy_proxy`` is dominated by the kinetic-style term."""

    def test_basic(self) -> None:
        prices = np.array([100.0, 102.0, 104.0])
        volumes = np.array([1.0, 1.0, 1.0])
        energy = compute_volatility_energy_proxy(prices, volumes)
        assert energy >= 0.0
        assert np.isfinite(energy)

    def test_vwap_residual_is_zero_when_volumes_match_vwap(self) -> None:
        """Σ_i v_i (P_i − VWAP) = 0 by construction → output is purely kinetic."""
        prices = np.array([100.0, 105.0, 110.0])
        volumes = np.array([2.0, 1.0, 3.0])
        velocities = np.array([0.0, 5.0, 5.0])
        kinetic_only = 0.5 * float(np.sum(volumes * velocities**2))
        energy = compute_volatility_energy_proxy(prices, volumes, velocities)
        assert abs(energy - kinetic_only) < 1e-9


class TestFlowMomentumProxy:
    def test_basic(self) -> None:
        prices = np.array([100.0, 102.0, 104.0])
        volumes = np.array([1.0, 1.0, 1.0])
        momentum = compute_flow_momentum_proxy(prices, volumes)
        assert np.isfinite(momentum)


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])
