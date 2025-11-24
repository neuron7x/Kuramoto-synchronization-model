"""Quick launcher to spin up or tear down TradePulse deployment stacks.

This CLI wraps `docker compose` commands with sensible defaults so that any
team member can bring services online or inspect them without memorizing the
full command set. It also supports optional smoke tests to validate the stack
once it is running.
"""
from __future__ import annotations

import argparse
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterable

DEFAULT_COMPOSE_FILE = Path("docker-compose.yml")
DEFAULT_ENV_FILE = Path(".env")
DEFAULT_PROJECT = "tradepulse"
DEFAULT_COMPOSE_CANDIDATES: tuple[tuple[str, ...], ...] = (("docker", "compose"), ("docker-compose",))


def _run(command: Iterable[str], *, dry_run: bool) -> subprocess.CompletedProcess[str] | None:
    printable = " ".join(shlex.quote(part) for part in command)
    print(f"[launcher] $ {printable}")
    if dry_run:
        return None
    return subprocess.run(list(command), check=True, text=True)


def _resolve_compose_command(
    preferred: str | None = None,
    *,
    allow_missing: bool = False,
) -> tuple[str, ...]:
    candidates: list[tuple[str, ...]] = []
    if preferred:
        candidates.append(tuple(shlex.split(preferred)))
    env_override = os.environ.get("TRADEPULSE_COMPOSE_CMD")
    if env_override:
        candidates.append(tuple(shlex.split(env_override)))
    candidates.extend(DEFAULT_COMPOSE_CANDIDATES)

    fallback = candidates[0] if candidates else None
    for candidate in candidates:
        try:
            subprocess.run(
                [*candidate, "version"],
                check=True,
                text=True,
                capture_output=True,
            )
        except (FileNotFoundError, subprocess.CalledProcessError):
            continue
        return candidate

    if allow_missing and fallback:
        return fallback

    raise RuntimeError("No docker compose binary available (tried docker compose and docker-compose)")


def _ensure_env_file(path: Path, *, bootstrap: bool) -> None:
    if path.exists():
        return
    if not bootstrap:
        raise FileNotFoundError(
            f"Environment file {path} is missing. Pass --bootstrap-env to copy .env.example automatically."
        )
    example = Path(".env.example")
    if not example.exists():
        raise FileNotFoundError(".env.example not found; cannot bootstrap environment file")
    print(f"[launcher] Bootstrapping {path} from {example}")
    shutil.copyfile(example, path)


def _compose_base(
    compose_cmd: tuple[str, ...],
    compose_file: Path,
    project: str,
    env_file: Path,
) -> list[str]:
    return [
        *compose_cmd,
        "--env-file",
        str(env_file),
        "-f",
        str(compose_file),
        "-p",
        project,
    ]


def _invoke_smoke_test(compose_file: Path, project: str, *, dry_run: bool) -> None:
    command = [
        sys.executable,
        "-m",
        "scripts.deploy.docker_compose_smoke",
        "--compose-file",
        str(compose_file),
        "--project-name",
        project,
    ]
    _run(command, dry_run=dry_run)


def handle_up(args: argparse.Namespace) -> None:
    compose_cmd = _resolve_compose_command(args.compose_binary, allow_missing=args.dry_run)
    compose_file = Path(args.compose_file).resolve()
    env_file = Path(args.env_file).resolve()
    _ensure_env_file(env_file, bootstrap=args.bootstrap_env)

    base = _compose_base(compose_cmd, compose_file, args.project_name, env_file)
    command = [*base, "up", "-d"]
    if args.build:
        command.append("--build")
    if args.services:
        command.extend(args.services)

    _run(command, dry_run=args.dry_run)

    if args.smoke_test:
        _invoke_smoke_test(compose_file, args.project_name, dry_run=args.dry_run)


def handle_down(args: argparse.Namespace) -> None:
    compose_cmd = _resolve_compose_command(args.compose_binary, allow_missing=args.dry_run)
    compose_file = Path(args.compose_file).resolve()
    env_file = Path(args.env_file).resolve()
    base = _compose_base(compose_cmd, compose_file, args.project_name, env_file)
    command = [*base, "down"]
    if args.prune_volumes:
        command.append("-v")
    _run(command, dry_run=args.dry_run)


def handle_status(args: argparse.Namespace) -> None:
    compose_cmd = _resolve_compose_command(args.compose_binary, allow_missing=args.dry_run)
    compose_file = Path(args.compose_file).resolve()
    env_file = Path(args.env_file).resolve()
    base = _compose_base(compose_cmd, compose_file, args.project_name, env_file)
    command = [*base, "ps"]
    _run(command, dry_run=args.dry_run)


def handle_logs(args: argparse.Namespace) -> None:
    compose_cmd = _resolve_compose_command(args.compose_binary, allow_missing=args.dry_run)
    compose_file = Path(args.compose_file).resolve()
    env_file = Path(args.env_file).resolve()
    base = _compose_base(compose_cmd, compose_file, args.project_name, env_file)
    command = [*base, "logs"]
    if args.follow:
        command.append("-f")
    if args.services:
        command.extend(args.services)
    _run(command, dry_run=args.dry_run)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--compose-file",
        default=str(DEFAULT_COMPOSE_FILE),
        help="Path to the docker-compose file to use (default: docker-compose.yml).",
    )
    parser.add_argument(
        "--env-file",
        default=str(DEFAULT_ENV_FILE),
        help="Environment file passed to docker compose (default: .env).",
    )
    parser.add_argument(
        "--project-name",
        default=DEFAULT_PROJECT,
        help="Compose project name (default: tradepulse).",
    )
    parser.add_argument(
        "--compose-binary",
        default=None,
        help="Override the compose binary (e.g., 'docker compose' or 'docker-compose').",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print commands without executing them.",
    )
    parser.add_argument(
        "--bootstrap-env",
        action="store_true",
        help="Copy .env.example to the specified env file if it is missing.",
    )

    subparsers = parser.add_subparsers(required=True, dest="command")

    up_parser = subparsers.add_parser("up", help="Start the stack.")
    up_parser.add_argument(
        "services",
        nargs="*",
        help="Optional list of services/modules to start (defaults to all).",
    )
    up_parser.add_argument(
        "--no-build",
        dest="build",
        action="store_false",
        help="Skip image builds and reuse existing images.",
    )
    up_parser.add_argument(
        "--smoke-test",
        action="store_true",
        help="Run the docker compose smoke test after startup.",
    )
    up_parser.set_defaults(build=True, handler=handle_up)

    down_parser = subparsers.add_parser("down", help="Stop the stack.")
    down_parser.add_argument(
        "--prune-volumes",
        action="store_true",
        help="Remove volumes when stopping the stack.",
    )
    down_parser.set_defaults(handler=handle_down)

    status_parser = subparsers.add_parser("status", help="Show container status for the stack.")
    status_parser.set_defaults(handler=handle_status)

    logs_parser = subparsers.add_parser("logs", help="Stream or print logs for the stack.")
    logs_parser.add_argument(
        "services",
        nargs="*",
        help="Optional list of services/modules whose logs should be shown.",
    )
    logs_parser.add_argument(
        "--follow",
        action="store_true",
        help="Follow log output instead of printing and exiting.",
    )
    logs_parser.set_defaults(handler=handle_logs)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        args.handler(args)
    except Exception as exc:  # pragma: no cover - surfaces clear failure context
        print(f"[launcher] {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
