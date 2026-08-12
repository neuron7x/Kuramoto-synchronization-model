# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""D-002K-P3 high-SNR event-transition metric guard suite.

D-002K-P3 pre-registers the metric LAYER only: the K-P0-locked primary
confirmatory endpoint ``pre_post_standardized_mean_shift`` gets its full
executable contract, and the six K-P0-listed secondary metrics are
locked ``exploratory_only``. Definitions only -- no scoring on real
data, no ingestion, no model fit, no canonical run, no numeric decision
threshold (power-gate territory).

This module fails closed if any future PR:

* swaps the primary endpoint or adds a second confirmatory metric,
* marks any secondary metric confirmatory or promotes it to primary,
* sets a numeric decision threshold here (power-gate only),
* scores on / ingests real data,
* breaks the primary metric's determinism or fail-closed contract,
* mutates a frozen D-002J / K-P0 / K-P1 / K-P2 artifact,
* promotes D-002K into a D-002J rescue or a systemic-risk / bank claim.

D-002J stays terminally REFUSED at P7.

All multi-line asserts use the msg-var idiom (``_amsg = ...`` extracted
above the ``assert``) so the module renders byte-identically under both
black 26.3.1 and ruff-format 0.14.0.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from research.systemic_risk.d002k_event_metrics import (
    K_P1_OBSERVABLE_FAMILIES,
    PRIMARY_METRIC_ID,
    SECONDARY_METRIC_IDS,
    area_under_stress_curve,
    crisis_vs_placebo_contrast,
    max_zscore,
    persistence_above_threshold,
    pre_post_standardized_mean_shift,
    recovery_half_life,
    slope_into_crisis,
    volatility_ratio,
)

# ---------------------------------------------------------------------------
# Anchors / constants
# ---------------------------------------------------------------------------

REPO_ROOT: Path = Path(__file__).resolve().parents[2]
CONTRACT_PATH: Path = REPO_ROOT / "artifacts/d002k/metrics/event_metric_contract_v1.json"
SUMMARY_PATH: Path = REPO_ROOT / "artifacts/d002k/metrics/event_metric_summary_v1.json"
VERDICT_PATH: Path = REPO_ROOT / "artifacts/governance/verdicts/d002k_p3_verdict_v1.json"

#: K-P0-locked primary endpoint id (immutable; no swap).
K_P0_PRIMARY_LOCK: str = "pre_post_standardized_mean_shift"

#: Frozen byte-exact parent sha256 anchors (K-P0 / K-P1 / K-P2 / prereg).
FROZEN_SHAS: dict[str, str] = {
    "docs/governance/D002K_PREREGISTRATION.yaml": (
        "2cd923810bf64547cd86ecb403bfd3f12a799cb16c3d10ebc07bc05865fee43f"  # pragma: allowlist secret
    ),
    "artifacts/d002k/prereg/d002k_primary_metric_contract_v1.json": (
        "7effc088810ba5933850618312fcad369fdac0386b4a3cab6f14455feeb5a569"  # pragma: allowlist secret
    ),
    "artifacts/d002k/observables/source_observable_contract_v1.json": (
        "952739cbfe4aa16a54eb5684be4bbd653e820eaf92113418e379a3bf8a2a71c3"  # pragma: allowlist secret
    ),
    "artifacts/d002k/placebo/matched_placebo_registry_v1.json": (
        "435d41df868859f25811236fa4675d01f202682c693d06208922c263ace09413"  # pragma: allowlist secret
    ),
}

_MARKER: re.Pattern[str] = re.compile(r"^(<<<<<<<|=======|>>>>>>>|\|\|\|\|\|\|\|)")


