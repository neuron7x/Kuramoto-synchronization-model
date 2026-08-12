# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Automate local environment bootstrapping workflows."""

from __future__ import annotations

# SPDX-License-Identifier: MIT
import logging
import os
import shutil
import sys
from argparse import Namespace, _SubParsersAction
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

from scripts.commands.base import CommandError, register, run_subprocess

LOGGER = logging.getLogger(__name__)

DEFAULT_VENV_PATH = Path(".venv")
DEFAULT_REQUIREMENTS = (Path("requirements.lock"),)
DEFAULT_DEV_REQUIREMENTS = (Path("requirements-dev.lock"),)
DEFAULT_FRONTEND_PATH = Path("ui/dashboard")


@dataclass(frozen=True)
class BootstrapConfig:
    """Configuration describing the desired bootstrap actions."""

    python: Path
    venv_path: Path
    recreate_venv: bool
    upgrade_pip: bool
    install_python_dependencies: bool
    include_dev_dependencies: bool
    requirements: Sequence[Path]
    dev_requirements: Sequence[Path]
    extras: Sequence[str]
    install_pre_commit: bool
    install_frontend: bool
    reinstall_frontend: bool
    frontend_path: Path
    run_readiness_checks: bool
    run_smoke_test: bool


def build_parser(subparsers: _SubParsersAction[object]) -> None:
    """Register the ``bootstrap`` subcommand with the main CLI parser."""

    parser = subparsers.add_parser(
        "bootstrap",
        help="Automate creation of the Python virtualenv and optional toolchains.",
    )
    parser.set_defaults(command="bootstrap", handler=handle)

    parser.add_argument(
        "--python",
        type=Path,
        default=Path(sys.executable),
        help="Python interpreter used to create the virtual environment.",
    )
    parser.add_argument(
        "--venv-path",
        type=Path,
        default=DEFAULT_VENV_PATH,
        help="Location of the virtual environment (defaults to .venv).",
    )
    parser.add_argument(
        "--recreate-venv",
        action="store_true",
        help="Recreate the virtual environment even if it already exists.",
    )
    parser.add_argument(
        "--no-pip-upgrade",
        dest="upgrade_pip",
        action="store_false",
        help="Skip upgrading pip/setuptools/wheel after creating the venv.",
    )
    parser.set_defaults(upgrade_pip=True)
    parser.add_argument(
        "--skip-python-deps",
        action="store_true",
        help="Do not install Python requirements (venv will still be created).",
    )
    parser.add_argument(
        "--include-dev",
        action="store_true",
        help="Install developer tooling from requirements-dev.lock.",
    )
    parser.add_argument(
        "--requirements",
        action="append",
        type=Path,
        default=None,
        help="Extra requirements files to install in addition to the defaults.",
    )
    parser.add_argument(
        "--dev-requirements",
        action="append",
        type=Path,
        default=None,
        help="Override developer requirements files (defaults to requirements-dev.lock).",
    )
    parser.add_argument(
        "--extras",
        nargs="*",
        default=(),
        metavar="EXTRA",
        help="Install optional extras defined in pyproject.toml (e.g. connectors gpu).",
    )
    parser.add_argument(
        "--pre-commit",
        dest="install_pre_commit",
        action="store_true",
        help="Install git hooks via pre-commit after dependencies are installed.",
    )
    parser.add_argument(
        "--frontend",
        dest="install_frontend",
        action="store_true",
        help="Install frontend package.json dependencies (requires npm/pnpm/yarn).",
    )
    parser.add_argument(
        "--frontend-path",
        type=Path,
        default=DEFAULT_FRONTEND_PATH,
        help="Path to the frontend workspace (defaults to ui/dashboard).",
    )
    parser.add_argument(
        "--reinstall-frontend",
        action="store_true",
        help="Force reinstall of frontend dependencies even if node_modules exists.",
    )
    parser.add_argument(
        "--verify",
        dest="run_readiness_checks",
        action="store_true",
        help=(
            "Run lightweight post-install verification (pip check and CLI help) "
            "to confirm the environment is healthy."
        ),
    )
    parser.add_argument(
        "--smoke-test",
        dest="run_smoke_test",
        action="store_true",
        help=(
            "Execute a sample CSV analysis using interfaces.cli to confirm core "
            "data pathways are operational."
        ),
    )


