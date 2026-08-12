# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Multi-factor authentication helpers.

Security contract:
- setup(email) accepts only a canonical e-mail string and fails closed on malformed input.
- verify(secret, token) accepts only canonical base32 secret + 6-digit token.
- missing optional dependencies raise ImportError deterministically.
"""

from __future__ import annotations

import re
from io import BytesIO

try:  # Optional dependency for MFA
    import pyotp
except ImportError:  # pragma: no cover - handled at runtime
    pyotp = None

try:  # Optional dependency for QR code generation
    import qrcode
except ImportError:  # pragma: no cover - handled at runtime
    qrcode = None

_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_SECRET_RE = re.compile(r"^[A-Z2-7]{16,128}$")
_TOKEN_RE = re.compile(r"^\d{6}$")


class MFA:
    """Time-based one-time password (TOTP) utilities with fail-closed validation."""

    @staticmethod
    def _require_text(value: str, *, field: str) -> str:
        if not isinstance(value, str):
            raise TypeError(f"{field} must be a string")
        if value != value.strip() or not value:
            raise ValueError(
                f"{field} must be non-empty and must not contain surrounding whitespace"
            )
        return value

    @staticmethod
    def _validate_email(email: str) -> str:
        normalized = MFA._require_text(email, field="email")
        if not _EMAIL_RE.fullmatch(normalized):
            raise ValueError("email must be a valid address")
        return normalized

    @staticmethod
    def _validate_secret(secret: str) -> str:
        normalized = MFA._require_text(secret, field="secret")
        if not _SECRET_RE.fullmatch(normalized):
            raise ValueError("secret must be uppercase base32 and 16-128 characters long")
        return normalized

    @staticmethod
    def _validate_token(token: str) -> str:
        normalized = MFA._require_text(token, field="token")
        if not _TOKEN_RE.fullmatch(normalized):
            raise ValueError("token must be a 6-digit numeric code")
        return normalized

    @staticmethod
    def setup(email: str) -> tuple[str, bytes]:
        """Return a new TOTP secret and PNG QR code for a canonical e-mail."""

        email_value = MFA._validate_email(email)

        if pyotp is None or qrcode is None:
            raise ImportError("pyotp and qrcode must be installed for MFA setup")

        secret = pyotp.random_base32()
        if not isinstance(secret, str) or not _SECRET_RE.fullmatch(secret):
            raise RuntimeError("generated TOTP secret is invalid")

        totp = pyotp.TOTP(secret)
        uri = totp.provisioning_uri(email_value, issuer_name="GeoSync")
        if not isinstance(uri, str) or not uri.startswith("otpauth://"):
            raise RuntimeError("generated provisioning URI is invalid")

        qr = qrcode.make(uri)
        buf = BytesIO()
        qr.save(buf, format="PNG")
        payload = buf.getvalue()
        if not payload:
            raise RuntimeError("generated QR payload is empty")

        return secret, payload

    @staticmethod
    def verify(secret: str, token: str) -> bool:
        """Validate a 6-digit TOTP token for a canonical base32 secret."""

        secret_value = MFA._validate_secret(secret)
        token_value = MFA._validate_token(token)

        if pyotp is None:
            raise ImportError("pyotp must be installed for MFA verification")

        return bool(pyotp.TOTP(secret_value).verify(token_value, valid_window=1))
