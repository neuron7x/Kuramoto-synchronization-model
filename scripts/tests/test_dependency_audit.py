# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for dependency_audit.py script."""

from __future__ import annotations

# SPDX-License-Identifier: MIT
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts import dependency_audit


def test_resolve_requirements_success(tmp_path: Path) -> None:
    """Test that _resolve_requirements resolves existing files."""
    req_file = tmp_path / "requirements.txt"
    req_file.write_text("numpy==1.0.0\n", encoding="utf-8")

    result = dependency_audit._resolve_requirements([req_file])

    assert len(result) == 1
    assert result[0] == req_file


def test_resolve_requirements_missing_file(tmp_path: Path) -> None:
    """Test that _resolve_requirements raises error for missing files."""
    missing_file = tmp_path / "missing.txt"

    with pytest.raises(dependency_audit.DependencyAuditError) as exc_info:
        dependency_audit._resolve_requirements([missing_file])

    assert "does not exist" in str(exc_info.value)


def test_parse_vulnerabilities_empty_output() -> None:
    """Test that _parse_vulnerabilities handles empty output."""
    result = dependency_audit._parse_vulnerabilities("")
    assert result == []


def test_parse_vulnerabilities_no_vulns() -> None:
    """Test that _parse_vulnerabilities handles no vulnerabilities."""
    output = json.dumps({"dependencies": [{"name": "numpy", "version": "1.0.0", "vulns": []}]})
    result = dependency_audit._parse_vulnerabilities(output)
    assert result == []


def test_parse_vulnerabilities_with_findings() -> None:
    """Test that _parse_vulnerabilities extracts vulnerability findings."""
    output = json.dumps(
        {
            "dependencies": [
                {
                    "name": "example-pkg",
                    "version": "1.0.0",
                    "vulns": [
                        {
                            "id": "CVE-2024-1234",
                            "aliases": ["GHSA-xxxx"],
                            "fix_versions": ["1.0.1"],
                            "description": "A test vulnerability",
                            "severity": "HIGH",
                        }
                    ],
                }
            ]
        }
    )

    result = dependency_audit._parse_vulnerabilities(output)

    assert len(result) == 1
    assert result[0]["name"] == "example-pkg"
    assert result[0]["version"] == "1.0.0"
    assert result[0]["id"] == "CVE-2024-1234"
    assert result[0]["severity"] == "high"


def test_parse_vulnerabilities_invalid_json() -> None:
    """Test that _parse_vulnerabilities raises error for invalid JSON."""
    with pytest.raises(dependency_audit.DependencyAuditError) as exc_info:
        dependency_audit._parse_vulnerabilities("{invalid json}")

    assert "Failed to parse" in str(exc_info.value)


def test_print_summary_no_findings(capsys) -> None:
    """Test that _print_summary prints success message for no findings."""
    dependency_audit._print_summary([])

    captured = capsys.readouterr()
    assert "No known vulnerabilities found" in captured.out


def test_print_summary_with_findings(capsys) -> None:
    """Test that _print_summary prints findings correctly."""
    findings = [
        {
            "name": "pkg",
            "version": "1.0.0",
            "id": "CVE-2024-1234",
            "aliases": ("GHSA-xxxx",),
            "fix_versions": ("1.0.1",),
            "description": "Test vuln",
            "severity": "high",
        }
    ]

    dependency_audit._print_summary(findings)

    captured = capsys.readouterr()
    assert "Found" in captured.out
    assert "pkg==1.0.0" in captured.out
    assert "CVE-2024-1234" in captured.out


def test_write_report_creates_json(tmp_path: Path) -> None:
    """Test that _write_report writes valid JSON."""
    findings = [
        {
            "name": "pkg",
            "version": "1.0.0",
            "id": "CVE-2024-1234",
            "aliases": ("GHSA-xxxx",),
            "fix_versions": ("1.0.1",),
            "description": "Test vuln",
            "severity": "high",
        }
    ]
    output_file = tmp_path / "subdir" / "report.json"

    dependency_audit._write_report(findings, output_file)

    assert output_file.exists()
    content = json.loads(output_file.read_text(encoding="utf-8"))
    assert content["total_findings"] == 1
    assert len(content["packages"]) == 1


def test_is_mitigated_not_pip() -> None:
    """Test that _is_mitigated returns False for non-pip packages."""
    finding = {"name": "other-pkg", "id": "GHSA-4xh5-x5gv-qwph"}
    assert dependency_audit._is_mitigated(finding) is False


def test_is_mitigated_wrong_advisory() -> None:
    """Test that _is_mitigated returns False for wrong advisory ID."""
    finding = {"name": "pip", "id": "OTHER-GHSA"}
    assert dependency_audit._is_mitigated(finding) is False


@patch("scripts.dependency_audit.shutil.which")
def test_run_pip_audit_not_installed(mock_which: MagicMock, tmp_path: Path) -> None:
    """Test that _run_pip_audit raises error when pip-audit not installed."""
    mock_which.return_value = None
    req_file = tmp_path / "requirements.txt"
    req_file.write_text("", encoding="utf-8")

    with pytest.raises(dependency_audit.DependencyAuditError) as exc_info:
        dependency_audit._run_pip_audit("pip-audit", [req_file], False, [])

    assert "pip-audit is not installed" in str(exc_info.value)


