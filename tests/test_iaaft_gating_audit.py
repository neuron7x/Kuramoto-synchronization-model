"""Tests for the IAAFT null positive-control gating audit.

The audit certifies whether the deployed `killtest._iaaft_pvalue` may be
promoted from an advisory report to a gating null. These tests lock its
operating-characteristic contract, the fail-closed eligibility reader, the
frozen canonical verdict, and the `run_killtest` wiring that consults it.

All configs are deterministic (seeded), so assertions are exact, not flaky.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from research.microstructure.iaaft_audit import (
    AUDIT_SCHEMA_VERSION,
    GatingAuditConfig,
    iaaft_is_gating_eligible,
    run_iaaft_gating_audit,
    verdict_to_json,
)
from research.microstructure.killtest import FeatureFrame, run_killtest

# Small but real config: every code path exercised, runs in a couple seconds.
_SMOKE = GatingAuditConfig(n_replications=12, n_rows=500, trials=40, iters=30)


def test_audit_verdict_is_wellformed() -> None:
    v = run_iaaft_gating_audit(_SMOKE)
    assert v.schema_version == AUDIT_SCHEMA_VERSION
    assert v.n_replications == _SMOKE.n_replications
    assert len(v.positive_pvalues) == _SMOKE.n_replications
    assert len(v.negative_pvalues) == _SMOKE.n_replications
    assert isinstance(v.reasons, list)
    for p in v.positive_pvalues + v.negative_pvalues:
        assert 0.0 < p <= 1.0, f"p-value out of (0,1]: {p}"
    assert 0.0 <= v.power <= 1.0
    assert 0.0 <= v.fpr <= 1.0


def test_audit_separates_edge_from_independence() -> None:
    """Operating-characteristic sanity: the null fires far more on a genuine
    edge than on independent data (power strictly exceeds FPR). This is the
    minimal property any usable null must have."""
    v = run_iaaft_gating_audit(_SMOKE)
    assert v.power > v.fpr, f"power={v.power} must exceed fpr={v.fpr}"
    assert v.power >= 0.8, f"null blind to a strong edge: power={v.power}"


def test_audit_is_deterministic() -> None:
    a = run_iaaft_gating_audit(_SMOKE)
    b = run_iaaft_gating_audit(_SMOKE)
    assert verdict_to_json(a) == verdict_to_json(b)


def test_audit_fails_closed_on_too_few_replications() -> None:
    cfg = GatingAuditConfig(n_replications=3, n_rows=400, trials=30, iters=20)
    v = run_iaaft_gating_audit(cfg)
    assert v.eligible is False
    assert any("n_replications" in r for r in v.reasons)


def test_eligibility_reader_is_fail_closed(tmp_path: Path) -> None:
    missing = tmp_path / "nope.json"
    assert iaaft_is_gating_eligible(missing) is False

    malformed = tmp_path / "bad.json"
    malformed.write_text("{not json")
    assert iaaft_is_gating_eligible(malformed) is False

    wrong_schema = tmp_path / "old.json"
    wrong_schema.write_text(json.dumps({"eligible": True, "schema_version": 0}))
    assert iaaft_is_gating_eligible(wrong_schema) is False

    ineligible = tmp_path / "ineligible.json"
    ineligible.write_text(
        json.dumps({"eligible": False, "schema_version": AUDIT_SCHEMA_VERSION})
    )
    assert iaaft_is_gating_eligible(ineligible) is False

    eligible = tmp_path / "eligible.json"
    eligible.write_text(
        json.dumps({"eligible": True, "schema_version": AUDIT_SCHEMA_VERSION})
    )
    assert iaaft_is_gating_eligible(eligible) is True


def test_frozen_canonical_artifact_is_ineligible() -> None:
    """The committed audit verdict locks the current finding: the IAAFT null is
    powered (power=1.0) but anti-conservative (FPR over ceiling) on the
    autocorrelated regime → must remain advisory. Guards against silent
    promotion via an edited artifact."""
    repo_root = Path(__file__).resolve().parents[1]
    artifact = repo_root / "results" / "L2_IAAFT_GATING_AUDIT.json"
    payload = json.loads(artifact.read_text())
    assert payload["schema_version"] == AUDIT_SCHEMA_VERSION
    assert payload["eligible"] is False
    assert payload["power"] == 1.0
    assert payload["fpr"] > payload["fpr_ceiling"]
    assert iaaft_is_gating_eligible(artifact) is False


def _noise_features(n_rows: int, n_sym: int, seed: int) -> FeatureFrame:
    rng = np.random.default_rng(seed)
    timestamps_ms = np.arange(n_rows, dtype=np.int64) * 1000
    mid = np.zeros((n_rows, n_sym), dtype=np.float64)
    for k in range(n_sym):
        mid[:, k] = 100.0 + (k + 1) + rng.normal(0.0, 0.03, size=n_rows).cumsum()
    return FeatureFrame(
        timestamps_ms=timestamps_ms,
        symbols=tuple(f"SYM{k}" for k in range(n_sym)),
        mid=mid,
        ofi=rng.normal(0.0, 1.0, size=(n_rows, n_sym)),
        queue_imbalance=rng.uniform(-1.0, 1.0, size=(n_rows, n_sym)),
    )


def test_killtest_iaaft_advisory_by_default() -> None:
    """Default resolution consults the committed (ineligible) artifact, so IAAFT
    never contributes a KILL reason and the verdict is unchanged from the
    pre-wiring behaviour."""
    features = _noise_features(1200, 5, seed=11)
    v = run_killtest(features)
    assert v.metadata["iaaft_gating"] is False
    assert not any("iaaft" in r for r in v.reasons)


def test_killtest_iaaft_gating_override_can_add_reason() -> None:
    """When gating is forced on (the post-certification path) and the IAAFT
    p-value exceeds the gate, an iaaft KILL reason appears — proving the wiring
    is live, not decorative."""
    features = _noise_features(1200, 5, seed=11)
    advisory = run_killtest(features, iaaft_gating=False)
    gated = run_killtest(features, iaaft_gating=True)
    assert gated.metadata["iaaft_gating"] is True
    iaaft_p = gated.null_test_pvalues["iaaft"]
    if iaaft_p > advisory.metadata["pvalue_gate"]:
        assert any("iaaft" in r for r in gated.reasons)
        assert not any("iaaft" in r for r in advisory.reasons)
