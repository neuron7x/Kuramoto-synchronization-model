"""Tests for scripts/sanity_cleanup package."""

from __future__ import annotations

# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
import json
import tempfile
from pathlib import Path

from scripts.sanity_cleanup import models, runner, utils


class TestModels:
    """Tests for sanity_cleanup.models module."""

    def test_task_status_enum_values(self) -> None:
        """Test TaskStatus enum values."""
        assert models.TaskStatus.SUCCESS.value == "success"
        assert models.TaskStatus.SKIPPED.value == "skipped"
        assert models.TaskStatus.FAILED.value == "failed"

    def test_task_report_dataclass(self) -> None:
        """Test TaskReport dataclass creation."""
        report = models.TaskReport(
            name="test_task",
            status=models.TaskStatus.SUCCESS,
            summary="All good",
            details=["Detail 1", "Detail 2"],
        )

        assert report.name == "test_task"
        assert report.status == models.TaskStatus.SUCCESS
        assert report.summary == "All good"
        assert len(report.details) == 2

    def test_task_report_default_details(self) -> None:
        """Test TaskReport default values."""
        report = models.TaskReport(
            name="task",
            status=models.TaskStatus.SUCCESS,
            summary="OK",
        )

        assert report.details == ()
        assert report.artifacts is None

    def test_cleanup_options_defaults(self) -> None:
        """Test CleanupOptions default values."""
        opts = models.CleanupOptions()

        assert opts.dry_run is False
        assert opts.archive_legacy is False
        assert opts.include_patterns is None
        assert opts.exclude_patterns is None

    def test_cleanup_options_custom_values(self) -> None:
        """Test CleanupOptions with custom values."""
        opts = models.CleanupOptions(
            dry_run=True,
            archive_legacy=True,
            include_patterns=["*.py"],
            exclude_patterns=["test_*"],
        )

        assert opts.dry_run is True
        assert opts.archive_legacy is True
        assert opts.include_patterns == ["*.py"]
        assert opts.exclude_patterns == ["test_*"]

    def test_task_context_dataclass(self) -> None:
        """Test TaskContext dataclass creation."""
        opts = models.CleanupOptions()
        with tempfile.TemporaryDirectory() as temp_dir:
            test_path = Path(temp_dir)
            context = models.TaskContext(
                root=test_path,
                options=opts,
            )

            assert context.root == test_path
            assert context.options is opts


class TestUtils:
    """Tests for sanity_cleanup.utils module."""

    def test_safe_relpath_absolute_path(self, tmp_path: Path) -> None:
        """Test safe_relpath with absolute path."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("test", encoding="utf-8")

        result = utils.safe_relpath(test_file, start=tmp_path)

        assert result == "test.txt"

    def test_safe_relpath_nested_path(self, tmp_path: Path) -> None:
        """Test safe_relpath with nested path."""
        nested = tmp_path / "sub" / "nested"
        nested.mkdir(parents=True)
        test_file = nested / "file.txt"
        test_file.write_text("test", encoding="utf-8")

        result = utils.safe_relpath(test_file, start=tmp_path)

        assert result == "sub/nested/file.txt"

    def test_safe_relpath_outside_base(self, tmp_path: Path) -> None:
        """Test safe_relpath with path outside base."""
        other_dir = tmp_path / "other"
        other_dir.mkdir()
        file_outside = other_dir / "file.txt"
        file_outside.write_text("content", encoding="utf-8")

        base = tmp_path / "base"
        base.mkdir()

        result = utils.safe_relpath(file_outside, start=base)

        # Should return absolute path when outside base
        assert "other" in result

    def test_format_path(self, tmp_path: Path) -> None:
        """Test format_path function."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("test", encoding="utf-8")

        result = utils.format_path(test_file)

        assert isinstance(result, str)
        assert "test.txt" in result

    def test_sha256sum(self, tmp_path: Path) -> None:
        """Test sha256sum computes correct hash."""
        test_file = tmp_path / "data.bin"
        test_file.write_bytes(b"hello world")

        result = utils.sha256sum(test_file)

        # Known SHA-256 hash of "hello world"
        expected = "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"
        assert result == expected

    def test_sha256sum_empty_file(self, tmp_path: Path) -> None:
        """Test sha256sum with empty file."""
        test_file = tmp_path / "empty.bin"
        test_file.write_bytes(b"")

        result = utils.sha256sum(test_file)

        # Known SHA-256 hash of empty file
        expected = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        assert result == expected

    def test_sha256sum_large_file(self, tmp_path: Path) -> None:
        """Test sha256sum with larger file uses streaming."""
        test_file = tmp_path / "large.bin"
        # Create a file larger than the default chunk size
        data = b"x" * (65536 * 3)
        test_file.write_bytes(data)

        result = utils.sha256sum(test_file)

        assert isinstance(result, str)
        assert len(result) == 64  # SHA-256 hex digest length


