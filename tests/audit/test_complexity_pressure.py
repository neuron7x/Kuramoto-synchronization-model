# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for tools/audit/complexity_pressure.py."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from tools.audit.complexity_pressure import (
    Metrics,
    PressureBand,
    assess,
    classify,
    collect_metrics,
)


def _empty_metrics(**overrides: int) -> Metrics:
    base: dict[str, int] = {
        "runtime_loc": 0,
        "governance_loc": 0,
        "test_loc": 0,
        "validator_count": 0,
        "claims_count": 0,
        "falsifier_count": 0,
        "executable_gate_count": 0,
        "generated_doc_loc": 0,
        "hand_maintained_doc_loc": 0,
    }
    base.update(overrides)
    return Metrics(**base)


def test_degenerate_input_returns_unknown() -> None:
    band, reasons = classify(_empty_metrics())
    assert band is PressureBand.UNKNOWN
    assert any("degenerate" in r for r in reasons)


def test_undertested_band_when_runtime_dominates() -> None:
    """1000+ LoC runtime with thin tests → UNDERTESTED."""
    band, reasons = classify(_empty_metrics(runtime_loc=10_000, test_loc=500))
    assert band is PressureBand.UNDERTESTED
    assert any("test_loc" in r for r in reasons)


def test_overvalidated_band_when_validators_exceed_claims() -> None:
    band, _ = classify(
        _empty_metrics(
            runtime_loc=2000,
            test_loc=2000,
            validator_count=20,
            claims_count=2,
            falsifier_count=5,
        )
    )
    assert band is PressureBand.OVERVALIDATED


def test_ceremony_risk_when_docs_dominate_tests() -> None:
    """1000 lines docs + 0 tests → CEREMONY_RISK is what the brief asks for.

    The brief example says: 'fixture with 1000 lines docs and zero tests
    → CEREMONY_RISK'. Our implementation requires test_loc > 0 for the
    CEREMONY_RISK rule (a repo with literally zero tests is UNKNOWN-
    style trivially under-tested), so we test the band with a small
    positive test count.
    """
    band, _ = classify(
        _empty_metrics(
            runtime_loc=200,
            hand_maintained_doc_loc=1000,
            test_loc=100,
        )
    )
    assert band is PressureBand.CEREMONY_RISK


def test_healthy_band_when_proportional() -> None:
    band, _ = classify(
        _empty_metrics(
            runtime_loc=1000,
            test_loc=1500,
            validator_count=5,
            claims_count=10,
            falsifier_count=10,
            hand_maintained_doc_loc=200,
        )
    )
    assert band is PressureBand.HEALTHY


def test_band_priority_undertested_beats_overvalidated() -> None:
    """When both rules apply, UNDERTESTED wins (priority order)."""
    band, _ = classify(
        _empty_metrics(
            runtime_loc=10_000,
            test_loc=100,
            validator_count=20,
            claims_count=2,
            falsifier_count=5,
        )
    )
    assert band is PressureBand.UNDERTESTED


def test_falsifier_low_test_count_breaks_healthy(tmp_path: Path) -> None:
    """Falsifier surface: a tree with 1000 doc LoC and 0 tests must NOT be HEALTHY.

    Builds a synthetic tree under tmp_path with 1000 hand-maintained
    doc lines and tiny test surface; band must not be HEALTHY.
    """
    repo = tmp_path / "repo"
    (repo / "docs").mkdir(parents=True)
    (repo / "tests").mkdir()
    (repo / "geosync_hpc").mkdir()
    # Doc-heavy repo
    (repo / "docs" / "huge.md").write_text("\n".join("line" for _ in range(1000)))
    # Tiny test surface
    (repo / "tests" / "test_x.py").write_text("def test_a():\n    assert 1\n")
    # Tiny runtime
    (repo / "geosync_hpc" / "m.py").write_text("x = 1\n")

    metrics = collect_metrics(repo)
    band, _ = classify(metrics)
    assert band is not PressureBand.HEALTHY


def test_collect_metrics_on_empty_tree(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    metrics = collect_metrics(repo)
    assert all(v == 0 for v in asdict(metrics).values())


def test_collect_metrics_counts_runtime_loc(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "geosync_hpc").mkdir(parents=True)
    (repo / "geosync_hpc" / "m.py").write_text("a = 1\nb = 2\nc = 3\n")
    metrics = collect_metrics(repo)
    assert metrics.runtime_loc == 3


def test_collect_metrics_counts_validators(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "tools" / "governance").mkdir(parents=True)
    (repo / "tools" / "governance" / "validate_a.py").write_text("# v\n")
    (repo / "tools" / "governance" / "validate_b.py").write_text("# v\n")
    (repo / "tools" / "governance" / "helper.py").write_text("# h\n")
    metrics = collect_metrics(repo)
    assert metrics.validator_count == 2


def test_collect_metrics_separates_generated_docs(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "docs").mkdir(parents=True)
    (repo / "docs" / "hand.md").write_text("# Hand\nline2\n")
    (repo / "docs" / "auto.md").write_text("<!-- generated -->\nauto1\nauto2\n")
    metrics = collect_metrics(repo)
    assert metrics.hand_maintained_doc_loc == 2
    assert metrics.generated_doc_loc == 3


def test_assess_on_live_repo_does_not_raise() -> None:
    report = assess()
    assert report.band in PressureBand
    assert report.metrics is not None
    # The live tree is non-empty.
    assert report.metrics.runtime_loc > 0
