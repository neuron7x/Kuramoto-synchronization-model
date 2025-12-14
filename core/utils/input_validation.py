# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Comprehensive input validation utilities for TradePulse.

This module provides robust input validation functions to prevent
injection attacks, data corruption, and other security issues.
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Callable, TypeVar

T = TypeVar("T")


class ValidationError(ValueError):
    """Raised when input validation fails."""

    pass


def validate_symbol(symbol: str, max_length: int = 20) -> str:
    """Validate a trading symbol.

    Args:
        symbol: The trading symbol to validate (e.g., 'BTC/USDT')
        max_length: Maximum allowed length

    Returns:
        The validated symbol in uppercase

    Raises:
        ValidationError: If the symbol is invalid

    Examples:
        >>> validate_symbol("BTC/USDT")
        'BTC/USDT'

        >>> validate_symbol("btc-usdt")
        'BTC-USDT'
    """
    if not symbol or not isinstance(symbol, str):
        raise ValidationError("Symbol must be a non-empty string")

    symbol = symbol.strip().upper()

    if len(symbol) > max_length:
        raise ValidationError(
            f"Symbol too long (max {max_length} characters): {symbol}"
        )

    # Allow alphanumeric, dash, slash, underscore
    if not re.match(r"^[A-Z0-9/_-]+$", symbol):
        raise ValidationError(
            f"Symbol contains invalid characters: {symbol}. "
            "Only letters, numbers, /, -, and _ are allowed."
        )

    return symbol


def validate_quantity(
    quantity: float | Decimal | int,
    min_value: float = 0.0,
    max_value: float | None = None,
    allow_zero: bool = False,
) -> Decimal:
    """Validate a trading quantity.

    Args:
        quantity: The quantity to validate
        min_value: Minimum allowed value
        max_value: Maximum allowed value (None for no limit)
        allow_zero: Whether zero is allowed

    Returns:
        The validated quantity as a Decimal

    Raises:
        ValidationError: If the quantity is invalid
    """
    try:
        if isinstance(quantity, Decimal):
            qty = quantity
        else:
            qty = Decimal(str(quantity))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValidationError(f"Invalid quantity format: {quantity}") from exc

    if not qty.is_finite():
        raise ValidationError(f"Quantity must be finite: {qty}")

    if not allow_zero and qty == 0:
        raise ValidationError("Quantity cannot be zero")

    if qty < Decimal(str(min_value)):
        raise ValidationError(f"Quantity {qty} is below minimum {min_value}")

    if max_value is not None and qty > Decimal(str(max_value)):
        raise ValidationError(f"Quantity {qty} exceeds maximum {max_value}")

    return qty


def validate_price(
    price: float | Decimal | int,
    min_value: float = 0.0,
    max_value: float | None = None,
    allow_zero: bool = False,
) -> Decimal:
    """Validate a trading price.

    Args:
        price: The price to validate
        min_value: Minimum allowed value
        max_value: Maximum allowed value (None for no limit)
        allow_zero: Whether a zero price is permitted

    Returns:
        The validated price as a Decimal

    Raises:
        ValidationError: If the price is invalid
    """
    try:
        if isinstance(price, Decimal):
            p = price
        else:
            p = Decimal(str(price))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValidationError(f"Invalid price format: {price}") from exc

    if not p.is_finite():
        raise ValidationError(f"Price must be finite: {p}")

    min_decimal = Decimal(str(min_value))
    if p == 0 and not allow_zero:
        raise ValidationError("Price cannot be zero")

    if p < min_decimal:
        raise ValidationError(f"Price {p} must be at least {min_value}")

    if max_value is not None and p > Decimal(str(max_value)):
        raise ValidationError(f"Price {p} exceeds maximum {max_value}")

    return p


def validate_percentage(
    value: float | Decimal | int,
    min_value: float = 0.0,
    max_value: float = 100.0,
) -> Decimal:
    """Validate a percentage value.

    Args:
        value: The percentage to validate
        min_value: Minimum allowed value
        max_value: Maximum allowed value

    Returns:
        The validated percentage as a Decimal

    Raises:
        ValidationError: If the percentage is invalid
    """
    try:
        if isinstance(value, Decimal):
            pct = value
        else:
            pct = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValidationError(f"Invalid percentage format: {value}") from exc

    if not pct.is_finite():
        raise ValidationError(f"Percentage must be finite: {pct}")

    if pct < Decimal(str(min_value)):
        raise ValidationError(f"Percentage {pct} is below minimum {min_value}%")

    if pct > Decimal(str(max_value)):
        raise ValidationError(f"Percentage {pct} exceeds maximum {max_value}%")

    return pct


def validate_order_side(side: str) -> str:
    """Validate an order side (buy/sell).

    Args:
        side: The order side to validate

    Returns:
        The validated side in lowercase

    Raises:
        ValidationError: If the side is invalid
    """
    if not side or not isinstance(side, str):
        raise ValidationError("Order side must be a non-empty string")

    side = side.strip().lower()

    if side not in ("buy", "sell", "long", "short"):
        raise ValidationError(
            f"Invalid order side: '{side}'. Must be 'buy', 'sell', 'long', or 'short'."
        )

    # Normalize to buy/sell
    if side == "long":
        side = "buy"
    elif side == "short":
        side = "sell"

    return side


