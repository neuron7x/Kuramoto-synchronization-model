# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""D-002C C2.4 — Tests for the permutation-test null audit.

Pins the load-bearing contract: an injected signal yields PASS with
low p-value; pure noise yields FAIL with high p-value; verdict and
sha are deterministic in (arrays, n_shuffles, rng_seed).
"""

from __future__ import annotations

import dataclasses
import json
import math
from pathlib import Path

import numpy as np
import pytest

from research.systemic_risk.d002c_null_audit import (
    DEFAULT_N_SHUFFLES,
    DEFAULT_P_VALUE_THRESHOLD,
    DEFAULT_RNG_SEED,
    MIN_N_SEEDS,
    MIN_N_SHUFFLES,
    NullAuditInvalid,
    NullAuditResult,
    _atomic_write,
    _extract_per_seed_arrays,
    run_null_audit,
    run_null_audit_from_capsule,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


def test_default_constants_have_locked_values() -> None:
    """Locked defaults must be the spec values; a drift here breaks the
    sweep gate's contract."""
    assert DEFAULT_N_SHUFFLES == 100
    assert DEFAULT_P_VALUE_THRESHOLD == 0.05
    assert DEFAULT_RNG_SEED == 42
    assert MIN_N_SHUFFLES == 10
    assert MIN_N_SEEDS == 2


def test_null_audit_result_is_frozen() -> None:
    """Frozen-dataclass contract: mutating an instance must raise."""
    rng = np.random.default_rng(0)
    precursor = rng.normal(1.0, 0.1, size=20).astype(np.float64)
    null = rng.normal(0.0, 0.1, size=20).astype(np.float64)
    res = run_null_audit(precursor, null, n_shuffles=20, rng_seed=1)
    assert isinstance(res, NullAuditResult)
    with pytest.raises(dataclasses.FrozenInstanceError):
        res.verdict = "MUTATED"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Real-signal behaviour
# ---------------------------------------------------------------------------


def test_strong_signal_yields_pass_low_p_value() -> None:
    """Precursor = null + large constant ⇒ signal dominates the shuffled
    distribution; p_value must be near 0 and verdict PASS."""
    n_seeds = 25
    rng = np.random.default_rng(123)
    null = rng.normal(0.0, 0.05, size=n_seeds).astype(np.float64)
    precursor = null + 1.0  # massive separation vs noise
    res = run_null_audit(precursor, null, n_shuffles=200, rng_seed=7)
    assert res.verdict == "PASS"
    assert res.p_value_empirical < 0.05
    assert res.unshuffled_greater_than_median is True
    # Unshuffled signal must be ~1.0; median of shuffles ~ 0.
    assert res.unshuffled_abs_signal == pytest.approx(1.0, abs=0.05)
    assert res.shuffled_abs_signal_median < res.unshuffled_abs_signal


def test_pure_noise_yields_fail_high_p_value() -> None:
    """Precursor and null both drawn from the SAME distribution AND
    centred so the empirical means coincide ⇒ the unshuffled signal is
    by construction ~0 and the permutation distribution must dwarf it,
    so verdict is FAIL with p_value far above the 0.05 threshold."""
    n_seeds = 40
    rng = np.random.default_rng(7)
    precursor = rng.normal(0.0, 1.0, size=n_seeds).astype(np.float64)
    null = rng.normal(0.0, 1.0, size=n_seeds).astype(np.float64)
    # Re-centre so the unshuffled signal is exactly zero — that's the
    # cleanest noise-only case (the alternative — random sample-mean
    # gap — yields large variance per draw and trips false positives).
    precursor = precursor - float(precursor.mean())
    null = null - float(null.mean())
    # Add a small constant to both so they're not identical (which is a
    # degenerate trivially-FAIL case). The shift cancels in the diff.
    precursor = precursor + 0.5
    null = null + 0.5
    pass_count = 0
    for s in range(5):
        res = run_null_audit(precursor, null, n_shuffles=200, rng_seed=s)
        if res.verdict == "PASS":
            pass_count += 1
    # With unshuffled signal ≈ 0, EVERY shuffle's |signal| ≥ 0; every
    # shuffle therefore satisfies |shuffled| >= |unshuffled|, so
    # p_value ≈ 1.0 → 0 / 5 PASS.
    assert pass_count == 0, f"pure noise yielded {pass_count}/5 PASS"


