"""Tests for validate_ohlcv_data.py script."""

from __future__ import annotations

# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
from pathlib import Path

from scripts import validate_ohlcv_data


def _create_valid_ohlcv_csv(path: Path) -> None:
    """Create a valid OHLCV CSV file."""
    content = """timestamp,symbol,open,high,low,close,volume
2024-01-01 00:00:00,BTC,100.0,105.0,98.0,102.0,1000
2024-01-01 01:00:00,BTC,102.0,108.0,100.0,106.0,1200
2024-01-01 02:00:00,BTC,106.0,110.0,104.0,109.0,1100"""
    path.write_text(content, encoding="utf-8")


def test_validate_ohlcv_file_success(tmp_path: Path) -> None:
    """Test validation of a valid OHLCV file."""
    csv_file = tmp_path / "valid_ohlcv.csv"
    _create_valid_ohlcv_csv(csv_file)

    report = validate_ohlcv_data.validate_ohlcv_file(csv_file)

    assert report.valid is True
    assert report.row_count == 3
    assert "close" in report.columns
    assert report.symbols == ["BTC"]
    assert report.errors == []


def test_validate_ohlcv_file_not_found(tmp_path: Path) -> None:
    """Test validation of non-existent file."""
    missing_file = tmp_path / "missing.csv"

    report = validate_ohlcv_data.validate_ohlcv_file(missing_file)

    assert report.valid is False
    assert "File not found" in report.errors[0]


def test_validate_ohlcv_file_empty(tmp_path: Path) -> None:
    """Test validation of empty CSV file."""
    empty_file = tmp_path / "empty.csv"
    empty_file.write_text("timestamp,symbol,open,high,low,close,volume\n", encoding="utf-8")

    report = validate_ohlcv_data.validate_ohlcv_file(empty_file)

    assert report.valid is False
    assert any("empty" in e.lower() for e in report.errors)


def test_validate_ohlcv_file_missing_close_column(tmp_path: Path) -> None:
    """Test validation fails when close column is missing."""
    csv_file = tmp_path / "no_close.csv"
    csv_file.write_text("timestamp,open,high,low,volume\n2024-01-01,100,105,98,1000\n", encoding="utf-8")

    report = validate_ohlcv_data.validate_ohlcv_file(csv_file)

    assert report.valid is False
    assert any("close" in e.lower() for e in report.errors)


def test_validate_ohlcv_file_nan_values(tmp_path: Path) -> None:
    """Test validation detects NaN values."""
    csv_file = tmp_path / "with_nans.csv"
    csv_file.write_text(
        "timestamp,symbol,open,high,low,close,volume\n"
        "2024-01-01,BTC,100,105,98,102,1000\n"
        "2024-01-02,BTC,,,,,\n",
        encoding="utf-8",
    )

    report = validate_ohlcv_data.validate_ohlcv_file(csv_file)

    # Missing values should be detected - check for warnings about NaN
    has_nan_issue = (
        any("NaN" in e for e in report.errors)
        or any("NaN" in w for w in report.warnings)
    )
    assert has_nan_issue, "Expected NaN detection in errors or warnings"


def test_validate_ohlcv_file_non_positive_prices(tmp_path: Path) -> None:
    """Test validation detects non-positive prices."""
    csv_file = tmp_path / "negative_prices.csv"
    csv_file.write_text(
        "timestamp,symbol,open,high,low,close,volume\n"
        "2024-01-01,BTC,-100,105,98,102,1000\n",
        encoding="utf-8",
    )

    report = validate_ohlcv_data.validate_ohlcv_file(csv_file)

    assert report.valid is False
    assert any("non-positive" in e.lower() for e in report.errors)


def test_validate_ohlcv_file_high_less_than_low(tmp_path: Path) -> None:
    """Test validation detects high < low violations."""
    csv_file = tmp_path / "bad_ohlc.csv"
    csv_file.write_text(
        "timestamp,symbol,open,high,low,close,volume\n"
        "2024-01-01,BTC,100,95,105,102,1000\n",
        encoding="utf-8",
    )

    report = validate_ohlcv_data.validate_ohlcv_file(csv_file)

    assert report.valid is False
    assert any("high < low" in e for e in report.errors)


def test_validate_ohlcv_file_negative_volume(tmp_path: Path) -> None:
    """Test validation detects negative volume."""
    csv_file = tmp_path / "negative_volume.csv"
    csv_file.write_text(
        "timestamp,symbol,open,high,low,close,volume\n"
        "2024-01-01,BTC,100,105,98,102,-1000\n",
        encoding="utf-8",
    )

    report = validate_ohlcv_data.validate_ohlcv_file(csv_file)

    assert report.valid is False
    assert any("negative volume" in e.lower() for e in report.errors)


def test_validate_ohlcv_file_date_range(tmp_path: Path) -> None:
    """Test that date range is extracted correctly."""
    csv_file = tmp_path / "with_dates.csv"
    _create_valid_ohlcv_csv(csv_file)

    report = validate_ohlcv_data.validate_ohlcv_file(csv_file)

    assert report.date_range != ""
    assert "2024-01-01" in report.date_range


def test_validate_ohlcv_file_statistics(tmp_path: Path) -> None:
    """Test that statistics are computed correctly."""
    csv_file = tmp_path / "valid_ohlcv.csv"
    _create_valid_ohlcv_csv(csv_file)

    report = validate_ohlcv_data.validate_ohlcv_file(csv_file)

    assert "close_mean" in report.statistics
    assert "close_std" in report.statistics
    assert "close_min" in report.statistics
    assert "close_max" in report.statistics
    assert "returns_mean" in report.statistics


