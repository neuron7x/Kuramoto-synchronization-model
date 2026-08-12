# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Volatility / flow proxies — NOT physical conservation laws.

This module historically advertised itself as "Conservation laws applied
to market dynamics", computing a "kinetic energy" ``½ Σ v_i (Δp_i)²`` and
a "potential energy" ``Σ v_i (P_i − VWAP)``. The 2026-04-30 external audit
([`docs/audit/2026-04-30-external-audit.md`](../../docs/audit/2026-04-30-external-audit.md))
flagged this as a **category error**:

1. There is no formal mapping ``market state → mechanical state`` proven in
   this repository (volume → mass, price displacement → position, …),
   so calling these quantities "energy" and "momentum" is rhetoric, not physics.
2. ``Σ_i v_i (P_i − VWAP) ≈ 0`` by construction whenever VWAP is the
   volume-weighted mean. The "potential energy" therefore collapses to
   numerical noise and the residual signal is dominated by the kinetic-style
   volatility term — i.e. this is a volatility/flow diagnostic wearing
   Newton's coat.

The functions below are therefore **renamed** to expose the demoted
contract:

* ``compute_volatility_energy_proxy``  — was ``compute_market_energy``
* ``compute_flow_momentum_proxy``      — was ``compute_market_momentum``
* ``check_proxy_drift``                — was ``check_energy_conservation``
                                          and ``check_momentum_conservation``

The historical names remain as **deprecation aliases** so that existing
callers (``backtest/physics_validation.py``, ``core/indicators/physics.py``,
the ``test_T3_conservation`` suite, …) keep working without behaviour
changes; new call sites must use the proxy names.

