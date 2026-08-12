# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for integrate_kuramoto_ricci.py script."""

from __future__ import annotations

# SPDX-License-Identifier: MIT
from pathlib import Path

import pytest

from scripts import integrate_kuramoto_ricci


def test_resolve_path_absolute(tmp_path: Path) -> None:
    """Test _resolve_path with absolute path."""
    test_file = tmp_path / "test.txt"
    test_file.write_text("test", encoding="utf-8")

    result = integrate_kuramoto_ricci._resolve_path(test_file)
    assert result == test_file


def test_resolve_path_missing_file_raises() -> None:
    """Test _resolve_path raises for missing file."""
    with pytest.raises(FileNotFoundError):
        integrate_kuramoto_ricci._resolve_path(Path("/nonexistent/file.txt"))


def test_resolve_path_missing_allowed(tmp_path: Path) -> None:
    """Test _resolve_path with allow_missing=True."""
    missing_path = tmp_path / "missing.txt"
    result = integrate_kuramoto_ricci._resolve_path(missing_path, allow_missing=True)
    assert result == missing_path


def test_path_default_uses_env_var(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test _path_default uses environment variable."""
    env_path = tmp_path / "from_env"
    env_path.mkdir()
    monkeypatch.setenv("TEST_ENV_VAR", str(env_path))

    result = integrate_kuramoto_ricci._path_default("TEST_ENV_VAR", Path("fallback/path"))

    assert result == env_path


def test_path_default_uses_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test _path_default uses fallback when env var not set."""
    monkeypatch.delenv("TEST_MISSING_VAR", raising=False)

    result = integrate_kuramoto_ricci._path_default("TEST_MISSING_VAR", Path("fallback/path"))

    # Should use fallback relative to REPO_ROOT
    assert "fallback/path" in str(result) or "fallback" in str(result)


def test_parse_args_required_data() -> None:
    """Test parse_args requires --data argument."""
    with pytest.raises(SystemExit):
        integrate_kuramoto_ricci.parse_args([])


def test_parse_args_with_data(tmp_path: Path) -> None:
    """Test parse_args with required --data."""
    data_file = tmp_path / "data.csv"
    data_file.write_text("close\n100\n", encoding="utf-8")

    args = integrate_kuramoto_ricci.parse_args(["--data", str(data_file)])

    assert args.data == data_file


def test_parse_args_mode_default() -> None:
    """Test parse_args default mode is analyze."""
    args = integrate_kuramoto_ricci.parse_args(["--data", "test.csv"])
    assert args.mode == "analyze"


def test_parse_args_dry_run() -> None:
    """Test parse_args with --dry-run flag."""
    args = integrate_kuramoto_ricci.parse_args(["--data", "test.csv", "--dry-run"])
    assert args.dry_run is True


def test_parse_args_config_overrides() -> None:
    """Test parse_args with config overrides."""
    args = integrate_kuramoto_ricci.parse_args(
        [
            "--data",
            "test.csv",
            "--config-override",
            "key1=value1",
            "--config-override",
            "key2=value2",
        ]
    )

    assert len(args.config_overrides) == 2
    assert "key1=value1" in args.config_overrides
    assert "key2=value2" in args.config_overrides


def test_parse_args_yes_flag() -> None:
    """Test parse_args with --yes flag."""
    args = integrate_kuramoto_ricci.parse_args(["--data", "test.csv", "--yes"])
    assert args.yes is True


def test_ensure_output_dir_creates_new(tmp_path: Path) -> None:
    """Test _ensure_output_dir creates new directory."""
    new_dir = tmp_path / "new_output"

    integrate_kuramoto_ricci._ensure_output_dir(new_dir, confirm=False)

    assert new_dir.exists()


def test_ensure_output_dir_existing_empty_allowed(tmp_path: Path) -> None:
    """Test _ensure_output_dir allows existing empty directory."""
    existing_dir = tmp_path / "existing"
    existing_dir.mkdir()

    # Should not raise
    integrate_kuramoto_ricci._ensure_output_dir(existing_dir, confirm=False)


def test_ensure_output_dir_existing_nonempty_blocked(tmp_path: Path) -> None:
    """Test _ensure_output_dir blocks non-empty directory without confirm."""
    existing_dir = tmp_path / "existing"
    existing_dir.mkdir()
    (existing_dir / "file.txt").write_text("content", encoding="utf-8")

    with pytest.raises(RuntimeError) as exc_info:
        integrate_kuramoto_ricci._ensure_output_dir(existing_dir, confirm=False)

    assert "not empty" in str(exc_info.value)


def test_ensure_output_dir_existing_nonempty_confirmed(tmp_path: Path) -> None:
    """Test _ensure_output_dir allows non-empty directory with confirm."""
    existing_dir = tmp_path / "existing"
    existing_dir.mkdir()
    (existing_dir / "file.txt").write_text("content", encoding="utf-8")

    # Should not raise when confirm=True
    integrate_kuramoto_ricci._ensure_output_dir(existing_dir, confirm=True)


def test_print_plan_output(tmp_path: Path, capsys) -> None:
    """Test _print_plan prints expected output."""
    data_path = tmp_path / "data.csv"
    config_path = tmp_path / "config.yaml"
    output_dir = tmp_path / "output"

    integrate_kuramoto_ricci._print_plan(data_path, config_path, output_dir, ["key=value"])

    captured = capsys.readouterr()
    assert "[dry-run]" in captured.out
    assert str(data_path) in captured.out
    assert str(config_path) in captured.out
    assert str(output_dir) in captured.out
    assert "key=value" in captured.out


def test_print_plan_no_overrides(tmp_path: Path, capsys) -> None:
    """Test _print_plan with no config overrides."""
    integrate_kuramoto_ricci._print_plan(
        tmp_path / "data.csv",
        tmp_path / "config.yaml",
        tmp_path / "output",
        [],
    )

    captured = capsys.readouterr()
    assert "<none>" in captured.out


def test_main_dry_run(tmp_path: Path, capsys) -> None:
    """Test main with --dry-run returns 0."""
    data_file = tmp_path / "data.csv"
    data_file.write_text("close,volume\n100,1000\n", encoding="utf-8")

    config_file = tmp_path / "config.yaml"
    config_file.write_text("key: value\n", encoding="utf-8")

    exit_code = integrate_kuramoto_ricci.main(
        [
            "--data",
            str(data_file),
            "--config",
            str(config_file),
            "--output",
            str(tmp_path / "output"),
            "--dry-run",
        ]
    )

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "[dry-run]" in captured.out


def test_main_missing_data_file() -> None:
    """Test main exits when data file is missing."""
    with pytest.raises(SystemExit) as exc_info:
        integrate_kuramoto_ricci.main(
            [
                "--data",
                "/nonexistent/data.csv",
            ]
        )

    # SystemExit message contains "not found" for missing file
    exit_message = str(exc_info.value).lower()
    assert "not found" in exit_message, f"Expected 'not found' in exit message: {exc_info.value}"


def test_main_missing_config_file(tmp_path: Path) -> None:
    """Test main exits when config file is missing."""
    data_file = tmp_path / "data.csv"
    data_file.write_text("close\n100\n", encoding="utf-8")

    with pytest.raises(SystemExit) as exc_info:
        integrate_kuramoto_ricci.main(
            [
                "--data",
                str(data_file),
                "--config",
                "/nonexistent/config.yaml",
            ]
        )

    # SystemExit message contains "not found" for missing config
    exit_message = str(exc_info.value).lower()
    assert "not found" in exit_message, f"Expected 'not found' in exit message: {exc_info.value}"


def test_main_output_dir_not_empty_blocked(tmp_path: Path) -> None:
    """Test main exits when output dir is not empty and --yes not provided."""
    data_file = tmp_path / "data.csv"
    data_file.write_text("close,volume\n100,1000\n", encoding="utf-8")

    config_file = tmp_path / "config.yaml"
    config_file.write_text("key: value\n", encoding="utf-8")

    output_dir = tmp_path / "output"
    output_dir.mkdir()
    (output_dir / "existing.txt").write_text("existing", encoding="utf-8")

    with pytest.raises(SystemExit) as exc_info:
        integrate_kuramoto_ricci.main(
            [
                "--data",
                str(data_file),
                "--config",
                str(config_file),
                "--output",
                str(output_dir),
            ]
        )

    # SystemExit message contains "not empty" for non-empty directory
    exit_message = str(exc_info.value).lower()
    assert "not empty" in exit_message, f"Expected 'not empty' in exit message: {exc_info.value}"


def test_constants_defined() -> None:
    """Test that module constants are defined."""
    assert integrate_kuramoto_ricci.DEFAULT_CONFIG_ENV is not None
    assert integrate_kuramoto_ricci.DEFAULT_OUTPUT_ENV is not None
    assert integrate_kuramoto_ricci.REPO_ROOT is not None
