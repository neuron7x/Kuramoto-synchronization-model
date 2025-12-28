"""Run a docker-compose smoke test for TradePulse deployments."""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlparse
from typing import Iterable
from urllib.parse import urlparse

import requests
from requests import Response

DEFAULT_SERVICE_TIMEOUT = 480.0
DEFAULT_HTTP_TIMEOUT = 30.0
DEFAULT_HTTP_PORT = 8000
DEFAULT_PROMETHEUS_PORT = 9090
DEFAULT_ELASTICSEARCH_PORT = 9200
DEFAULT_LOGSTASH_PORT = 5044
DEFAULT_KIBANA_PORT = 5601
PROMETHEUS_RUNTIME_TEMPLATE = "http://localhost:{port}/api/v1/status/runtimeinfo"
PROMETHEUS_UP_TEMPLATE = "http://localhost:{port}/api/v1/query?query=up"
SAFE_PATH_RE = re.compile(r"[A-Za-z0-9_./-]+")
SAFE_NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}")


def _validate_path(value: str, *, expected_file: bool) -> Path:
    if not SAFE_PATH_RE.fullmatch(value):
        raise argparse.ArgumentTypeError(
            "Paths may only contain letters, numbers, and ./_- characters."
        )
    path = Path(value).expanduser().resolve()
    if expected_file:
        if not path.exists():
            raise argparse.ArgumentTypeError(f"File does not exist: {path}")
        if not path.is_file():
            raise argparse.ArgumentTypeError(f"Expected file path, got: {path}")
    else:
        if path.exists() and not path.is_dir():
            raise argparse.ArgumentTypeError(f"Expected directory path, got: {path}")
    return path


def _validate_compose_file(value: str) -> Path:
    path = _validate_path(value, expected_file=True)
    if path.suffix.lower() not in {".yml", ".yaml"}:
        raise argparse.ArgumentTypeError(
            "Compose file must have a .yml or .yaml extension."
        )
    return path


def _validate_name(value: str, *, label: str) -> str:
    if not SAFE_NAME_RE.fullmatch(value):
        raise argparse.ArgumentTypeError(
            f"{label} must use letters, numbers, '.', '-', or '_' and be 1-64 characters long."
        )
    return value


def _validate_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme != "http":
        raise argparse.ArgumentTypeError("Only http:// URLs are supported.")
    if parsed.hostname not in {"localhost", "127.0.0.1"}:
        raise argparse.ArgumentTypeError("URL host must be localhost or 127.0.0.1.")
    if parsed.port is None or not (1 <= parsed.port <= 65535):
        raise argparse.ArgumentTypeError("URL must include a valid port number.")
    if not parsed.path.startswith("/"):
        raise argparse.ArgumentTypeError("URL path must be absolute.")
    return value


def _validate_positive_float(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Expected a number, got {value!r}") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("Value must be greater than zero.")
    return parsed


def _run(
    command: Iterable[str], *, check: bool = True, capture_output: bool = False
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command),
        check=check,
        text=True,
        capture_output=capture_output,
    )


def _compose_cmd(compose_file: Path, project: str, *args: str) -> list[str]:
    command = ["docker", "compose", "-f", str(compose_file), "-p", project]
    command.extend(args)
    return command


def _wait_for_service(
    project: str, compose_file: Path, service: str, timeout: float
) -> None:
    deadline = time.monotonic() + timeout
    last_status = "unknown"
    while time.monotonic() < deadline:
        container_id = _run(
            _compose_cmd(compose_file, project, "ps", "-q", service),
            capture_output=True,
        ).stdout.strip()
        if not container_id:
            time.sleep(2.0)
            continue

        inspect = _run(
            [
                "docker",
                "inspect",
                "--format",
                "{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}",
                container_id,
            ],
            capture_output=True,
        )
        status = inspect.stdout.strip().lower()
        if status in {"healthy", "running"}:
            return
        last_status = status
        time.sleep(3.0)

    raise TimeoutError(
        f"service '{service}' did not become healthy (last status: {last_status})"
    )


def _port_is_available(port: int) -> bool:
    with contextlib.closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def _parse_port(value: str, *, source: str) -> int:
    try:
        port = int(value)
    except ValueError as exc:  # pragma: no cover - defensive guard
        raise ValueError(f"{source} must be an integer port (got {value!r})") from exc
    if not (1 <= port <= 65535):  # pragma: no cover - defensive guard
        raise ValueError(f"{source} must be between 1 and 65535 (got {port})")
    return port


def _find_available_port(preferred: int) -> int:
    if _port_is_available(preferred):
        return preferred
    with contextlib.closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        return sock.getsockname()[1]