def _resolve_python_interpreter(candidate: Path) -> Path:
    interpreter = candidate.resolve()
    if not interpreter.exists():
        raise CommandError(f"Python interpreter not found at {interpreter}.")
    if not os.access(interpreter, os.X_OK):
        raise CommandError(f"Python interpreter is not executable: {interpreter}.")
    return interpreter


def _resolve_requirements(paths: Iterable[Path]) -> tuple[Path, ...]:
    resolved: list[Path] = []
    for path in paths:
        absolute = path.resolve()
        if not absolute.exists():
            raise CommandError(f"Requirements file missing: {absolute}.")
        resolved.append(absolute)
    return tuple(resolved)


def _venv_python_path(venv_path: Path) -> Path:
    if os.name == "nt":
        return venv_path / "Scripts" / "python.exe"
    return venv_path / "bin" / "python"


def _venv_exists(venv_path: Path) -> bool:
    return (venv_path / "pyvenv.cfg").exists()


def _create_virtualenv(python: Path, venv_path: Path, recreate: bool) -> None:
    if _venv_exists(venv_path):
        if not recreate:
            LOGGER.info(
                "Virtual environment already present at %s – skipping creation.",
                venv_path,
            )
            return
        LOGGER.info("Removing existing virtual environment at %s", venv_path)
        shutil.rmtree(venv_path)

    LOGGER.info("Creating virtual environment at %s", venv_path)
    run_subprocess((str(python), "-m", "venv", str(venv_path)))

    interpreter = _venv_python_path(venv_path)
    if not interpreter.exists():
        raise CommandError(
            "Virtual environment creation did not produce a Python executable. "
            f"Expected to find {interpreter}."
        )


def _upgrade_pip(venv_python: Path) -> None:
    LOGGER.info("Upgrading pip, setuptools, and wheel…")
    run_subprocess(
        (
            str(venv_python),
            "-m",
            "pip",
            "install",
            "--upgrade",
            "pip",
            "setuptools",
            "wheel",
        )
    )


def _install_from_requirements(venv_python: Path, files: Sequence[Path]) -> None:
    for requirement in files:
        LOGGER.info("Installing Python dependencies from %s", requirement)
        run_subprocess((str(venv_python), "-m", "pip", "install", "-r", str(requirement)))


def _install_extras(venv_python: Path, extras: Sequence[str]) -> None:
    if not extras:
        return
    extras_arg = ",".join(extras)
    LOGGER.info("Installing project extras: %s", extras_arg)
    run_subprocess((str(venv_python), "-m", "pip", "install", f".[{extras_arg}]"), cwd=Path.cwd())


def _install_pre_commit(venv_python: Path) -> None:
    LOGGER.info("Installing pre-commit hooks…")
    run_subprocess((str(venv_python), "-m", "pre_commit", "install", "--install-hooks"))
    run_subprocess(
        (
            str(venv_python),
            "-m",
            "pre_commit",
            "install",
            "--hook-type",
            "commit-msg",
        )
    )


def _select_package_manager(frontend_path: Path) -> Sequence[str]:
    pnpm_lock = frontend_path / "pnpm-lock.yaml"
    yarn_lock = frontend_path / "yarn.lock"
    npm_lock = frontend_path / "package-lock.json"

    if pnpm_lock.exists() and shutil.which("pnpm"):
        return ("pnpm", "install")
    if yarn_lock.exists() and shutil.which("yarn"):
        return ("yarn", "install", "--frozen-lockfile")
    if npm_lock.exists() and shutil.which("npm"):
        return ("npm", "ci")
    if shutil.which("npm"):
        return ("npm", "install")
    if shutil.which("yarn"):
        return ("yarn", "install")
    if shutil.which("pnpm"):
        return ("pnpm", "install")
    raise CommandError("No supported Node.js package manager (pnpm, yarn, npm) found in PATH.")


def _install_frontend_dependencies(frontend_path: Path, reinstall: bool) -> None:
    package_json = frontend_path / "package.json"
    if not package_json.exists():
        raise CommandError(
            f"package.json not found in {frontend_path}; cannot install frontend dependencies."
        )

    node_modules = frontend_path / "node_modules"
    if node_modules.exists() and not reinstall:
        LOGGER.info("Frontend dependencies already installed at %s – skipping.", node_modules)
        return

    command = _select_package_manager(frontend_path)
    LOGGER.info("Installing frontend dependencies with: %s", " ".join(command))
    run_subprocess(command, cwd=frontend_path)


