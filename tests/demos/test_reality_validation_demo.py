# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for demos/reality_validation_demo/run_demo.py."""

from __future__ import annotations

from pathlib import Path

from demos.reality_validation_demo.run_demo import (
    DemoStatus,
    render_terminal,
    run_demo,
)


def test_demo_passes_on_live_tree(tmp_path: Path) -> None:
    """Falsifier surface from brief: every detector must catch its injection."""
    report = run_demo(output_path=tmp_path / "out.json")
    assert report.status is DemoStatus.DEMO_PASS, render_terminal(report)
    assert len(report.steps) == 3
    for step in report.steps:
        assert step.matched, f"step {step.step_id} did not match: {step.excerpt}"


def test_demo_steps_have_unique_ids(tmp_path: Path) -> None:
    report = run_demo(output_path=tmp_path / "out.json")
    ids = [s.step_id for s in report.steps]
    assert len(set(ids)) == len(ids)


def test_demo_steps_cover_three_distinct_validators(tmp_path: Path) -> None:
    report = run_demo(output_path=tmp_path / "out.json")
    descs = " ".join(s.description for s in report.steps)
    assert "translation" in descs.lower()
    assert "dependency" in descs.lower() or "dep" in descs.lower()
    assert "false-confidence" in descs.lower() or "concentration" in descs.lower()


def test_render_terminal_contains_status_line(tmp_path: Path) -> None:
    report = run_demo(output_path=tmp_path / "out.json")
    text = render_terminal(report)
    assert "GeoSync reality-validation demo" in text
    assert report.status.value in text


def test_demo_does_not_mutate_live_tree(tmp_path: Path) -> None:
    """Every demo step must work on tmp/synthetic copies — never the live tree.

    Snapshot the mtime of three live files the demo READS; verify they
    are unchanged after the demo runs.
    """
    repo_root = Path(__file__).resolve().parents[2]
    targets = [
        repo_root / ".claude" / "research" / "PHYSICS_2026_TRANSLATION.yaml",
        repo_root / ".claude" / "audit" / "false_confidence_exemptions.yaml",
        repo_root / "requirements.txt",
    ]
    before = {p: p.stat().st_mtime for p in targets if p.exists()}
    run_demo(output_path=tmp_path / "out.json")
    after = {p: p.stat().st_mtime for p in targets if p.exists()}
    for p, mtime in before.items():
        assert after[p] == mtime, f"{p} mutated by demo"


def test_demo_report_serialisable_to_json(tmp_path: Path) -> None:
    import json

    out = tmp_path / "out.json"
    run_demo(output_path=out)
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["status"] in {"DEMO_PASS", "DEMO_FAIL"}
    assert "steps" in data and len(data["steps"]) == 3