def validate_order_type(order_type: str) -> str:
    """Validate an order type.

    Args:
        order_type: The order type to validate

    Returns:
        The validated order type in lowercase

    Raises:
        ValidationError: If the order type is invalid
    """
    if not order_type or not isinstance(order_type, str):
        raise ValidationError("Order type must be a non-empty string")

    order_type = order_type.strip().lower()

    valid_types = ("market", "limit", "stop", "stop_limit", "trailing_stop")

    if order_type not in valid_types:
        raise ValidationError(
            f"Invalid order type: '{order_type}'. "
            f"Must be one of: {', '.join(valid_types)}"
        )

    return order_type


def validate_timeframe(timeframe: str) -> str:
    """Validate a timeframe/interval string.

    Args:
        timeframe: The timeframe to validate (e.g., '1m', '5m', '1h', '1d')

    Returns:
        The validated timeframe

    Raises:
        ValidationError: If the timeframe is invalid
    """
    if not timeframe or not isinstance(timeframe, str):
        raise ValidationError("Timeframe must be a non-empty string")

    timeframe = timeframe.strip().lower()

    # Valid timeframe pattern: number followed by unit
    if not re.match(r"^\d+[smhdwMy]$", timeframe):
        raise ValidationError(
            f"Invalid timeframe format: '{timeframe}'. "
            "Expected format: number + unit (s/m/h/d/w/M/y), e.g., '5m', '1h', '1d'"
        )

    return timeframe


def validate_string_length(
    value: str,
    min_length: int = 1,
    max_length: int = 1000,
    field_name: str = "value",
) -> str:
    """Validate string length.

    Args:
        value: The string to validate
        min_length: Minimum allowed length
        max_length: Maximum allowed length
        field_name: Name of the field (for error messages)

    Returns:
        The validated string

    Raises:
        ValidationError: If the string length is invalid
    """
    if not isinstance(value, str):
        raise ValidationError(f"{field_name} must be a string")

    length = len(value)

    if length < min_length:
        raise ValidationError(
            f"{field_name} too short (min {min_length} characters): got {length}"
        )

    if length > max_length:
        raise ValidationError(
            f"{field_name} too long (max {max_length} characters): got {length}"
        )

    return value


def validate_enum(
    value: str,
    allowed_values: set[str] | list[str] | tuple[str, ...],
    case_sensitive: bool = False,
    field_name: str = "value",
) -> str:
    """Validate that a value is in an allowed set.

    Args:
        value: The value to validate
        allowed_values: Set of allowed values
        case_sensitive: Whether comparison should be case-sensitive
        field_name: Name of the field (for error messages)

    Returns:
        The validated value

    Raises:
        ValidationError: If the value is not allowed
    """
    if not isinstance(value, str):
        raise ValidationError(f"{field_name} must be a string")

    allowed_set = set(allowed_values)

    if not case_sensitive:
        value_check = value.lower()
        allowed_set = {v.lower() for v in allowed_set}
    else:
        value_check = value

    if value_check not in allowed_set:
        raise ValidationError(
            f"Invalid {field_name}: '{value}'. "
            f"Must be one of: {', '.join(sorted(allowed_values))}"
        )

    return value


def sanitize_sql_identifier(identifier: str, max_length: int = 63) -> str:
    """Sanitize a SQL identifier (table/column name).

    This does NOT make arbitrary input safe for SQL queries.
    Use parameterized queries instead.

    Args:
        identifier: The identifier to sanitize
        max_length: Maximum length (PostgreSQL limit is 63)

    Returns:
        Sanitized identifier

    Raises:
        ValidationError: If the identifier is invalid
    """
    if not identifier or not isinstance(identifier, str):
        raise ValidationError("Identifier must be a non-empty string")

    # SQL identifiers: letters, digits, underscores, starting with letter/underscore
    if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", identifier):
        raise ValidationError(
            f"Invalid SQL identifier: '{identifier}'. "
            "Must start with letter or underscore, contain only letters, digits, and underscores."
        )

    if len(identifier) > max_length:
        raise ValidationError(
            f"Identifier too long (max {max_length} characters): {identifier}"
        )

    return identifier


def validate_with_custom(
    value: T,
    validator: Callable[[T], bool],
    error_message: str = "Validation failed",
) -> T:
    """Validate using a custom validation function.

    Args:
        value: The value to validate
        validator: A function that returns True if valid
        error_message: Error message if validation fails

    Returns:
        The validated value

    Raises:
        ValidationError: If validation fails
    """
    try:
        if not validator(value):
            raise ValidationError(error_message)
    except ValidationError:
        raise
    except Exception as exc:
        raise ValidationError(f"Validation error: {exc}") from exc

    return value


__all__ = [
    "ValidationError",
    "validate_symbol",
    "validate_quantity",
    "validate_price",
    "validate_percentage",
    "validate_order_side",
    "validate_order_type",
    "validate_timeframe",
    "validate_string_length",
    "validate_enum",
    "sanitize_sql_identifier",
    "validate_with_custom",
]
