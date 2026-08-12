# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""D-002C C2.6 — Writer sha alignment with the preflight validator.

Bug
===
The C2.4-A/B/C writers (pos_control, neg_control, smoke_test) hashed a
small surrogate dict (3-7 fields) and then wrote a FULL capsule (~16
fields) carrying that mismatched sha. The C2.4-D preflight validator
recomputes sha over the full capsule minus the ``sha256`` field via
:func:`canonical_preflight_json` — so the recomputed sha never matched
and launch was refused with ``capsule_sha256_mismatch`` on every
freshly-written capsule.

Contract
========
Writer emits capsule body B; writes ``capsule = B ∪ {"sha256": sha}``
to disk where ``sha = sha256(canonical_preflight_json(B))``.  Reader
recomputes ``sha256(canonical_preflight_json(capsule - {"sha256"}))``
and refuses launch on mismatch.  The two computations MUST agree by
construction, for every input the writers accept — including
non-finite per-cell fields (``signal_ci_ratio == inf`` in
degenerate-variance branches), which the validator's
``_sanitize`` collapses to a stable string sentinel.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, cast

import pytest

from research.systemic_risk.d002c_metrics import ALL_METRICS, AucPreEventMetric, Metric
from research.systemic_risk.d002c_neg_control import run_neg_control_all
from research.systemic_risk.d002c_pos_control import run_pos_control_all
from research.systemic_risk.d002c_preflight import (
    NULL_AUDIT_KIND,
    PreflightCapsulePaths,
    canonical_preflight_json,
    load_and_validate_preflight_capsules,
)
from research.systemic_risk.d002c_smoke_test import run_smoke_test
from research.systemic_risk.d002c_substrates import (
    ALL_SUBSTRATES,
    BlockStructuredSubstrate,
    Substrate,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_json_dict(path: Path) -> dict[str, Any]:
    """Read a JSON object from disk; cast for mypy --strict.

    The on-disk capsule format tolerates ``NaN`` / ``Infinity`` literals
    (python-flavour JSON, not RFC 8259) because :func:`json.loads` accepts
    them by default. The validator's :func:`canonical_preflight_json`
    canonicalises those into stable string sentinels before hashing.
    """
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def _recompute_sha(capsule: dict[str, Any]) -> str:
    body = {k: v for k, v in capsule.items() if k != "sha256"}
    return hashlib.sha256(canonical_preflight_json(body).encode("utf-8")).hexdigest()


def _emit_pos(path: Path) -> dict[str, Any]:
    """Emit a tiny POS capsule via the actual writer; return parsed JSON."""
    run_pos_control_all(
        (BlockStructuredSubstrate(),),
        (AucPreEventMetric(),),
        N=20,
        lambda_=1.0,
        n_seeds=4,
        threshold=0.01,
        steps_per_quarter=3,
        output_path=path,
    )
    return _load_json_dict(path)


def _emit_neg(path: Path) -> dict[str, Any]:
    """Emit a tiny NEG capsule via the actual writer (uses a single N
    inside the locked DEFAULT_NEG_N_GRID so the preflight accepts it
    without ``capsule_unknown_N``)."""
    run_neg_control_all(
        (BlockStructuredSubstrate(),),
        (AucPreEventMetric(),),
        N_grid=(50,),
        n_seeds=4,
        steps_per_quarter=3,
        output_path=path,
    )
    return _load_json_dict(path)


def _emit_smoke(path: Path) -> dict[str, Any]:
    run_smoke_test(
        substrates=(BlockStructuredSubstrate(),),
        metrics=(AucPreEventMetric(),),
        N_grid=(20,),
        lambda_grid=(0.0,),
        n_seeds=2,
        steps_per_quarter=3,
        max_wallclock_seconds=120.0,
        output_path=path,
    )
    return _load_json_dict(path)


def _write_null_audit_stub(path: Path) -> dict[str, Any]:
    """Write an aggregate-only null-audit stub via the same canonical form
    the validator uses. The stub carries ``aggregate_only=True`` so the
    validator does not require per-cell results — it only checks the
    capsule sha + kind + generated_at."""
    body: dict[str, Any] = {
        "kind": NULL_AUDIT_KIND,
        "aggregate_only": True,
        "results": [],
        "generated_at": "2026-05-11T12:00:00Z",
    }
    sha = hashlib.sha256(canonical_preflight_json(body).encode("utf-8")).hexdigest()
    capsule = {**body, "sha256": sha}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(capsule, sort_keys=True, indent=2), encoding="utf-8")
    return capsule


