# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

from pathlib import Path

import pytest

from formal.proof_invariant import (
    HAS_Z3,
    apply_three_step_induction,
    build_three_step_induction,
    run_cache_coherence_proof,
    run_cache_liveness_proof,
    run_hlc_monotonicity_proof,
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


@pytest.mark.skipif(not HAS_Z3, reason="z3-solver dependency is not installed")
def test_cache_coherence_proof_holds(tmp_path: Path) -> None:
    target = tmp_path / "CACHE_COHERENCE_CERT.txt"
    result = run_cache_coherence_proof(target, steps=4, max_action_age_ms=250)

    assert result.cache_db_alignment_safe is True
    assert result.action_freshness_safe is True
    assert result.version_regress_safe is True
    content = target.read_text(encoding="utf-8")
    assert "Invariant I: UNSAT" in content
    assert "Invariant II: UNSAT" in content
    assert "Invariant III: UNSAT" in content


@pytest.mark.skipif(not HAS_Z3, reason="z3-solver dependency is not installed")
def test_cache_liveness_proof_holds(tmp_path: Path) -> None:
    target = tmp_path / "CACHE_LIVENESS_CERT.txt"
    result = run_cache_liveness_proof(target, steps=5)

    assert result.eventually_coherent is True
    content = target.read_text(encoding="utf-8")
    assert "Invariant IV: UNSAT" in content


@pytest.mark.skipif(not HAS_Z3, reason="z3-solver dependency is not installed")
def test_hlc_monotonicity_proof_holds(tmp_path: Path) -> None:
    target = tmp_path / "HLC_MONOTONICITY_CERT.txt"
    result = run_hlc_monotonicity_proof(target)

    assert result.monotonic is True
    content = target.read_text(encoding="utf-8")
    assert "Invariant V: UNSAT" in content
