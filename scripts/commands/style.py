"""Code-style maintenance command: formatters, linters, and pre-commit integration."""

from __future__ import annotations

# SPDX-License-Identifier: MIT
import logging
import shutil
import subprocess
from argparse import ArgumentParser, Namespace, _SubParsersAction
from pathlib import Path
from typing import Iterable, Sequence

from scripts.commands.base import ensure_tools_exist, register, run_subprocess

LOGGER = logging.getLogger(__name__)

PYTHON_EXTENSIONS = (".py",)
DEFAULT_TARGETS = (
    Path("analytics"),
    Path("application"),
    Path("backtest"),
    Path("core"),
    Path("domain"),
    Path("execution"),
    Path("src"),
    Path("scripts"),
)
FORMATTERS: Sequence[str] = ("black", "isort")
LINTERS: Sequence[str] = ("ruff",)


def build_parser(subparsers: _SubParsersAction[ArgumentParser]) -> None:
    parser = subparsers.add_parser(
        "style",
        help="Apply repository code-style policies, run linters, and manage pre-commit hooks.",
    )
    parser.set_defaults(command="style", handler=handle)
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        help="Explicit paths or files to process. Defaults to core packages when omitted.",
    )
    parser.add_argument(
        "--changed-only",
        action="store_true",
        help="Restrict execution to files modified in git (staged, unstaged, and untracked).",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Run tools in verification mode without writing changes.",
    )
    parser.add_argument(
        "--skip-hook-install",
        action="store_true",
        help="Do not install or update pre-commit hooks automatically.",
    )
    parser.add_argument(
        "--run-pre-commit",
        action="store_true",
        help="Execute 'pre-commit run --all-files' after local linters succeed.",
    )
    parser.add_argument(
        "--pre-commit-autoupdate",
        action="store_true",
        help="Update pinned hook revisions before installing them.",
    )
    parser.add_argument(
        "--extra-hook",
        action="append",
        default=None,
        help="Additional pre-commit hook IDs to run explicitly after installation.",
    )


@register("style")
def handle(args: Namespace) -> int:
    namespace = args
    targets = _determine_targets(tuple(namespace.paths or ()), namespace.changed_only)
    LOGGER.debug(
        "Style targets resolved to: %s", ", ".join(map(str, targets)) or "<none>"
    )

    if not targets:
        LOGGER.info("No targets found for style enforcement; exiting early.")
        return 0

    _run_python_style_suite(targets, namespace.check)

    if not namespace.skip_hook_install:
        _manage_pre_commit(namespace.pre_commit_autoupdate)

    if namespace.run_pre_commit:
        _run_pre_commit_hooks(namespace.extra_hook or (), namespace.check)

    LOGGER.info("Code-style tasks completed successfully.")
    return 0


# ---------------------------------------------------------------------------
# Tool orchestration helpers
# ---------------------------------------------------------------------------


def _determine_targets(paths: Sequence[Path], changed_only: bool) -> list[Path]:
    if paths:
        return [
            path for path in paths if path.exists() and "node_modules" not in path.parts
        ]

    if changed_only:
        changed = _discover_changed_paths()
        return [
            Path(path) for path in changed if "node_modules" not in Path(path).parts
        ]

    return [path for path in DEFAULT_TARGETS if path.exists()]


def _discover_changed_paths() -> list[str]:
    commands = (
        ("git", "diff", "--name-only", "--diff-filter=ACMRTUXB"),
        ("git", "diff", "--name-only", "--cached", "--diff-filter=ACMRTUXB"),
        ("git", "ls-files", "--others", "--exclude-standard"),
    )
    results: set[str] = set()
    for command in commands:
        try:
            output = subprocess.run(
                command,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
            ).stdout
        except (FileNotFoundError, subprocess.CalledProcessError):
            LOGGER.debug(
                "git not available when computing changed files – skipping optimisation."
            )
            return []

        for line in output.splitlines():
            if Path(line).suffix in PYTHON_EXTENSIONS:
                results.add(line)

    return sorted(results)


def _run_python_style_suite(targets: Sequence[Path], check: bool) -> None:
    ensure_tools_exist([*FORMATTERS, *LINTERS])

    string_targets = [str(path) for path in targets]

    _run_ruff(string_targets, check)
    _run_black(string_targets, check)
    _run_isort(string_targets, check)


def _run_ruff(targets: Sequence[str], check: bool) -> None:
    command = ["ruff", "check", "--config", "pyproject.toml", *targets]
    if not check:
        command.append("--fix")
    LOGGER.info("Running ruff (%s mode)…", "check" if check else "autofix")
    run_subprocess(command)


def _run_black(targets: Sequence[str], check: bool) -> None:
    command = ["black", "--config", "pyproject.toml", *targets]
    if check:
        command.append("--check")
    LOGGER.info("Running black (%s mode)…", "check" if check else "format")
    run_subprocess(command)


def _run_isort(targets: Sequence[str], check: bool) -> None:
    command = ["isort", "--settings-path", "pyproject.toml"]
    if check:
        command.append("--check-only")
    else:
        command.append("--profile=black")
    command.extend(targets)
    LOGGER.info("Running isort (%s mode)…", "check" if check else "reorder")
    run_subprocess(command)


def _manage_pre_commit(autoupdate: bool) -> None:
    if shutil.which("pre-commit") is None:
        LOGGER.warning(
            "pre-commit executable not found. Install it with 'pip install pre-commit' to manage hooks."
        )
        return

    if autoupdate:
        LOGGER.info("Updating pre-commit hook revisions…")
        run_subprocess(["pre-commit", "autoupdate"])

    LOGGER.info("Installing pre-commit hooks…")
    run_subprocess(["pre-commit", "install"])


def _run_pre_commit_hooks(extra_hooks: Iterable[str], check: bool) -> None:
    if shutil.which("pre-commit") is None:
        LOGGER.warning("Cannot run pre-commit hooks because the executable is missing.")
        return

    base_command = ["pre-commit", "run"]
    if check:
        base_command.append("--all-files")
    else:
        base_command.extend(["--all-files", "--hook-stage", "manual"])

    LOGGER.info("Running pre-commit across all files…")
    run_subprocess(base_command)

    for hook_id in extra_hooks:
        if not hook_id:
            continue
        LOGGER.info("Running pre-commit hook '%s'…", hook_id)
        run_subprocess(["pre-commit", "run", hook_id, "--all-files"])
