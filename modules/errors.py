# Copyright (c) 2025 TradePulse
# SPDX-License-Identifier: Apache-2.0
"""Shared exception types for TradePulse modules."""


class TradePulseError(Exception):
    """Base class for module-level errors in TradePulse."""


class InvalidInputError(TradePulseError):
    """Raised when inputs or parameters fail validation checks."""


class InsufficientDataError(TradePulseError):
    """Raised when required data is missing or too sparse to compute results."""


class ConfigurationError(TradePulseError):
    """Raised when configuration or registration conflicts are detected."""


class ProcessingError(TradePulseError):
    """Raised when a module operation fails during processing."""


class NotificationError(TradePulseError):
    """Raised when delivering notifications or callbacks fails."""