def _resolve_port(
    env: dict[str, str],
    primary_key: str,
    *,
    aliases: Iterable[str] = (),
    default: int,
) -> int:
    keys = (primary_key, *aliases)
    for key in keys:
        value = env.get(key)
        if not value:
            continue
        port = _parse_port(value, source=key)
        if not _port_is_available(port):
            port = _find_available_port(port)
        for alias in keys:
            env[alias] = str(port)
        return port

    port = _find_available_port(default)
    for key in keys:
        env[key] = str(port)
    return port


def _validate_http_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError(f"Unsupported URL scheme for {url!r}")


def _request_url(url: str, timeout: float, *, headers: dict[str, str] | None = None) -> Response:
    _validate_http_url(url)
    request_timeout = (timeout, timeout)
    response = requests.get(url, headers=headers, timeout=request_timeout)
    response.raise_for_status()
    return response


def _fetch_json(url: str, timeout: float) -> dict[str, object]:
    """Fetch JSON from URL. URL is controlled and validated by caller (localhost health checks)."""
    response = _request_url(url, timeout, headers={"Accept": "application/json"})
    return response.json()


def _fetch_text(url: str, timeout: float) -> str:
    """Fetch text from URL. URL is controlled and validated by caller (localhost health checks)."""
    response = _request_url(url, timeout)
    return response.text


def _write_artifact(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload)


