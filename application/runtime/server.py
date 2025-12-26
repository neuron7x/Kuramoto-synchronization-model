"""Uvicorn bootstrapper that applies hardened TLS configuration."""

from __future__ import annotations

import argparse
import logging
import ssl
from typing import Any, Dict, Optional

import uvicorn

from application.runtime.init_control_platform import initialize_control_platform
from application.security.tls import build_api_server_ssl_context

_LOGGER = logging.getLogger(__name__)


def _build_cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="TradePulse control-platform server")
    parser.add_argument(
        "--config",
        dest="config_path",
        default=None,
        help="Optional YAML config path (applied below environment overrides)",
    )
    parser.add_argument(
        "--host",
        dest="host",
        default=None,
        help="Override API host (CLI > ENV > YAML > defaults)",
    )
    parser.add_argument(
        "--port",
        dest="port",
        type=int,
        default=None,
        help="Override API port (CLI > ENV > YAML > defaults)",
    )
    parser.add_argument(
        "--allow-plaintext",
        dest="allow_plaintext",
        action="store_true",
        help="Allow HTTP without TLS (for local testing only)",
    )
    parser.add_argument(
        "--serotonin-config",
        dest="serotonin_config",
        default=None,
        help="Path to serotonin controller config",
    )
    parser.add_argument(
        "--thermo-config",
        dest="thermo_config",
        default=None,
        help="Path to thermo controller config",
    )
    return parser


def run(
    *,
    config_path: Optional[str] = None,
    cli_overrides: Optional[Dict[str, Any]] = None,
) -> None:
    """Start the TradePulse API server with unified initialization."""

    cli_overrides = cli_overrides or {}
    server_overrides = {
        "host": cli_overrides.get("host"),
        "port": cli_overrides.get("port"),
        "allow_plaintext": cli_overrides.get("allow_plaintext"),
    }

    init_result = initialize_control_platform(
        config_path=config_path,
        cli_server_overrides=server_overrides,
        cli_runtime_overrides=None,
        cli_serotonin_config=cli_overrides.get("serotonin_config"),
        cli_thermo_config=cli_overrides.get("thermo_config"),
    )

    runtime_settings = init_result.runtime_settings
    server_settings = init_result.server_settings
    tls_settings = server_settings.tls
    app = init_result.app

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
            ssl_ca_certs=(
                str(tls_settings.client_ca) if tls_settings.client_ca else None
            ),
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

    controllers_loaded = init_result.telemetry_meta.get("controllers_loaded", [])
    _LOGGER.info(
        "Starting TradePulse API server on %s://%s:%s effective_config_source=%s controllers_loaded=%s",
        scheme,
        server_settings.host,
        server_settings.port,
        init_result.telemetry_meta.get("effective_config_source", "unknown"),
        controllers_loaded,
    )

    server = uvicorn.Server(config)
    server.run()


def main() -> None:  # pragma: no cover - CLI wiring
    parser = _build_cli_parser()
    args = parser.parse_args()
    run(
        config_path=args.config_path,
        cli_overrides={
            "host": args.host,
            "port": args.port,
            "allow_plaintext": args.allow_plaintext,
            "serotonin_config": args.serotonin_config,
            "thermo_config": args.thermo_config,
        },
    )


if __name__ == "__main__":  # pragma: no cover - manual entrypoint
    main()
