"""Uvicorn bootstrapper that applies hardened TLS configuration."""

from __future__ import annotations

import argparse
import json
import logging
import os
import ssl
from typing import Any, Dict, Optional

import uvicorn

from application.runtime.decision_telemetry import (
    get_controller_health,
    to_json_line,
)
from application.runtime.init_control_platform import initialize_control_platform
from application.security.tls import build_api_server_ssl_context

_LOGGER = logging.getLogger(__name__)


def enforce_prod_server_flags(config: uvicorn.Config) -> None:
    """Ensure production runs never enable uvicorn reload."""

    env = os.getenv("TRADEPULSE_ENV", "").lower()
    if env in {"prod", "production"} and getattr(config, "reload", False):
        msg = "Uvicorn reload is not allowed in production deployments"
        raise RuntimeError(msg)


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
    parser.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        help="Initialise control platform and evaluate gates without starting the server",
    )
    parser.add_argument(
        "--health",
        dest="health",
        action="store_true",
        help="Emit controller health snapshot and exit (no server binding)",
    )
    return parser


def run(
    *,
    config_path: Optional[str] = None,
    cli_overrides: Optional[Dict[str, Any]] = None,
) -> None:
    """Start the TradePulse API server with unified initialization."""

    cli_overrides = cli_overrides or {}
    dry_run = bool(cli_overrides.get("dry_run"))
    health_only = bool(cli_overrides.get("health"))
    allow_plaintext_override = cli_overrides.get("allow_plaintext")
    if dry_run:
        allow_plaintext_override = True
    server_overrides = {
        "host": cli_overrides.get("host"),
        "port": cli_overrides.get("port"),
        "allow_plaintext": allow_plaintext_override,
    }

    init_result = initialize_control_platform(
        config_path=config_path,
        cli_server_overrides=server_overrides,
        cli_runtime_overrides=None,
        cli_serotonin_config=cli_overrides.get("serotonin_config"),
        cli_thermo_config=cli_overrides.get("thermo_config"),
    )

    if dry_run or health_only:
        baseline_signals = {
            "risk_score": 1.0,
            "volatility": 1.0,
            "drawdown": -0.01,
            "free_energy": 0.2,
        }
        gate_result = init_result.gate_pipeline(
            init_result.runtime_settings, init_result.controllers, baseline_signals
        )
        summary = {
            "control_gate_decision": gate_result.gate.decision.value,
            "reasons": gate_result.gate.reasons,
            "position_multiplier": gate_result.gate.position_multiplier,
            "effective_config_source": init_result.telemetry_meta.get(
                "effective_config_source", "unknown"
            ),
        }
        summary_json = json.dumps(summary, sort_keys=True)
        _LOGGER.info(summary_json)
        print(summary_json)
        decision_event = gate_result.decision_event
        if decision_event:
            event_line = to_json_line(decision_event)
            _LOGGER.info("dry_run_decision_event %s", event_line)
            print(event_line)
        health_snapshot = get_controller_health(
            init_result.controllers,
            proxy_flags=getattr(gate_result.gate, "meta", {}).get("proxy_flags", []),
            telemetry=gate_result.telemetry,
        )
        print(json.dumps(health_snapshot, sort_keys=True))
        return

    runtime_settings = init_result.runtime_settings
    server_settings = init_result.server_settings
    tls_settings = server_settings.tls
    app = init_result.app
    app.state.control_gates = init_result.gate_pipeline
    app.state.controllers = init_result.controllers
    app.state.controllers_required = init_result.controllers_required

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
    enforce_prod_server_flags(config)
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
            "dry_run": args.dry_run,
            "health": args.health,
        },
    )


if __name__ == "__main__":  # pragma: no cover - manual entrypoint
    main()
