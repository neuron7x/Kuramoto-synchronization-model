# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""The flagship-preregistration gate must have teeth (RES-002).

A preregistration is only tamper-evident if the gate can actually catch tampering.
These tests prove:

  POSITIVE  — the committed, intact protocol passes: every required section is
              present, and the stored digest matches the SHA-256 of the canonical
              protocol body (exit 0).
  NEGATIVE  — (a) mutating a single byte of the frozen body WITHOUT re-deriving the
              digest is rejected (digest mismatch, non-zero exit); and
              (b) a protocol missing ``stopping_rules`` is rejected (non-zero exit).

Determinism: ``prereg_date`` is a fixed string, so the digest is reproducible and
these assertions do not depend on wall-clock time.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import yaml

from scripts.ci.check_preregistration import (
    DEFAULT_PREREG,
    PREREG_DATE,
    REQUIRED_SECTIONS,
    compute_digest,
    evaluate,
    main,
)


def _clone_protocol(dst: Path) -> Path:
    """Copy the committed protocol into a writable temp location."""
    target = dst / "flagship_preregistration.yaml"
    shutil.copy2(DEFAULT_PREREG, target)
    return target


# --------------------------------------------------------------------------- #
# POSITIVE                                                                     #
# --------------------------------------------------------------------------- #
def test_committed_protocol_is_intact() -> None:
    """The real committed protocol is complete and its digest matches."""
    verdict = evaluate(DEFAULT_PREREG)
    assert verdict["ok"] is True, verdict["problems"]
    assert verdict["missing_sections"] == []
    assert verdict["digest_ok"] is True
    assert verdict["stored_digest"] == verdict["computed_digest"]


def test_gate_exits_zero_on_committed_protocol() -> None:
    """The gate entrypoint returns 0 on the committed, intact protocol."""
    assert main(["--path", str(DEFAULT_PREREG)]) == 0


def test_all_required_sections_are_enforced() -> None:
    """The frozen analysis-plan sections are exactly the ones the gate demands."""
    assert set(REQUIRED_SECTIONS) == {
        "hypotheses",
        "primary_outcomes",
        "secondary_outcomes",
        "dataset_versions",
        "exclusions",
        "splits",
        "nulls",
        "baselines",
        "metrics",
        "multiple_testing_corrections",
        "stopping_rules",
        "promotion_rules",
    }


def test_prereg_date_is_fixed() -> None:
    """The committed protocol carries the fixed, deterministic prereg date."""
    data = yaml.safe_load(DEFAULT_PREREG.read_text(encoding="utf-8"))
    assert data["prereg_date"] == PREREG_DATE == "2026-07-19"


# --------------------------------------------------------------------------- #
# NEGATIVE — tamper: mutate one body byte without updating the digest          #
# --------------------------------------------------------------------------- #
def test_tampered_body_is_rejected(tmp_path: Path) -> None:
    """Mutating one body value without re-deriving the digest fails the gate."""
    path = _clone_protocol(tmp_path)
    data = yaml.safe_load(path.read_text(encoding="utf-8"))

    # Flip a single semantic byte inside the frozen body; leave digest untouched.
    original = data["protocol_body"]["primary_outcomes"][0]["decision_threshold"]
    data["protocol_body"]["primary_outcomes"][0]["decision_threshold"] = (
        original + " TAMPERED"
    )
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

    verdict = evaluate(path)
    assert verdict["ok"] is False
    assert verdict["digest_ok"] is False
    assert any("digest" in p.lower() for p in verdict["problems"])
    assert main(["--path", str(path)]) == 1


def test_recomputing_digest_reblesses_a_deliberate_change(tmp_path: Path) -> None:
    """A body change re-passes ONLY after the digest is legitimately re-derived.

    Confirms the mismatch above is genuine tamper-evidence, not a broken check:
    re-deriving the digest over the mutated body restores exit 0.
    """
    path = _clone_protocol(tmp_path)
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data["protocol_body"]["hypotheses"]["directionality"] = "one-sided (revised)"
    data["digest"] = compute_digest(data["protocol_body"])
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    assert main(["--path", str(path)]) == 0


# --------------------------------------------------------------------------- #
# NEGATIVE — missing a required section (stopping_rules)                       #
# --------------------------------------------------------------------------- #
def test_missing_stopping_rules_is_rejected(tmp_path: Path) -> None:
    """A protocol missing ``stopping_rules`` fails the gate with non-zero exit."""
    path = _clone_protocol(tmp_path)
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    del data["protocol_body"]["stopping_rules"]
    # Re-derive the digest so this is a pure completeness failure, not a digest one.
    data["digest"] = compute_digest(data["protocol_body"])
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

    verdict = evaluate(path)
    assert verdict["ok"] is False
    assert "stopping_rules" in verdict["missing_sections"]
    assert main(["--path", str(path)]) == 1


# --------------------------------------------------------------------------- #
# NEGATIVE — deviations log must be append-only                               #
# --------------------------------------------------------------------------- #
def test_non_contiguous_deviations_are_rejected(tmp_path: Path) -> None:
    """A deviations log with a seq gap (deletion / reorder) fails the gate."""
    path = _clone_protocol(tmp_path)
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    # seq jumps 1 -> 3: an entry was deleted or reordered. Not append-only.
    data["deviations"] = [
        {"seq": 1, "date": "2026-07-19", "reason": "a", "decision": "x"},
        {"seq": 3, "date": "2026-07-19", "reason": "b", "decision": "y"},
    ]
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

    verdict = evaluate(path)
    assert verdict["ok"] is False
    assert any("deviations" in p for p in verdict["problems"])
    assert main(["--path", str(path)]) == 1


def test_well_formed_appended_deviation_passes(tmp_path: Path) -> None:
    """A single appended, well-formed deviation (seq=1) keeps the gate green."""
    path = _clone_protocol(tmp_path)
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data["deviations"] = [
        {
            "seq": 1,
            "date": "2026-07-19",
            "reason": "example appended deviation",
            "decision": "recorded; body unchanged",
        }
    ]
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    assert main(["--path", str(path)]) == 0


# --------------------------------------------------------------------------- #
# NEGATIVE — malformed input is fail-closed (exit 2)                          #
# --------------------------------------------------------------------------- #
def test_missing_file_is_fail_closed(tmp_path: Path) -> None:
    """A missing protocol file is a hard, fail-closed error (exit 2)."""
    assert main(["--path", str(tmp_path / "does_not_exist.yaml")]) == 2
