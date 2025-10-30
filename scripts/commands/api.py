from __future__ import annotations

# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
import logging
from argparse import _SubParsersAction
from pathlib import Path

from scripts.api_management import ApiGovernanceRunner, load_registry
from scripts.api_management.generator import GeneratedArtifacts
from scripts.api_management.validation import ApiValidationReport
from scripts.commands.base import CommandError, register

LOGGER = logging.getLogger(__name__)
DEFAULT_REGISTRY = Path("configs/api/registry.yaml")
DEFAULT_CLIENTS_DIR = Path("docs/api/clients")
DEFAULT_DOCS_DIR = Path("docs/api")
DEFAULT_EXAMPLES_DIR = Path("docs/api/examples")


def build_parser(subparsers: _SubParsersAction[object]) -> None:
    parser = subparsers.add_parser(
        "api",
        help="Validate API contracts and generate client/documentation artifacts.",
    )
    parser.add_argument(
        "action",
        choices=("validate", "generate"),
        help="Action to execute. 'validate' runs checks only, 'generate' also writes artifacts.",
    )
    parser.add_argument(
        "--registry",
        type=Path,
        default=DEFAULT_REGISTRY,
        help="Path to the API registry definition.",
    )
    parser.add_argument(
        "--clients-dir",
        type=Path,
        default=DEFAULT_CLIENTS_DIR,
        help="Directory where generated client SDKs are written.",
    )
    parser.add_argument(
        "--docs-dir",
        type=Path,
        default=DEFAULT_DOCS_DIR,
        help="Directory where governance documentation is emitted.",
    )
    parser.add_argument(
        "--examples-dir",
        type=Path,
        default=DEFAULT_EXAMPLES_DIR,
        help="Directory for response simulator payloads.",
    )
    parser.add_argument(
        "--visualization",
        type=Path,
        default=None,
        help="Optional explicit path for the generated DOT visualization.",
    )
    parser.add_argument(
        "--fail-on-warnings",
        action="store_true",
        help="Treat validation warnings as errors.",
    )
    parser.set_defaults(command="api", handler=handle_api)


@register("api")
def handle_api(args: object) -> int:
    registry_path = Path(args.registry)
    if not registry_path.exists():
        raise CommandError(f"Registry file {registry_path} does not exist.")

    repo_root = Path.cwd()
    registry = load_registry(registry_path, repo_root=repo_root)
    runner = ApiGovernanceRunner(registry, repo_root=repo_root)

    if args.action == "validate":
        report = runner.validate()
        _log_report(report)
        return 0 if report.ok else 1

    if args.action == "generate":
        outcome = runner.orchestrate(
            clients_dir=Path(args.clients_dir),
            docs_dir=Path(args.docs_dir),
            examples_dir=Path(args.examples_dir),
            visualization_path=Path(args.visualization) if args.visualization else None,
            fail_on_warnings=bool(args.fail_on_warnings),
        )
        _log_report(outcome.report)
        _log_artifacts(outcome.artifacts)
        return 0

    raise CommandError(f"Unsupported action: {args.action}")


def _log_report(report: ApiValidationReport) -> None:
    for message in report.checks:
        LOGGER.info("%s", message)
    for warning in report.warnings:
        LOGGER.warning("%s", warning)
    for error in report.errors:
        LOGGER.error("%s", error)


def _log_artifacts(artifacts: GeneratedArtifacts) -> None:
    LOGGER.info("Python client: %s", _rel(artifacts.python_client))
    LOGGER.info("TypeScript client: %s", _rel(artifacts.typescript_client))
    LOGGER.info("Overview document: %s", _rel(artifacts.overview))
    LOGGER.info("Routes index: %s", _rel(artifacts.routes_index))
    LOGGER.info("Webhook contracts: %s", _rel(artifacts.webhooks_doc))
    LOGGER.info("Smoke tests index: %s", _rel(artifacts.smoke_tests_index))
    LOGGER.info("Changelog: %s", _rel(artifacts.changelog))
    LOGGER.info("Deprecations: %s", _rel(artifacts.deprecations))
    LOGGER.info("Migrations: %s", _rel(artifacts.migrations))
    LOGGER.info("Visualization: %s", _rel(artifacts.visualization))
    LOGGER.info("Examples generated: %d", len(artifacts.examples))


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(Path.cwd()))
    except ValueError:
        return str(path)
