# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Security primitives shared across GeoSync services.

This module provides comprehensive security controls aligned with:
- ISO/IEC 25010 Security Quality Attributes
- ISO/IEC 42001:2023 AI System Security
- OWASP Top 10
- CWE Top 25
- NIST Cybersecurity Framework
"""

from .integrity import (
    ChecksumManifest,
    HMACVerifier,
    IntegrityError,
    IntegrityVerifier,
    ModelIntegrityChecker,
)
from .random import (
    SecureNumpyRandom,
    SecureRandom,
    secure_numpy_random,
    secure_random,
)
from .tls import (
    DEFAULT_HTTP_ALPN_PROTOCOLS,
    DEFAULT_MODERN_CIPHER_SUITES,
    create_server_ssl_context,
    parse_tls_version,
)
from .validation import (
    CommandValidator,
    NumericRangeValidator,
    PathValidator,
    TradingSymbolValidator,
    ValidationError,
    validate_with_retry,
)

__all__ = [
    # TLS/Network Security
    "DEFAULT_HTTP_ALPN_PROTOCOLS",
    "DEFAULT_MODERN_CIPHER_SUITES",
    "create_server_ssl_context",
    "parse_tls_version",
    # Input Validation
    "ValidationError",
    "TradingSymbolValidator",
    "NumericRangeValidator",
    "PathValidator",
    "CommandValidator",
    "validate_with_retry",
    # Cryptographic Integrity
    "IntegrityError",
    "ChecksumManifest",
    "IntegrityVerifier",
    "HMACVerifier",
    "ModelIntegrityChecker",
    # Secure Random Number Generation
    "SecureRandom",
    "SecureNumpyRandom",
    "secure_random",
    "secure_numpy_random",
]