def _load(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as fh:
        obj = json.load(fh)
    assert isinstance(obj, dict), f"{path} must be a JSON object"
    return obj


def _sha256(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


# Tiny deterministic synthetic event series (definitional correctness
# only -- NOT real / ingested data). pre = low-variance baseline (non-
# constant so sigma_pre > 0), post = a level shift, so the metrics have
# known sign.
_SYNTH: list[float] = [1.0, 1.1, 0.9, 1.05, 0.95, 4.0, 5.0, 6.0, 5.0, 4.0]
_ONSET = 5
_PRE = 5
_POST = 5


# ---------------------------------------------------------------------------
# 1-2. Artifacts exist
# ---------------------------------------------------------------------------


def test_metric_contract_exists() -> None:
    assert CONTRACT_PATH.is_file(), f"missing contract {CONTRACT_PATH}"
    c = _load(CONTRACT_PATH)
    assert "metrics" in c and isinstance(c["metrics"], list), "contract.metrics list required"


def test_metric_summary_exists() -> None:
    assert SUMMARY_PATH.is_file(), f"missing summary {SUMMARY_PATH}"
    s = _load(SUMMARY_PATH)
    assert "counts" in s, "summary.counts required"


# ---------------------------------------------------------------------------
# 3. Schema version
# ---------------------------------------------------------------------------


def test_contract_schema_version() -> None:
    c = _load(CONTRACT_PATH)
    _a = f"contract schema must be D002K-EVENT-METRIC-CONTRACT-v1; got {c.get('schema_version')!r}"
    assert c["schema_version"] == "D002K-EVENT-METRIC-CONTRACT-v1", _a
    s = _load(SUMMARY_PATH)
    _b = f"summary schema must be D002K-EVENT-METRIC-SUMMARY-v1; got {s.get('schema_version')!r}"
    assert s["schema_version"] == "D002K-EVENT-METRIC-SUMMARY-v1", _b


# ---------------------------------------------------------------------------
# 4. Parent SHAs pinned (K-P3 -> K-P0 / K-P1 / K-P2 coupling)
# ---------------------------------------------------------------------------


def test_parent_shas_pinned() -> None:
    c = _load(CONTRACT_PATH)
    k_p0 = FROZEN_SHAS["artifacts/d002k/prereg/d002k_primary_metric_contract_v1.json"]
    k_p1 = FROZEN_SHAS["artifacts/d002k/observables/source_observable_contract_v1.json"]
    k_p2 = FROZEN_SHAS["artifacts/d002k/placebo/matched_placebo_registry_v1.json"]
    k_pre = FROZEN_SHAS["docs/governance/D002K_PREREGISTRATION.yaml"]
    _a = "contract must pin parent_primary_metric_contract_sha256 (K-P0)"
    assert c["parent_primary_metric_contract_sha256"] == k_p0, _a
    _b = "contract must pin parent_observable_contract_sha256 (K-P1)"
    assert c["parent_observable_contract_sha256"] == k_p1, _b
    _c2 = "contract must pin parent_placebo_registry_sha256 (K-P2)"
    assert c["parent_placebo_registry_sha256"] == k_p2, _c2
    _d = "contract must pin parent_prereg_sha256 (D-002K prereg)"
    assert c["parent_prereg_sha256"] == k_pre, _d


# ---------------------------------------------------------------------------
# 5. Exactly one primary confirmatory metric
# ---------------------------------------------------------------------------


def test_exactly_one_primary_confirmatory_metric() -> None:
    c = _load(CONTRACT_PATH)
    primary = [m for m in c["metrics"] if m["role"] == "primary_confirmatory"]
    _a = f"exactly 1 primary_confirmatory metric required; got {len(primary)}"
    assert len(primary) == 1, _a
    confirmatory = [m for m in c["metrics"] if m["confirmatory"] is True]
    _b = f"exactly 1 confirmatory:true metric required; got {len(confirmatory)}"
    assert len(confirmatory) == 1, _b
    assert c.get("n_primary_confirmatory") == 1, "summary n_primary_confirmatory must be 1"


# ---------------------------------------------------------------------------
# 6. Primary metric is the K-P0 lock
# ---------------------------------------------------------------------------


def test_primary_metric_is_pre_post_standardized_mean_shift() -> None:
    c = _load(CONTRACT_PATH)
    primary = next(m for m in c["metrics"] if m["role"] == "primary_confirmatory")
    _a = f"primary metric_id must == K-P0 lock {K_P0_PRIMARY_LOCK!r}; got {primary['metric_id']!r}"
    assert primary["metric_id"] == K_P0_PRIMARY_LOCK, _a
    assert c["primary_metric"] == K_P0_PRIMARY_LOCK, "contract.primary_metric must == K-P0 lock"
    assert PRIMARY_METRIC_ID == K_P0_PRIMARY_LOCK, "module PRIMARY_METRIC_ID must == K-P0 lock"


# ---------------------------------------------------------------------------
# 7. No secondary marked confirmatory
# ---------------------------------------------------------------------------


def test_no_secondary_marked_confirmatory() -> None:
    c = _load(CONTRACT_PATH)
    secondary = [m for m in c["metrics"] if m["role"] == "secondary_exploratory"]
    assert len(secondary) >= 6, f"need >= 6 secondary metrics; got {len(secondary)}"
    for m in secondary:
        _a = f"secondary metric {m['metric_id']!r} must be confirmatory:false"
        assert m["confirmatory"] is False, _a


# ---------------------------------------------------------------------------
# 8. >= 6 secondary exploratory metrics
# ---------------------------------------------------------------------------


def test_min_six_secondary_exploratory_metrics() -> None:
    c = _load(CONTRACT_PATH)
    sec_ids = {m["metric_id"] for m in c["metrics"] if m["role"] == "secondary_exploratory"}
    _a = f"need >= 6 secondary_exploratory metrics; got {len(sec_ids)}"
    assert len(sec_ids) >= 6, _a
    _b = f"secondary ids must match K-P0 list {set(SECONDARY_METRIC_IDS)!r}; got {sec_ids!r}"
    assert sec_ids == set(SECONDARY_METRIC_IDS), _b


# ---------------------------------------------------------------------------
# 9. Every metric maps to a K-P1 observable family
# ---------------------------------------------------------------------------


def test_every_metric_maps_to_k_p1_observable_family() -> None:
    c = _load(CONTRACT_PATH)
    valid = set(K_P1_OBSERVABLE_FAMILIES)
    for m in c["metrics"]:
        fams = m["input_observable_families"]
        _a = f"metric {m['metric_id']!r} must map to >= 1 observable family"
        assert isinstance(fams, list) and len(fams) >= 1, _a
        _b = f"metric {m['metric_id']!r} families {fams!r} not all in K-P1 set {sorted(valid)!r}"
        assert all(f in valid for f in fams), _b


# ---------------------------------------------------------------------------
# 10. Every metric defers threshold to power gate
# ---------------------------------------------------------------------------


def test_every_metric_defers_threshold_to_power_gate() -> None:
    c = _load(CONTRACT_PATH)
    for m in c["metrics"]:
        sem = m["decision_threshold_semantics"]
        _a = f"metric {m['metric_id']!r} must defer threshold to power gate; got {sem!r}"
        assert "deferred to D-002K power gate" in sem, _a
        assert "NOT set here" in sem, f"metric {m['metric_id']!r} must say NOT set here"
    s = _load(SUMMARY_PATH)
    assert s["threshold_deferred_all"] is True, "summary threshold_deferred_all must be True"


# ---------------------------------------------------------------------------
# 11. Primary metric definition deterministic
# ---------------------------------------------------------------------------


def test_primary_metric_definition_deterministic() -> None:
    a = pre_post_standardized_mean_shift(_SYNTH, _ONSET, _PRE, _POST)
    b = pre_post_standardized_mean_shift(_SYNTH, _ONSET, _PRE, _POST)
    assert a == b, f"primary metric not deterministic: {a!r} != {b!r}"
    # Known sign: post mean (4.8) > pre mean (1.0), pre sigma small.
    assert a > 0.0, f"level-shift synthetic must yield positive shift; got {a!r}"


# ---------------------------------------------------------------------------
# 12. Primary metric fail-closed on zero sigma
# ---------------------------------------------------------------------------


def test_primary_metric_fail_closed_on_zero_sigma() -> None:
    flat = [2.0, 2.0, 2.0, 2.0, 9.0, 9.0]  # constant pre-window -> sigma==0
    with pytest.raises(ValueError, match="sigma_pre == 0"):
        pre_post_standardized_mean_shift(flat, 4, 4, 2)
    with pytest.raises(ValueError, match="sigma_pre == 0"):
        max_zscore(flat, 4, 4, 2)


# ---------------------------------------------------------------------------
# 13. Primary metric fail-closed on short window
# ---------------------------------------------------------------------------


def test_primary_metric_fail_closed_on_short_window() -> None:
    short = [1.0, 2.0, 3.0]
    with pytest.raises(ValueError, match="insufficient pre-window"):
        pre_post_standardized_mean_shift(short, 1, 5, 1)
    with pytest.raises(ValueError, match="insufficient post-window"):
        pre_post_standardized_mean_shift(short, 2, 2, 5)


# ---------------------------------------------------------------------------
# 14. Contrast uses K-P2 placebos
# ---------------------------------------------------------------------------


def test_crisis_vs_placebo_contrast_uses_k_p2_placebos() -> None:
    c = _load(CONTRACT_PATH)
    for m in c["metrics"]:
        _a = f"metric {m['metric_id']!r} contrast must reference K-P2 matched placebos"
        assert "K-P2 matched placebos" in m["contrast"], _a
    placebos = [[1.0, 1.1, 0.9, 1.05, 0.95, 1.1, 1.2, 1.1, 1.0, 1.0] for _ in range(3)]
    out = crisis_vs_placebo_contrast(
        pre_post_standardized_mean_shift, _SYNTH, placebos, _ONSET, _PRE, _POST
    )
    assert out["n_placebos"] == 3, f"n_placebos must be 3; got {out['n_placebos']!r}"
    with pytest.raises(ValueError, match="non-empty"):
        crisis_vs_placebo_contrast(
            pre_post_standardized_mean_shift, _SYNTH, [], _ONSET, _PRE, _POST
        )


# ---------------------------------------------------------------------------
# 15. Contrast returns delta WITHOUT a threshold decision
# ---------------------------------------------------------------------------


def test_contrast_returns_delta_without_threshold_decision() -> None:
    placebos = [[1.0, 1.1, 0.9, 1.05, 0.95, 1.0, 1.0, 1.0, 1.0, 1.0] for _ in range(4)]
    out = crisis_vs_placebo_contrast(
        pre_post_standardized_mean_shift, _SYNTH, placebos, _ONSET, _PRE, _POST
    )
    expected = {"crisis_value", "placebo_mean", "placebo_std", "delta", "n_placebos"}
    assert set(out.keys()) == expected, f"contrast keys must be {expected!r}; got {set(out)!r}"
    # No verdict / pass / threshold key may leak into the contrast dict.
    forbidden = {"pass", "fail", "decision", "threshold", "verdict", "significant"}
    leaked = forbidden & set(out.keys())
    assert not leaked, f"contrast must emit NO decision; leaked {leaked!r}"


# ---------------------------------------------------------------------------
# 16. Secondary metrics deterministic
# ---------------------------------------------------------------------------


def test_secondary_metrics_deterministic() -> None:
    fns: list[Callable[..., float]] = [
        max_zscore,
        area_under_stress_curve,
        recovery_half_life,
        slope_into_crisis,
        volatility_ratio,
        persistence_above_threshold,
    ]
    for fn in fns:
        a = fn(_SYNTH, _ONSET, _PRE, _POST)
        b = fn(_SYNTH, _ONSET, _PRE, _POST)
        assert a == b, f"{fn.__name__} not deterministic: {a!r} != {b!r}"
    # Fail-closed propagates through the secondary battery too.
    with pytest.raises(ValueError):
        slope_into_crisis([1.0, 1.0, 1.0, 9.0], 3, 3, 1)


# ---------------------------------------------------------------------------
# 17. No metric scores real data (no ingestion / artifact data read)
# ---------------------------------------------------------------------------


def test_no_metric_scores_real_data() -> None:
    src = (REPO_ROOT / "research/systemic_risk/d002k_event_metrics.py").read_text(encoding="utf-8")
    banned = ["pandas", "read_csv", "requests", "urllib", "yfinance", "fredapi", "open("]
    for tok in banned:
        _a = f"metric module must not ingest/score real data; found {tok!r}"
        assert tok not in src, _a
    c = _load(CONTRACT_PATH)
    assert c["no_scoring_on_real_data"] is True, "contract no_scoring_on_real_data must be True"


# ---------------------------------------------------------------------------
# 18. Summary counts match contract
# ---------------------------------------------------------------------------


def test_summary_counts_match_contract() -> None:
    c = _load(CONTRACT_PATH)
    s = _load(SUMMARY_PATH)
    total = len(c["metrics"])
    primary = sum(1 for m in c["metrics"] if m["role"] == "primary_confirmatory")
    secondary = sum(1 for m in c["metrics"] if m["role"] == "secondary_exploratory")
    assert s["counts"]["total"] == total, f"summary total {s['counts']['total']} != {total}"
    assert s["counts"]["primary"] == primary == 1, "summary primary must be 1"
    _a = f"summary secondary_exploratory {s['counts']['secondary_exploratory']} != {secondary}"
    assert s["counts"]["secondary_exploratory"] == secondary, _a


# ---------------------------------------------------------------------------
# 19. No systemic-risk prediction claim
# ---------------------------------------------------------------------------


def test_no_systemic_risk_prediction_claim() -> None:
    doc = (REPO_ROOT / "docs/research/D002K_EVENT_METRIC_CONTRACT.md").read_text(encoding="utf-8")
    low = doc.lower()
    for phrase in ("predicts systemic", "forecasts the crisis", "proves contagion"):
        assert phrase not in low, f"doc must not claim {phrase!r}"
    c = _load(CONTRACT_PATH)
    assert c["canonical_run_authorized"] is False, "contract canonical_run_authorized must be False"


# ---------------------------------------------------------------------------
# 20. No bank-level validation claim
# ---------------------------------------------------------------------------


def test_no_bank_level_validation_claim() -> None:
    doc = (REPO_ROOT / "docs/research/D002K_EVENT_METRIC_CONTRACT.md").read_text(encoding="utf-8")
    low = doc.lower()
    for phrase in ("bank-level validated", "validated at the bank", "per-bank validation"):
        assert phrase not in low, f"doc must not claim {phrase!r}"
    assert "rescue" in low and "refused" in low, "doc must keep no-rescue / refused boundary"


# ---------------------------------------------------------------------------
# 21. No D-002K prereg / prior-phase edit (K-P0/K-P1/K-P2 + D-002J frozen)
# ---------------------------------------------------------------------------


def test_no_d002k_prereg_or_prior_phase_edit() -> None:
    for rel, sha in FROZEN_SHAS.items():
        p = REPO_ROOT / rel
        assert p.is_file(), f"frozen anchor missing: {rel}"
        actual = _sha256(p)
        _a = f"FROZEN {rel} drifted: expected {sha[:12]}..., got {actual[:12]}..."
        assert actual == sha, _a
    d002j_prereg = REPO_ROOT / "docs/governance/D002J_PREREGISTRATION.yaml"
    d002j_sha = "f3dc65b7e64b96eafe6f23ca8bdd0e05dc9bf95b12c2658b227bd0340f7975a0"  # pragma: allowlist secret
    _b = "D-002J prereg must stay byte-exact"
    assert _sha256(d002j_prereg) == d002j_sha, _b


# ---------------------------------------------------------------------------
# 22. No canonical run authorized
# ---------------------------------------------------------------------------


def test_no_canonical_run_authorized() -> None:
    c = _load(CONTRACT_PATH)
    s = _load(SUMMARY_PATH)
    assert c["canonical_run_authorized"] is False, "contract canonical_run_authorized must be False"
    assert s["canonical_run_authorized"] is False, "summary canonical_run_authorized must be False"
    v = _load(VERDICT_PATH)
    _a = f"verdict decision must be D002K_EVENT_METRICS_READY; got {v['decision']!r}"
    assert v["decision"] == "D002K_EVENT_METRICS_READY", _a
    assert v["allowed_next_nodes"] == ["D002K-P4"], "verdict next must be D002K-P4"


# ---------------------------------------------------------------------------
# 23. No unresolved merge markers
# ---------------------------------------------------------------------------


def test_no_unresolved_merge_markers() -> None:
    targets = [
        REPO_ROOT / "research/systemic_risk/d002k_event_metrics.py",
        CONTRACT_PATH,
        SUMMARY_PATH,
        VERDICT_PATH,
        REPO_ROOT / "docs/research/D002K_EVENT_METRIC_CONTRACT.md",
        Path(__file__),
    ]
    for t in targets:
        for i, line in enumerate(t.read_text(encoding="utf-8").splitlines(), 1):
            assert not _MARKER.match(line), f"merge marker in {t} line {i}"
    assert len(targets) == 6, "expected exactly 6 scanned targets"
