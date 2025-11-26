"""Automate local system startup via Docker Compose and health polling."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import time
from argparse import ArgumentParser, _SubParsersAction
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Mapping, Sequence

from scripts.commands.base import CommandError, register, run_subprocess
from scripts.runtime import AutomationRunner, AutomationStep, parse_env_file

LOGGER = logging.getLogger(__name__)
REQUIRED_ENV_VARS: tuple[str, ...] = (
    "TRADEPULSE_AUDIT_SECRET",
    "TRADEPULSE_RBAC_AUDIT_SECRET",
)
COMPOSE_BINARY = ("docker", "compose")


@dataclass(frozen=True)
class ServiceStatus:
    """Normalized view of service state reported by Docker Compose."""

    name: str
    state: str
    health: str | None

    def summary(self) -> str:
        """Human-readable representation useful for error messages."""

        return f"{self.name}={self.health or self.state}"


def build_parser(subparsers: _SubParsersAction[ArgumentParser]) -> None:
    parser = subparsers.add_parser(
        "system-launch",
        help=__doc__,
    )
    parser.set_defaults(command="system-launch", handler=handle)
    parser.add_argument(
        "--compose-file",
        type=Path,
        default=Path("docker-compose.yml"),
        help="Path to the docker-compose.yml manifest controlling the stack.",
    )
    parser.add_argument(
        "--compose-env",
        type=Path,
        default=Path(".env"),
        help="Env file containing required secrets for the Compose stack.",
    )
    parser.add_argument(
        "--profile",
        dest="profiles",
        action="append",
        default=None,
        help="Optional Compose profiles to activate (can be provided multiple times).",
    )
    parser.add_argument(
        "--wait-timeout",
        type=float,
        default=180.0,
        help="Seconds to wait for services to report healthy before failing.",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=5.0,
        help="Seconds between health polling attempts.",
    )
    parser.add_argument(
        "--require-service",
        dest="required_services",
        action="append",
        default=None,
        help="Restrict health checks to these services (defaults to all).",
    )
    parser.add_argument(
        "--skip-healthcheck",
        action="store_true",
        help="Skip waiting for container health checks after startup.",
    )


@register("system-launch")
def handle(args: object) -> int:  # noqa: ARG001 - argparse namespace
    namespace: Mapping[str, object] = args if isinstance(args, Mapping) else vars(args)

    compose_file = Path(namespace.get("compose_file", Path("docker-compose.yml")))
    compose_env = Path(namespace.get("compose_env", Path(".env")))
    profiles = _normalise_sequence(namespace.get("profiles"))
    required_services = _normalise_sequence(namespace.get("required_services"))
    wait_timeout = float(namespace.get("wait_timeout", 180.0))
    poll_interval = float(namespace.get("poll_interval", 5.0))
    skip_healthcheck = bool(namespace.get("skip_healthcheck", False))

    steps = _build_steps(
        compose_file,
        compose_env,
        profiles,
        required_services,
        wait_timeout,
        poll_interval,
        skip_healthcheck,
    )

    runner = AutomationRunner(steps)
    report = runner.run()

    if not report.succeeded:
        failures = ", ".join(
            f"{res.name} ({res.status})" for res in report.failed_steps
        )
        raise CommandError(f"System launch failed: {failures}")

    duration = (report.completed_at - report.started_at).total_seconds()
    LOGGER.info("System launch completed in %.1fs", duration)
    return 0


def _build_steps(
    compose_file: Path,
    compose_env: Path,
    profiles: Sequence[str] | None,
    required_services: Sequence[str] | None,
    wait_timeout: float,
    poll_interval: float,
    skip_healthcheck: bool,
) -> list[AutomationStep]:
    return [
        AutomationStep(
            name="validate-environment",
            action=lambda ctx: validate_environment(compose_env, REQUIRED_ENV_VARS),
            description="Ensure required Compose secrets are available.",
        ),
        AutomationStep(
            name="start-services",
            action=lambda ctx: compose_up(compose_file, profiles),
            description="Start the Docker Compose stack in detached mode.",
        ),
        AutomationStep(
            name="wait-for-health",
            action=lambda ctx: wait_for_healthy_services(
                compose_file,
                profiles,
                required_services,
                timeout=wait_timeout,
                interval=poll_interval,
            ),
            description="Poll Docker for service health until the stack is ready.",
            skip_if=(lambda ctx: skip_healthcheck),
        ),
    ]


def _normalise_sequence(value: object) -> list[str] | None:
    if value is None:
        return None
    if isinstance(value, (str, bytes)):
        return [str(value)]
    try:
        return [str(item) for item in value]  # type: ignore[arg-type]
    except TypeError:
        return [str(value)]


def validate_environment(
    env_file: Path, required_vars: Iterable[str]
) -> Mapping[str, str]:
    """Ensure required environment variables are available for Compose."""

    loaded = parse_env_file(env_file)
    if loaded is None:
        LOGGER.warning(
            "Compose env file %s is missing; falling back to OS env", env_file
        )
        variables: dict[str, str] = dict(os.environ)
    else:
        variables = {**os.environ, **dict(loaded.variables)}

    missing = [var for var in required_vars if not variables.get(var)]
    if missing:
        raise CommandError(
            "Missing required environment variables for docker compose: "
            + ", ".join(sorted(missing))
        )

    LOGGER.debug("Validated Compose environment with %d variables", len(variables))
    return variables


def compose_up(compose_file: Path, profiles: Sequence[str] | None = None) -> None:
    """Start the Compose stack in detached mode."""

    if not compose_file.exists():
        raise CommandError(f"Compose file not found: {compose_file}")

    command: list[str] = [*COMPOSE_BINARY, "-f", str(compose_file)]
    for profile in profiles or []:
        command.extend(["--profile", profile])
    command.extend(["up", "-d"])

    LOGGER.info("Starting services with %s", " ".join(command))
    run_subprocess(command)


def compose_services_status(
    compose_file: Path,
    profiles: Sequence[str] | None = None,
) -> list[ServiceStatus]:
    """Return the status of services from ``docker compose ps``."""

    command: list[str] = [
        *COMPOSE_BINARY,
        "-f",
        str(compose_file),
        "ps",
        "--format",
        "json",
    ]
    for profile in profiles or []:
        command.extend(["--profile", profile])

    result = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise CommandError("docker compose ps failed; check Docker daemon status")

    try:
        payload = json.loads(result.stdout or "[]")
    except json.JSONDecodeError as exc:  # pragma: no cover - defensive
        raise CommandError("Unable to parse docker compose ps output as JSON") from exc

    statuses: list[ServiceStatus] = []
    for entry in payload:
        status = ServiceStatus(
            name=str(entry.get("Service") or entry.get("Name")),
            state=str(entry.get("State") or entry.get("Status") or "unknown").lower(),
            health=(entry.get("Health") or entry.get("HealthStatus")),
        )
        statuses.append(status)
    return statuses


def _service_is_healthy(status: ServiceStatus) -> bool:
    if status.health is not None:
        return str(status.health).lower() == "healthy"
    return status.state in {"running", "up"}


def wait_for_healthy_services(
    compose_file: Path,
    profiles: Sequence[str] | None,
    required_services: Sequence[str] | None,
    *,
    timeout: float,
    interval: float,
    status_fetcher: Callable[
        [Path, Sequence[str] | None], list[ServiceStatus]
    ] = compose_services_status,
) -> list[ServiceStatus]:
    """Poll Docker until all services are healthy or a timeout is reached."""

    deadline = time.monotonic() + timeout
    required = set(required_services or [])
    last_statuses: list[ServiceStatus] = []

    while time.monotonic() < deadline:
        statuses = status_fetcher(compose_file, profiles)
        last_statuses = statuses
        names = {status.name for status in statuses}

        if required:
            missing = required - names
            if missing:
                raise CommandError(
                    "Required services missing from docker compose: "
                    + ", ".join(sorted(missing))
                )
            statuses = [status for status in statuses if status.name in required]

        if statuses and all(_service_is_healthy(status) for status in statuses):
            LOGGER.info(
                "All services healthy: %s",
                ", ".join(status.summary() for status in statuses),
            )
            return statuses

        time.sleep(interval)

    summary = (
        ", ".join(status.summary() for status in last_statuses)
        or "no services reported"
    )
    raise CommandError(
        f"Services failed to become healthy within {timeout:.0f}s: {summary}"
    )


__all__ = [
    "build_parser",
    "compose_services_status",
    "compose_up",
    "handle",
    "validate_environment",
    "wait_for_healthy_services",
]
