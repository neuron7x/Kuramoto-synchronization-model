import math
from pathlib import Path

import pytest

z3 = pytest.importorskip("z3")  # noqa: F401
hypothesis = pytest.importorskip("hypothesis")  # noqa: F401
from hypothesis import given  # noqa: E402
from hypothesis import strategies as st  # noqa: E402

from formal.proof_invariant import (  # noqa: E402
    ProofConfig,
    recovery_mean,
    run_proof,
    tolerance_budget,
)

TOLERANCE_EPS = 1e-12


def test_proof_unsat_under_default_params(tmp_path: Path) -> None:
    cert_path = tmp_path / "cert.txt"
    result = run_proof(output_path=cert_path)

    assert result.is_safe
    assert "UNSAT" in result.certificate
    assert "UNSAT" in cert_path.read_text(encoding="utf-8")


def test_proof_turns_sat_when_recovery_guard_removed() -> None:
    cfg = ProofConfig(
        epsilon_cap=0.2,
        delta_growth=0.4,
        enforce_recovery=False,
    )
    result = run_proof(config=cfg)

    assert not result.is_safe
    assert "SAT" in result.certificate


@given(
    baseline=st.floats(min_value=0.0, max_value=10.0, allow_nan=False, allow_infinity=False),
    F_prev=st.floats(min_value=0.0, max_value=10.0, allow_nan=False, allow_infinity=False),
    eps=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
)
def test_tolerance_budget_is_clamped_and_monotone(baseline: float, F_prev: float, eps: float) -> None:
    cfg = ProofConfig()
    tol = tolerance_budget(baseline, F_prev, eps, cfg)
    assert tol >= cfg.tolerance_floor

    scaled = tolerance_budget(baseline * 2.0, F_prev * 2.0, eps, cfg)
    assert scaled + TOLERANCE_EPS >= tol


@given(
    baseline=st.floats(min_value=0.0, max_value=10.0, allow_nan=False, allow_infinity=False),
    F_new=st.floats(min_value=0.0, max_value=10.0, allow_nan=False, allow_infinity=False),
)
def test_recovery_mean_stays_within_bounds(baseline: float, F_new: float) -> None:
    cfg = ProofConfig()
    mean = recovery_mean(F_new, baseline, cfg)
    lo, hi = sorted((baseline, F_new))
    assert lo - 1e-9 <= mean <= hi + 1e-9
    assert math.isfinite(mean)
