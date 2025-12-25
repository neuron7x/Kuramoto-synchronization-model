from __future__ import annotations

from pathlib import Path

import pytest

from formal.proof_invariant import (
    HAS_Z3,
    apply_three_step_induction,
    build_three_step_induction,
    run_proof,
)


@pytest.mark.skipif(not HAS_Z3, reason="z3-solver dependency is not installed")
def test_proof_invariant_generates_certificate(tmp_path: Path) -> None:
    target = tmp_path / "INVARIANT_CERT.txt"
    result = run_proof(target)

    assert result.is_safe is True
    content = target.read_text(encoding="utf-8")
    assert "UNSAT" in content
    assert "delta_growth" in content


@pytest.mark.skipif(not HAS_Z3, reason="z3-solver dependency is not installed")
def test_induction_builder_encodes_three_step_guard() -> None:
    import z3

    system = build_three_step_induction()
    assert len(system.states) == 4
    assert len(system.epsilons) == 3

    apply_three_step_induction(system)
    assert system.solver.check() == z3.unsat
