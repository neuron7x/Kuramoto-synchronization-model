"""TLS helpers shared across API and microservices."""

from __future__ import annotations

import ssl
from pathlib import Path
from typing import Iterable, Sequence

DEFAULT_MODERN_CIPHER_SUITES: tuple[str, ...] = (
    "ECDHE-ECDSA-AES256-GCM-SHA384",
    "ECDHE-RSA-AES256-GCM-SHA384",
    "ECDHE-ECDSA-CHACHA20-POLY1305",
    "ECDHE-RSA-CHACHA20-POLY1305",
    "ECDHE-ECDSA-AES128-GCM-SHA256",
    "ECDHE-RSA-AES128-GCM-SHA256",
)
"""Cipher suites aligned with Mozilla's "modern" TLS recommendations."""

DEFAULT_HTTP_ALPN_PROTOCOLS: tuple[str, ...] = ("h2", "http/1.1")
"""Protocols presented during ALPN negotiation for TLS endpoints."""

_TLS_VERSION_ALIASES: dict[str, ssl.TLSVersion] = {
    "TLSV1.2": ssl.TLSVersion.TLSv1_2,
    "TLSV1.3": ssl.TLSVersion.TLSv1_3,
}


def _ensure_file(path: Path, *, description: str) -> Path:
    if not path.exists():
        msg = f"{description} '{path}' does not exist"
        raise FileNotFoundError(msg)
    if not path.is_file():
        msg = f"{description} '{path}' must be a file"
        raise ValueError(msg)
    return path


def parse_tls_version(version: str) -> ssl.TLSVersion:
    """Translate a textual TLS version into :class:`ssl.TLSVersion`."""

    key = version.replace(" ", "").upper()
    try:
        return _TLS_VERSION_ALIASES[key]
    except KeyError as exc:  # pragma: no cover - defensive guard
        msg = f"Unsupported TLS version '{version}'"
        raise ValueError(msg) from exc


def _normalise_sequence(values: Sequence[str] | str) -> tuple[str, ...]:
    if isinstance(values, str):
        candidates = (item.strip() for item in values.split(","))
    else:
        candidates = (str(item).strip() for item in values)
    cleaned = [value for value in candidates if value]
    return tuple(dict.fromkeys(cleaned))


def create_server_ssl_context(
    *,
    certificate_chain: Path,
    private_key: Path,
    trusted_client_ca: Path | None = None,
    client_revocation_list: Path | None = None,
    require_client_certificate: bool = False,
    minimum_version: ssl.TLSVersion = ssl.TLSVersion.TLSv1_2,
    cipher_suites: Sequence[str] | str | None = None,
    alpn_protocols: Iterable[str] = DEFAULT_HTTP_ALPN_PROTOCOLS,
) -> ssl.SSLContext:
    """Construct an :class:`ssl.SSLContext` configured for server usage."""

    certificate_chain = _ensure_file(certificate_chain, description="Certificate chain")
    private_key = _ensure_file(private_key, description="Private key")

    context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    context.minimum_version = minimum_version
    context.maximum_version = ssl.TLSVersion.TLSv1_3
    context.options |= ssl.OP_NO_COMPRESSION
    context.load_cert_chain(certfile=str(certificate_chain), keyfile=str(private_key))
    context.set_alpn_protocols(list(alpn_protocols))

    if cipher_suites:
        suites = _normalise_sequence(cipher_suites)
        if suites:
            context.set_ciphers(":".join(suites))

    if trusted_client_ca is not None:
        trusted_client_ca = _ensure_file(trusted_client_ca, description="Trusted client CA bundle")
        context.load_verify_locations(cafile=str(trusted_client_ca))
        context.verify_mode = ssl.CERT_REQUIRED if require_client_certificate else ssl.CERT_OPTIONAL
    else:
        if require_client_certificate:
            msg = "Client certificate verification requested without a CA bundle"
            raise ValueError(msg)
        context.verify_mode = ssl.CERT_NONE

    if client_revocation_list is not None:
        client_revocation_list = _ensure_file(client_revocation_list, description="Client revocation list")
        crl_payload = client_revocation_list.read_bytes()
        if crl_payload:
            context.load_verify_locations(cadata=crl_payload)
            context.verify_flags |= ssl.VERIFY_CRL_CHECK_LEAF

    return context


def create_client_ssl_context(
    *,
    trusted_server_ca: Path | None = None,
    client_certificate: Path | None = None,
    client_private_key: Path | None = None,
    minimum_version: ssl.TLSVersion = ssl.TLSVersion.TLSv1_2,
    cipher_suites: Sequence[str] | str | None = None,
    alpn_protocols: Iterable[str] = DEFAULT_HTTP_ALPN_PROTOCOLS,
    check_hostname: bool = True,
) -> ssl.SSLContext:
    """Construct an :class:`ssl.SSLContext` configured for client usage.
    
    Args:
        trusted_server_ca: Path to CA bundle for verifying server certificates.
        client_certificate: Optional path to client certificate for mutual TLS.
        client_private_key: Optional path to client private key for mutual TLS.
        minimum_version: Minimum TLS version to accept.
        cipher_suites: Cipher suites to enable (string or sequence).
        alpn_protocols: Application-Layer Protocol Negotiation protocols.
        check_hostname: Whether to verify the server hostname against the certificate.
        
    Returns:
        Configured SSL context for client connections.
        
    Raises:
        ValueError: If client certificate provided without private key.
        FileNotFoundError: If specified files don't exist.
    """
    context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
    context.minimum_version = minimum_version
    context.maximum_version = ssl.TLSVersion.TLSv1_3
    context.options |= ssl.OP_NO_COMPRESSION
    context.check_hostname = check_hostname
    context.set_alpn_protocols(list(alpn_protocols))

    if cipher_suites:
        suites = _normalise_sequence(cipher_suites)
        if suites:
            context.set_ciphers(":".join(suites))

    if trusted_server_ca is not None:
        trusted_server_ca = _ensure_file(trusted_server_ca, description="Trusted server CA bundle")
        context.load_verify_locations(cafile=str(trusted_server_ca))

    if client_certificate is not None or client_private_key is not None:
        if client_certificate is None or client_private_key is None:
            msg = "Both client certificate and private key must be provided for mutual TLS"
            raise ValueError(msg)
        client_certificate = _ensure_file(client_certificate, description="Client certificate")
        client_private_key = _ensure_file(client_private_key, description="Client private key")
        context.load_cert_chain(certfile=str(client_certificate), keyfile=str(client_private_key))

    return context


__all__ = [
    "DEFAULT_HTTP_ALPN_PROTOCOLS",
    "DEFAULT_MODERN_CIPHER_SUITES",
    "create_server_ssl_context",
    "create_client_ssl_context",
    "parse_tls_version",
]