def run_smoke_test(args: argparse.Namespace) -> None:
    compose_file = Path(args.compose_file).resolve()
    project = args.project_name
    artifact_dir = Path(args.artifact_dir).resolve()
    artifact_dir.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env.setdefault("COMPOSE_DOCKER_CLI_BUILD", "1")

    default_http_port_env = (
        os.environ.get("TRADEPULSE_HTTP_PORT")
        or os.environ.get("HTTP_PORT")
        or str(DEFAULT_HTTP_PORT)
    )
    default_health_url = f"http://localhost:{default_http_port_env}/health"
    default_metrics_url = f"http://localhost:{default_http_port_env}/metrics"

    http_port = _resolve_port(
        env,
        "TRADEPULSE_HTTP_PORT",
        aliases=["HTTP_PORT"],
        default=DEFAULT_HTTP_PORT,
    )
    prometheus_port = _resolve_port(
        env,
        "TRADEPULSE_PROMETHEUS_PORT",
        aliases=["PROMETHEUS_PORT"],
        default=DEFAULT_PROMETHEUS_PORT,
    )
    _resolve_port(
        env,
        "TRADEPULSE_ELASTICSEARCH_PORT",
        aliases=["ELASTICSEARCH_PORT"],
        default=DEFAULT_ELASTICSEARCH_PORT,
    )
    _resolve_port(
        env,
        "TRADEPULSE_LOGSTASH_PORT",
        aliases=["LOGSTASH_PORT"],
        default=DEFAULT_LOGSTASH_PORT,
    )
    _resolve_port(
        env,
        "TRADEPULSE_KIBANA_PORT",
        aliases=["KIBANA_PORT"],
        default=DEFAULT_KIBANA_PORT,
    )

    if args.health_url == default_health_url:
        args.health_url = f"http://localhost:{http_port}/health"
    if args.metrics_url == default_metrics_url:
        args.metrics_url = f"http://localhost:{http_port}/metrics"

    default_runtime_url = PROMETHEUS_RUNTIME_TEMPLATE.format(
        port=DEFAULT_PROMETHEUS_PORT
    )
    default_up_url = PROMETHEUS_UP_TEMPLATE.format(port=DEFAULT_PROMETHEUS_PORT)
    if args.prometheus_runtime_url == default_runtime_url:
        args.prometheus_runtime_url = PROMETHEUS_RUNTIME_TEMPLATE.format(
            port=prometheus_port
        )
    if args.prometheus_up_url == default_up_url:
        args.prometheus_up_url = PROMETHEUS_UP_TEMPLATE.format(port=prometheus_port)

    up_command = _compose_cmd(compose_file, project, "up", "-d", "--build")
    try:
        subprocess.run(up_command, check=True, text=True, env=env)

        _wait_for_service(project, compose_file, args.service_name, args.timeout)

        try:
            health_payload = _fetch_json(args.health_url, timeout=args.http_timeout)
        except (requests.Timeout, requests.RequestException, ValueError) as exc:
            raise RuntimeError(
                f"Failed to fetch service health from {args.health_url}: {exc}"
            ) from exc

        _write_artifact(
            artifact_dir / "api-health.json",
            json.dumps(health_payload, indent=2, sort_keys=True),
        )

        try:
            prom_runtime = _fetch_json(
                args.prometheus_runtime_url, timeout=args.http_timeout
            )
            prom_up = _fetch_json(args.prometheus_up_url, timeout=args.http_timeout)
        except (requests.Timeout, requests.RequestException, ValueError) as exc:
            raise RuntimeError(f"Failed to query Prometheus: {exc}") from exc

        _write_artifact(
            artifact_dir / "prometheus-runtime.json",
            json.dumps(prom_runtime, indent=2, sort_keys=True),
        )
        _write_artifact(
            artifact_dir / "prometheus-up.json",
            json.dumps(prom_up, indent=2, sort_keys=True),
        )

        metrics_text = _fetch_text(args.metrics_url, timeout=args.http_timeout)
        _write_artifact(artifact_dir / "api-metrics.txt", metrics_text)

        logs_path = artifact_dir / "docker-compose-logs.txt"
        with logs_path.open("w", encoding="utf-8") as handle:
            subprocess.run(
                _compose_cmd(compose_file, project, "logs"),
                check=True,
                text=True,
                stdout=handle,
                stderr=subprocess.STDOUT,
            )

        ps_output = _run(
            _compose_cmd(compose_file, project, "ps"),
            capture_output=True,
        ).stdout
        _write_artifact(artifact_dir / "docker-compose-ps.txt", ps_output)
    finally:
        subprocess.run(
            _compose_cmd(compose_file, project, "down", "-v"),
            check=False,
            text=True,
            env=env,
        )


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--compose-file",
        default="docker-compose.yml",
        type=_validate_compose_file,
        help="Path to the docker-compose file.",
    )
    parser.add_argument(
        "--project-name",
        default="tradepulse-smoke",
        type=lambda value: _validate_name(value, label="Project name"),
        help="Docker compose project name used to isolate resources.",
    )
    parser.add_argument(
        "--service-name",
        default="tradepulse",
        type=lambda value: _validate_name(value, label="Service name"),
        help="Primary service to wait for before executing health checks.",
    )

    # Use TRADEPULSE_HTTP_PORT/HTTP_PORT environment variables with fallback to DEFAULT_HTTP_PORT
    http_port = (
        os.environ.get("TRADEPULSE_HTTP_PORT")
        or os.environ.get("HTTP_PORT")
        or str(DEFAULT_HTTP_PORT)
    )
    default_health = f"http://localhost:{http_port}/health"
    default_metrics = f"http://localhost:{http_port}/metrics"

    parser.add_argument(
        "--health-url",
        default=default_health,
        type=_validate_url,
        help="HTTP URL used to validate API health. Can be overridden by TRADEPULSE_HTTP_PORT env var or --health-url.",
    )
    parser.add_argument(
        "--metrics-url",
        default=default_metrics,
        type=_validate_url,
        help="HTTP URL used to download API metrics for diagnostics. Can be overridden by TRADEPULSE_HTTP_PORT env var or --metrics-url.",
    )
    parser.add_argument(
        "--prometheus-runtime-url",
        default=PROMETHEUS_RUNTIME_TEMPLATE.format(port=DEFAULT_PROMETHEUS_PORT),
        type=_validate_url,
        help="Prometheus runtime endpoint for environment diagnostics.",
    )
    parser.add_argument(
        "--prometheus-up-url",
        default=PROMETHEUS_UP_TEMPLATE.format(port=DEFAULT_PROMETHEUS_PORT),
        type=_validate_url,
        help="Prometheus query endpoint to verify scraped targets.",
    )
    parser.add_argument(
        "--artifact-dir",
        default="artifacts/deploy-smoke",
        type=lambda value: _validate_path(value, expected_file=False),
        help="Directory where smoke test artifacts will be stored.",
    )
    parser.add_argument(
        "--timeout",
        type=_validate_positive_float,
        default=DEFAULT_SERVICE_TIMEOUT,
        help="Maximum number of seconds to wait for the service health check to succeed.",
    )
    parser.add_argument(
        "--http-timeout",
        type=_validate_positive_float,
        default=DEFAULT_HTTP_TIMEOUT,
        help="Timeout in seconds for individual HTTP calls.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_argument_parser()
    args = parser.parse_args(argv)
    args.compose_file = _validate_compose_file(str(args.compose_file))
    args.project_name = _validate_name(str(args.project_name), label="Project name")
    args.service_name = _validate_name(str(args.service_name), label="Service name")
    args.health_url = _validate_url(str(args.health_url))
    args.metrics_url = _validate_url(str(args.metrics_url))
    args.prometheus_runtime_url = _validate_url(str(args.prometheus_runtime_url))
    args.prometheus_up_url = _validate_url(str(args.prometheus_up_url))
    args.artifact_dir = _validate_path(str(args.artifact_dir), expected_file=False)
    args.timeout = _validate_positive_float(str(args.timeout))
    args.http_timeout = _validate_positive_float(str(args.http_timeout))
    try:
        run_smoke_test(args)
    except Exception as exc:  # pragma: no cover - surfaces failure context
        print(f"[docker-compose-smoke] {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