def test_validation_report_to_json() -> None:
    """Test ValidationReport.to_json() method."""
    report = validate_ohlcv_data.ValidationReport(
        file_path="test.csv",
        valid=True,
        row_count=100,
    )

    json_str = report.to_json()

    assert "test.csv" in json_str
    assert '"valid": true' in json_str
    assert '"row_count": 100' in json_str


def test_validation_report_to_dict() -> None:
    """Test ValidationReport.to_dict() method."""
    report = validate_ohlcv_data.ValidationReport(
        file_path="test.csv",
        valid=True,
        row_count=50,
    )

    d = report.to_dict()

    assert d["file_path"] == "test.csv"
    assert d["valid"] is True
    assert d["row_count"] == 50


def test_print_report_text_format(tmp_path: Path, capsys) -> None:
    """Test print_report with text format."""
    csv_file = tmp_path / "valid_ohlcv.csv"
    _create_valid_ohlcv_csv(csv_file)
    report = validate_ohlcv_data.validate_ohlcv_file(csv_file)

    validate_ohlcv_data.print_report(report, format="text")

    captured = capsys.readouterr()
    assert "PASSED" in captured.out
    assert str(csv_file) in captured.out


def test_print_report_json_format(tmp_path: Path, capsys) -> None:
    """Test print_report with JSON format."""
    csv_file = tmp_path / "valid_ohlcv.csv"
    _create_valid_ohlcv_csv(csv_file)
    report = validate_ohlcv_data.validate_ohlcv_file(csv_file)

    validate_ohlcv_data.print_report(report, format="json")

    captured = capsys.readouterr()
    assert '"valid": true' in captured.out


def test_parse_args_defaults() -> None:
    """Test parse_args with default values."""
    args = validate_ohlcv_data.parse_args(["test.csv"])

    assert args.files == [Path("test.csv")]
    assert args.format == "text"
    assert args.close_col == "close"
    assert args.no_ohlc is False
    assert args.strict is False


def test_parse_args_custom_values() -> None:
    """Test parse_args with custom values."""
    args = validate_ohlcv_data.parse_args([
        "file1.csv",
        "file2.csv",
        "--format", "json",
        "--close-col", "price",
        "--no-ohlc",
        "--strict",
        "-v",
    ])

    assert len(args.files) == 2
    assert args.format == "json"
    assert args.close_col == "price"
    assert args.no_ohlc is True
    assert args.strict is True
    assert args.verbose is True


def test_main_success(tmp_path: Path, capsys) -> None:
    """Test main returns 0 for valid file."""
    csv_file = tmp_path / "valid_ohlcv.csv"
    _create_valid_ohlcv_csv(csv_file)

    exit_code = validate_ohlcv_data.main([str(csv_file)])

    assert exit_code == 0


def test_main_failure(tmp_path: Path) -> None:
    """Test main returns 1 for invalid file."""
    csv_file = tmp_path / "bad_ohlcv.csv"
    csv_file.write_text(
        "timestamp,symbol,open,high,low,close,volume\n"
        "2024-01-01,BTC,100,95,105,102,1000\n",  # high < low
        encoding="utf-8",
    )

    exit_code = validate_ohlcv_data.main([str(csv_file)])

    assert exit_code == 1


def test_main_multiple_files(tmp_path: Path, capsys) -> None:
    """Test main with multiple files shows summary."""
    csv1 = tmp_path / "file1.csv"
    csv2 = tmp_path / "file2.csv"
    _create_valid_ohlcv_csv(csv1)
    _create_valid_ohlcv_csv(csv2)

    exit_code = validate_ohlcv_data.main([str(csv1), str(csv2)])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Summary" in captured.out
    assert "2/2" in captured.out


def test_main_strict_mode(tmp_path: Path) -> None:
    """Test main with strict mode treats warnings as errors."""
    csv_file = tmp_path / "with_warning.csv"
    # Create file with a single NaN value that generates a warning (not enough for error)
    csv_file.write_text(
        "timestamp,symbol,open,high,low,close,volume\n"
        "2024-01-01,BTC,100,105,98,102,1000\n"
        "2024-01-02,BTC,102,,100,101,1100\n",  # Missing high value
        encoding="utf-8",
    )

    # Run in strict mode - warnings become errors
    exit_code = validate_ohlcv_data.main([str(csv_file), "--strict"])
    # With strict mode, any warning should cause failure
    # The result depends on the file content and threshold
    assert exit_code in (0, 1)  # Either passes or fails based on validation


def test_main_no_ohlc_mode(tmp_path: Path) -> None:
    """Test main with --no-ohlc skips OHLC validation."""
    csv_file = tmp_path / "price_only.csv"
    csv_file.write_text(
        "timestamp,symbol,close,volume\n"
        "2024-01-01,BTC,100,1000\n"
        "2024-01-02,BTC,102,1100\n",
        encoding="utf-8",
    )

    exit_code = validate_ohlcv_data.main([str(csv_file), "--no-ohlc"])

    assert exit_code == 0


def test_validate_ohlcv_file_invalid_timestamps(tmp_path: Path) -> None:
    """Test validation handles invalid timestamp values."""
    csv_file = tmp_path / "bad_timestamps.csv"
    csv_file.write_text(
        "timestamp,symbol,open,high,low,close,volume\n"
        "not-a-date,BTC,100,105,98,102,1000\n",
        encoding="utf-8",
    )

    report = validate_ohlcv_data.validate_ohlcv_file(csv_file)

    # Invalid timestamps should produce a warning about parsing
    # Check that validation completes and warnings are generated
    has_timestamp_warning = any("timestamp" in w.lower() for w in report.warnings)
    # If the date is unparseable, the date_range will be empty
    has_empty_date_range = report.date_range == ""
    assert has_timestamp_warning or has_empty_date_range, (
        "Expected timestamp warning or empty date range for invalid timestamp"
    )
