"""Tests for input validation utilities."""

from decimal import Decimal

import pytest

from core.utils.input_validation import (
    ValidationError,
    sanitize_sql_identifier,
    validate_enum,
    validate_order_side,
    validate_order_type,
    validate_percentage,
    validate_price,
    validate_quantity,
    validate_string_length,
    validate_symbol,
    validate_timeframe,
)


class TestValidateSymbol:
    """Tests for validate_symbol function."""

    def test_valid_symbol(self):
        """Test validation of valid trading symbols."""
        assert validate_symbol("BTC/USDT") == "BTC/USDT"
        assert validate_symbol("btc/usdt") == "BTC/USDT"
        assert validate_symbol("BTC-USDT") == "BTC-USDT"
        assert validate_symbol("BTC_USDT") == "BTC_USDT"

    def test_empty_symbol_rejected(self):
        """Test that empty symbol is rejected."""
        with pytest.raises(ValidationError):
            validate_symbol("")

    def test_too_long_symbol_rejected(self):
        """Test that too long symbol is rejected."""
        with pytest.raises(ValidationError, match="too long"):
            validate_symbol("A" * 100)

    def test_invalid_characters_rejected(self):
        """Test that invalid characters are rejected."""
        with pytest.raises(ValidationError, match="invalid characters"):
            validate_symbol("BTC@USDT")

        with pytest.raises(ValidationError):
            validate_symbol("BTC USDT")  # space not allowed

    def test_none_symbol_rejected(self):
        """Test that None is rejected."""
        with pytest.raises(ValidationError):
            validate_symbol(None)


class TestValidateQuantity:
    """Tests for validate_quantity function."""

    def test_valid_quantity(self):
        """Test validation of valid quantities."""
        assert validate_quantity(10.5) == Decimal("10.5")
        assert validate_quantity(Decimal("100.25")) == Decimal("100.25")
        assert validate_quantity(5) == Decimal("5")

    def test_zero_rejected_by_default(self):
        """Test that zero is rejected by default."""
        with pytest.raises(ValidationError, match="cannot be zero"):
            validate_quantity(0)

    def test_zero_allowed_when_enabled(self):
        """Test that zero can be allowed."""
        assert validate_quantity(0, allow_zero=True) == Decimal("0")

    def test_negative_quantity_rejected(self):
        """Test that negative quantity is rejected."""
        with pytest.raises(ValidationError, match="below minimum"):
            validate_quantity(-10)

    def test_quantity_below_minimum_rejected(self):
        """Test that quantity below minimum is rejected."""
        with pytest.raises(ValidationError):
            validate_quantity(5, min_value=10)

    def test_quantity_above_maximum_rejected(self):
        """Test that quantity above maximum is rejected."""
        with pytest.raises(ValidationError, match="exceeds maximum"):
            validate_quantity(150, max_value=100)

    def test_invalid_format_rejected(self):
        """Test that invalid format is rejected."""
        with pytest.raises(ValidationError, match="Invalid quantity format"):
            validate_quantity("not a number")

    def test_infinity_rejected(self):
        """Test that infinity is rejected."""
        with pytest.raises(ValidationError, match="must be finite"):
            validate_quantity(float("inf"))


class TestValidatePrice:
    """Tests for validate_price function."""

    def test_valid_price(self):
        """Test validation of valid prices."""
        assert validate_price(100.50) == Decimal("100.50")
        assert validate_price(Decimal("50.25")) == Decimal("50.25")

    def test_zero_price_rejected(self):
        """Test that zero price is rejected."""
        with pytest.raises(ValidationError, match="cannot be zero"):
            validate_price(0)

    def test_negative_price_rejected(self):
        """Test that negative price is rejected."""
        with pytest.raises(ValidationError):
            validate_price(-10)

    def test_price_at_minimum_is_accepted(self):
        """Prices equal to the configured minimum should be valid."""
        assert validate_price(10, min_value=10) == Decimal("10")

    def test_price_above_maximum_rejected(self):
        """Test that price above maximum is rejected."""
        with pytest.raises(ValidationError, match="exceeds maximum"):
            validate_price(1500, max_value=1000)

    def test_invalid_format_rejected(self):
        """Test that invalid format is rejected."""
        with pytest.raises(ValidationError, match="Invalid price format"):
            validate_price("invalid")


class TestValidatePercentage:
    """Tests for validate_percentage function."""

    def test_valid_percentage(self):
        """Test validation of valid percentages."""
        assert validate_percentage(50) == Decimal("50")
        assert validate_percentage(0.5) == Decimal("0.5")
        assert validate_percentage(99.99) == Decimal("99.99")

    def test_percentage_below_minimum_rejected(self):
        """Test that percentage below minimum is rejected."""
        with pytest.raises(ValidationError, match="below minimum"):
            validate_percentage(-5)

    def test_percentage_above_maximum_rejected(self):
        """Test that percentage above 100 is rejected by default."""
        with pytest.raises(ValidationError, match="exceeds maximum"):
            validate_percentage(150)

    def test_custom_range(self):
        """Test custom percentage range."""
        assert validate_percentage(150, max_value=200) == Decimal("150")

        with pytest.raises(ValidationError):
            validate_percentage(250, max_value=200)


