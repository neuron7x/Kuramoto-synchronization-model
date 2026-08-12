# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""D-002C C2.1 — Pre-registration validator tests.

Pins the C2.1 gates:

  G1  load_and_lock parses the canonical YAML into a frozen dataclass
  G2  preregistration_sha is deterministic across calls
  G3  preregistration_sha changes on any byte-level edit of the YAML
  G4  validate_sweep_config accepts a config that matches the lock
  G5  validate_sweep_config raises on any single-field mismatch
  G6  __post_init__ enforces all numeric invariants
  G7  Bonferroni effective_alpha_per_cell is exactly ci_alpha / n_cells
  G8  acceptance_rule text is deterministic and matches YAML requirements

Strict scope: validator only. No sweep execution.
"""

from __future__ import annotations

import dataclasses
import math
from pathlib import Path
from typing import Any

import pytest

from research.systemic_risk.d002c_preregistration import (
    PREREGISTRATION_SCHEMA_VERSION,
    CIMethod,
    D002CPreregistration,
    MultipleTestingCorrection,
    PreregistrationCorrupt,
    PreregistrationMismatch,
    load_and_lock,
    validate_sweep_config,
)

# ---------------------------------------------------------------------------
# Path to the canonical pre-registration YAML (single source of truth)
# ---------------------------------------------------------------------------

CANONICAL_YAML = (
    Path(__file__).resolve().parents[3] / "docs" / "governance" / "D002C_PREREGISTRATION.yaml"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _well_formed_sweep_config(prereg: D002CPreregistration) -> dict[str, Any]:
    """Build a sweep config that should validate cleanly."""
    return {
        "ci_method": prereg.ci_method.value,
        "ci_alpha": prereg.ci_alpha,
        "signal_ci_ratio_threshold": prereg.signal_ci_ratio_threshold,
        "direction_consistency_min_seeds": prereg.direction_consistency_min_seeds,
        "direction_stability_min_fraction": prereg.direction_stability_min_fraction,
        "multiple_testing_correction": prereg.multiple_testing_correction.value,
        "n_seeds": prereg.n_seeds,
        "n_bootstrap": prereg.n_bootstrap,
        "N_grid": list(prereg.N_grid),
        "lambda_grid": list(prereg.lambda_grid),
        "substrate_ids": list(prereg.substrate_ids),
        "metric_ids": list(prereg.metric_ids),
        "variance_reduction": list(prereg.variance_reduction),
        "substrate_seed": prereg.substrate_seed,
        "preregistration_sha": prereg.preregistration_sha,
    }


# ---------------------------------------------------------------------------
# G1 — load_and_lock parses the canonical YAML
# ---------------------------------------------------------------------------


def test_g1_canonical_yaml_loads_to_frozen_dataclass() -> None:
    prereg = load_and_lock(CANONICAL_YAML)
    # Identity / contract fields
    assert prereg.schema_version == PREREGISTRATION_SCHEMA_VERSION
    assert prereg.issue == 654
    assert prereg.tier_if_pass == "SYNTHETIC_GATE6_CERTIFIED_REDESIGN_N_LE_200"
    assert prereg.tier_if_fail == "D002C_REDESIGN_INSUFFICIENT_AT_TESTED_BUDGET"
    # Locked formal decisions per the YAML
    assert prereg.ci_method is CIMethod.BCA_BOOTSTRAP
    assert prereg.ci_alpha == pytest.approx(0.05)
    assert prereg.signal_ci_ratio_threshold == pytest.approx(1.0)
    assert prereg.direction_consistency_min_seeds == 3
    assert prereg.direction_stability_min_fraction == pytest.approx(0.80)
    assert prereg.multiple_testing_correction is MultipleTestingCorrection.BONFERRONI
    assert prereg.n_cells == 216
    assert prereg.n_seeds == 20
    assert prereg.n_bootstrap == 16
    # Grids
    assert prereg.N_grid == (50, 100, 200)
    assert prereg.lambda_grid == (0.0, 0.05, 0.10, 0.20, 0.40, 1.0)
    # Substrates / metrics (order matches YAML)
    assert prereg.substrate_ids == (
        "ricci_flow",
        "block_structured",
        "temporal_coupling",
    )
    assert prereg.metric_ids == ("tau_onset", "sync_auc", "phase_lag")
    assert prereg.substrate_seed == 42
    # sha format
    assert len(prereg.preregistration_sha) == 64
    assert all(c in "0123456789abcdef" for c in prereg.preregistration_sha)


def test_g1_frozen_dataclass_is_immutable() -> None:
    prereg = load_and_lock(CANONICAL_YAML)
    with pytest.raises(dataclasses.FrozenInstanceError):
        prereg.ci_alpha = 0.10  # type: ignore[misc]


# ---------------------------------------------------------------------------
# G2 — preregistration_sha is deterministic across calls
# ---------------------------------------------------------------------------


def test_g2_sha_deterministic_across_repeated_loads() -> None:
    a = load_and_lock(CANONICAL_YAML).preregistration_sha
    b = load_and_lock(CANONICAL_YAML).preregistration_sha
    c = load_and_lock(CANONICAL_YAML).preregistration_sha
    assert a == b == c


# ---------------------------------------------------------------------------
# G3 — sha changes on any byte-level edit (content-addressed lock)
# ---------------------------------------------------------------------------


def test_g3_single_byte_edit_changes_sha(tmp_path: Path) -> None:
    src = CANONICAL_YAML.read_bytes()
    # baseline
    canonical = tmp_path / "canonical.yaml"
    canonical.write_bytes(src)
    sha_canonical = load_and_lock(canonical).preregistration_sha
    # 1-byte mutation: append a single newline at EOF
    mutated = tmp_path / "mutated.yaml"
    mutated.write_bytes(src + b"\n")
    sha_mutated = load_and_lock(mutated).preregistration_sha
    assert sha_canonical != sha_mutated


def test_g3_whitespace_change_changes_sha(tmp_path: Path) -> None:
    src = CANONICAL_YAML.read_bytes()
    canonical = tmp_path / "canonical.yaml"
    canonical.write_bytes(src)
    sha_canonical = load_and_lock(canonical).preregistration_sha
    # Add a single trailing space at end of first non-comment line
    text = src.decode("utf-8")
    lines = text.splitlines(keepends=True)
    for i, line in enumerate(lines):
        if line.strip() and not line.lstrip().startswith("#"):
            lines[i] = line.rstrip("\n") + " \n"
            break
    mutated = tmp_path / "ws.yaml"
    mutated.write_bytes("".join(lines).encode("utf-8"))
    sha_mutated = load_and_lock(mutated).preregistration_sha
    assert sha_canonical != sha_mutated


# ---------------------------------------------------------------------------
# G4 — validate_sweep_config accepts a matching config
# ---------------------------------------------------------------------------


def test_g4_well_formed_config_validates_cleanly() -> None:
    prereg = load_and_lock(CANONICAL_YAML)
    cfg = _well_formed_sweep_config(prereg)
    # Must not raise
    validate_sweep_config(prereg, cfg)


def test_g4_tuple_or_list_grid_both_accepted() -> None:
    """The driver may construct N_grid / lambda_grid as either list or tuple;
    the validator normalises before comparison."""
    prereg = load_and_lock(CANONICAL_YAML)
    cfg = _well_formed_sweep_config(prereg)
    cfg["N_grid"] = tuple(prereg.N_grid)
    cfg["lambda_grid"] = tuple(prereg.lambda_grid)
    validate_sweep_config(prereg, cfg)


# ---------------------------------------------------------------------------
# G5 — single-field mismatch raises with all disagreements listed
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "key, mutation",
    [
        ("ci_method", "percentile_bootstrap"),
        ("ci_alpha", 0.10),
        ("signal_ci_ratio_threshold", 2.0),
        ("direction_consistency_min_seeds", 5),
        ("direction_stability_min_fraction", 0.50),
        ("multiple_testing_correction", "fdr_bh"),
        ("n_seeds", 50),
        ("n_bootstrap", 100),
        ("N_grid", [50, 100, 400]),
        ("lambda_grid", [0.0, 1.0]),
        ("substrate_ids", ["only_ricci"]),
        ("metric_ids", ["tau_onset"]),
        ("variance_reduction", ["common_random_numbers"]),
        ("substrate_seed", 7),
        ("preregistration_sha", "0" * 64),
    ],
)
def test_g5_any_single_field_mismatch_raises(key: str, mutation: object) -> None:
    prereg = load_and_lock(CANONICAL_YAML)
    cfg = _well_formed_sweep_config(prereg)
    cfg[key] = mutation
    with pytest.raises(PreregistrationMismatch) as exc:
        validate_sweep_config(prereg, cfg)
    assert key in str(exc.value)


def test_g5_missing_keys_listed_in_one_exception() -> None:
    prereg = load_and_lock(CANONICAL_YAML)
    cfg = _well_formed_sweep_config(prereg)
    del cfg["ci_method"]
    del cfg["preregistration_sha"]
    with pytest.raises(PreregistrationMismatch) as exc:
        validate_sweep_config(prereg, cfg)
    msg = str(exc.value)
    assert "ci_method" in msg
    assert "preregistration_sha" in msg


def test_g5_multiple_mismatches_all_reported() -> None:
    """A single re-launch should be able to see EVERY disagreement,
    not the first."""
    prereg = load_and_lock(CANONICAL_YAML)
    cfg = _well_formed_sweep_config(prereg)
    cfg["ci_method"] = "percentile_bootstrap"
    cfg["ci_alpha"] = 0.10
    cfg["n_seeds"] = 999
    with pytest.raises(PreregistrationMismatch) as exc:
        validate_sweep_config(prereg, cfg)
    msg = str(exc.value)
    assert "ci_method" in msg
    assert "ci_alpha" in msg
    assert "n_seeds" in msg


# ---------------------------------------------------------------------------
# G6 — __post_init__ enforces numeric invariants
# ---------------------------------------------------------------------------


def _kwargs_for_prereg(**override: Any) -> dict[str, Any]:
    """Minimal kwarg set for a valid D002CPreregistration; tests can
    override one field at a time to violate exactly one invariant."""
    base: dict[str, Any] = dict(
        schema_version=PREREGISTRATION_SCHEMA_VERSION,
        version=1,
        issue=654,
        follows=656,
        tier_if_pass="X",
        tier_if_fail="Y",
        acceptance_rule="R1: …",
        ci_method=CIMethod.BCA_BOOTSTRAP,
        ci_alpha=0.05,
        signal_ci_ratio_threshold=1.0,
        direction_consistency_min_seeds=3,
        direction_stability_min_fraction=0.80,
        multiple_testing_correction=MultipleTestingCorrection.BONFERRONI,
        n_cells=216,
        effective_alpha_per_cell=0.05 / 216,
        n_seeds=20,
        n_bootstrap=16,
        N_grid=(50, 100, 200),
        lambda_grid=(0.0, 0.05, 0.10, 0.20, 0.40, 1.0),
        substrate_ids=("a", "b", "c"),
        metric_ids=("m1", "m2", "m3"),
        variance_reduction=("crn",),
        substrate_seed=42,
        forbidden_outputs=("FOO",),
        preregistration_sha="a" * 64,
        yaml_path="/tmp/d002c.yaml",
    )
    base.update(override)
    return base


def test_g6_baseline_kwargs_construct_cleanly() -> None:
    # Sanity: the helper itself is valid (no invariant is touched)
    D002CPreregistration(**_kwargs_for_prereg())


@pytest.mark.parametrize(
    "field, bad_value",
    [
        ("ci_alpha", 0.0),
        ("ci_alpha", 1.0),
        ("ci_alpha", -0.1),
        ("signal_ci_ratio_threshold", 0.0),
        ("signal_ci_ratio_threshold", -1.0),
        ("signal_ci_ratio_threshold", math.nan),
        ("direction_consistency_min_seeds", 0),
        ("direction_consistency_min_seeds", 21),  # > n_seeds
        ("direction_stability_min_fraction", 0.0),
        ("direction_stability_min_fraction", 1.5),
        ("n_seeds", 1),
        ("n_bootstrap", 1),
        ("n_cells", 0),
    ],
)
def test_g6_invariants_reject_bad_values(field: str, bad_value: Any) -> None:
    with pytest.raises(PreregistrationCorrupt):
        D002CPreregistration(**_kwargs_for_prereg(**{field: bad_value}))


def test_g6_invariants_reject_short_or_non_hex_sha() -> None:
    with pytest.raises(PreregistrationCorrupt):
        D002CPreregistration(**_kwargs_for_prereg(preregistration_sha="abc"))
    with pytest.raises(PreregistrationCorrupt):
        D002CPreregistration(**_kwargs_for_prereg(preregistration_sha="z" * 64))


def test_g6_invariants_reject_empty_grids() -> None:
    with pytest.raises(PreregistrationCorrupt):
        D002CPreregistration(**_kwargs_for_prereg(N_grid=()))
    with pytest.raises(PreregistrationCorrupt):
        D002CPreregistration(**_kwargs_for_prereg(lambda_grid=()))
    with pytest.raises(PreregistrationCorrupt):
        D002CPreregistration(**_kwargs_for_prereg(substrate_ids=()))
    with pytest.raises(PreregistrationCorrupt):
        D002CPreregistration(**_kwargs_for_prereg(metric_ids=()))


# ---------------------------------------------------------------------------
# G7 — Bonferroni effective_alpha_per_cell is exactly ci_alpha / n_cells
# ---------------------------------------------------------------------------


def test_g7_bonferroni_effective_alpha_is_exact() -> None:
    prereg = load_and_lock(CANONICAL_YAML)
    expected = prereg.ci_alpha / float(prereg.n_cells)
    assert prereg.effective_alpha_per_cell == expected
    # And the canonical value (sanity)
    assert prereg.effective_alpha_per_cell == pytest.approx(0.05 / 216, abs=1e-15)


def test_g7_bonferroni_drift_is_rejected_in_post_init() -> None:
    """If a misconstruction passes a wrong derived value it must be rejected."""
    with pytest.raises(PreregistrationCorrupt):
        D002CPreregistration(**_kwargs_for_prereg(effective_alpha_per_cell=0.0001))


def test_g7_none_correction_uses_family_alpha() -> None:
    kw = _kwargs_for_prereg(
        multiple_testing_correction=MultipleTestingCorrection.NONE,
        effective_alpha_per_cell=0.05,
    )
    obj = D002CPreregistration(**kw)
    assert obj.effective_alpha_per_cell == obj.ci_alpha


# ---------------------------------------------------------------------------
# G8 — acceptance_rule text is deterministic and contains R1/R2/R3
# ---------------------------------------------------------------------------


def test_g8_acceptance_rule_deterministic_and_complete() -> None:
    a = load_and_lock(CANONICAL_YAML).acceptance_rule
    b = load_and_lock(CANONICAL_YAML).acceptance_rule
    assert a == b
    # All three pre-committed requirements present
    assert "R1:" in a
    assert "R2:" in a
    assert "R3:" in a
    # And the canonical R1 text matches the YAML
    assert "exists N in [50,100,200], substrate, metric: |signal|/CI > 1" in a


# ---------------------------------------------------------------------------
# Corruption + missing-key paths (additional fail-closed coverage)
# ---------------------------------------------------------------------------


def test_corrupt_yaml_path_does_not_exist(tmp_path: Path) -> None:
    with pytest.raises(PreregistrationCorrupt):
        load_and_lock(tmp_path / "does-not-exist.yaml")


def test_corrupt_yaml_not_a_mapping(tmp_path: Path) -> None:
    p = tmp_path / "bad.yaml"
    p.write_text("- just\n- a\n- list\n", encoding="utf-8")
    with pytest.raises(PreregistrationCorrupt):
        load_and_lock(p)


def test_corrupt_yaml_missing_acceptance(tmp_path: Path) -> None:
    p = tmp_path / "no_acceptance.yaml"
    p.write_text("version: 1\nissue: 654\nfollows: 656\n", encoding="utf-8")
    with pytest.raises(PreregistrationCorrupt):
        load_and_lock(p)


def test_corrupt_yaml_unknown_ci_method(tmp_path: Path) -> None:
    src = CANONICAL_YAML.read_text(encoding="utf-8").replace(
        "ci_method: bca_bootstrap",
        "ci_method: telepathy",
    )
    p = tmp_path / "bad_ci.yaml"
    p.write_text(src, encoding="utf-8")
    with pytest.raises(PreregistrationCorrupt):
        load_and_lock(p)


def test_corrupt_yaml_unknown_correction_method(tmp_path: Path) -> None:
    src = CANONICAL_YAML.read_text(encoding="utf-8").replace(
        "method: bonferroni",
        "method: vibes",
    )
    p = tmp_path / "bad_corr.yaml"
    p.write_text(src, encoding="utf-8")
    with pytest.raises(PreregistrationCorrupt):
        load_and_lock(p)