class TestRunner:
    """Tests for sanity_cleanup.runner module."""

    def test_cleanup_result_exit_code_success(self, tmp_path: Path) -> None:
        """Test CleanupResult.exit_code with all successful tasks."""
        reports = [
            models.TaskReport(
                name="task1", status=models.TaskStatus.SUCCESS, summary="OK"
            ),
            models.TaskReport(
                name="task2", status=models.TaskStatus.SKIPPED, summary="Skipped"
            ),
        ]
        result = runner.CleanupResult(root=tmp_path, reports=reports)

        assert result.exit_code == 0

    def test_cleanup_result_exit_code_failure(self, tmp_path: Path) -> None:
        """Test CleanupResult.exit_code with failed task."""
        reports = [
            models.TaskReport(
                name="task1", status=models.TaskStatus.SUCCESS, summary="OK"
            ),
            models.TaskReport(
                name="task2", status=models.TaskStatus.FAILED, summary="Error"
            ),
        ]
        result = runner.CleanupResult(root=tmp_path, reports=reports)

        assert result.exit_code == 1

    def test_write_summary_creates_file(self, tmp_path: Path) -> None:
        """Test _write_summary creates summary JSON file."""
        reports = [
            models.TaskReport(
                name="test_task",
                status=models.TaskStatus.SUCCESS,
                summary="All good",
                details=["Detail 1"],
                artifacts={"output": tmp_path / "output.txt"},
            )
        ]
        result = runner.CleanupResult(root=tmp_path, reports=reports)

        summary_path = runner._write_summary(result)

        assert summary_path is not None
        assert summary_path.exists()

        content = json.loads(summary_path.read_text(encoding="utf-8"))
        assert "generated_at" in content
        assert content["root"] == str(tmp_path)
        assert len(content["tasks"]) == 1
        assert content["tasks"][0]["name"] == "test_task"

    def test_execute_task_success(self, tmp_path: Path) -> None:
        """Test _execute_task with successful task."""

        def successful_task(ctx: models.TaskContext) -> models.TaskReport:
            return models.TaskReport(
                name="successful_task",
                status=models.TaskStatus.SUCCESS,
                summary="Completed",
            )

        context = models.TaskContext(
            root=tmp_path, options=models.CleanupOptions()
        )

        report = runner._execute_task(successful_task, context)

        assert report.status == models.TaskStatus.SUCCESS
        assert report.name == "successful_task"

    def test_execute_task_exception(self, tmp_path: Path) -> None:
        """Test _execute_task handles exceptions."""

        def failing_task(ctx: models.TaskContext) -> models.TaskReport:
            raise ValueError("Something went wrong")

        context = models.TaskContext(
            root=tmp_path, options=models.CleanupOptions()
        )

        report = runner._execute_task(failing_task, context)

        assert report.status == models.TaskStatus.FAILED
        assert "Something went wrong" in report.summary

    def test_run_all_creates_summary(self, tmp_path: Path) -> None:
        """Test run_all creates summary file."""
        result = runner.run_all(tmp_path)

        assert result.root == tmp_path.resolve()
        assert len(result.reports) > 0

        summary_path = tmp_path / "reports" / "sanity_cleanup_summary.json"
        assert summary_path.exists()

    def test_run_all_with_options(self, tmp_path: Path) -> None:
        """Test run_all with custom options."""
        opts = models.CleanupOptions(dry_run=True)

        result = runner.run_all(tmp_path, options=opts)

        assert result.root == tmp_path.resolve()
        assert len(result.reports) > 0

    def test_run_all_returns_cleanup_result(self, tmp_path: Path) -> None:
        """Test run_all returns CleanupResult instance."""
        result = runner.run_all(tmp_path)

        assert isinstance(result, runner.CleanupResult)
        assert isinstance(result.reports, tuple)
