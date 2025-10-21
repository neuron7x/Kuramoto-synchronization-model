"""Run a docker-compose smoke test for TradePulse deployments."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def _run(command: Iterable[str], *, check: bool = True, capture_output: bool = False) -> subprocess.CompletedProcess[str]:
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


def _wait_for_service(project: str, compose_file: Path, service: str, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    last_status = "unknown"
    while time.monotonic() < deadline:
        container_id = (
            _run(
                _compose_cmd(compose_file, project, "ps", "-q", service),
                capture_output=True,
            )
            .stdout.strip()
        )
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

    raise TimeoutError(f"service '{service}' did not become healthy (last status: {last_status})")


def _fetch_json(url: str, timeout: float) -> dict[str, object]:
    request = Request(url, headers={"Accept": "application/json"})
    with urlopen(request, timeout=timeout) as response:  # noqa: S310 (controlled URL)
        payload = response.read()
    return json.loads(payload.decode("utf-8"))


def _fetch_text(url: str, timeout: float) -> str:
    request = Request(url)
    with urlopen(request, timeout=timeout) as response:  # noqa: S310 (controlled URL)
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

    up_command = _compose_cmd(compose_file, project, "up", "-d", "--build")
    try:
        subprocess.run(up_command, check=True, text=True, env=env)

        _wait_for_service(project, compose_file, args.service_name, args.timeout)

        try:
            health_payload = _fetch_json(args.health_url, timeout=args.http_timeout)
        except (HTTPError, URLError, TimeoutError) as exc:
            raise RuntimeError(f"Failed to fetch service health from {args.health_url}: {exc}") from exc

        _write_artifact(
            artifact_dir / "api-health.json",
            json.dumps(health_payload, indent=2, sort_keys=True),
        )

        try:
            prom_runtime = _fetch_json(args.prometheus_runtime_url, timeout=args.http_timeout)
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
    parser.add_argument(
        "--health-url",
        default="http://localhost:8001/health",
        help="HTTP URL used to validate API health.",
    )
    parser.add_argument(
        "--metrics-url",
        default="http://localhost:8001/metrics",
        help="HTTP URL used to download API metrics for diagnostics.",
    )
    parser.add_argument(
        "--prometheus-runtime-url",
        default="http://localhost:9090/api/v1/status/runtimeinfo",
        help="Prometheus runtime endpoint for environment diagnostics.",
    )
    parser.add_argument(
        "--prometheus-up-url",
        default="http://localhost:9090/api/v1/query?query=up",
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
        default=300.0,
        help="Maximum number of seconds to wait for the service health check to succeed.",
    )
    parser.add_argument(
        "--http-timeout",
        type=float,
        default=15.0,
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
