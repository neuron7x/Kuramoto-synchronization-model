# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Unit tests for core/data/warehouses/_validators.py."""

from __future__ import annotations

import pytest

from core.data.warehouses._validators import (
    ensure_identifier,
    ensure_timezone,
    literal,
)


class TestEnsureIdentifier:
    """Tests for ensure_identifier function."""

    def test_valid_simple_identifier(self) -> None:
        """Verify simple alphabetic identifiers are accepted."""
        result = ensure_identifier("my_table", label="table_name")
        assert result == "my_table"

    def test_valid_identifier_with_underscore_prefix(self) -> None:
        """Verify identifiers starting with underscore are accepted."""
        result = ensure_identifier("_private", label="column")
        assert result == "_private"

    def test_valid_identifier_with_numbers(self) -> None:
        """Verify identifiers with numbers (not at start) are accepted."""
        result = ensure_identifier("table123", label="table_name")
        assert result == "table123"

    def test_valid_uppercase_identifier(self) -> None:
        """Verify uppercase identifiers are accepted."""
        result = ensure_identifier("TABLE_NAME", label="table")
        assert result == "TABLE_NAME"

    def test_valid_mixed_case_identifier(self) -> None:
        """Verify mixed case identifiers are accepted."""
        result = ensure_identifier("MyTable", label="table")
        assert result == "MyTable"

    def test_empty_identifier_raises(self) -> None:
        """Verify empty string raises ValueError."""
        with pytest.raises(ValueError, match="must be a non-empty identifier"):
            ensure_identifier("", label="column")

    def test_identifier_starting_with_number_raises(self) -> None:
        """Verify identifiers starting with number raise ValueError."""
        with pytest.raises(ValueError, match="must match"):
            ensure_identifier("123table", label="table")

    def test_identifier_with_special_chars_raises(self) -> None:
        """Verify identifiers with special characters raise ValueError."""
        with pytest.raises(ValueError, match="must match"):
            ensure_identifier("table-name", label="table")

    def test_identifier_with_spaces_raises(self) -> None:
        """Verify identifiers with spaces raise ValueError."""
        with pytest.raises(ValueError, match="must match"):
            ensure_identifier("my table", label="table")

    def test_identifier_with_sql_injection_raises(self) -> None:
        """Verify SQL injection attempts raise ValueError."""
        with pytest.raises(ValueError, match="must match"):
            ensure_identifier("table; DROP TABLE users;--", label="table")


class TestEnsureTimezone:
    """Tests for ensure_timezone function."""

    def test_valid_utc_timezone(self) -> None:
        """Verify UTC timezone is accepted."""
        result = ensure_timezone("UTC")
        assert result == "UTC"

    def test_valid_iana_timezone(self) -> None:
        """Verify IANA timezone names are accepted."""
        result = ensure_timezone("America/New_York")
        assert result == "America/New_York"

    def test_valid_timezone_with_numbers(self) -> None:
        """Verify timezones with numbers are accepted."""
        result = ensure_timezone("Etc/GMT+5")
        assert result == "Etc/GMT+5"

    def test_empty_timezone_raises(self) -> None:
        """Verify empty string raises ValueError."""
        with pytest.raises(ValueError, match="timezone must be provided"):
            ensure_timezone("")

    def test_timezone_with_special_chars_raises(self) -> None:
        """Verify timezones with special characters raise ValueError."""
        with pytest.raises(ValueError, match="contains unexpected characters"):
            ensure_timezone("America;DROP")


class TestLiteral:
    """Tests for literal function."""

    def test_simple_string(self) -> None:
        """Verify simple strings are properly quoted."""
        result = literal("hello")
        assert result == "'hello'"

    def test_empty_string(self) -> None:
        """Verify empty strings are properly quoted."""
        result = literal("")
        assert result == "''"

    def test_string_with_numbers(self) -> None:
        """Verify strings with numbers are properly quoted."""
        result = literal("test123")
        assert result == "'test123'"

    def test_string_with_spaces(self) -> None:
        """Verify strings with spaces are properly quoted."""
        result = literal("hello world")
        assert result == "'hello world'"

    def test_string_with_single_quote_raises(self) -> None:
        """Verify strings with single quotes raise ValueError."""
        with pytest.raises(ValueError, match="may not contain single quotes"):
            literal("it's")

    def test_sql_injection_prevention(self) -> None:
        """Verify SQL injection via quotes is prevented."""
        with pytest.raises(ValueError, match="may not contain single quotes"):
            literal("'; DROP TABLE users;--")