This module **does not** correspond to any ``INV-*`` invariant in
``.claude/physics/INVARIANTS.yaml`` (``INV-TH1`` is about thermodynamic
energy/work bookkeeping in `core/physics/thermodynamics.py`, not about
market price/volume series). If a physical conservation contract is ever
proven for market microstructure, the binding will be reintroduced
explicitly via a new ``INV-MKT*`` block — not by retroactively
upgrading these proxies.
"""

from __future__ import annotations

import warnings

import numpy as np

__all__ = [
    "compute_volatility_energy_proxy",
    "compute_flow_momentum_proxy",
    "check_proxy_drift",
    # Deprecated aliases — kept for backward compatibility, do not use in new code.
    "compute_market_energy",
    "compute_market_momentum",
    "check_energy_conservation",
    "check_momentum_conservation",
]


def compute_volatility_energy_proxy(
    prices: np.ndarray,
    volumes: np.ndarray | None = None,
    velocities: np.ndarray | None = None,
) -> float:
    """Compute a kinetic-style volatility proxy plus a (near-zero) VWAP-residual term.

    Formally:

    .. math::

        E_\\text{proxy} = \\tfrac{1}{2} \\sum_i v_i (\\Delta p_i)^2
                       + \\sum_i v_i (P_i - \\overline{P}_v)

    where :math:`\\overline{P}_v` is the volume-weighted mean (VWAP). The
    second term is identically zero whenever ``volumes`` is the same vector
    used to compute VWAP, so this function is **dominated by the volatility
    term** by construction. Use it as such.

    This is **not** kinetic energy in any physical sense — there is no
    proven ``volume → mass`` mapping. See module docstring.

    Args:
        prices: Array of price values.
        volumes: Volume weights (default: uniform).
        velocities: Price velocities (default: ``np.diff(prices)`` zero-padded).

    Returns:
        Volatility-energy proxy (units: ``volume × price²``, not joules).
    """
    prices_arr = np.asarray(prices, dtype=float)
    n = prices_arr.size

    if n == 0:
        return 0.0

    if volumes is None:
        volumes_arr = np.ones(n, dtype=float)
    else:
        volumes_arr = np.asarray(volumes, dtype=float)

    if velocities is None:
        if n < 2:
            velocities_arr = np.zeros(n, dtype=float)
        else:
            velocities_arr = np.zeros(n, dtype=float)
            velocities_arr[1:] = np.diff(prices_arr)
    else:
        velocities_arr = np.asarray(velocities, dtype=float)

    kinetic_proxy = 0.5 * np.sum(volumes_arr * velocities_arr**2)
    vwap = np.average(prices_arr, weights=volumes_arr)
    heights = prices_arr - vwap
    vwap_residual = np.sum(volumes_arr * heights)

    return float(kinetic_proxy + vwap_residual)


def compute_flow_momentum_proxy(
    prices: np.ndarray,
    volumes: np.ndarray | None = None,
    velocities: np.ndarray | None = None,
) -> float:
    """Compute a volume-weighted price-velocity flow proxy ``Σ v_i Δp_i``.

    This is **not** mechanical momentum. There is no proven mapping from
    market state to a mechanical state. Treat the output as a directional
    flow indicator with units ``volume × price``.

    Args:
        prices: Array of price values.
        volumes: Volume weights (default: uniform).
        velocities: Price velocities (default: ``np.diff(prices)`` zero-padded).

    Returns:
        Volume-weighted flow proxy (units: ``volume × price``).
    """
    prices_arr = np.asarray(prices, dtype=float)
    n = prices_arr.size

    if n == 0:
        return 0.0

    if volumes is None:
        volumes_arr = np.ones(n, dtype=float)
    else:
        volumes_arr = np.asarray(volumes, dtype=float)

    if velocities is None:
        if n < 2:
            velocities_arr = np.zeros(n, dtype=float)
        else:
            velocities_arr = np.zeros(n, dtype=float)
            velocities_arr[1:] = np.diff(prices_arr)
    else:
        velocities_arr = np.asarray(velocities, dtype=float)

    flow_proxy = np.sum(volumes_arr * velocities_arr)

    return float(flow_proxy)


def check_proxy_drift(
    proxy_before: float,
    proxy_after: float,
    tolerance: float = 0.01,
) -> tuple[bool, float]:
    """Check whether a proxy value drifted by more than ``tolerance`` (relative).

    This is a **diagnostic** — there is no underlying conservation law.
    The function name and docstring used to advertise "energy/momentum
    conservation" semantics; that framing is retired.

    Args:
        proxy_before: Proxy at time ``t``.
        proxy_after: Proxy at time ``t+1``.
        tolerance: Relative tolerance (default: 1%).

    Returns:
        ``(is_within_tolerance, relative_change)``.
    """
    if abs(proxy_before) < 1e-10:
        absolute_change = abs(proxy_after - proxy_before)
        return absolute_change < tolerance, absolute_change

    relative_change = abs(proxy_after - proxy_before) / abs(proxy_before)
    is_within_tolerance = relative_change <= tolerance

    return is_within_tolerance, float(relative_change)


# ---------------------------------------------------------------------------
# Deprecation aliases.
#
# These keep the old import surface working for in-tree callers
# (`backtest/physics_validation.py`, `core/indicators/physics.py`,
# `core/physics/__init__.py`, the `test_T3_conservation` / `test_conservation`
# suites). New code MUST NOT use the *_market_* / *_conservation names —
# they are wrong about the physics, and CI will gate on this once the call
# sites are migrated. Until then, the aliases preserve behaviour bit-for-bit.
# ---------------------------------------------------------------------------


def _emit_alias_warning(old_name: str, new_name: str) -> None:
    warnings.warn(
        f"{old_name} is a deprecated alias for {new_name}; the underlying "
        f"quantity is a volatility/flow proxy, not a physical conservation "
        f"law. See core.physics.conservation module docstring "
        f"(audit 2026-04-30).",
        DeprecationWarning,
        stacklevel=3,
    )


def compute_market_energy(
    prices: np.ndarray,
    volumes: np.ndarray | None = None,
    velocities: np.ndarray | None = None,
) -> float:
    """Deprecated alias for :func:`compute_volatility_energy_proxy`."""
    _emit_alias_warning("compute_market_energy", "compute_volatility_energy_proxy")
    return compute_volatility_energy_proxy(prices, volumes, velocities)


def compute_market_momentum(
    prices: np.ndarray,
    volumes: np.ndarray | None = None,
    velocities: np.ndarray | None = None,
) -> float:
    """Deprecated alias for :func:`compute_flow_momentum_proxy`."""
    _emit_alias_warning("compute_market_momentum", "compute_flow_momentum_proxy")
    return compute_flow_momentum_proxy(prices, volumes, velocities)


def check_energy_conservation(
    energy_before: float,
    energy_after: float,
    tolerance: float = 0.01,
) -> tuple[bool, float]:
    """Deprecated alias for :func:`check_proxy_drift`."""
    _emit_alias_warning("check_energy_conservation", "check_proxy_drift")
    return check_proxy_drift(energy_before, energy_after, tolerance)


def check_momentum_conservation(
    momentum_before: float,
    momentum_after: float,
    tolerance: float = 0.01,
) -> tuple[bool, float]:
    """Deprecated alias for :func:`check_proxy_drift`."""
    _emit_alias_warning("check_momentum_conservation", "check_proxy_drift")
    return check_proxy_drift(momentum_before, momentum_after, tolerance)
