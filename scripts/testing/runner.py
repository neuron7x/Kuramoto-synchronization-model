"""High-level orchestration for repository-wide test execution."""

from __future__ import annotations

# SPDX-License-Identifier: MIT
import hashlib
import importlib.util
import json
import logging
import os
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

import requests

from scripts.commands.base import CommandError, run_subprocess

LOGGER = logging.getLogger(__name__)

DEFAULT_PYTEST_ROOTS = (
    Path("tests/unit"),
    Path("tests/integration"),
    Path("tests/property"),
)
DEFAULT_COVERAGE_SOURCES = ("core", "backtest", "execution", "analytics", "src")
DEFAULT_ARTIFACT_DIR = Path("reports/tests/latest")
DEFAULT_CACHE_DIR = Path(".cache/test-runner")


@dataclass(slots=True)
class TestRunnerConfig:
    """User configurable options for :class:`TestRunner`."""

    pytest_args: tuple[str, ...] = ()
    mode: str = "full"
    workers: str = "auto"
    collect_coverage: bool = True
    enable_mutation_tests: bool = True
    artifacts_dir: Path = DEFAULT_ARTIFACT_DIR
    cache_dir: Path = DEFAULT_CACHE_DIR
    use_cache: bool = True
    rerun_flaky_attempts: int = 1
    coverage_threshold: float = 90.0
    mutation_threshold: float = 0.0
    junit_report: Path | None = None
    html_report: Path | None = None
    coverage_xml: Path | None = None
    coverage_json: Path | None = None
    mutation_report: Path | None = None
    ci_mode: bool = bool(os.getenv("CI"))
    debug_logs: bool = False
    auto_issue: bool = False
    issue_repository: str | None = None
    issue_labels: tuple[str, ...] = ("ci", "tests")

    def normalized_mode(self) -> str:
        mode = self.mode.lower().strip()
        if mode not in {"full", "quick"}:
            raise CommandError(f"Unsupported test mode '{self.mode}'.")
        return mode


@dataclass(slots=True)
class MutationSummary:
    survived: int = 0
    killed: int = 0
    timeout: int = 0
    incompetent: int = 0

    @property
    def total(self) -> int:
        return self.survived + self.killed + self.timeout + self.incompetent

    @property
    def score(self) -> float:
        total = self.total
        if total == 0:
            return 100.0
        return (self.killed / total) * 100


@dataclass(slots=True)
class TestRunResult:
    pytest_return_code: int
    flaky_reruns: int = 0
    mutation_summary: MutationSummary | None = None
    coverage_percent: float | None = None
    cache_key: str | None = None


