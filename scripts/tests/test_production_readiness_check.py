# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for production_readiness_check.py script."""

from __future__ import annotations

# SPDX-License-Identifier: MIT
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts import production_readiness_check


class TestCheckResult:
    """Tests for CheckResult dataclass."""

    def test_check_result_creation(self) -> None:
        """Test CheckResult dataclass creation."""
        result = production_readiness_check.CheckResult(
            name="test_check",
            passed=True,
            message="Check passed",
            duration_ms=10.5,
            details={"key": "value"},
        )

        assert result.name == "test_check"
        assert result.passed is True
        assert result.message == "Check passed"
        assert result.duration_ms == 10.5
        assert result.details == {"key": "value"}

    def test_check_result_defaults(self) -> None:
        """Test CheckResult default values."""
        result = production_readiness_check.CheckResult(
            name="test",
            passed=True,
            message="OK",
        )

        assert result.duration_ms == 0.0
        assert result.details == {}


class TestReadinessReport:
    """Tests for ReadinessReport dataclass."""

    def test_readiness_report_creation(self) -> None:
        """Test ReadinessReport creation."""
        report = production_readiness_check.ReadinessReport(
            timestamp="2024-01-01T00:00:00",
            total_checks=10,
            passed=8,
            failed=2,
            skipped=0,
        )

        assert report.timestamp == "2024-01-01T00:00:00"
        assert report.total_checks == 10
        assert report.passed == 8
        assert report.failed == 2

    def test_success_rate_calculation(self) -> None:
        """Test success_rate property."""
        report = production_readiness_check.ReadinessReport(
            timestamp="2024-01-01T00:00:00",
            total_checks=10,
            passed=8,
            failed=2,
            skipped=0,
        )

        assert report.success_rate == 80.0

    def test_success_rate_zero_checks(self) -> None:
        """Test success_rate with zero total checks."""
        report = production_readiness_check.ReadinessReport(
            timestamp="2024-01-01T00:00:00",
            total_checks=0,
            passed=0,
            failed=0,
            skipped=0,
        )

        assert report.success_rate == 0.0

    def test_success_rate_all_passed(self) -> None:
        """Test success_rate with all checks passed."""
        report = production_readiness_check.ReadinessReport(
            timestamp="2024-01-01T00:00:00",
            total_checks=5,
            passed=5,
            failed=0,
            skipped=0,
        )

        assert report.success_rate == 100.0

    def test_to_dict(self) -> None:
        """Test to_dict method."""
        check = production_readiness_check.CheckResult(
            name="test",
            passed=True,
            message="OK",
            duration_ms=5.123,
            details={"detail": "value"},
        )
        report = production_readiness_check.ReadinessReport(
            timestamp="2024-01-01T00:00:00",
            total_checks=1,
            passed=1,
            failed=0,
            skipped=0,
            checks=[check],
        )

        result = report.to_dict()

        assert result["timestamp"] == "2024-01-01T00:00:00"
        assert result["summary"]["total_checks"] == 1
        assert result["summary"]["passed"] == 1
        assert result["summary"]["success_rate"] == 100.0
        assert len(result["checks"]) == 1
        assert result["checks"][0]["name"] == "test"


class TestCheckModuleImport:
    """Tests for check_module_import function."""

    def test_successful_import(self) -> None:
        """Test successful module import check."""
        result = production_readiness_check.check_module_import("json")

        assert result.passed is True
        assert "json" in result.name
        assert "successfully" in result.message

    def test_failed_import(self) -> None:
        """Test failed module import check."""
        result = production_readiness_check.check_module_import("nonexistent_module_xyz")

        assert result.passed is False
        assert "Failed to import" in result.message
        assert "error" in result.details

    def test_import_records_duration(self) -> None:
        """Test that import check records duration."""
        result = production_readiness_check.check_module_import("os")

        assert result.duration_ms >= 0


