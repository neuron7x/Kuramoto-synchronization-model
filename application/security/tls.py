"""Helpers for constructing TLS contexts used by the API server."""

from __future__ import annotations

import ssl

from application.settings import ApiServerTLSSettings
from core.security import create_server_ssl_context, parse_tls_version


def build_api_server_ssl_context(settings: ApiServerTLSSettings) -> ssl.SSLContext:
    """Return an :class:`ssl.SSLContext` matching the supplied configuration."""

    return create_server_ssl_context(
        certificate_chain=settings.certificate,
        private_key=settings.private_key,
        trusted_client_ca=settings.client_ca,
        client_revocation_list=settings.client_revocation_list,
        require_client_certificate=settings.require_client_certificate,
        minimum_version=parse_tls_version(settings.minimum_version),
        cipher_suites=settings.cipher_suites,
        alpn_protocols=settings.alpn_protocols,
    )


__all__ = ["build_api_server_ssl_context"]
