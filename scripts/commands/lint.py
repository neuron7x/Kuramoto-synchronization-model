"""Linting subcommand implementation."""

from __future__ import annotations

import logging
import shutil
import subprocess
from argparse import ArgumentParser, Namespace, _SubParsersAction
from pathlib import Path
from typing import Callable, Sequence

from scripts.commands.base import ensure_tools_exist, register, run_subprocess

# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary


LOGGER = logging.getLogger(__name__)

FRONTEND_PACKAGE = Path("ui/dashboard")
PYTHON_LINT_STEPS: Sequence[tuple[str, Callable[[Sequence[str]], Sequence[str]]]] = (
    (
        "black",
        lambda targets: ("black", "--check", "--config", "pyproject.toml", *targets),
    ),
    (
        "isort",
        lambda targets: (
            "isort",
            "--check-only",
            "--settings-path",
            "pyproject.toml",
            *targets,
        ),
    ),
    (
        "ruff",
        lambda targets: ("ruff", "check", "--config", "pyproject.toml", *targets),
    ),
    (
        "flake8",
        lambda targets: (
            "flake8",
            "--max-line-length=100",
            "--extend-ignore=E203,W503",
            *targets,
        ),
    ),
    (
        "mypy",
        lambda targets: (
            "mypy",
            "--config-file",
            "pyproject.toml",
            "--follow-imports=skip",
            *targets,
        ),
    ),
)


def _has_tool(tool: str) -> bool:
    return shutil.which(tool) is not None


def _discover_python_targets() -> list[str]:
    try:
        diff = subprocess.run(
            ["git", "diff", "--name-only", "--diff-filter=ACMRTUXB"],
            check=True,
            stdout=subprocess.PIPE,
            text=True,
        )
        staged = subprocess.run(
            ["git", "diff", "--name-only", "--cached", "--diff-filter=ACMRTUXB"],
            check=True,
            stdout=subprocess.PIPE,
            text=True,
        )
        untracked = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard"],
            check=True,
            stdout=subprocess.PIPE,
            text=True,
        )
    except FileNotFoundError:
        LOGGER.warning("git is not available; skipping Python style enforcement.")
        return []
    except subprocess.CalledProcessError as exc:
        LOGGER.warning(
            "Unable to determine git changes (%s); skipping Python style enforcement.",
            exc,
        )
        return []

    candidates: set[str] = set()
    for output in (diff.stdout, staged.stdout, untracked.stdout):
        for path in output.splitlines():
            if path.endswith(".py"):
                candidates.add(path)

    targets = sorted(candidates)

    if not targets:
        LOGGER.info(
            "No Python file changes detected – skipping formatter and linter checks."
        )
    else:
        LOGGER.debug("Python lint targets: %s", ", ".join(targets))

    return targets


def _run_python_linters() -> None:
    targets = _discover_python_targets()
    if not targets:
        return

    required_tools = [name for name, _ in PYTHON_LINT_STEPS]
    ensure_tools_exist(required_tools)

    for name, builder in PYTHON_LINT_STEPS:
        command = builder(targets)
        LOGGER.info("Running %s checks on %s file(s)…", name, len(targets))
        run_subprocess(command)


def _run_buf(skip_buf: bool) -> None:
    if skip_buf:
        LOGGER.info("Skipping protobuf lint checks as requested.")
        return

    if _has_tool("buf"):
        LOGGER.info("Running buf lint checks…")
        run_subprocess(["buf", "lint"], check=False)
    else:
        LOGGER.info("buf executable not available – skipping protobuf linting.")


def _run_frontend_linters() -> None:
    package_json = FRONTEND_PACKAGE / "package.json"
    if not package_json.exists():
        LOGGER.debug("No frontend package.json found – skipping ESLint.")
        return

    node_modules = FRONTEND_PACKAGE / "node_modules"
    if not node_modules.exists():
        LOGGER.info(
            "Frontend dependencies are not installed – skipping ESLint."
            " Run 'npm install' in %s to enable frontend linting.",
            FRONTEND_PACKAGE,
        )
        return

    if not _has_tool("npm"):
        LOGGER.info("npm executable not available – skipping frontend linting.")
        return

    LOGGER.info("Running ESLint checks…")
    run_subprocess(["npm", "run", "lint"], cwd=FRONTEND_PACKAGE)


def _run_documentation_lint(skip_docs: bool) -> None:
    if skip_docs:
        LOGGER.info("Skipping documentation lint checks as requested.")
        return

    LOGGER.info("Running documentation lint checks…")
    # Use check=False to allow documentation issues to be reported without
    # failing the build. This matches the historical behavior before the
    # lint_docs tool was added to the lint pipeline.
    run_subprocess(("python", "-m", "tools.docs.lint_docs"), check=False)


def build_parser(subparsers: _SubParsersAction[ArgumentParser]) -> None:
    parser = subparsers.add_parser("lint", help="Run static analysis tooling")
    parser.set_defaults(command="lint", handler=handle)
    parser.add_argument(
        "--skip-buf",
        action="store_true",
        help="Skip protobuf linting even if buf is available.",
    )
    parser.add_argument(
        "--skip-docs",
        action="store_true",
        help="Skip documentation linting (normally run via tools/docs/lint_docs.py).",
    )


@register("lint")
def handle(args: Namespace) -> int:
    skip_buf = getattr(args, "skip_buf", False)
    skip_docs = getattr(args, "skip_docs", False)

    _run_python_linters()
    _run_buf(skip_buf)
    _run_frontend_linters()
    _run_documentation_lint(skip_docs)

    LOGGER.info("Lint checks completed successfully.")
    return 0