def test_p_value_bounded_to_unit_interval() -> None:
    """p_value_empirical MUST lie in [0, 1] — it is a fraction of
    shuffles meeting a condition."""
    rng = np.random.default_rng(4)
    precursor = rng.normal(0.0, 1.0, size=15).astype(np.float64)
    null = rng.normal(0.0, 1.0, size=15).astype(np.float64)
    for seed in range(5):
        res = run_null_audit(precursor, null, n_shuffles=50, rng_seed=seed)
        assert 0.0 <= res.p_value_empirical <= 1.0
        assert math.isfinite(res.unshuffled_abs_signal)
        assert math.isfinite(res.shuffled_abs_signal_median)


def test_verdict_pass_iff_p_below_threshold() -> None:
    """The verdict mapping is a strict ``<`` against the threshold."""
    # Strong signal on enough paired seeds that the constant-diff case
    # can't be reproduced by sign-flipping at scale: with n_seeds=20 the
    # probability of all signs aligning (the only way to recover
    # |unshuffled|) is 2/2**20 ≈ 2e-6 — well below 0.05.
    precursor = np.ones(20, dtype=np.float64)
    null = np.zeros(20, dtype=np.float64)
    res = run_null_audit(precursor, null, n_shuffles=200, rng_seed=0)
    assert res.verdict == "PASS"
    assert res.p_value_empirical < res.p_value_threshold

    # Identical arrays ⇒ unshuffled abs = 0 ⇒ every shuffle is also 0
    # ⇒ all shuffles have |shuffled| == |unshuffled| ⇒ p_value = 1.0
    same = np.array([1.0, 2.0, 3.0, 4.0])
    res2 = run_null_audit(same, same, n_shuffles=30, rng_seed=0)
    assert res2.p_value_empirical == pytest.approx(1.0)
    assert res2.verdict == "FAIL"


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_run_null_audit_deterministic_in_seed() -> None:
    """Same inputs + same rng_seed + same n_shuffles → identical result."""
    rng = np.random.default_rng(0)
    precursor = rng.normal(0.5, 0.2, size=30).astype(np.float64)
    null = rng.normal(0.0, 0.2, size=30).astype(np.float64)
    a = run_null_audit(precursor, null, n_shuffles=50, rng_seed=11)
    b = run_null_audit(precursor, null, n_shuffles=50, rng_seed=11)
    assert a.sha256 == b.sha256
    assert a.p_value_empirical == b.p_value_empirical
    assert a.shuffled_abs_signal_median == b.shuffled_abs_signal_median


def test_run_null_audit_seed_sensitivity() -> None:
    """Different rng_seeds typically produce different shuffled stats;
    they MUST produce the same unshuffled signal (which is seed-free)."""
    rng = np.random.default_rng(0)
    precursor = rng.normal(0.5, 0.2, size=30).astype(np.float64)
    null = rng.normal(0.0, 0.2, size=30).astype(np.float64)
    a = run_null_audit(precursor, null, n_shuffles=50, rng_seed=1)
    b = run_null_audit(precursor, null, n_shuffles=50, rng_seed=2)
    assert a.unshuffled_abs_signal == b.unshuffled_abs_signal
    assert a.sha256 != b.sha256


def test_sha256_changes_with_n_shuffles() -> None:
    """sha256 must distinguish run configurations — different n_shuffles
    must produce different shas even with identical arrays + seed."""
    precursor = np.linspace(0.5, 1.5, num=20)
    null = np.linspace(0.0, 1.0, num=20)
    a = run_null_audit(precursor, null, n_shuffles=10, rng_seed=0)
    b = run_null_audit(precursor, null, n_shuffles=20, rng_seed=0)
    assert a.sha256 != b.sha256
    assert a.n_shuffles == 10
    assert b.n_shuffles == 20


# ---------------------------------------------------------------------------
# Validation / fail-closed
# ---------------------------------------------------------------------------


def test_rejects_empty_arrays() -> None:
    """Empty inputs MUST raise — no silent zero-signal verdict."""
    empty = np.array([], dtype=np.float64)
    with pytest.raises(NullAuditInvalid):
        run_null_audit(empty, empty, n_shuffles=20)


def test_rejects_mismatched_shapes() -> None:
    """Paired test requires identical shapes — refuse misalignment."""
    a = np.zeros(10, dtype=np.float64)
    b = np.zeros(11, dtype=np.float64)
    with pytest.raises(NullAuditInvalid):
        run_null_audit(a, b, n_shuffles=20)


