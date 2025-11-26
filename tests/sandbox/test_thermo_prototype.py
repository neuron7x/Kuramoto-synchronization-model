from __future__ import annotations

import math

from sandbox.control.thermo_prototype import PrototypeResult, run_prototype


def test_run_prototype_reduces_free_energy() -> None:
    result = run_prototype(seed=42)

    assert isinstance(result, PrototypeResult)
    assert result.initial_free_energy > result.optimised_free_energy
    assert (
        result.delta_free_energy
        == result.optimised_free_energy - result.initial_free_energy
    )
    assert math.isclose(
        result.derivative,
        result.delta_free_energy / 1e-3,
    )
    assert result.energy_trace == [
        result.initial_free_energy,
        result.optimised_free_energy,
    ]
    assert result.stable is True

    payload = result.as_dict()
    assert payload["initial_free_energy"] == result.initial_free_energy
    assert payload["energy_trace"] == result.energy_trace


def test_run_prototype_is_seed_deterministic() -> None:
    first = run_prototype(seed=7)
    second = run_prototype(seed=7)
    third = run_prototype(seed=8)

    assert first == second
    assert first != third
