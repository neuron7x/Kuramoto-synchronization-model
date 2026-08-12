"""Multi-factor authentication helpers."""

from __future__ import annotations

from io import BytesIO

try:  # Optional dependency for MFA
    import pyotp
except ImportError:  # pragma: no cover - handled at runtime
    pyotp = None

try:  # Optional dependency for QR code generation
    import qrcode
except ImportError:  # pragma: no cover - handled at runtime
    qrcode = None


class MFA:
    """Time-based one-time password (TOTP) utilities."""

    @staticmethod
    def setup(email: str) -> tuple[str, bytes]:
        """Return a new TOTP secret and PNG QR code for the provided email."""

        if pyotp is None or qrcode is None:
            raise ImportError("pyotp and qrcode must be installed for MFA setup")

        secret = pyotp.random_base32()
        totp = pyotp.TOTP(secret)
        uri = totp.provisioning_uri(email, issuer_name="TradePulse")

        qr = qrcode.make(uri)
        buf = BytesIO()
        qr.save(buf, format="PNG")

        return secret, buf.getvalue()

    @staticmethod
    def verify(secret: str, token: str) -> bool:
        """Validate a TOTP token for the given secret."""

        if pyotp is None:
            raise ImportError("pyotp must be installed for MFA verification")

        return pyotp.TOTP(secret).verify(token, valid_window=1)
