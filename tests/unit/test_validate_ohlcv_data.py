"""Tests for OHLCV data validation script.

This module tests the scripts/validate_ohlcv_data.py module.
"""

# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary

import tempfile
from pathlib import Path

import pandas as pd
import pytest

from scripts.validate_ohlcv_data import (
    ValidationReport,
    validate_ohlcv_file,
)


class TestValidationReport:
    """Tests for ValidationReport dataclass."""

    def test_basic_creation(self):
        """Test basic report creation."""
        report = ValidationReport(file_path="test.csv")
        assert report.file_path == "test.csv"
        assert report.valid is True
        assert report.errors == []
        assert report.warnings == []

    def test_to_dict(self):
        """Test conversion to dictionary."""
        report = ValidationReport(
            file_path="test.csv",
            row_count=100,
            errors=["Error 1"],
        )
        data = report.to_dict()
        assert data["file_path"] == "test.csv"
        assert data["row_count"] == 100
        assert data["errors"] == ["Error 1"]

    def test_to_json(self):
        """Test conversion to JSON."""
        report = ValidationReport(file_path="test.csv", row_count=100)
        json_str = report.to_json()
        assert '"file_path": "test.csv"' in json_str
        assert '"row_count": 100' in json_str


class TestValidateOHLCVFile:
    """Tests for validate_ohlcv_file function."""

    def test_valid_ohlcv_file(self):
        """Test validation of valid OHLCV file."""
        df = pd.DataFrame(
            {
                "timestamp": pd.date_range("2024-01-01", periods=10, freq="1h"),
                "symbol": "TEST",
                "open": [100.0] * 10,
                "high": [102.0] * 10,
                "low": [99.0] * 10,
                "close": [101.0] * 10,
                "volume": [1000.0] * 10,
            }
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.csv"
            df.to_csv(path, index=False)

            report = validate_ohlcv_file(path)

            assert report.valid is True
            assert report.row_count == 10
            assert "TEST" in report.symbols
            assert len(report.errors) == 0

    def test_file_not_found(self):
        """Test validation of non-existent file."""
        report = validate_ohlcv_file(Path("/nonexistent/file.csv"))

        assert report.valid is False
        assert any("not found" in e for e in report.errors)

    def test_empty_file(self):
        """Test validation of empty file."""
        df = pd.DataFrame(columns=["close"])

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "empty.csv"
            df.to_csv(path, index=False)

            report = validate_ohlcv_file(path)

            assert report.valid is False
            assert any("empty" in e.lower() for e in report.errors)

    def test_missing_close_column(self):
        """Test validation fails when close column is missing."""
        df = pd.DataFrame({"price": [100.0, 101.0, 102.0]})

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "missing_close.csv"
            df.to_csv(path, index=False)

            report = validate_ohlcv_file(path)

            assert report.valid is False
            assert any("close" in e for e in report.errors)

    def test_custom_close_column(self):
        """Test validation with custom close column name."""
        df = pd.DataFrame({"price": [100.0, 101.0, 102.0]})

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "custom.csv"
            df.to_csv(path, index=False)

            report = validate_ohlcv_file(path, close_col="price")

            assert report.valid is True
            assert report.row_count == 3

    def test_nan_values_warning(self):
        """Test warning for small number of NaN values."""
        df = pd.DataFrame(
            {
                "close": [100.0, None, 102.0, 103.0, 104.0] * 10,
            }
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "some_nan.csv"
            df.to_csv(path, index=False)

            report = validate_ohlcv_file(path)

            # 10 NaN out of 50 is 20%, should be an error
            assert report.valid is False
            assert any("NaN" in e for e in report.errors)

    def test_negative_prices_error(self):
        """Test error for negative prices."""
        df = pd.DataFrame(
            {
                "close": [100.0, -50.0, 102.0],
            }
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "negative.csv"
            df.to_csv(path, index=False)

            report = validate_ohlcv_file(path)

            assert report.valid is False
            assert any("non-positive" in e for e in report.errors)

    def test_high_low_violation(self):
        """Test error when high < low."""
        df = pd.DataFrame(
            {
                "open": [100.0],
                "high": [99.0],  # Less than low!
                "low": [101.0],
                "close": [100.0],
            }
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "hl_violation.csv"
            df.to_csv(path, index=False)

            report = validate_ohlcv_file(path)

            assert report.valid is False
            assert any("high < low" in e for e in report.errors)

    def test_negative_volume(self):
        """Test error for negative volume."""
        df = pd.DataFrame(
            {
                "close": [100.0, 101.0, 102.0],
                "volume": [1000.0, -500.0, 1200.0],
            }
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "neg_vol.csv"
            df.to_csv(path, index=False)

            report = validate_ohlcv_file(path)

            assert report.valid is False
            assert any("negative volume" in e for e in report.errors)

    def test_statistics_calculated(self):
        """Test that statistics are calculated correctly."""
        df = pd.DataFrame(
            {
                "close": [100.0, 110.0, 105.0, 115.0, 120.0],
                "volume": [1000.0, 1100.0, 1050.0, 1150.0, 1200.0],
            }
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "stats.csv"
            df.to_csv(path, index=False)

            report = validate_ohlcv_file(path)

            assert report.valid is True
            assert "close_mean" in report.statistics
            assert "close_std" in report.statistics
            assert "volume_mean" in report.statistics
            assert report.statistics["close_mean"] == pytest.approx(110.0, rel=0.01)

    def test_no_ohlc_columns(self):
        """Test validation with only close column (no OHLC)."""
        df = pd.DataFrame(
            {
                "close": [100.0, 101.0, 102.0],
            }
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "simple.csv"
            df.to_csv(path, index=False)

            report = validate_ohlcv_file(
                path,
                open_col=None,
                high_col=None,
                low_col=None,
            )

            assert report.valid is True

    def test_multi_symbol_detection(self):
        """Test that multiple symbols are detected."""
        df = pd.DataFrame(
            {
                "symbol": ["BTC", "BTC", "ETH", "ETH"],
                "close": [45000.0, 45100.0, 2500.0, 2510.0],
            }
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "multi.csv"
            df.to_csv(path, index=False)

            report = validate_ohlcv_file(path)

            assert report.valid is True
            assert set(report.symbols) == {"BTC", "ETH"}

    def test_date_range_detection(self):
        """Test that date range is detected."""
        df = pd.DataFrame(
            {
                "timestamp": pd.date_range("2024-01-01", periods=5, freq="1D"),
                "close": [100.0, 101.0, 102.0, 103.0, 104.0],
            }
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "dated.csv"
            df.to_csv(path, index=False)

            report = validate_ohlcv_file(path)

            assert report.valid is True
            assert "2024-01-01" in report.date_range
            assert "2024-01-05" in report.date_range