@patch("scripts.dependency_audit.shutil.which")
@patch("scripts.dependency_audit.subprocess.run")
def test_run_pip_audit_execution_failure(
    mock_run: MagicMock, mock_which: MagicMock, tmp_path: Path
) -> None:
    """Test that _run_pip_audit handles execution failures."""
    mock_which.return_value = "/usr/bin/pip-audit"
    mock_run.return_value = MagicMock(returncode=2, stderr="some error")
    req_file = tmp_path / "requirements.txt"
    req_file.write_text("", encoding="utf-8")

    with pytest.raises(dependency_audit.DependencyAuditError) as exc_info:
        dependency_audit._run_pip_audit("pip-audit", [req_file], False, [])

    assert "failed with exit code 2" in str(exc_info.value)


@patch("scripts.dependency_audit.shutil.which")
@patch("scripts.dependency_audit.subprocess.run")
def test_run_pip_audit_success(mock_run: MagicMock, mock_which: MagicMock, tmp_path: Path) -> None:
    """Test that _run_pip_audit returns result on success."""
    mock_which.return_value = "/usr/bin/pip-audit"
    mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps({"dependencies": []}))
    req_file = tmp_path / "requirements.txt"
    req_file.write_text("", encoding="utf-8")

    result = dependency_audit._run_pip_audit("pip-audit", [req_file], False, [])

    assert result.returncode == 0


@patch("scripts.dependency_audit._run_pip_audit")
@patch("scripts.dependency_audit._resolve_requirements")
def test_main_no_vulnerabilities(
    mock_resolve: MagicMock, mock_run: MagicMock, tmp_path: Path
) -> None:
    """Test that main returns 0 when no vulnerabilities found."""
    req_file = tmp_path / "requirements.txt"
    req_file.write_text("numpy==1.0.0\n", encoding="utf-8")
    mock_resolve.return_value = [req_file]
    mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps({"dependencies": []}))

    exit_code = dependency_audit.main(["-r", str(req_file)])

    assert exit_code == 0


@patch("scripts.dependency_audit._run_pip_audit")
@patch("scripts.dependency_audit._resolve_requirements")
def test_main_with_vulnerabilities(
    mock_resolve: MagicMock, mock_run: MagicMock, tmp_path: Path
) -> None:
    """Test that main returns 1 when vulnerabilities found."""
    req_file = tmp_path / "requirements.txt"
    req_file.write_text("example-pkg==1.0.0\n", encoding="utf-8")
    mock_resolve.return_value = [req_file]
    mock_run.return_value = MagicMock(
        returncode=1,
        stdout=json.dumps(
            {
                "dependencies": [
                    {
                        "name": "example-pkg",
                        "version": "1.0.0",
                        "vulns": [
                            {
                                "id": "CVE-2024-1234",
                                "aliases": [],
                                "fix_versions": ["1.0.1"],
                                "description": "Test",
                                "severity": "high",
                            }
                        ],
                    }
                ]
            }
        ),
    )

    exit_code = dependency_audit.main(["-r", str(req_file)])

    assert exit_code == 1


@patch("scripts.dependency_audit._run_pip_audit")
@patch("scripts.dependency_audit._resolve_requirements")
def test_main_fail_on_none(mock_resolve: MagicMock, mock_run: MagicMock, tmp_path: Path) -> None:
    """Test that main returns 0 with --fail-on=none even with vulnerabilities."""
    req_file = tmp_path / "requirements.txt"
    req_file.write_text("example-pkg==1.0.0\n", encoding="utf-8")
    mock_resolve.return_value = [req_file]
    mock_run.return_value = MagicMock(
        returncode=1,
        stdout=json.dumps(
            {
                "dependencies": [
                    {
                        "name": "example-pkg",
                        "version": "1.0.0",
                        "vulns": [
                            {
                                "id": "CVE-2024-1234",
                                "aliases": [],
                                "fix_versions": [],
                                "description": "",
                                "severity": None,
                            }
                        ],
                    }
                ]
            }
        ),
    )

    exit_code = dependency_audit.main(["-r", str(req_file), "--fail-on", "none"])

    assert exit_code == 0


@patch("scripts.dependency_audit._run_pip_audit")
@patch("scripts.dependency_audit._resolve_requirements")
def test_main_writes_json_report(
    mock_resolve: MagicMock, mock_run: MagicMock, tmp_path: Path
) -> None:
    """Test that main writes JSON report when requested."""
    req_file = tmp_path / "requirements.txt"
    req_file.write_text("numpy==1.0.0\n", encoding="utf-8")
    mock_resolve.return_value = [req_file]
    mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps({"dependencies": []}))
    report_file = tmp_path / "report.json"

    dependency_audit.main(["-r", str(req_file), "--write-json", str(report_file)])

    assert report_file.exists()
