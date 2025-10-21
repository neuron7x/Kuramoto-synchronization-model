"""Execute the project's automated test suites with advanced orchestration."""

from __future__ import annotations

# SPDX-License-Identifier: MIT
import argparse
import logging
import os
from shutil import which
from argparse import Namespace, _SubParsersAction
from pathlib import Path
from typing import Sequence

from scripts.commands.base import register, run_subprocess
from scripts.testing import (
    DEFAULT_ARTIFACT_DIR,
    DEFAULT_CACHE_DIR,
    TestRunner,
    TestRunnerConfig,
)

DASHBOARD_TEST_ENTRYPOINT = Path("domains/ui/dashboard/tests/test.js")

LOGGER = logging.getLogger(__name__)


def build_parser(subparsers: _SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser(
        "test",
        help="Run automated tests across supported stacks with caching and gates",
    )
    parser.set_defaults(command="test", handler=handle)

    parser.add_argument(
        "--mode",
        choices=("full", "quick"),
        default="full",
        help="Select between full validation (default) or a quick local smoke run.",
    )
    parser.add_argument(
        "--workers",
        default="auto",
        help="Number of pytest-xdist workers. Accepts integers or 'auto'.",
    )
    parser.add_argument(
        "--pytest-args",
        nargs=argparse.REMAINDER,
        default=(),
        help="Additional arguments forwarded verbatim to pytest. Use '--' to separate.",
    )
    parser.add_argument(
        "--no-coverage",
        action="store_true",
        help="Disable coverage tracking even during full runs.",
    )
    parser.add_argument(
        "--no-mutation",
        action="store_true",
        help="Skip mutation analysis stage.",
    )
    parser.add_argument(
        "--artifacts-dir",
        type=Path,
        default=None,
        help="Directory where reports will be written. Defaults to reports/tests/latest.",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=None,
        help="Directory used for storing cached artifacts.",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Do not persist artifacts into the local cache directory.",
    )
    parser.add_argument(
        "--rerun-flaky",
        type=int,
        default=1,
        help="Number of times to rerun flaky tests detected by pytest's cache.",
    )
    parser.add_argument(
        "--coverage-threshold",
        type=float,
        default=90.0,
        help="Fail the run if line coverage (percentage) drops below this threshold.",
    )
    parser.add_argument(
        "--mutation-threshold",
        type=float,
        default=60.0,
        help="Fail the run if mutation score (percentage) drops below this threshold.",
    )
    parser.add_argument(
        "--junit-report",
        type=Path,
        help="Custom path for the generated JUnit XML report.",
    )
    parser.add_argument(
        "--html-report",
        type=Path,
        help="Custom path for the generated pytest HTML report.",
    )
    parser.add_argument(
        "--coverage-xml",
        type=Path,
        help="Override the output path for the coverage XML report.",
    )
    parser.add_argument(
        "--coverage-json",
        type=Path,
        help="Override the output path for the coverage JSON report.",
    )
    parser.add_argument(
        "--mutation-report",
        type=Path,
        help="Where to store the textual mutation testing summary.",
    )
    parser.add_argument(
        "--auto-issue",
        action="store_true",
        help="Create a GitHub issue automatically when gates fail (requires GITHUB_TOKEN).",
    )
    parser.add_argument(
        "--issue-repo",
        help="Repository in 'owner/name' format used for automatic issue creation.",
    )
    parser.add_argument(
        "--issue-label",
        action="append",
        default=None,
        help="Labels to apply to automatically created issues (can be repeated).",
    )
    parser.add_argument(
        "--debug-logs",
        action="store_true",
        help="Emit verbose debug logs for troubleshooting the runner itself.",
    )
    parser.add_argument(
        "--ci-mode",
        action="store_true",
        help="Force CI mode regardless of environment variables.",
    )


@register("test")
def handle(args: Namespace) -> int:
    namespace = args
    pytest_args: Sequence[str] = tuple(namespace.pytest_args or ())
    issue_labels: tuple[str, ...]
    if namespace.issue_label:
        issue_labels = tuple(label for label in namespace.issue_label if label)
    else:
        issue_labels = ("ci", "tests")

    artifacts_dir = namespace.artifacts_dir or DEFAULT_ARTIFACT_DIR
    cache_dir = namespace.cache_dir or DEFAULT_CACHE_DIR

    config = TestRunnerConfig(
        pytest_args=tuple(pytest_args),
        mode=namespace.mode,
        workers=str(namespace.workers),
        collect_coverage=not namespace.no_coverage,
        enable_mutation_tests=not namespace.no_mutation,
        artifacts_dir=artifacts_dir,
        cache_dir=cache_dir,
        use_cache=not namespace.no_cache,
        rerun_flaky_attempts=max(0, namespace.rerun_flaky),
        coverage_threshold=namespace.coverage_threshold,
        mutation_threshold=max(0.0, namespace.mutation_threshold),
        junit_report=namespace.junit_report,
        html_report=namespace.html_report,
        coverage_xml=namespace.coverage_xml,
        coverage_json=namespace.coverage_json,
        mutation_report=namespace.mutation_report,
        ci_mode=namespace.ci_mode or bool(os.getenv("CI")),
        debug_logs=namespace.debug_logs,
        auto_issue=namespace.auto_issue,
        issue_repository=namespace.issue_repo,
        issue_labels=issue_labels,
    )

    runner = TestRunner(config)
    result = runner.run()
    if result.flaky_reruns:
        LOGGER.info("Recovered flaky tests after %s rerun(s).", result.flaky_reruns)

    _run_node_dashboard_tests()

    return result.pytest_return_code


def _run_node_dashboard_tests() -> None:
    if which("node") is None:
        LOGGER.info("Node.js not available – skipping front-end tests.")
        return

    if not DASHBOARD_TEST_ENTRYPOINT.exists():
        LOGGER.info(
            "No Node.js test suite found at %s – skipping.", DASHBOARD_TEST_ENTRYPOINT
        )
        return

    LOGGER.info("Running Node.js dashboard tests…")
    run_subprocess(["node", str(DASHBOARD_TEST_ENTRYPOINT)])