# ---------------------------------------------------------------------------
# Per-writer round-trip
# ---------------------------------------------------------------------------


def test_pos_control_capsule_sha_matches_preflight_recompute(tmp_path: Path) -> None:
    """Round-trip: emit POS capsule, then have preflight validator recompute
    its sha. They MUST match (otherwise the launch script refuses)."""
    capsule = _emit_pos(tmp_path / "pos.json")
    assert "sha256" in capsule
    recomputed = _recompute_sha(capsule)
    assert capsule["sha256"] == recomputed
    # The fix is honest only if the capsule has the FULL load-bearing
    # field set, not the buggy 3-field surrogate dict.
    assert len(capsule) > 5


def test_neg_control_capsule_sha_matches_preflight_recompute(tmp_path: Path) -> None:
    """Same contract for NEG."""
    capsule = _emit_neg(tmp_path / "neg.json")
    assert "sha256" in capsule
    recomputed = _recompute_sha(capsule)
    assert capsule["sha256"] == recomputed
    assert len(capsule) > 5


def test_smoke_test_capsule_sha_matches_preflight_recompute(tmp_path: Path) -> None:
    """Same contract for SMOKE."""
    capsule = _emit_smoke(tmp_path / "smoke.json")
    assert "sha256" in capsule
    recomputed = _recompute_sha(capsule)
    assert capsule["sha256"] == recomputed
    assert len(capsule) > 5


# ---------------------------------------------------------------------------
# End-to-end: load via the preflight validator
# ---------------------------------------------------------------------------


def test_pos_control_capsule_loads_via_preflight_validator(tmp_path: Path) -> None:
    """End-to-end: emit POS+NEG+NULL+SMOKE capsules, run
    load_and_validate_preflight_capsules — verify launch_allowed=True
    (no sha mismatch refusal). This is THE falsifier for the writer-sha
    alignment fix."""
    pos_path = tmp_path / "pos.json"
    neg_path = tmp_path / "neg.json"
    null_path = tmp_path / "null.json"
    smoke_path = tmp_path / "smoke.json"

    _emit_pos(pos_path)
    _emit_neg(neg_path)
    _emit_smoke(smoke_path)
    _write_null_audit_stub(null_path)

    decision = load_and_validate_preflight_capsules(
        PreflightCapsulePaths(
            pos_control=pos_path,
            neg_control=neg_path,
            null_audit=null_path,
            smoke_test=smoke_path,
        )
    )
    # The contract under test: no capsule_sha256_mismatch in refusal_reasons.
    sha_mismatches = [r for r in decision.refusal_reasons if "capsule_sha256_mismatch" in r]
    assert sha_mismatches == [], (
        f"Writer-sha alignment regression: {len(sha_mismatches)} sha mismatches; "
        f"first={sha_mismatches[0]!r}"
    )
    # And the bigger contract: launch is allowed (no other refusal either,
    # since the four capsules are well-formed at small N).
    assert decision.launch_allowed, f"refusal_reasons={list(decision.refusal_reasons)}"


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_writer_sha_deterministic_across_calls(tmp_path: Path) -> None:
    """Same inputs → same per-cell sha (per-cell payloads are wallclock-free
    and so deterministic). The aggregate capsule sha drifts across runs
    because the body carries ``wallclock_seconds``; we therefore assert
    determinism at the per-cell level and round-trip correctness at the
    capsule level."""
    a = _emit_pos(tmp_path / "a.json")
    b = _emit_pos(tmp_path / "b.json")
    assert a["results"][0]["sha256"] == b["results"][0]["sha256"]
    # And each on-disk capsule must round-trip cleanly.
    assert a["sha256"] == _recompute_sha(a)
    assert b["sha256"] == _recompute_sha(b)


# ---------------------------------------------------------------------------
# Non-finite forward-safety
# ---------------------------------------------------------------------------


