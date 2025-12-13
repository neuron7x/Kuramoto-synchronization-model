"""Run a docker-compose smoke test for TradePulse deployments."""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DEFAULT_SERVICE_TIMEOUT = 480.0
DEFAULT_HTTP_TIMEOUT = 30.0
DEFAULT_HTTP_PORT = 8000
DEFAULT_PROMETHEUS_PORT = 9090
DEFAULT_ELASTICSEARCH_PORT = 9200
DEFAULT_LOGSTASH_PORT = 5044
DEFAULT_KIBANA_PORT = 5601
PROMETHEUS_RUNTIME_TEMPLATE = "http://localhost:{port}/api/v1/status/runtimeinfo"
PROMETHEUS_UP_TEMPLATE = "http://localhost:{port}/api/v1/query?query=up"


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


def _fetch_json(url: str, timeout: float) -> dict[str, object]:
    """Fetch JSON from URL. URL is controlled and validated by caller (localhost health checks)."""
    request = Request(url, headers={"Accept": "application/json"})
    with urlopen(request, timeout=timeout) as response:  # nosec B310 - URL is controlled, only used for localhost health checks
        payload = response.read()
    return json.loads(payload.decode("utf-8"))


def _fetch_text(url: str, timeout: float) -> str:
    """Fetch text from URL. URL is controlled and validated by caller (localhost health checks)."""
    request = Request(url)
    with urlopen(request, timeout=timeout) as response:  # nosec B310 - URL is controlled, only used for localhost health checks
        return response.read().decode("utf-8")


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
        except (HTTPError, URLError, TimeoutError) as exc:
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
        except (HTTPError, URLError, TimeoutError) as exc:
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
        help="Path to the docker-compose file.",
    )
    parser.add_argument(
        "--project-name",
        default="tradepulse-smoke",
        help="Docker compose project name used to isolate resources.",
    )
    parser.add_argument(
        "--service-name",
        default="tradepulse",
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
        help="HTTP URL used to validate API health. Can be overridden by TRADEPULSE_HTTP_PORT env var or --health-url.",
    )
    parser.add_argument(
        "--metrics-url",
        default=default_metrics,
        help="HTTP URL used to download API metrics for diagnostics. Can be overridden by TRADEPULSE_HTTP_PORT env var or --metrics-url.",
    )
    parser.add_argument(
        "--prometheus-runtime-url",
        default=PROMETHEUS_RUNTIME_TEMPLATE.format(port=DEFAULT_PROMETHEUS_PORT),
        help="Prometheus runtime endpoint for environment diagnostics.",
    )
    parser.add_argument(
        "--prometheus-up-url",
        default=PROMETHEUS_UP_TEMPLATE.format(port=DEFAULT_PROMETHEUS_PORT),
        help="Prometheus query endpoint to verify scraped targets.",
    )
    parser.add_argument(
        "--artifact-dir",
        default="artifacts/deploy-smoke",
        help="Directory where smoke test artifacts will be stored.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_SERVICE_TIMEOUT,
        help="Maximum number of seconds to wait for the service health check to succeed.",
    )
    parser.add_argument(
        "--http-timeout",
        type=float,
        default=DEFAULT_HTTP_TIMEOUT,
        help="Timeout in seconds for individual HTTP calls.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_argument_parser()
    args = parser.parse_args(argv)
    try:
        run_smoke_test(args)
    except Exception as exc:  # pragma: no cover - surfaces failure context
        print(f"[docker-compose-smoke] {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
