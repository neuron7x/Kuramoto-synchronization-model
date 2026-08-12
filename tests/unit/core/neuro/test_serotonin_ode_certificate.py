# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""The parameter-level Lyapunov certificate must reflect the real PD condition.

lyapunov_parameter_certificate proves, from parameters alone, that V is a strict
Lyapunov function for (baseline, 0) on the unforced sub-threshold flow — the guarantee
that the trajectory-only verify_lyapunov cannot give. The certificate is exactly the
positive-definiteness of M = [[α+γ, δ/2], [δ/2, 2λμ]] with target == baseline.
"""
from __future__ import annotations

from core.neuro.serotonin_ode import SerotoninODE, SerotoninODEParams


def test_defaults_are_certified() -> None:
    ode = SerotoninODE(SerotoninODEParams())
    # α+γ=0.15, 2λμ=0.005, (δ/2)²=1e-4 → 7.5e-4 > 1e-4.
    assert ode.lyapunov_parameter_certificate() is True


def test_cross_coupling_that_breaks_positive_definiteness_is_rejected() -> None:
    # A large δ (level↔desens suppression) makes (δ/2)² exceed (α+γ)·2λμ.
    bad = SerotoninODEParams(delta=0.5)
    ode = SerotoninODE(bad)
    assert ode.lyapunov_parameter_certificate() is False


def test_target_offset_from_baseline_is_not_certified() -> None:
    # V is centred on target; if the equilibrium (baseline) differs, V is not a
    # Lyapunov function for it — the certificate must refuse rather than overclaim.
    offset = SerotoninODEParams(target=0.5, baseline=0.3)
    ode = SerotoninODE(offset)
    assert ode.lyapunov_parameter_certificate() is False


def test_certificate_agrees_with_a_zero_stress_descent() -> None:
    # When the parameters are certified, an unforced sub-threshold trajectory does
    # empirically descend — the two views are consistent for a well-posed system.
    params = SerotoninODEParams()
    ode = SerotoninODE(params, level=0.45, desensitization=0.0)  # below threshold 0.5
    trajectory = [(ode.level, ode.desensitization)]
    for _ in range(200):
        trajectory.append(ode.step(stress=0.0, dt=0.1))
    assert ode.lyapunov_parameter_certificate() is True
    assert ode.verify_lyapunov(trajectory) is True
