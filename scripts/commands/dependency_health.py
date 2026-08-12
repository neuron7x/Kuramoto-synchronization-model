# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Commands to validate dependency health across toolchains."""

from __future__ import annotations

import logging
from argparse import Namespace, _SubParsersAction
from pathlib import Path
from typing import Sequence

from scripts.commands.base import CommandError, register
from scripts.dependency_health import (
    DependencyHealthError,
    check_go_dependencies,
    check_node_dependencies,
    check_python_dependencies,
    merge_reports,
)

LOGGER = logging.getLogger(__name__)

DEFAULT_REQUIREMENTS = (Path("requirements.txt"),)
DEFAULT_DEV_REQUIREMENTS = (Path("requirements-dev.txt"),)
DEFAULT_BACKEND_REQUIREMENTS = (Path("requirements-backend.txt"),)
DEFAULT_CONSTRAINTS = (Path("constraints/security.txt"),)
DEFAULT_RUNTIME_LOCK = Path("requirements.lock")
DEFAULT_DEV_LOCK = Path("requirements-dev.lock")
DEFAULT_GO_MOD = Path("go.mod")
DEFAULT_GO_SUM = Path("go.sum")
DEFAULT_NODE_PACKAGES = (
    (Path("ui/dashboard/package.json"), Path("ui/dashboard/package-lock.json")),
    (Path("apps/web/package.json"), Path("apps/web/package-lock.json")),
)


def build_parser(subparsers: _SubParsersAction[object]) -> None:
    parser = subparsers.add_parser(
        "dependency-health",
        help="Validate dependency manifests for Python, Node, and Go stacks.",
    )
    parser.set_defaults(command="dependency-health", handler=handle)

    parser.add_argument(
        "--requirements",
        action="append",
        type=Path,
        default=None,
        help="Runtime requirement files (default: requirements.txt).",
    )
    parser.add_argument(
        "--dev-requirements",
        action="append",
        type=Path,
        default=None,
        help="Developer requirement files (default: requirements-dev.txt).",
    )
    parser.add_argument(
        "--backend-requirements",
        action="append",
        type=Path,
        default=None,
        help="Backend pinned requirements (default: requirements-backend.txt).",
    )
    parser.add_argument(
        "--constraints",
        action="append",
        type=Path,
        default=None,
        help="Constraint files (default: constraints/security.txt).",
    )
    parser.add_argument(
        "--runtime-lock",
        type=Path,
        default=DEFAULT_RUNTIME_LOCK,
        help="Runtime lock file (default: requirements.lock).",
    )
    parser.add_argument(
        "--dev-lock",
        type=Path,
        default=DEFAULT_DEV_LOCK,
        help="Development lock file (default: requirements-dev.lock).",
    )
    parser.add_argument(
        "--python-version",
        type=str,
        default=None,
        help="Override python marker evaluation (e.g. 3.12).",
    )
    parser.add_argument(
        "--skip-node",
        action="store_true",
        help="Skip Node dependency validation.",
    )
    parser.add_argument(
        "--skip-go",
        action="store_true",
        help="Skip Go dependency validation.",
    )
    parser.add_argument(
        "--node-package",
        action="append",
        type=Path,
        default=None,
        help="Additional package.json paths (package-lock.json inferred).",
    )
    parser.add_argument(
        "--go-mod",
        type=Path,
        default=DEFAULT_GO_MOD,
        help="Path to go.mod (default: go.mod).",
    )
    parser.add_argument(
        "--go-sum",
        type=Path,
        default=DEFAULT_GO_SUM,
        help="Path to go.sum (default: go.sum).",
    )


def _resolve_paths(paths: Sequence[Path] | None, defaults: Sequence[Path]) -> tuple[Path, ...]:
    return tuple(paths if paths else defaults)


def _resolve_node_pairs(extra_packages: Sequence[Path] | None) -> tuple[tuple[Path, Path], ...]:
    pairs = list(DEFAULT_NODE_PACKAGES)
    for package_path in extra_packages or ():
        lock_path = package_path.with_name("package-lock.json")
        pairs.append((package_path, lock_path))
    return tuple(pairs)


@register("dependency-health")
def handle(args: object) -> int:
    namespace: Namespace = args if isinstance(args, Namespace) else Namespace(**vars(args))

    requirements = _resolve_paths(namespace.requirements, DEFAULT_REQUIREMENTS)
    dev_requirements = _resolve_paths(namespace.dev_requirements, DEFAULT_DEV_REQUIREMENTS)
    backend_requirements = _resolve_paths(
        namespace.backend_requirements, DEFAULT_BACKEND_REQUIREMENTS
    )
    constraints = _resolve_paths(namespace.constraints, DEFAULT_CONSTRAINTS)

    try:
        python_report = check_python_dependencies(
            requirements=requirements,
            dev_requirements=dev_requirements,
            backend_requirements=backend_requirements,
            constraints=constraints,
            runtime_lock=namespace.runtime_lock,
            dev_lock=namespace.dev_lock,
            python_version=namespace.python_version,
        )
    except DependencyHealthError as exc:
        raise CommandError(str(exc)) from exc

    reports = [python_report]

    if not namespace.skip_node:
        for package_json, package_lock in _resolve_node_pairs(namespace.node_package):
            try:
                reports.append(check_node_dependencies(package_json, package_lock))
            except DependencyHealthError as exc:
                raise CommandError(str(exc)) from exc

    if not namespace.skip_go:
        try:
            reports.append(check_go_dependencies(namespace.go_mod, namespace.go_sum))
        except DependencyHealthError as exc:
            raise CommandError(str(exc)) from exc

    combined = merge_reports(*reports)
    if combined.issues:
        for issue in combined.issues:
            LOGGER.error(
                "%s:%s: %s",
                issue.system,
                issue.path,
                issue.message,
            )
        raise CommandError(f"Dependency health check failed with {len(combined.issues)} issue(s).")

    LOGGER.info("Dependency health checks passed.")
    return 0
