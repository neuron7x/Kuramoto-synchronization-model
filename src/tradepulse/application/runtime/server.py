"""Uvicorn bootstrapper that applies hardened TLS configuration."""

from __future__ import annotations

import logging
import ssl

import uvicorn

from tradepulse.application.api.service import create_app
from tradepulse.application.security.tls import build_api_server_ssl_context
from tradepulse.application.settings import ApiServerSettings, BackendRuntimeSettings

_LOGGER = logging.getLogger(__name__)


def run() -> None:
    """Start the TradePulse API server with TLS enabled."""

    runtime_settings = BackendRuntimeSettings()
    server_settings = ApiServerSettings()
    tls_settings = server_settings.tls

    app = create_app(runtime_settings=runtime_settings)

    config_kwargs: dict[str, object] = {
        "app": app,
        "host": server_settings.host,
        "port": server_settings.port,
        "log_level": runtime_settings.resolve_log_level(),
    }

    if tls_settings is not None:
        config_kwargs.update(
            ssl_certfile=str(tls_settings.certificate),
            ssl_keyfile=str(tls_settings.private_key),
            ssl_ca_certs=str(tls_settings.client_ca) if tls_settings.client_ca else None,
            ssl_cert_reqs=(
                ssl.CERT_REQUIRED
                if tls_settings.require_client_certificate
                else (ssl.CERT_OPTIONAL if tls_settings.client_ca else ssl.CERT_NONE)
            ),
            ssl_ciphers=":".join(tls_settings.cipher_suites),
            ssl_version=ssl.PROTOCOL_TLS_SERVER,
        )
    elif not server_settings.allow_plaintext:
        msg = "TLS configuration is required to start the TradePulse API server"
        raise RuntimeError(msg)

    config = uvicorn.Config(**config_kwargs)
    config.load()

    scheme = "http"
    if tls_settings is not None:
        config.ssl = build_api_server_ssl_context(tls_settings)
        scheme = "https"

    server = uvicorn.Server(config)
    _LOGGER.info(
        "Starting TradePulse API server on %s://%s:%s",
        scheme,
        server_settings.host,
        server_settings.port,
    )
    server.run()


if __name__ == "__main__":  # pragma: no cover - manual entrypoint
    run()
