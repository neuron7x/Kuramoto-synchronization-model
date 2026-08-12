# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for export_geosync_schema.py script."""

from __future__ import annotations

# SPDX-License-Identifier: MIT
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from scripts import export_geosync_schema


def test_parse_args_defaults() -> None:
    """Test that parse_args returns correct defaults."""
    args = export_geosync_schema.parse_args([])

    assert args.output is None
    assert args.indent == 2


def test_parse_args_custom_output(tmp_path: Path) -> None:
    """Test parse_args with custom output path."""
    output = tmp_path / "schema.json"
    args = export_geosync_schema.parse_args(["--output", str(output)])

    assert args.output == output


def test_parse_args_custom_indent() -> None:
    """Test parse_args with custom indent value."""
    args = export_geosync_schema.parse_args(["--indent", "4"])

    assert args.indent == 4


@patch("scripts.export_geosync_schema.export_geosync_settings_schema")
def test_main_with_output_file(mock_export: MagicMock, tmp_path: Path) -> None:
    """Test main function writes to output file."""
    output = tmp_path / "test_schema.json"
    mock_schema = {"type": "object", "properties": {"test": {"type": "string"}}}
    mock_export.return_value = mock_schema

    with patch("sys.argv", ["export_geosync_schema.py", "--output", str(output)]):
        export_geosync_schema.main()

    mock_export.assert_called_once_with(output, indent=2)


@patch("scripts.export_geosync_schema.export_geosync_settings_schema")
def test_main_stdout(mock_export: MagicMock, capsys) -> None:
    """Test main function prints to stdout when no output file specified."""
    mock_schema = {"type": "object", "properties": {"test": {"type": "string"}}}
    mock_export.return_value = mock_schema

    with patch("sys.argv", ["export_geosync_schema.py"]):
        export_geosync_schema.main()

    mock_export.assert_called_once_with(None, indent=2)

    captured = capsys.readouterr()
    output_schema = json.loads(captured.out)
    assert output_schema == mock_schema


@patch("scripts.export_geosync_schema.export_geosync_settings_schema")
def test_main_custom_indent(mock_export: MagicMock, capsys) -> None:
    """Test main function uses custom indent."""
    mock_schema = {"test": "value"}
    mock_export.return_value = mock_schema

    with patch("sys.argv", ["export_geosync_schema.py", "--indent", "4"]):
        export_geosync_schema.main()

    mock_export.assert_called_once_with(None, indent=4)

    captured = capsys.readouterr()
    # Verify indent is applied in output
    assert captured.out.count("    ") > 0  # 4-space indent
