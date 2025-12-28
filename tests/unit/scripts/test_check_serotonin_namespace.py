from __future__ import annotations

from pathlib import Path

from scripts import check_serotonin_namespace


def test_namespace_check_passes_for_repo_root():
    errors = check_serotonin_namespace.run_checks()
    assert errors == []


def test_detects_non_canonical_import(tmp_path: Path):
    offender = tmp_path / "offender.py"
    offender.write_text(
        "import core.neuro.serotonin.serotonin_controller\n", encoding="utf-8"
    )
    violations = check_serotonin_namespace.find_non_canonical_imports(tmp_path)
    assert violations
    assert violations[0].path == offender
    assert violations[0].module.startswith("core.neuro.serotonin")
