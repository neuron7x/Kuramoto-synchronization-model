# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""TLS-enabled runtime bootstrap for the cortex microservice."""

from __future__ import annotations

import logging
import ssl

import uvicorn

from core.security import create_server_ssl_context, parse_tls_version

from .config import load_settings

_LOGGER = logging.getLogger(__name__)


def run() -> None:
    """Launch the cortex FastAPI application with HTTPS enabled."""

    settings = load_settings()
    tls_settings = settings.service.tls
    if tls_settings is None:
        raise RuntimeError("TLS configuration is required for the cortex service")

    config = uvicorn.Config(
        "cortex_service.app.api:create_app",
        host=settings.service.host,
        port=settings.service.port,
        factory=True,
        log_level=settings.service.log_level.lower(),
        ssl_certfile=str(tls_settings.cert_file),
        ssl_keyfile=str(tls_settings.key_file),
        ssl_ca_certs=(str(tls_settings.client_ca_file) if tls_settings.client_ca_file else None),
        ssl_cert_reqs=(
            ssl.CERT_REQUIRED
            if tls_settings.require_client_certificate
            else (ssl.CERT_OPTIONAL if tls_settings.client_ca_file else ssl.CERT_NONE)
        ),
        ssl_ciphers=":".join(tls_settings.cipher_suites),
        ssl_version=ssl.PROTOCOL_TLS_SERVER,
    )
    config.load()
    config.ssl = create_server_ssl_context(
        certificate_chain=tls_settings.cert_file,
        private_key=tls_settings.key_file,
        trusted_client_ca=tls_settings.client_ca_file,
        client_revocation_list=tls_settings.client_revocation_list_file,
        require_client_certificate=tls_settings.require_client_certificate,
        minimum_version=parse_tls_version(tls_settings.minimum_version),
        cipher_suites=tls_settings.cipher_suites,
        alpn_protocols=tls_settings.alpn_protocols,
    )

    server = uvicorn.Server(config)
    _LOGGER.info(
        "Starting cortex service on https://%s:%s",
        settings.service.host,
        settings.service.port,
    )
    server.run()


if __name__ == "__main__":  # pragma: no cover - manual entrypoint
    run()
