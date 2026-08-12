# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Energy-ontology contract: operational cost vs canonical free energy.

These tests pin the resolution of the energy-sign / unit contradiction in
``core/energy.py``. Two energies with OPPOSITE entropy conventions coexist by
design and must never be conflated again:

- ``operational_cost_energy``  — TACL minimization objective; entropy is a
  disorder PENALTY (∂/∂S ≥ 0). NOT a thermodynamic free energy.
- ``thermo_free_energy``       — canonical F = U − T·S (INV-FE2); entropy
  LOWERS F (∂F/∂S = −T ≤ 0). Mirrors ``ThermodynamicState.gibbs_energy``.

Routing: ``*energy*`` → INV-FE1..2 (CLAUDE.md). The unit contract pins that the
module emits dimensionless values and makes no joule claim.
"""

from __future__ import annotations

import math

from core.energy import (
    ENERGY_SCALE,
    ENERGY_UNITS,
    BondType,
    operational_cost_energy,
    system_free_energy,
    thermo_free_energy,
)
from core.validation.physics_validator import ThermodynamicState

_BONDS: dict[tuple[str, str], BondType] = {("a", "b"): "ionic", ("b", "c"): "metallic"}
_LAT = {("a", "b"): 0.6, ("b", "c"): 0.3}
_COH = {("a", "b"): 0.7, ("b", "c"): 0.85}


def _cost(entropy: float) -> float:
    return operational_cost_energy(_BONDS, _LAT, _COH, resource_usage=0.4, entropy=entropy)


def test_operational_cost_entropy_is_a_penalty() -> None:
    """∂/∂entropy ≥ 0 — disorder raises the minimization objective."""
    low = _cost(0.0)
    high = _cost(5.0)
    assert high >= low, (
        f"ENERGY-ONTOLOGY VIOLATED: operational_cost_energy must be non-decreasing "
        f"in entropy (disorder penalty); got cost(S=0)={low:.3e} > cost(S=5)={high:.3e}. "
        f"Entropy is a cost penalty for a minimization target, not a −T·S stabilizer."
    )


def test_thermo_free_energy_entropy_is_a_stabilizer() -> None:
    """∂F/∂entropy = −temperature ≤ 0 — raising entropy LOWERS F (INV-FE2)."""
    u, t = 1.0, 300.0
    f_low_s = thermo_free_energy(u, t, entropy=0.1)
    f_high_s = thermo_free_energy(u, t, entropy=0.9)
    assert f_high_s < f_low_s, (
        f"INV-FE2 VIOLATED: thermo_free_energy F=U−T·S must DECREASE as entropy rises; "
        f"got F(S=0.1)={f_low_s:.4f} ≤ F(S=0.9)={f_high_s:.4f} at U={u}, T={t}."
    )


def test_two_energies_have_opposite_entropy_sign() -> None:
    """The core contradiction resolution: the entropy conventions are opposite."""
    cost_slope = _cost(1.0) - _cost(0.0)  # operational: ≥ 0
    thermo_slope = thermo_free_energy(1.0, 300.0, 1.0) - thermo_free_energy(1.0, 300.0, 0.0)
    assert cost_slope >= 0.0 >= thermo_slope, (
        f"ENERGY-ONTOLOGY VIOLATED: operational entropy slope ({cost_slope:.3e}) and "
        f"thermodynamic entropy slope ({thermo_slope:.3e}) must straddle zero with "
        f"opposite sign — they encode opposite physics and must not be conflated."
    )


def test_thermo_free_energy_matches_physics_validator_gibbs() -> None:
    """thermo_free_energy is numerically identical to the canonical gibbs_energy."""
    state = ThermodynamicState(
        free_energy=0.0, entropy=0.42, temperature=300.0, internal_energy=2.5
    )
    assert thermo_free_energy(
        state.internal_energy, state.temperature, state.entropy
    ) == state.gibbs_energy


def test_backward_compatible_alias_is_identical() -> None:
    """system_free_energy must remain a true alias of operational_cost_energy."""
    assert system_free_energy is operational_cost_energy
    assert system_free_energy(_BONDS, _LAT, _COH, 0.4, 1.0) == _cost(1.0)


def test_unit_contract_is_dimensionless_and_finite() -> None:
    """Output is declared dimensionless; no joule claim; always finite."""
    assert ENERGY_UNITS == "dimensionless"
    value = _cost(3.0)
    assert math.isfinite(value), f"operational_cost_energy must be finite, got {value}"
    # ENERGY_SCALE is the dimensionless normalization factor, not a joule scale.
    assert ENERGY_SCALE > 0.0
