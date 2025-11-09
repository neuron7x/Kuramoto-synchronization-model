"""PostgreSQL configuration helpers with TLS validation."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

__all__ = [
    "ALLOWED_POSTGRES_SSLMODES",
    "ensure_secure_postgres_uri",
    "get_postgres_sslmode",
    "is_postgres_uri",
]


ALLOWED_POSTGRES_SSLMODES = frozenset({"verify-ca", "verify-full"})


def is_postgres_uri(uri: str) -> bool:
    """Return ``True`` when *uri* targets a PostgreSQL backend."""

    scheme = urlparse(uri).scheme.lower()
    return scheme.startswith("postgres")


def get_postgres_sslmode(uri: str) -> str | None:
    """Extract the ``sslmode`` component from a Postgres connection URI."""

    parsed = urlparse(uri)
    values = parse_qs(parsed.query, keep_blank_values=True).get("sslmode")
    if not values:
        return None
    # ``parse_qs`` preserves ordering so the last value takes precedence.
    return values[-1] or None


def ensure_secure_postgres_uri(uri: str) -> str:
    """Validate that a Postgres URI specifies a strong TLS ``sslmode``."""

    if not is_postgres_uri(uri):
        return uri

    sslmode = get_postgres_sslmode(uri)
    if sslmode is None:
        msg = "PostgreSQL connection URIs must declare an sslmode"
        raise ValueError(msg)

    if sslmode not in ALLOWED_POSTGRES_SSLMODES:
        msg = f"sslmode '{sslmode}' is not permitted; use one of {sorted(ALLOWED_POSTGRES_SSLMODES)}"
        raise ValueError(msg)

    return uri
