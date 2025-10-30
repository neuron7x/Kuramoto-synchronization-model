"""Shared exit codes for script automation."""

from __future__ import annotations

# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary

EXIT_CODES: dict[str, int] = {
    "success": 0,
    "invalid_arguments": 64,
    "missing_resource": 66,
    "api_rate_limited": 69,
    "network_failure": 70,
    "io_failure": 71,
    "checksum_mismatch": 74,
    "circuit_breaker_open": 75,
    "internal_error": 1,
    "interrupted": 130,
}
