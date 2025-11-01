# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
from __future__ import annotations

from pathlib import Path

from tools.ci.verify_repository_layout import (
    ARTIFACT_DIR,
    REQUIRED_PATHS,
    LayoutResult,
    evaluate_layout,
    write_artifacts,
)


def test_evaluate_layout_detects_missing_paths(tmp_path: Path) -> None:
    (tmp_path / "core").mkdir()
    (tmp_path / "tacl").mkdir()
    result = evaluate_layout(tmp_path)
    missing = set(result.missing)
    assert "infra/terraform" in missing
    assert "ui/dashboard" in missing
    assert result.passed is False


def test_write_artifacts_persists_results(tmp_path: Path, monkeypatch) -> None:
    artifact_dir = tmp_path / ".ci_artifacts"
    monkeypatch.setenv("CI", "true")
    result = LayoutResult(missing=("foo",))
    write_artifacts(result, artifact_dir=artifact_dir)

    report = (artifact_dir / "repository_structure.json").read_text(encoding="utf-8")
    assert "\n" in report
    markdown = (artifact_dir / "repository_structure.md").read_text(encoding="utf-8")
    assert "foo" in markdown


def test_all_required_paths_are_declared() -> None:
    assert ARTIFACT_DIR == Path(".ci_artifacts")
    assert REQUIRED_PATHS  # sanity guard to ensure we do not regress to an empty tuple