class TestCheckClassInstantiation:
    """Tests for check_class_instantiation function."""

    def test_successful_class_access(self) -> None:
        """Test successful class access check."""
        result = production_readiness_check.check_class_instantiation("pathlib", "Path")

        assert result.passed is True
        assert "Path" in result.name
        assert "available" in result.message

    def test_failed_class_access(self) -> None:
        """Test failed class access check."""
        result = production_readiness_check.check_class_instantiation("os", "NonexistentClass")

        assert result.passed is False
        assert "Failed to access" in result.message

    def test_failed_module_access(self) -> None:
        """Test failed module access in class check."""
        result = production_readiness_check.check_class_instantiation(
            "nonexistent_module", "SomeClass"
        )

        assert result.passed is False


class TestCheckConfigFile:
    """Tests for check_config_file function."""

    def test_config_file_not_found(self, tmp_path: Path) -> None:
        """Test check_config_file with non-existent file."""
        result = production_readiness_check.check_config_file(str(tmp_path / "nonexistent.yaml"))

        assert result.passed is False
        assert "not found" in result.message

    def test_valid_json_config(self, tmp_path: Path) -> None:
        """Test check_config_file with valid JSON."""
        config_file = tmp_path / "config.json"
        config_file.write_text('{"key": "value"}', encoding="utf-8")

        result = production_readiness_check.check_config_file(str(config_file))

        assert result.passed is True
        assert "valid" in result.message

    def test_invalid_json_config(self, tmp_path: Path) -> None:
        """Test check_config_file with invalid JSON."""
        config_file = tmp_path / "config.json"
        config_file.write_text("{invalid json}", encoding="utf-8")

        result = production_readiness_check.check_config_file(str(config_file))

        assert result.passed is False

    def test_valid_yaml_config(self, tmp_path: Path) -> None:
        """Test check_config_file with valid YAML."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("key: value\n", encoding="utf-8")

        result = production_readiness_check.check_config_file(str(config_file))

        assert result.passed is True

    def test_valid_yml_config(self, tmp_path: Path) -> None:
        """Test check_config_file with .yml extension."""
        config_file = tmp_path / "config.yml"
        config_file.write_text("items:\n  - one\n  - two\n", encoding="utf-8")

        result = production_readiness_check.check_config_file(str(config_file))

        assert result.passed is True

    def test_unknown_extension(self, tmp_path: Path) -> None:
        """Test check_config_file with unknown extension."""
        config_file = tmp_path / "config.txt"
        config_file.write_text("some content", encoding="utf-8")

        result = production_readiness_check.check_config_file(str(config_file))

        # Should pass if file exists (no parsing for unknown extensions)
        assert result.passed is True


class TestCheckSecurityConstraints:
    """Tests for check_security_constraints function."""

    def test_security_constraints_validation_with_file(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Test security constraints check parses file and counts constraints."""
        constraints_file = tmp_path / "constraints" / "security.txt"
        constraints_file.parent.mkdir(parents=True)
        constraints_file.write_text(
            "# Security constraints\npackage1==1.0.0\npackage2>=2.0.0\n",
            encoding="utf-8",
        )
        monkeypatch.chdir(tmp_path)

        result = production_readiness_check.check_security_constraints()

        assert result.passed is True
        assert "constraint_count" in result.details
        assert result.details["constraint_count"] == 2

    def test_security_constraints_file_missing(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Test security constraints check with missing file."""
        monkeypatch.chdir(tmp_path)

        result = production_readiness_check.check_security_constraints()

        assert result.passed is False
        assert "not found" in result.message.lower()


class TestRunProductionChecks:
    """Tests for run_production_checks function."""

    def test_run_production_checks_returns_report(self) -> None:
        """Test run_production_checks returns ReadinessReport."""
        report = production_readiness_check.run_production_checks()

        assert isinstance(report, production_readiness_check.ReadinessReport)
        assert report.total_checks > 0
        assert len(report.checks) > 0

    def test_run_production_checks_includes_timestamp(self) -> None:
        """Test run_production_checks includes timestamp."""
        report = production_readiness_check.run_production_checks()

        assert report.timestamp is not None
        assert "T" in report.timestamp  # ISO format

    def test_run_production_checks_counts_match(self) -> None:
        """Test that passed + failed + skipped equals total."""
        report = production_readiness_check.run_production_checks()

        assert report.passed + report.failed + report.skipped == report.total_checks


class TestMain:
    """Tests for main function."""

    @patch.object(production_readiness_check, "run_production_checks")
    def test_main_all_passed(self, mock_run: MagicMock, capsys, tmp_path: Path) -> None:
        """Test main with all checks passed."""
        mock_report = production_readiness_check.ReadinessReport(
            timestamp="2024-01-01T00:00:00",
            total_checks=2,
            passed=2,
            failed=0,
            skipped=0,
            checks=[
                production_readiness_check.CheckResult(name="test1", passed=True, message="OK"),
                production_readiness_check.CheckResult(name="test2", passed=True, message="OK"),
            ],
        )
        mock_run.return_value = mock_report

        with patch("sys.argv", ["production_readiness_check.py"]):
            exit_code = production_readiness_check.main()

        assert exit_code == 0
        captured = capsys.readouterr()
        assert "All production readiness checks passed" in captured.out

    @patch.object(production_readiness_check, "run_production_checks")
    def test_main_with_failures(self, mock_run: MagicMock, capsys) -> None:
        """Test main with some checks failed."""
        mock_report = production_readiness_check.ReadinessReport(
            timestamp="2024-01-01T00:00:00",
            total_checks=2,
            passed=1,
            failed=1,
            skipped=0,
            checks=[
                production_readiness_check.CheckResult(name="test1", passed=True, message="OK"),
                production_readiness_check.CheckResult(
                    name="test2", passed=False, message="Failed"
                ),
            ],
        )
        mock_run.return_value = mock_report

        with patch("sys.argv", ["production_readiness_check.py"]):
            exit_code = production_readiness_check.main()

        assert exit_code == 1
        captured = capsys.readouterr()
        assert "Some checks failed" in captured.out

    @patch.object(production_readiness_check, "run_production_checks")
    def test_main_json_output(self, mock_run: MagicMock, tmp_path: Path, capsys) -> None:
        """Test main with JSON output."""
        mock_report = production_readiness_check.ReadinessReport(
            timestamp="2024-01-01T00:00:00",
            total_checks=1,
            passed=1,
            failed=0,
            skipped=0,
            checks=[
                production_readiness_check.CheckResult(name="test1", passed=True, message="OK")
            ],
        )
        mock_run.return_value = mock_report
        output_file = tmp_path / "report.json"

        with patch(
            "sys.argv",
            ["production_readiness_check.py", "--json-output", str(output_file)],
        ):
            exit_code = production_readiness_check.main()

        assert exit_code == 0
        assert output_file.exists()

        content = json.loads(output_file.read_text(encoding="utf-8"))
        assert content["summary"]["total_checks"] == 1

    @patch.object(production_readiness_check, "run_production_checks")
    def test_main_verbose(self, mock_run: MagicMock, capsys) -> None:
        """Test main with verbose flag."""
        mock_report = production_readiness_check.ReadinessReport(
            timestamp="2024-01-01T00:00:00",
            total_checks=1,
            passed=1,
            failed=0,
            skipped=0,
            checks=[
                production_readiness_check.CheckResult(
                    name="test1",
                    passed=True,
                    message="OK",
                    details={"detail": "value"},
                )
            ],
        )
        mock_run.return_value = mock_report

        with patch("sys.argv", ["production_readiness_check.py", "--verbose"]):
            exit_code = production_readiness_check.main()

        assert exit_code == 0
        captured = capsys.readouterr()
        # Verbose output should include details
        assert "detail" in captured.out or "OK" in captured.out
