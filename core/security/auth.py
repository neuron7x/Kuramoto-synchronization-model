"""
Authentication and authorization security primitives.

Provides secure password hashing, session token generation, and other
authentication-related security functions aligned with OWASP guidelines.
"""

import hashlib
import secrets


def hash_password(password: str, salt: bytes | None = None) -> str:
    """
    Hash a password using PBKDF2-HMAC-SHA256.

    Args:
        password: The plaintext password to hash
        salt: Optional salt (generated if not provided)

    Returns:
        Combined salt and hash as hex string (salt:hash format)
    """
    if salt is None:
        salt = secrets.token_bytes(32)

    # Use PBKDF2 with 100,000 iterations (OWASP recommendation)
    key = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, 100000, dklen=32  # iterations
    )

    # Return salt:hash format for storage
    return f"{salt.hex()}:{key.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    """
    Verify a password against a stored hash.

    Args:
        password: The plaintext password to verify
        stored_hash: The stored hash in salt:hash format

    Returns:
        True if password matches, False otherwise
    """
    try:
        salt_hex, hash_hex = stored_hash.split(":")
        salt = bytes.fromhex(salt_hex)
        stored_key = bytes.fromhex(hash_hex)
    except ValueError:
        return False

    # Hash the provided password with the stored salt
    key = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, 100000, dklen=32
    )

    # Constant-time comparison to prevent timing attacks
    return secrets.compare_digest(key, stored_key)


def generate_session_token(length: int = 32) -> str:
    """
    Generate a cryptographically secure session token.

    Args:
        length: Number of random bytes (will be twice as long in hex)

    Returns:
        Secure random token as hex string
    """
    return secrets.token_hex(length)


def generate_api_key(prefix: str = "sk", length: int = 32) -> str:
    """
    Generate a cryptographically secure API key.

    Args:
        prefix: Key prefix for identification (e.g., 'sk' for secret key)
        length: Number of random bytes

    Returns:
        API key with format: prefix_randomhex
    """
    return f"{prefix}_{secrets.token_hex(length)}"


def generate_csrf_token() -> str:
    """
    Generate a CSRF token for form protection.

    Returns:
        Secure random CSRF token
    """
    return secrets.token_urlsafe(32)


__all__ = [
    "hash_password",
    "verify_password",
    "generate_session_token",
    "generate_api_key",
    "generate_csrf_token",
]