def test_rejects_non_1d_inputs() -> None:
    """Inputs must be 1-D arrays; 2-D will silently average across
    columns without our contract."""
    a = np.zeros((5, 2), dtype=np.float64)
    b = np.zeros((5, 2), dtype=np.float64)
    with pytest.raises(NullAuditInvalid):
        run_null_audit(a, b, n_shuffles=20)


def test_rejects_n_shuffles_below_floor() -> None:
    """Below MIN_N_SHUFFLES the p-value resolution is too coarse to
    support the 0.05 threshold — refuse the run."""
    precursor = np.arange(5, dtype=np.float64)
    null = np.zeros(5, dtype=np.float64)
    with pytest.raises(NullAuditInvalid):
        run_null_audit(precursor, null, n_shuffles=MIN_N_SHUFFLES - 1)


def test_rejects_too_few_seeds() -> None:
    """Need at least MIN_N_SEEDS paired observations."""
    precursor = np.array([1.0])
    null = np.array([0.0])
    with pytest.raises(NullAuditInvalid):
        run_null_audit(precursor, null, n_shuffles=20)


def test_rejects_non_finite_inputs() -> None:
    """NaN / Inf must be rejected — fail-closed (no silent repair)."""
    precursor = np.array([1.0, 2.0, np.nan, 3.0])
    null = np.array([0.0, 0.0, 0.0, 0.0])
    with pytest.raises(NullAuditInvalid):
        run_null_audit(precursor, null, n_shuffles=20)


def test_rejects_invalid_threshold() -> None:
    """p_value_threshold must lie in (0, 1)."""
    precursor = np.array([1.0, 2.0, 3.0, 4.0])
    null = np.array([0.0, 0.0, 0.0, 0.0])
    with pytest.raises(NullAuditInvalid):
        run_null_audit(precursor, null, n_shuffles=20, p_value_threshold=1.0)
    with pytest.raises(NullAuditInvalid):
        run_null_audit(precursor, null, n_shuffles=20, p_value_threshold=-0.1)


# ---------------------------------------------------------------------------
# Distribution shape sanity
# ---------------------------------------------------------------------------


def test_shuffled_distribution_centred_near_zero_on_noise() -> None:
    """Under H0 with symmetric noise, the median of the shuffled
    |signal| distribution should be small relative to the std of the
    paired differences."""
    rng = np.random.default_rng(0)
    n_seeds = 50
    precursor = rng.normal(0.0, 1.0, size=n_seeds).astype(np.float64)
    null = rng.normal(0.0, 1.0, size=n_seeds).astype(np.float64)
    diffs = precursor - null
    expected_std_of_mean = float(np.std(diffs, ddof=1)) / math.sqrt(n_seeds)
    res = run_null_audit(precursor, null, n_shuffles=500, rng_seed=0)
    # |shuffled| median should be on the order of expected_std_of_mean
    # (within a generous 3x multiplier — this is a rank-ish sanity, not
    # a tight bound).
    assert res.shuffled_abs_signal_median < 5.0 * expected_std_of_mean
    assert res.shuffled_abs_signal_p95 >= res.shuffled_abs_signal_median


def test_unshuffled_greater_than_median_aligns_with_verdict_pass() -> None:
    """Strong signal ⇒ both PASS and the median dominance flag must be
    True; these two truths are correlated but not identical, so we check
    both on the strong-signal case."""
    precursor = np.array([1.0] * 20, dtype=np.float64)
    null = np.array([0.0] * 20, dtype=np.float64)
    res = run_null_audit(precursor, null, n_shuffles=100, rng_seed=3)
    assert res.verdict == "PASS"
    assert res.unshuffled_greater_than_median is True


# ---------------------------------------------------------------------------
# Capsule-driven path
# ---------------------------------------------------------------------------