def test_capsule_with_non_finite_field_has_consistent_sha(tmp_path: Path) -> None:
    """If a per-cell result carries ``inf`` (saturated metric), the writer's
    sha MUST still match the validator's recompute. canonical_preflight_json
    handles this via sentinel substitution.

    We trigger the path by surgically injecting ``inf`` into a real
    per-cell result, then re-sha via the writer-equivalent canonical
    form and verify the validator's recompute agrees. The point of this
    test is to lock the sentinel substitution path on BOTH sides of the
    round-trip — if either side stopped using
    :func:`canonical_preflight_json` the recomputed sha would diverge.
    """
    cap = tmp_path / "pos_inf.json"
    capsule = _emit_pos(cap)
    capsule["results"][0]["signal_ci_ratio"] = float("inf")
    body = {k: v for k, v in capsule.items() if k != "sha256"}
    new_sha = hashlib.sha256(canonical_preflight_json(body).encode("utf-8")).hexdigest()
    capsule["sha256"] = new_sha
    # Writer-equivalent disk format: tolerate NaN/Infinity literals.
    cap.write_text(json.dumps(capsule, sort_keys=True, indent=2), encoding="utf-8")

    reread = _load_json_dict(cap)
    recomputed = _recompute_sha(reread)
    assert reread["sha256"] == recomputed
    # Verify the inf actually went through the sentinel substitution.
    canon = canonical_preflight_json({k: v for k, v in reread.items() if k != "sha256"})
    assert '"Infinity"' in canon


# ---------------------------------------------------------------------------
# Regression: refute the OLD (buggy) sha formula
# ---------------------------------------------------------------------------


def test_writer_does_not_emit_old_buggy_aggregate_sha(tmp_path: Path) -> None:
    """The OLD writer hashed a small dict like
    {n_pass, n_exclude, excluded_combos} and stored that sha as the
    capsule's sha. This test verifies the writer no longer does that
    — i.e. the surrogate-aggregate sha is NEVER equal to the emitted
    capsule sha for any non-trivial capsule.

    Falsifier: if someone reverts the fix to hash a smaller aggregate
    dict, this test fails."""
    capsule = _emit_pos(tmp_path / "pos.json")
    old_aggregate: dict[str, Any] = {
        "per_cell_shas": [r["sha256"] for r in capsule["results"]],
        "n_pass": capsule["n_pass"],
        "n_exclude": capsule["n_exclude"],
        "threshold": capsule["threshold"],
        "all_pass": capsule["all_pass"],
        "excluded_combos": capsule["excluded_combos"],
    }
    old_sha = hashlib.sha256(
        json.dumps(old_aggregate, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    assert capsule["sha256"] != old_sha, (
        "writer regressed to the buggy small-aggregate sha formula; "
        "preflight will refuse launch with capsule_sha256_mismatch"
    )
    # Sanity: the NEW sha must equal the validator's recompute.
    assert capsule["sha256"] == _recompute_sha(capsule)


# ---------------------------------------------------------------------------
# Canonical-form parity (writer vs validator)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "substrate, metric",
    [(ALL_SUBSTRATES[0], ALL_METRICS[0])],
)
def test_full_capsule_canonical_form_is_validator_canonical_form(
    tmp_path: Path,
    substrate: Substrate,
    metric: Metric,
) -> None:
    """The writer and the validator MUST share one canonical form.
    Anything that bypasses :func:`canonical_preflight_json` (e.g. a
    raw ``json.dumps(sort_keys=True)``) would silently drift. This test
    locks the contract by forcing the recompute through the validator's
    own function and comparing to the on-disk sha."""
    cap = tmp_path / "pos.json"
    run_pos_control_all(
        (substrate,),
        (metric,),
        N=20,
        lambda_=1.0,
        n_seeds=4,
        threshold=0.01,
        steps_per_quarter=3,
        output_path=cap,
    )
    data = _load_json_dict(cap)
    body = {k: v for k, v in data.items() if k != "sha256"}
    via_validator = hashlib.sha256(canonical_preflight_json(body).encode("utf-8")).hexdigest()
    assert data["sha256"] == via_validator
    assert isinstance(data["sha256"], str)
