from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.security.check_dependency_drift import (
    evaluate_drift,
    main,
    write_report,
)


def _make_pyproject(path: Path, deps: list[str], optional: list[str]) -> None:
    path.write_text(
        "\n".join(
            [
                "[project]",
                "name = 'sample'",
                "version = '0.0.0'",
                "dependencies = [",
                *[f'    "{dep}",' for dep in deps],
                "]",
                "",
                "[project.optional-dependencies]",
                "dev = [",
                *[f'    "{dep}",' for dep in optional],
                "]",
                "",
            ]
        ),
        encoding="utf-8",
    )


def test_dependency_drift_passes_when_lock_matches(tmp_path: Path) -> None:
    lock = tmp_path / "lock.txt"
    lock.write_text("foo==1.2.0\nbar==2.1.0\n", encoding="utf-8")

    req = tmp_path / "requirements.txt"
    req.write_text("foo>=1.0\n", encoding="utf-8")

    pyproject = tmp_path / "pyproject.toml"
    _make_pyproject(pyproject, deps=["foo>=1.0"], optional=["bar>=2.0"])

    constraints = tmp_path / "constraints.txt"
    constraints.write_text("# none required\n", encoding="utf-8")

    issues = evaluate_drift(
        lock_path=lock,
        requirements_paths=[req],
        pyproject_path=pyproject,
        constraints_path=constraints,
    )
    assert issues == []

    output = tmp_path / "artifacts" / "security" / "dependency-drift.json"
    write_report(output, issues)
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["status"] == "pass"
    assert payload["issue_count"] == 0


def test_dependency_drift_detects_mismatch_and_writes_report(tmp_path: Path) -> None:
    lock = tmp_path / "lock.txt"
    lock.write_text("foo==0.5.0\n", encoding="utf-8")

    req = tmp_path / "requirements.txt"
    req.write_text("foo>=1.0\n", encoding="utf-8")

    pyproject = tmp_path / "pyproject.toml"
    _make_pyproject(pyproject, deps=["foo>=1.0"], optional=[])

    constraints = tmp_path / "constraints.txt"
    constraints.write_text("foo>=1.0\n", encoding="utf-8")

    output = tmp_path / "artifacts" / "security" / "dependency-drift.json"
    exit_code = main(
        [
            "--lock",
            str(lock),
            "--requirements",
            str(req),
            "--pyproject",
            str(pyproject),
            "--constraints",
            str(constraints),
            "--output",
            str(output),
        ]
    )

    assert exit_code == 1
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["status"] == "fail"
    assert payload["issue_count"] == 1
    issue = payload["issues"][0]
    assert issue["package"].lower() == "foo"
    assert "lock" in issue["reason"]