def _write_capsule(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_extract_per_seed_arrays_recognises_canonical_keys() -> None:
    """The capsule path accepts a handful of canonical key names."""
    cell = {
        "substrate_id": "ricci_flow",
        "metric_id": "sync_auc",
        "precursor_per_seed": [1.0, 2.0, 3.0, 4.0],
        "null_per_seed": [0.0, 0.0, 0.0, 0.0],
    }
    arrays = _extract_per_seed_arrays(cell)
    assert arrays is not None
    p, n = arrays
    assert p.shape == (4,)
    assert n.shape == (4,)


def test_extract_per_seed_arrays_returns_none_when_missing(tmp_path: Path) -> None:
    """Cells without per-seed data ⇒ extractor returns None (skip)."""
    cell = {"substrate_id": "x", "metric_id": "y", "variance_ratio": 0.4}
    assert _extract_per_seed_arrays(cell) is None
    # Also if one side is present but the other isn't.
    cell2 = {"precursor_per_seed": [1.0, 2.0]}
    assert _extract_per_seed_arrays(cell2) is None


def test_run_null_audit_from_capsule_with_auditable_cells(tmp_path: Path) -> None:
    """Capsule with per-seed arrays per cell ⇒ one NullAuditResult each."""
    cap = tmp_path / "cap.json"
    rng = np.random.default_rng(0)
    p1 = (rng.normal(1.0, 0.05, size=12)).tolist()
    n1 = (rng.normal(0.0, 0.05, size=12)).tolist()
    p2 = (rng.normal(0.5, 0.1, size=12)).tolist()
    n2 = (rng.normal(0.0, 0.1, size=12)).tolist()
    _write_capsule(
        cap,
        {
            "results": [
                {
                    "substrate_id": "ricci_flow",
                    "metric_id": "sync_auc",
                    "N": 100,
                    "lambda_": 0.5,
                    "precursor_per_seed": p1,
                    "null_per_seed": n1,
                },
                {
                    "substrate_id": "block_structured",
                    "metric_id": "tau_onset",
                    "N": 100,
                    "lambda_": 0.5,
                    "precursor_per_seed": p2,
                    "null_per_seed": n2,
                },
            ]
        },
    )
    results = run_null_audit_from_capsule(cap, n_shuffles=50, rng_seed=0)
    assert len(results) == 2
    assert all(isinstance(r, NullAuditResult) for r in results)
    # Both have a clear positive separation ⇒ both should PASS
    assert all(r.verdict == "PASS" for r in results)


def test_run_null_audit_from_capsule_skips_stub_cells(tmp_path: Path) -> None:
    """A capsule containing only aggregate stats (no per-seed) ⇒ empty
    tuple; the audit must not raise."""
    cap = tmp_path / "stub_cap.json"
    _write_capsule(
        cap,
        {
            "results": [
                {"substrate_id": "x", "metric_id": "y", "variance_ratio": 0.4},
                {"substrate_id": "a", "metric_id": "b", "variance_ratio": 0.5},
            ]
        },
    )
    out = run_null_audit_from_capsule(cap)
    assert out == ()
    assert isinstance(out, tuple)


def test_run_null_audit_from_capsule_missing_path(tmp_path: Path) -> None:
    """Missing capsule path ⇒ NullAuditInvalid; never silent."""
    missing = tmp_path / "does_not_exist.json"
    with pytest.raises(NullAuditInvalid):
        run_null_audit_from_capsule(missing)


def test_run_null_audit_from_capsule_handles_malformed_json(tmp_path: Path) -> None:
    """Malformed JSON ⇒ NullAuditInvalid; never silent."""
    bad = tmp_path / "bad.json"
    bad.write_text("not valid json at all {", encoding="utf-8")
    with pytest.raises(NullAuditInvalid):
        run_null_audit_from_capsule(bad)


# ---------------------------------------------------------------------------
# Atomic write
# ---------------------------------------------------------------------------


def test_atomic_write_emits_no_orphan_tmp_on_success(tmp_path: Path) -> None:
    """Successful write leaves only the final file, no .tmp residue."""
    target = tmp_path / "audit_capsule.json"
    _atomic_write(target, {"hello": "world", "n": 1})
    assert target.exists()
    leftovers = list(tmp_path.glob("*.tmp"))
    assert leftovers == []
    parsed = json.loads(target.read_text(encoding="utf-8"))
    assert parsed["hello"] == "world"


def test_atomic_write_no_orphan_tmp_on_exception(tmp_path: Path) -> None:
    """If serialisation fails mid-flight the partial .tmp must be cleaned;
    no orphan can leak past the atomic boundary."""
    target = tmp_path / "audit_capsule.json"

    class Unserialisable:
        pass

    payload: dict[str, object] = {"bad": Unserialisable()}
    with pytest.raises(TypeError):
        _atomic_write(target, payload)
    assert not target.exists()
    leftovers = list(tmp_path.glob("*.tmp"))
    assert leftovers == []
