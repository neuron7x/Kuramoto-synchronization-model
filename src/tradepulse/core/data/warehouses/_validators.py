"""Validation helpers to harden SQL identifier handling."""


from __future__ import annotations

import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_TIMEZONE_RE = re.compile(r"^[A-Za-z0-9_+\-./]+$")


def ensure_identifier(value: str, *, label: str) -> str:
    """Return *value* when it is a valid SQL identifier or raise ``ValueError``."""

    if not value:
        raise ValueError(f"{label} must be a non-empty identifier")
    if not _IDENTIFIER_RE.fullmatch(value):
        raise ValueError(f"{label} must match {_IDENTIFIER_RE.pattern!r}: {value!r}")
    return value


def ensure_timezone(value: str) -> str:
    """Validate that *value* is a well-formed IANA timezone name."""

    if not value:
        raise ValueError("timezone must be provided")
    if not _TIMEZONE_RE.fullmatch(value):
        raise ValueError(f"timezone contains unexpected characters: {value!r}")
    try:
        ZoneInfo(value)
    except ZoneInfoNotFoundError as exc:  # pragma: no cover - depends on system tzdata
        raise ValueError(f"unknown timezone: {value!r}") from exc
    return value


def literal(value: str) -> str:
    """Return a SQL string literal for *value* (single quoted)."""

    if "'" in value:
        raise ValueError("string literal may not contain single quotes")
    return "'" + value + "'"