class TestValidateOrderSide:
    """Tests for validate_order_side function."""

    def test_valid_sides(self):
        """Test validation of valid order sides."""
        assert validate_order_side("buy") == "buy"
        assert validate_order_side("SELL") == "sell"
        assert validate_order_side("Buy") == "buy"
        assert validate_order_side("long") == "buy"  # normalized
        assert validate_order_side("short") == "sell"  # normalized

    def test_invalid_side_rejected(self):
        """Test that invalid side is rejected."""
        with pytest.raises(ValidationError, match="Invalid order side"):
            validate_order_side("invalid")

    def test_empty_side_rejected(self):
        """Test that empty side is rejected."""
        with pytest.raises(ValidationError):
            validate_order_side("")


class TestValidateOrderType:
    """Tests for validate_order_type function."""

    def test_valid_types(self):
        """Test validation of valid order types."""
        assert validate_order_type("market") == "market"
        assert validate_order_type("LIMIT") == "limit"
        assert validate_order_type("Stop") == "stop"
        assert validate_order_type("STOP_LIMIT") == "stop_limit"
        assert validate_order_type("trailing_stop") == "trailing_stop"

    def test_invalid_type_rejected(self):
        """Test that invalid type is rejected."""
        with pytest.raises(ValidationError, match="Invalid order type"):
            validate_order_type("invalid")


class TestValidateTimeframe:
    """Tests for validate_timeframe function."""

    def test_valid_timeframes(self):
        """Test validation of valid timeframes."""
        assert validate_timeframe("1m") == "1m"
        assert validate_timeframe("5M") == "5m"
        assert validate_timeframe("1h") == "1h"
        assert validate_timeframe("1d") == "1d"
        assert validate_timeframe("1w") == "1w"
        assert validate_timeframe("30s") == "30s"

    def test_invalid_timeframe_rejected(self):
        """Test that invalid timeframe is rejected."""
        with pytest.raises(ValidationError, match="Invalid timeframe"):
            validate_timeframe("5minutes")

        with pytest.raises(ValidationError):
            validate_timeframe("1x")


class TestValidateStringLength:
    """Tests for validate_string_length function."""

    def test_valid_length(self):
        """Test validation of valid length string."""
        assert validate_string_length("test", min_length=1, max_length=10) == "test"

    def test_too_short_rejected(self):
        """Test that too short string is rejected."""
        with pytest.raises(ValidationError, match="too short"):
            validate_string_length("a", min_length=5)

    def test_too_long_rejected(self):
        """Test that too long string is rejected."""
        with pytest.raises(ValidationError, match="too long"):
            validate_string_length("a" * 100, max_length=50)

    def test_non_string_rejected(self):
        """Test that non-string is rejected."""
        with pytest.raises(ValidationError, match="must be a string"):
            validate_string_length(123)


class TestValidateEnum:
    """Tests for validate_enum function."""

    def test_valid_value(self):
        """Test validation of valid enum value."""
        allowed = ["USD", "EUR", "GBP"]
        assert validate_enum("USD", allowed) == "USD"

    def test_case_insensitive_by_default(self):
        """Test that validation is case-insensitive by default."""
        allowed = ["USD", "EUR", "GBP"]
        assert validate_enum("usd", allowed, case_sensitive=False) == "usd"

    def test_case_sensitive_when_enabled(self):
        """Test case-sensitive validation."""
        allowed = ["USD", "EUR", "GBP"]

        with pytest.raises(ValidationError):
            validate_enum("usd", allowed, case_sensitive=True)

    def test_invalid_value_rejected(self):
        """Test that invalid value is rejected."""
        allowed = ["USD", "EUR", "GBP"]

        with pytest.raises(ValidationError, match="Invalid"):
            validate_enum("JPY", allowed)


class TestSanitizeSqlIdentifier:
    """Tests for sanitize_sql_identifier function."""

    def test_valid_identifier(self):
        """Test validation of valid SQL identifier."""
        assert sanitize_sql_identifier("table_name") == "table_name"
        assert sanitize_sql_identifier("_private") == "_private"
        assert sanitize_sql_identifier("col123") == "col123"

    def test_invalid_start_character_rejected(self):
        """Test that identifier starting with digit is rejected."""
        with pytest.raises(ValidationError, match="Invalid SQL identifier"):
            sanitize_sql_identifier("123table")

    def test_invalid_characters_rejected(self):
        """Test that invalid characters are rejected."""
        with pytest.raises(ValidationError):
            sanitize_sql_identifier("table-name")

        with pytest.raises(ValidationError):
            sanitize_sql_identifier("table name")

    def test_too_long_identifier_rejected(self):
        """Test that too long identifier is rejected."""
        with pytest.raises(ValidationError, match="too long"):
            sanitize_sql_identifier("a" * 100)

    def test_empty_identifier_rejected(self):
        """Test that empty identifier is rejected."""
        with pytest.raises(ValidationError):
            sanitize_sql_identifier("")
