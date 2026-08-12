# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Symbolic proof of the all-to-all Kuramoto potential identity.

INV-K7/K8 treat the energy E = ½·Σ m·θ̇² + V with the all-to-all potential
V(θ) = -½·Σ_ij A_ij·cos(θ_j − θ_i), A_ij = K/N. Two algebraic facts underpin
them and are usually only *numerically* corroborated:

    (1)  V = -(K·N/2)·R² + K/2          (the INV-K7 potential up to a constant)
    (2)  -∂V/∂θ_i = Σ_j A_ij·sin(θ_j − θ_i)   (the swing-equation coupling force)

(2) is the reason energy is conserved: the coupling is the gradient of a
potential, so the autonomous flow is conservative. Here we *prove* both
symbolically with sympy (exact, no numerical tolerance), elevating them from
numerically-consistent to algebraically-proven. Skipped where sympy is absent.
"""

from __future__ import annotations

from typing import Any

import pytest

sp = pytest.importorskip("sympy")


def _all_to_all_potential_and_R2(n: int) -> tuple[Any, Any, Any, Any]:
    """Return (V, R², K, θ-symbols) for the all-to-all model with A_ij = K/N."""
    k = sp.symbols("K", positive=True)
    theta = sp.symbols(f"theta0:{n}", real=True)

    def adj(i: int, j: int) -> Any:
        return sp.Integer(0) if i == j else k / n

    potential = -sp.Rational(1, 2) * sum(
        adj(i, j) * sp.cos(theta[j] - theta[i]) for i in range(n) for j in range(n)
    )
    r_squared = sp.Rational(1, 1) / n**2 * sum(
        sp.cos(theta[j] - theta[i]) for i in range(n) for j in range(n)
    )
    return potential, r_squared, k, theta


@pytest.mark.parametrize("n", [3, 4, 5])
def test_potential_equals_minus_half_kn_r_squared(n: int) -> None:
    """INV-K7/K8 foundation: V = -(K·N/2)·R² + K/2 exactly (symbolic)."""
    potential, r_squared, k, _ = _all_to_all_potential_and_R2(n)
    residual = sp.simplify(potential - (-(k * n) / 2 * r_squared + k / 2))
    assert residual == 0, f"V identity residual ≠ 0 for N={n}: {residual}"


@pytest.mark.parametrize("n", [3, 4, 5])
def test_coupling_is_minus_gradient_of_potential(n: int) -> None:
    """INV-K7/K8 root: -∂V/∂θ_i equals the Σ_j A_ij·sin(θ_j−θ_i) coupling force.

    This is *why* the autonomous swing flow conserves energy: the coupling is a
    conservative (gradient) force.
    """
    potential, _, k, theta = _all_to_all_potential_and_R2(n)
    for i in range(n):
        force = sum(
            (sp.Integer(0) if i == j else k / n) * sp.sin(theta[j] - theta[i])
            for j in range(n)
        )
        residual = sp.simplify(-sp.diff(potential, theta[i]) + (-force))
        assert residual == 0, f"-∂V/∂θ_{i} ≠ coupling for N={n}: {residual}"
