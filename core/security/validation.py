"""Comprehensive input validation and sanitization framework.

This module provides enterprise-grade input validation aligned with:
- OWASP Top 10 (A03:2021 Injection)
- CWE-20 (Improper Input Validation)
- ISO/IEC 25010 Security Quality Attributes
- NIST SP 800-53 SI-10 (Information Input Validation)
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, TypeVar

from pydantic import BaseModel, Field, field_validator

T = TypeVar("T")


class ValidationError(ValueError):
    """Raised when input validation fails."""

    def __init__(self, field: str, message: str, value: Any = None) -> None:
        """Initialize validation error.

        Args:
            field: Name of the field that failed validation
            message: Human-readable error message
            value: The invalid value (will be sanitized in logs)
        """
        self.field = field
        self.message = message
        self.value = value
        super().__init__(f"Validation failed for '{field}': {message}")


class TradingSymbolValidator(BaseModel):
    """Validates trading symbols according to exchange standards.

    Ensures symbols match expected format and don't contain injection patterns.
    """

    symbol: str = Field(
        ...,
        min_length=1,
        max_length=20,
        description="Trading symbol (e.g., AAPL, BTC-USD)",
    )

    @field_validator("symbol")
    @classmethod
    def validate_symbol_format(cls, v: str) -> str:
        """Validate symbol format and sanitize.

        Args:
            v: Symbol string to validate

        Returns:
            Validated and normalized symbol

        Raises:
            ValueError: If symbol contains invalid characters
        """
        # Allow alphanumeric, dash, dot, underscore only
        if not re.match(r"^[A-Z0-9._-]+$", v.upper()):
            raise ValueError(
                "Symbol must contain only alphanumeric characters, dash, dot, or underscore"
            )

        # Check for common injection patterns
        dangerous_patterns = [
            r"--",  # SQL comment
            r";",  # SQL delimiter
            r"\/\*",  # SQL comment start
            r"\*\/",  # SQL comment end
            r"<script",  # XSS
            r"javascript:",  # XSS
            r"\.\.\/",  # Path traversal
        ]

        for pattern in dangerous_patterns:
            if re.search(pattern, v, re.IGNORECASE):
                raise ValueError(
                    f"Symbol contains potentially malicious pattern: {pattern}"
                )

        return v.upper()


class NumericRangeValidator:
    """Validates numeric inputs within safe ranges for financial calculations.

    Prevents overflow, underflow, and precision loss in trading calculations.
    Aligned with IEEE 754 and financial industry best practices.
    """

    @staticmethod
    def validate_price(
        value: float | Decimal,
        min_price: float = 0.0001,
        max_price: float = 1_000_000_000.0,
        field_name: str = "price",
    ) -> Decimal:
        """Validate trading price.

        Args:
            value: Price value to validate
            min_price: Minimum acceptable price (default: $0.0001)
            max_price: Maximum acceptable price (default: $1B)
            field_name: Name of field for error reporting

        Returns:
            Validated price as Decimal for precision

        Raises:
            ValidationError: If price is out of valid range
        """
        try:
            price = Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError) as e:
            raise ValidationError(
                field=field_name,
                message=f"Invalid price format: {e}",
                value=value,
            ) from e

        min_decimal = Decimal(str(min_price))
        if price < min_decimal:
            raise ValidationError(
                field=field_name,
                message=f"Price must be at least {min_price}",
                value=value,
            )

        if price > Decimal(str(max_price)):
            raise ValidationError(
                field=field_name,
                message=f"Price exceeds maximum allowed ({max_price})",
                value=value,
            )

        # Check for excessive precision (prevents precision attacks)
        if price.as_tuple().exponent < -8:
            raise ValidationError(
                field=field_name,
                message="Price has excessive decimal places (max 8)",
                value=value,
            )

        return price

    @staticmethod
    def validate_quantity(
        value: float | Decimal,
        min_qty: float = 0.000001,
        max_qty: float = 100_000_000.0,
        field_name: str = "quantity",
    ) -> Decimal:
        """Validate trading quantity.

        Args:
            value: Quantity value to validate
            min_qty: Minimum acceptable quantity
            max_qty: Maximum acceptable quantity
            field_name: Name of field for error reporting

        Returns:
            Validated quantity as Decimal

        Raises:
            ValidationError: If quantity is out of valid range
        """
        try:
            qty = Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError) as e:
            raise ValidationError(
                field=field_name,
                message=f"Invalid quantity format: {e}",
                value=value,
            ) from e

        if qty <= Decimal(str(min_qty)):
            raise ValidationError(
                field=field_name,
                message=f"Quantity must be greater than {min_qty}",
                value=value,
            )

        if qty > Decimal(str(max_qty)):
            raise ValidationError(
                field=field_name,
                message=f"Quantity exceeds maximum allowed ({max_qty})",
                value=value,
            )

        return qty

    @staticmethod
    def validate_percentage(
        value: float,
        min_pct: float = -100.0,
        max_pct: float = 100.0,
        field_name: str = "percentage",
    ) -> float:
        """Validate percentage value.

        Args:
            value: Percentage value to validate
            min_pct: Minimum acceptable percentage
            max_pct: Maximum acceptable percentage
            field_name: Name of field for error reporting

        Returns:
            Validated percentage

        Raises:
            ValidationError: If percentage is out of valid range
        """
        try:
            pct = float(value)
        except (ValueError, TypeError) as e:
            raise ValidationError(
                field=field_name,
                message=f"Invalid percentage format: {e}",
                value=value,
            ) from e

        # Check for NaN or infinity
        if not (-float("inf") < pct < float("inf")):
            raise ValidationError(
                field=field_name,
                message="Percentage must be a finite number",
                value=value,
            )

        if pct < min_pct or pct > max_pct:
            raise ValidationError(
                field=field_name,
                message=f"Percentage must be between {min_pct} and {max_pct}",
                value=value,
            )

        return pct


class PathValidator:
    """Validates file paths to prevent path traversal attacks.

    Aligned with CWE-22 (Improper Limitation of a Pathname to a Restricted Directory).
    """

    @staticmethod
    def validate_safe_path(
        path: str,
        allowed_base: str | None = None,
        field_name: str = "path",
    ) -> str:
        """Validate that path doesn't contain traversal patterns.

        Args:
            path: Path to validate
            allowed_base: Optional base directory (path must be under this)
            field_name: Name of field for error reporting

        Returns:
            Validated path

        Raises:
            ValidationError: If path contains dangerous patterns
        """
        from pathlib import Path

        # Check for path traversal patterns
        dangerous_patterns = [
            r"\.\.",  # Parent directory
            r"~",  # Home directory
            r"\$",  # Environment variable
            r"%",  # Windows environment variable
            r"\/\/",  # Double slash
            r"\\\\",  # Double backslash
        ]

        for pattern in dangerous_patterns:
            if re.search(pattern, path):
                raise ValidationError(
                    field=field_name,
                    message=f"Path contains potentially dangerous pattern: {pattern}",
                    value=path,
                )

        # Additional check: ensure path doesn't escape base directory
        if allowed_base is not None:
            try:
                normalized = Path(path).resolve()
                base = Path(allowed_base).resolve()

                if not str(normalized).startswith(str(base)):
                    raise ValidationError(
                        field=field_name,
                        message=f"Path must be within allowed base directory: {allowed_base}",
                        value=path,
                    )
            except (OSError, ValueError) as e:
                raise ValidationError(
                    field=field_name,
                    message=f"Invalid path: {e}",
                    value=path,
                ) from e

        return path


class CommandValidator:
    """Validates command-line arguments for subprocess execution.

    Prevents command injection attacks (CWE-78).
    Implements whitelist-based validation for allowed commands.
    """

    # Whitelist of allowed commands (extend as needed)
    ALLOWED_COMMANDS = frozenset(
        {
            "git",
            "python",
            "python3",
            "pip",
            "pytest",
            "mypy",
            "black",
            "ruff",
            "bandit",
        }
    )

    @staticmethod
    def validate_command(
        command: str | list[str],
        field_name: str = "command",
    ) -> list[str]:
        """Validate command and arguments for safe subprocess execution.

        Args:
            command: Command string or list of arguments
            field_name: Name of field for error reporting

        Returns:
            Validated command as list of arguments

        Raises:
            ValidationError: If command is not in whitelist or contains dangerous patterns
        """
        # Convert string to list
        if isinstance(command, str):
            cmd_list = command.split()
        else:
            cmd_list = list(command)

        if not cmd_list:
            raise ValidationError(
                field=field_name,
                message="Command cannot be empty",
                value=command,
            )

        # Validate command is in whitelist
        base_command = cmd_list[0].split("/")[-1]  # Handle full paths
        if base_command not in CommandValidator.ALLOWED_COMMANDS:
            raise ValidationError(
                field=field_name,
                message=f"Command '{base_command}' not in whitelist",
                value=command,
            )

        # Check for shell injection patterns
        dangerous_patterns = [
            r";",  # Command separator
            r"\|",  # Pipe
            r"&",  # Background execution
            r"\$\(",  # Command substitution
            r"`",  # Command substitution
            r"\n",  # Newline
            r">",  # Redirect
            r"<",  # Redirect
        ]

        for arg in cmd_list:
            for pattern in dangerous_patterns:
                if re.search(pattern, str(arg)):
                    raise ValidationError(
                        field=field_name,
                        message=f"Command argument contains potentially dangerous pattern: {pattern}",
                        value=command,
                    )

        return cmd_list


def validate_with_retry(
    validator: Callable[[T], T],
    value: T,
    max_attempts: int = 3,
    cleanup: Callable[[T], T] | None = None,
) -> T:
    """Validate input with automatic cleanup and retry.

    Args:
        validator: Validation function to apply
        value: Value to validate
        max_attempts: Maximum number of cleanup/retry attempts
        cleanup: Optional cleanup function to apply before retry

    Returns:
        Validated value

    Raises:
        ValidationError: If validation fails after all attempts
    """
    last_error = None

    for attempt in range(max_attempts):
        try:
            return validator(value)
        except ValidationError as e:
            last_error = e
            if cleanup is not None and attempt < max_attempts - 1:
                value = cleanup(value)
            else:
                break

    if last_error is not None:
        raise last_error
    raise ValidationError(
        field="unknown",
        message="Validation failed with unknown error",
        value=value,
    )


__all__ = [
    "ValidationError",
    "TradingSymbolValidator",
    "NumericRangeValidator",
    "PathValidator",
    "CommandValidator",
    "validate_with_retry",
]