def _run_readiness_checks(venv_python: Path) -> None:
    LOGGER.info("Running dependency integrity check (pip check)…")
    run_subprocess((str(venv_python), "-m", "pip", "check"))

    LOGGER.info("Verifying core CLI responds to --help…")
    run_subprocess((str(venv_python), "-m", "interfaces.cli", "--help"))


def _run_sample_analysis(venv_python: Path) -> None:
    sample_path = Path("sample.csv").resolve()
    if not sample_path.exists():
        LOGGER.warning("sample.csv not found at %s; skipping smoke test.", sample_path)
        return

    LOGGER.info("Running smoke-test analysis on %s", sample_path)
    run_subprocess(
        (
            str(venv_python),
            "-m",
            "interfaces.cli",
            "analyze",
            "--csv",
            str(sample_path),
            "--window",
            "200",
        )
    )


def _build_config(args: Namespace) -> BootstrapConfig:
    python = _resolve_python_interpreter(getattr(args, "python"))
    venv_path = getattr(args, "venv_path").resolve()
    recreate_venv = bool(getattr(args, "recreate_venv", False))
    upgrade_pip = bool(getattr(args, "upgrade_pip", True))
    install_python_dependencies = not bool(getattr(args, "skip_python_deps", False))
    include_dev = bool(getattr(args, "include_dev", False))

    extra_requirements = tuple(getattr(args, "requirements") or ())
    requirements = DEFAULT_REQUIREMENTS + extra_requirements
    dev_requirements = tuple(getattr(args, "dev_requirements") or DEFAULT_DEV_REQUIREMENTS)

    resolved_requirements = _resolve_requirements(requirements)
    resolved_dev_requirements = _resolve_requirements(dev_requirements) if include_dev else ()

    extras = tuple(getattr(args, "extras", ()))
    install_pre_commit = bool(getattr(args, "install_pre_commit", False))
    install_frontend = bool(getattr(args, "install_frontend", False))
    reinstall_frontend = bool(getattr(args, "reinstall_frontend", False))
    frontend_path = getattr(args, "frontend_path", DEFAULT_FRONTEND_PATH).resolve()
    run_readiness_checks = bool(getattr(args, "run_readiness_checks", False))
    run_smoke_test = bool(getattr(args, "run_smoke_test", False))

    return BootstrapConfig(
        python=python,
        venv_path=venv_path,
        recreate_venv=recreate_venv,
        upgrade_pip=upgrade_pip,
        install_python_dependencies=install_python_dependencies,
        include_dev_dependencies=include_dev,
        requirements=resolved_requirements,
        dev_requirements=resolved_dev_requirements,
        extras=extras,
        install_pre_commit=install_pre_commit,
        install_frontend=install_frontend,
        reinstall_frontend=reinstall_frontend,
        frontend_path=frontend_path,
        run_readiness_checks=run_readiness_checks,
        run_smoke_test=run_smoke_test,
    )


def execute(config: BootstrapConfig) -> None:
    """Run the bootstrap workflow described by *config*."""

    _create_virtualenv(config.python, config.venv_path, config.recreate_venv)
    venv_python = _venv_python_path(config.venv_path)

    if config.install_python_dependencies:
        if config.upgrade_pip:
            _upgrade_pip(venv_python)
        _install_from_requirements(venv_python, config.requirements)
        if config.include_dev_dependencies and config.dev_requirements:
            _install_from_requirements(venv_python, config.dev_requirements)
        _install_extras(venv_python, config.extras)
    else:
        LOGGER.info("Skipping Python dependency installation as requested.")

    if config.install_pre_commit:
        if not config.install_python_dependencies and not config.include_dev_dependencies:
            LOGGER.warning(
                "pre-commit installation requested but Python dependencies were skipped."
                " Ensure pre-commit is available inside the virtual environment."
            )
        _install_pre_commit(venv_python)

    if config.install_frontend:
        _install_frontend_dependencies(config.frontend_path, config.reinstall_frontend)

    if config.run_readiness_checks:
        _run_readiness_checks(venv_python)

    if config.run_smoke_test:
        _run_sample_analysis(venv_python)


@register("bootstrap")
def handle(args: Namespace) -> int:
    config = _build_config(args)
    execute(config)
    LOGGER.info("Bootstrap completed successfully.")
    return 0
