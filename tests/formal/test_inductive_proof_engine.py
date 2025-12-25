"""Tests for the generic inductive proof engine."""

from __future__ import annotations

import pytest

from formal.inductive import HAS_Z3, InductiveProofEngine


@pytest.mark.skipif(not HAS_Z3, reason="z3-solver dependency is not installed")
def test_inductive_engine_proves_monotonicity() -> None:
    """Ensure the engine proves a simple monotonic property."""

    engine = InductiveProofEngine(timeout_ms=10000)

    def base(z3):
        x0 = z3.Int("x0")
        return [x0 == 0, x0 < 0]

    def step(z3):
        xk = z3.Int("xk")
        xk1 = z3.Int("xk1")
        transition = xk1 == xk + 1
        safe_k = xk >= 0
        violation = xk1 < 0
        return [safe_k, transition, violation]

    result = engine.prove(base, step)

    assert result.proved is True
    assert result.base_case_unsat is True
    assert result.inductive_step_unsat is True
    assert "Inductive step" in result.certificate
