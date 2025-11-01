from __future__ import annotations

from pathlib import Path

import pytest

from formal.proof_invariant import HAS_Z3, run_proof


@pytest.mark.skipif(not HAS_Z3, reason="z3-solver dependency is not installed")
def test_proof_invariant_generates_certificate(tmp_path: Path) -> None:
    target = tmp_path / "INVARIANT_CERT.txt"
    result = run_proof(target)

    assert result.is_safe is True
    content = target.read_text(encoding="utf-8")
    assert "UNSAT" in content
    assert "delta_growth" in content