class TestRunner:
    """Execute end-to-end test suites with artifact management and quality gates."""

    def __init__(self, config: TestRunnerConfig) -> None:
        self.config = config
        self._xdist_supported = self._xdist_available()
        self.config.workers = self._normalize_workers(self.config.workers)
        if self.config.ci_mode and self.config.use_cache:
            LOGGER.debug(
                "CI mode detected – disabling local artifact cache to avoid workspace bloat."
            )
            self.config.use_cache = False

        self.artifacts_dir = self._resolve_artifact_root(config.artifacts_dir)
        self.config.artifacts_dir = self.artifacts_dir
        self.cache_dir = config.cache_dir
        self._ensure_directories()
        self._setup_logging()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def run(self) -> TestRunResult:
        LOGGER.info(
            "Starting universal test runner (mode=%s)", self.config.normalized_mode()
        )
        LOGGER.debug(
            "Runner configuration: workers=%s coverage=%s mutation=%s cache=%s artifacts=%s",
            self.config.workers,
            self.config.collect_coverage,
            self.config.enable_mutation_tests,
            self.config.use_cache,
            self.artifacts_dir,
        )
        cache_key = self._compute_cache_key()
        LOGGER.debug("Computed cache key: %s", cache_key)

        pytest_result = self._run_pytest_suite()
        flaky_reruns = 0
        if pytest_result.returncode != 0 and self.config.rerun_flaky_attempts > 0:
            flaky_reruns = self._attempt_flaky_reruns()
            if flaky_reruns:
                LOGGER.info("Flaky tests recovered after %s rerun(s).", flaky_reruns)
                pytest_result = subprocess.CompletedProcess(pytest_result.args, 0)

        if pytest_result.returncode != 0:
            self._handle_failure("pytest", pytest_result.returncode)

        coverage_percent: float | None = None
        if self.config.collect_coverage:
            coverage_percent = self._collect_and_check_coverage()

        mutation_summary: MutationSummary | None = None
        if self._should_run_mutation_tests():
            mutation_summary = self._run_mutation_tests()
            self._enforce_mutation_threshold(mutation_summary)

        if self.config.use_cache:
            self._persist_artifacts(cache_key)

        LOGGER.info("All test stages completed successfully.")
        return TestRunResult(
            pytest_return_code=0,
            flaky_reruns=flaky_reruns,
            mutation_summary=mutation_summary,
            coverage_percent=coverage_percent,
            cache_key=cache_key,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _setup_logging(self) -> None:
        if self.config.debug_logs:
            logging.getLogger().setLevel(logging.DEBUG)
            LOGGER.debug("Debug logging enabled for test runner.")

    def _ensure_directories(self) -> None:
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        LOGGER.debug("Ensured artifacts directory exists at %s", self.artifacts_dir)
        if self.config.use_cache:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            LOGGER.debug("Ensured cache directory exists at %s", self.cache_dir)

    def _resolve_artifact_root(self, configured: Path) -> Path:
        if not self.config.ci_mode:
            return configured

        run_identifier = os.getenv("GITHUB_RUN_ID") or os.getenv("CI_RUN_ID")
        if not run_identifier:
            run_identifier = datetime.utcnow().strftime("%Y%m%d-%H%M%S")

        if configured == DEFAULT_ARTIFACT_DIR:
            ci_dir = configured / f"ci-{run_identifier}"
            LOGGER.debug("CI artifact directory resolved to %s", ci_dir)
            return ci_dir
        return configured

    def _xdist_available(self) -> bool:
        return importlib.util.find_spec("xdist") is not None

    def _pytest_plugin_available(self, module_name: str) -> bool:
        return importlib.util.find_spec(module_name) is not None

    def _normalize_workers(self, workers: str) -> str:
        normalized = (workers or "").strip()
        if not normalized:
            return ""

        lowered = normalized.lower()
        if lowered in {"serial", "none", "off"}:
            return ""

        try:
            count = int(normalized)
        except ValueError:
            if lowered in {"auto", "logical", "cores"}:
                if self._xdist_supported:
                    return normalized
                LOGGER.warning(
                    "pytest-xdist not available – running tests in serial mode."
                )
                return ""
            if not self._xdist_supported:
                LOGGER.warning(
                    "pytest-xdist not available – running tests in serial mode."
                )
                return ""
            return normalized

        if count <= 1:
            return ""
        if not self._xdist_supported:
            LOGGER.warning("pytest-xdist not available – running tests in serial mode.")
            return ""
        return str(count)

    def _compute_cache_key(self) -> str:
        git_rev = self._safe_git_describe()
        payload = {
            "git": git_rev,
            "mode": self.config.normalized_mode(),
            "pytest_args": self.config.pytest_args,
            "workers": self.config.workers,
            "coverage": self.config.collect_coverage,
            "mutation": self._should_run_mutation_tests(),
        }
        data = json.dumps(payload, sort_keys=True).encode()
        return hashlib.sha1(data).hexdigest()

    def _safe_git_describe(self) -> str:
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
            )
            return result.stdout.strip()
        except (subprocess.CalledProcessError, FileNotFoundError):
            return "unknown"

    def _determine_pytest_roots(self) -> list[Path]:
        roots: list[Path] = []
        mode = self.config.normalized_mode()
        preferred_roots: Iterable[Path]
        if mode == "quick":
            preferred_roots = (Path("tests/unit"),)
        else:
            preferred_roots = DEFAULT_PYTEST_ROOTS

        for root in preferred_roots:
            if root.exists():
                roots.append(root)

        if not roots:
            raise CommandError("No pytest suites were discovered in the repository.")
        return roots

    def _build_pytest_command(self) -> list[str]:
        artifacts = self._resolve_artifact_paths()
        command: list[str] = ["pytest", "-q", "-ra"]

        if self.config.workers:
            command.extend(["-n", self.config.workers])

        mode = self.config.normalized_mode()
        if mode == "quick":
            command.extend(["-m", "not slow", "--maxfail", "1"])

        if self.config.collect_coverage:
            if not self._pytest_plugin_available("pytest_cov"):
                raise CommandError(
                    "Coverage reporting requested but pytest-cov is not installed."
                )
            command.extend(["--cov-config", "pyproject.toml"])
            for package in DEFAULT_COVERAGE_SOURCES:
                command.extend(["--cov", package])
            command.extend(
                [
                    "--cov-report",
                    f"xml:{artifacts['coverage_xml']}",
                    "--cov-report",
                    "term-missing",
                ]
            )

        if artifacts.get("junit"):
            command.append(f"--junitxml={artifacts['junit']}")
        if artifacts.get("html"):
            if self._pytest_plugin_available("pytest_html"):
                command.extend(
                    [
                        f"--html={artifacts['html']}",
                        "--self-contained-html",
                    ]
                )
            else:
                LOGGER.debug(
                    "pytest-html plugin not available – skipping HTML report generation."
                )

        command.extend(self.config.pytest_args)
        command.extend(str(path) for path in self._determine_pytest_roots())
        return command

    def _run_pytest_suite(self) -> subprocess.CompletedProcess[int]:
        command = self._build_pytest_command()
        LOGGER.info("Running pytest command: %s", " ".join(command))
        return run_subprocess(command, check=False)

    def _attempt_flaky_reruns(self) -> int:
        attempts = 0
        for attempt in range(1, self.config.rerun_flaky_attempts + 1):
            LOGGER.warning(
                "Retrying flaky failures (attempt %s/%s)",
                attempt,
                self.config.rerun_flaky_attempts,
            )
            command = ["pytest", "--last-failed", "--maxfail", "1", "-q"]
            result = run_subprocess(command, check=False)
            attempts = attempt
            if result.returncode == 0:
                return attempts
        return attempts

    def _collect_and_check_coverage(self) -> float:
        artifacts = self._resolve_artifact_paths()
        coverage_xml = artifacts["coverage_xml"]
        coverage_json = artifacts["coverage_json"]
        coverage_html_dir = artifacts["coverage_html"]

        LOGGER.debug("Generating HTML coverage report at %s", coverage_html_dir)
        run_subprocess(["coverage", "html", "-d", str(coverage_html_dir)])
        LOGGER.debug("Generating JSON coverage report at %s", coverage_json)
        run_subprocess(["coverage", "json", "-o", str(coverage_json)])

        coverage = self._parse_coverage_percentage(coverage_xml)
        LOGGER.info("Line coverage: %.2f%%", coverage)
        if coverage < self.config.coverage_threshold:
            self._handle_failure(
                "coverage",
                1,
                detail=f"Coverage {coverage:.2f}% is below threshold {self.config.coverage_threshold:.2f}%",
            )
        return coverage

    def _parse_coverage_percentage(self, coverage_xml: Path) -> float:
        import xml.etree.ElementTree as ET

        if not coverage_xml.exists():
            raise CommandError(
                f"Coverage XML report not found at {coverage_xml}. Ensure pytest-cov is installed."
            )
        tree = ET.parse(coverage_xml)
        root = tree.getroot()
        line_rate = root.attrib.get("line-rate")
        if line_rate is None:
            raise CommandError(
                f"Coverage XML {coverage_xml} is missing 'line-rate' attribute."
            )
        return float(line_rate) * 100

    def _should_run_mutation_tests(self) -> bool:
        if not self.config.enable_mutation_tests:
            return False
        if self.config.normalized_mode() == "quick":
            LOGGER.debug("Skipping mutation tests in quick mode.")
            return False
        if shutil.which("mutmut") is None:
            LOGGER.warning(
                "mutmut executable not available – skipping mutation testing stage."
            )
            return False
        return True

    def _run_mutation_tests(self) -> MutationSummary:
        LOGGER.info("Running mutation tests via mutmut…")
        env = {"PYTHONHASHSEED": "0", "MUTMUT_NO_PROGRESS": "1"}
        run_subprocess(["mutmut", "run"], env=env)
        result = subprocess.run(
            ["mutmut", "results"],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        output = result.stdout or ""
        artifacts = self._resolve_artifact_paths()
        mutation_report = artifacts["mutation_report"]
        mutation_report.write_text(output, encoding="utf-8")
        summary = self._parse_mutmut_results(output)
        LOGGER.info(
            "Mutation testing summary: killed=%s survived=%s timeout=%s incompetent=%s score=%.2f%%",
            summary.killed,
            summary.survived,
            summary.timeout,
            summary.incompetent,
            summary.score,
        )
        return summary

    def _parse_mutmut_results(self, output: str) -> MutationSummary:
        summary = MutationSummary()
        for line in output.splitlines():
            line = line.strip()
            if not line:
                continue
            if line.lower().startswith("survived"):
                summary.survived = self._extract_count(line)
            elif line.lower().startswith("killed"):
                summary.killed = self._extract_count(line)
            elif line.lower().startswith("timeout"):
                summary.timeout = self._extract_count(line)
            elif line.lower().startswith("incompetent"):
                summary.incompetent = self._extract_count(line)
        return summary

    def _extract_count(self, line: str) -> int:
        import re

        match = re.search(r"(\d+)", line)
        return int(match.group(1)) if match else 0

    def _enforce_mutation_threshold(self, summary: MutationSummary) -> None:
        score = summary.score
        threshold = self.config.mutation_threshold
        if threshold <= 0:
            return
        if score < threshold:
            self._handle_failure(
                "mutation",
                1,
                detail=f"Mutation score {score:.2f}% is below threshold {threshold:.2f}%",
            )

    def _persist_artifacts(self, cache_key: str) -> None:
        artifacts = self._resolve_artifact_paths()
        metadata = {
            "cache_key": cache_key,
            "timestamp": datetime.utcnow().isoformat(),
            "mode": self.config.normalized_mode(),
        }
        metadata_path = self.artifacts_dir / "metadata.json"
        metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        LOGGER.debug("Wrote artifact metadata to %s", metadata_path)

        if not self.config.use_cache:
            return

        cache_bucket = self.cache_dir / cache_key
        cache_bucket.mkdir(parents=True, exist_ok=True)
        for name, path in artifacts.items():
            if isinstance(path, Path) and path.exists():
                destination = cache_bucket / path.name
                if path.is_dir():
                    if destination.exists():
                        shutil.rmtree(destination)
                    shutil.copytree(path, destination)
                else:
                    shutil.copy2(path, destination)
        (cache_bucket / "metadata.json").write_text(
            json.dumps(metadata, indent=2),
            encoding="utf-8",
        )
        LOGGER.info("Cached test artifacts under %s", cache_bucket)

    def _resolve_artifact_paths(self) -> dict[str, Path]:
        artifacts: dict[str, Path] = {}
        junit = self.config.junit_report or (self.artifacts_dir / "pytest-junit.xml")
        html = self.config.html_report or (self.artifacts_dir / "pytest-report.html")
        coverage_xml = self.config.coverage_xml or (self.artifacts_dir / "coverage.xml")
        coverage_json = self.config.coverage_json or (
            self.artifacts_dir / "coverage.json"
        )
        coverage_html = self.artifacts_dir / "coverage-html"
        mutation_report = self.config.mutation_report or (
            self.artifacts_dir / "mutation.txt"
        )

        artifacts.update(
            {
                "junit": junit,
                "html": html,
                "coverage_xml": coverage_xml,
                "coverage_json": coverage_json,
                "coverage_html": coverage_html,
                "mutation_report": mutation_report,
            }
        )
        return artifacts

    def _handle_failure(
        self, stage: str, return_code: int, *, detail: str | None = None
    ) -> None:
        message = f"{stage} stage failed with exit code {return_code}."
        if detail:
            message += f" {detail}"
        LOGGER.error(message)
        if self.config.auto_issue:
            self._maybe_create_issue(stage, detail)
        raise CommandError(message)

    def _maybe_create_issue(self, stage: str, detail: str | None) -> None:
        repository = self.config.issue_repository or os.getenv("TEST_RUNNER_ISSUE_REPO")
        token = os.getenv("GITHUB_TOKEN")
        if not repository or not token:
            LOGGER.debug(
                "Skipping issue creation – repository or token missing (repo=%s).",
                repository,
            )
            return

        title = f"Automated test runner detected failing {stage} stage"
        body_lines = [
            "Automated quality gate detected a failure in the continuous testing pipeline.",
            "",
            f"- Stage: `{stage}`",
            f"- Mode: `{self.config.mode}`",
            f"- Coverage enabled: `{self.config.collect_coverage}`",
            f"- Mutation enabled: `{self._should_run_mutation_tests()}`",
        ]
        if detail:
            body_lines.extend(["", detail])
        body_lines.append(
            "\nPlease investigate the build artifacts for additional context."
        )
        payload = {
            "title": title,
            "body": "\n".join(body_lines),
            "labels": list(self.config.issue_labels),
        }
        url = f"https://api.github.com/repos/{repository}/issues"
        try:
            response = requests.post(
                url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github+json",
                },
                json=payload,
                timeout=10,
            )
            if response.status_code >= 400:
                LOGGER.warning(
                    "Failed to create GitHub issue (%s): %s",
                    response.status_code,
                    response.text,
                )
            else:
                issue_url = response.json().get("html_url", "<unknown>")
                LOGGER.info("Created GitHub issue at %s", issue_url)
        except requests.RequestException as exc:
            LOGGER.warning("Unable to create GitHub issue: %s", exc)
