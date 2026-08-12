#!/usr/bin/env python3
"""Deterministic, fail-closed structural checks for the PR gate workflow.

Problem, in one sentence: the required merge-gate contract must be validated
without depending on Docker, Go module downloads, or best-effort comments.

The validator treats a green workflow as a resting potential (REST): every
invariant is below firing threshold. Any contract drift creates an action
potential (ACTION): concrete violations are emitted and CI fails. Required job
names are inferred from the branch-protection documents, then checked against the
workflow and the repository-specific gate invariants.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PR_GATE = ROOT / ".github" / "workflows" / "pr-gate.yml"
DEFAULT_BRANCH_PROTECTION = ROOT / ".github" / "BRANCH_PROTECTION_MAIN.md"
DEFAULT_WORKFLOWS_README = ROOT / ".github" / "workflows" / "README.md"
DEFAULT_RUST_ACCEL_CONTRACT = ROOT / "rust" / "geosync-accel" / "validation_contract.json"
DEFAULT_RUST_TOOLCHAIN = ROOT / "rust-toolchain.toml"

REQUIRED_JOB_FLOOR: tuple[str, ...] = (
    "repo-policy",
    "python-quality",
    "python-fast-tests",
    "frontend-gate",
    "rust-accel-gate",
    "dependency-review",
    "secrets-supply-chain",
    "go-workspace-integrity",
)

PINNED_SETUP_PYTHON = "actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1"
RUST_ACCEL_CLIPPY = (
    "cargo clippy --locked --manifest-path rust/geosync-accel/Cargo.toml "
    "--all-targets --all-features -- -D warnings"
)
RUST_ACCEL_TEST = "cargo test --locked --manifest-path rust/geosync-accel/Cargo.toml --all-features"
RUST_ACCEL_BENCH = (
    "cargo bench --locked --manifest-path rust/geosync-accel/Cargo.toml "
    "--bench numeric -- --sample-size 10 --warm-up-time 1 --measurement-time 2"
)
RUST_CHANGE_PATTERN = r"^(rust/geosync-accel/|Cargo\.(toml|lock)$|.*\.rs$)"
REQUIRED_JOB_LINE = re.compile(r"^\s*\d+\.\s+`(?P<job>[A-Za-z0-9_-]+)`\s*$")
SECTION_HEADING = re.compile(r"^##\s+")
PR_GATE_CONTRACT_COMMAND = "python scripts/ci/check_pr_gate_contract.py"
ACTIONLINT_COMMAND = "python scripts/ci/run_actionlint.py"
DEPENDENCY_REVIEW_MERGE_GROUP_PASS = (
    'echo "dependency-review is pull_request-only; merge_group emits deterministic pass."'
)
RUST_TOOLCHAIN_VERSION = "1.95.0"
REQUIRED_WORKFLOW_TRIGGERS = ("pull_request:", "merge_group:")
BRANCH_REQUIRED_HEADING = "## Required status checks (strict, fail-closed)"
README_REQUIRED_HEADING = "## Required status checks for `main`"
RUST_ACCEL_CONTRACT_SCHEMA_VERSION = "1.0"
RUST_ACCEL_CONTRACT_ARTIFACT_ID = "rust-geosync-accel-ci-contract"
RUST_ACCEL_CONTRACT_REQUIRED_CATEGORIES = (
    "property_convolution",
    "fuzz_numeric_primitives",
    "workflow_ast",
    "criterion_benchmark_smoke",
)
RUST_ACCEL_FUZZ_COMMAND = RUST_ACCEL_TEST
RUST_ACCEL_CONTRACT_RUNNER = "python scripts/ci/run_rust_accel_contract.py --format json"
RUST_ACCEL_CONTRACT_DRY_RUN = "python scripts/ci/run_rust_accel_contract.py --dry-run --format json"
RUST_ACCEL_CONTRACT_REQUIRED_TOP_LEVEL = (
    "schema_version",
    "artifact_id",
    "owner",
    "autonomy_level",
    "value_function",
    "readiness",
    "status_semantics",
    "acceptance_criteria",
    "automation",
    "required_categories",
    "categories",
)


@dataclass(frozen=True)
class Violation:
    invariant: str
    detail: str

    def format(self) -> str:
        return f"[{self.invariant}] {self.detail}"

    def as_dict(self) -> dict[str, str]:
        return {"invariant": self.invariant, "detail": self.detail}


@dataclass(frozen=True)
class WorkflowAst:
    top_level_keys: tuple[str, ...]
    job_ids: tuple[str, ...]


@dataclass(frozen=True)
class GateReport:
    required_jobs: tuple[str, ...]
    violations: tuple[Violation, ...]

    @property
    def state(self) -> str:
        return "REST" if not self.violations else "ACTION"

    @property
    def action_potential(self) -> int:
        return len(self.violations)

    def as_dict(self) -> dict[str, object]:
        return {
            "state": self.state,
            "action_potential": self.action_potential,
            "required_jobs": list(self.required_jobs),
            "violations": [violation.as_dict() for violation in self.violations],
        }


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(f"unable to read {path}: {exc}") from exc


def strip_full_line_comments(text: str) -> str:
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))


def top_level_keys(document: str) -> tuple[str, ...]:
    return tuple(
        match.group("key")
        for line in strip_full_line_comments(document).splitlines()
        if (match := re.match(r"^(?P<key>[A-Za-z0-9_-]+):(?:\s|$)", line))
    )


def top_level_block(document: str, key: str) -> str:
    lines = document.splitlines()
    start: int | None = None
    key_pattern = re.compile(rf"^{re.escape(key)}:\s*(?:#.*)?$")
    for index, line in enumerate(lines):
        if key_pattern.match(line):
            start = index + 1
            break
    if start is None:
        return ""

    body: list[str] = []
    for line in lines[start:]:
        if line and not line.startswith((" ", "-")):
            break
        body.append(line)
    return "\n".join(body)


def jobs_block(workflow: str) -> str:
    return top_level_block(workflow, "jobs")


def workflow_job_ids(workflow: str) -> tuple[str, ...]:
    return tuple(
        match.group("job")
        for line in jobs_block(workflow).splitlines()
        if (match := re.match(r"^  (?P<job>[A-Za-z0-9_-]+):\s*$", line))
    )


def parse_workflow_ast(workflow: str) -> WorkflowAst:
    """Parse the repository workflow subset into a structural AST.

    The validator intentionally owns this minimal AST instead of treating regex
    matches as facts; downstream checks consume top-level keys and job ids from
    this parsed representation before validating repository-specific contracts.
    """

    return WorkflowAst(
        top_level_keys=top_level_keys(workflow),
        job_ids=workflow_job_ids(workflow),
    )


def job_block(workflow: str, job_id: str) -> str | None:
    block = jobs_block(workflow)
    pattern = re.compile(rf"(?ms)^  {re.escape(job_id)}:\n.*?(?=^  [A-Za-z0-9_-]+:|\Z)")
    match = pattern.search(block)
    return match.group(0) if match else None


def yaml_semantic_lines(block: str) -> tuple[str, ...]:
    lines: list[str] = []
    block_scalar_indent: int | None = None
    for raw_line in strip_full_line_comments(block).splitlines():
        if not raw_line.strip():
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        if block_scalar_indent is not None:
            if indent > block_scalar_indent:
                continue
            block_scalar_indent = None
        stripped = raw_line.strip()
        lines.append(stripped)
        if re.search(r":\s*[|>][-+]?\s*(?:#.*)?$", stripped):
            block_scalar_indent = indent
    return tuple(lines)


def has_line(block: str, text: str) -> bool:
    return any(line == text for line in yaml_semantic_lines(block))


def semantic_lines(block: str) -> tuple[str, ...]:
    return tuple(
        line.strip() for line in strip_full_line_comments(block).splitlines() if line.strip()
    )


def has_uses_reference(block: str, reference: str) -> bool:
    for line in yaml_semantic_lines(block):
        if line.startswith("uses: ") or line.startswith("- uses: "):
            value = line.split("uses: ", 1)[1].split(" #", 1)[0].strip()
            if value == reference:
                return True
    return False


def has_run_command(block: str, command: str) -> bool:
    return any(
        line in {command, f"run: {command}", f"- run: {command}"} for line in semantic_lines(block)
    )


def duplicate_items(items: Sequence[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    duplicates: list[str] = []
    for item in items:
        if item in seen and item not in duplicates:
            duplicates.append(item)
        seen.add(item)
    return tuple(duplicates)


def section_body(document: str, heading: str) -> str:
    lines = document.splitlines()
    start: int | None = None
    for index, line in enumerate(lines):
        if line.strip() == heading:
            start = index + 1
            break
    if start is None:
        return ""

    body: list[str] = []
    for line in lines[start:]:
        if SECTION_HEADING.match(line):
            break
        body.append(line)
    return "\n".join(body)


def extract_required_jobs(document: str, heading: str) -> tuple[str, ...]:
    body = section_body(document, heading)
    return tuple(
        match.group("job") for line in body.splitlines() if (match := REQUIRED_JOB_LINE.match(line))
    )


def count_phrase_present(document: str, expected_count: int) -> bool:
    count_words = {
        1: "one",
        2: "two",
        3: "three",
        4: "four",
        5: "five",
        6: "six",
        7: "seven",
        8: "eight",
        9: "nine",
        10: "ten",
    }
    word = count_words.get(expected_count, str(expected_count))
    return bool(re.search(rf"\bAll {re.escape(word)}\b", document, flags=re.IGNORECASE))


def validate_unique_workflow_keys(workflow: str) -> list[Violation]:
    """Fail closed on ambiguous workflow YAML keys before contract checks run.

    GitHub/YAML parsers can collapse duplicate mapping keys, while a structural
    text scan may otherwise observe the first block and miss the executable one.
    Treat duplicate top-level keys and duplicate job ids as fatal contract drift.
    """

    ast = parse_workflow_ast(workflow)
    violations: list[Violation] = []
    duplicate_top_level = duplicate_items(ast.top_level_keys)
    if duplicate_top_level:
        violations.append(
            Violation(
                "workflow-duplicate-top-level-key",
                f"workflow has duplicate top-level keys {duplicate_top_level!r}",
            )
        )
    duplicate_jobs = duplicate_items(ast.job_ids)
    if duplicate_jobs:
        violations.append(
            Violation(
                "workflow-duplicate-job",
                f"workflow has duplicate job ids {duplicate_jobs!r}",
            )
        )
    return violations


def validate_required_job_sources(
    branch_jobs: tuple[str, ...],
    readme_jobs: tuple[str, ...],
) -> list[Violation]:
    violations: list[Violation] = []
    for source, jobs in (
        ("branch-protection", branch_jobs),
        ("workflow README", readme_jobs),
    ):
        duplicates = duplicate_items(jobs)
        if duplicates:
            violations.append(
                Violation(
                    "required-job-duplicates",
                    f"{source} has duplicate required jobs {duplicates!r}",
                )
            )
    if not branch_jobs:
        violations.append(
            Violation("required-job-source", "branch-protection manifest has no required job list")
        )
    if not readme_jobs:
        violations.append(
            Violation("required-job-source", "workflow README has no required job list")
        )
    if branch_jobs and readme_jobs and branch_jobs != readme_jobs:
        violations.append(
            Violation(
                "required-job-source-drift",
                f"branch-protection jobs {branch_jobs!r} != workflow README jobs {readme_jobs!r}",
            )
        )
    inferred_jobs = branch_jobs or readme_jobs
    if inferred_jobs and inferred_jobs != REQUIRED_JOB_FLOOR:
        violations.append(
            Violation(
                "required-job-floor-drift",
                f"documented jobs {inferred_jobs!r} != expected floor {REQUIRED_JOB_FLOOR!r}",
            )
        )
    return violations


def validate_required_job_counts(
    branch_protection: str,
    workflows_readme: str,
    required_jobs: tuple[str, ...],
) -> list[Violation]:
    violations: list[Violation] = []
    expected_count = len(required_jobs)
    branch_section = section_body(branch_protection, BRANCH_REQUIRED_HEADING)
    readme_section = section_body(workflows_readme, README_REQUIRED_HEADING)
    if required_jobs and not count_phrase_present(branch_section, expected_count):
        violations.append(
            Violation(
                "required-job-count-drift",
                f"branch-protection text must say All {expected_count} required jobs",
            )
        )
    if required_jobs and not count_phrase_present(readme_section, expected_count):
        violations.append(
            Violation(
                "required-job-count-drift",
                f"workflow README text must say All {expected_count} required jobs",
            )
        )
    return violations


def infer_required_jobs(
    branch_protection: str,
    workflows_readme: str,
) -> tuple[tuple[str, ...], list[Violation]]:
    branch_jobs = extract_required_jobs(
        branch_protection,
        BRANCH_REQUIRED_HEADING,
    )
    readme_jobs = extract_required_jobs(workflows_readme, README_REQUIRED_HEADING)
    violations = validate_required_job_sources(branch_jobs, readme_jobs)
    inferred_jobs = branch_jobs or readme_jobs or REQUIRED_JOB_FLOOR
    violations.extend(
        validate_required_job_counts(branch_protection, workflows_readme, inferred_jobs)
    )
    return inferred_jobs, violations


def validate_required_jobs(workflow: str, required_jobs: Sequence[str]) -> list[Violation]:
    violations: list[Violation] = []
    jobs = {job for job in required_jobs if job_block(workflow, job) is not None}
    for job in required_jobs:
        if job not in jobs:
            violations.append(Violation("required-job", f"missing job {job!r}"))
            continue
        block = job_block(workflow, job)
        assert block is not None
        if not has_line(block, f"name: {job}"):
            violations.append(Violation("required-job-name", f"job {job!r} must emit name {job!r}"))
        if not has_line(block, "continue-on-error: false"):
            violations.append(
                Violation("fail-closed", f"job {job!r} must set continue-on-error: false")
            )
        header = block.split("\n    steps:", 1)[0]
        if "if: github.event_name == 'pull_request'" in yaml_semantic_lines(header):
            violations.append(
                Violation(
                    "required-job-merge-group",
                    f"required job {job!r} must emit or deterministically pass in merge_group",
                )
            )
    return violations


def validate_dependency_review(workflow: str) -> list[Violation]:
    block = job_block(workflow, "dependency-review")
    if block is None:
        return []
    violations: list[Violation] = []
    if not has_line(block, "fail-on-severity: high"):
        violations.append(
            Violation(
                "dependency-review-severity",
                "dependency-review must fail on high severity",
            )
        )
    if not has_line(block, "if: github.event_name == 'pull_request'"):
        violations.append(
            Violation(
                "dependency-review-merge-group",
                "dependency-review action step must remain pull_request-only",
            )
        )
    if not has_line(block, "if: github.event_name == 'merge_group'") or not has_run_command(
        block, DEPENDENCY_REVIEW_MERGE_GROUP_PASS
    ):
        violations.append(
            Violation(
                "dependency-review-merge-group",
                "dependency-review must emit a deterministic merge_group pass step",
            )
        )
    return violations


def validate_rust_accel_gate(workflow: str) -> list[Violation]:
    block = job_block(workflow, "rust-accel-gate")
    if block is None:
        return []
    violations: list[Violation] = []
    checks = (
        (has_uses_reference(block, PINNED_SETUP_PYTHON), PINNED_SETUP_PYTHON),
        (has_line(block, "python-version: '3.12'"), "python-version: '3.12'"),
        (
            has_run_command(block, "python -m pip install numpy==2.3.3"),
            "python -m pip install numpy==2.3.3",
        ),
        (
            has_run_command(block, "python scripts/ci/emit_pyo3_env.py"),
            "python scripts/ci/emit_pyo3_env.py",
        ),
        (has_run_command(block, RUST_ACCEL_CLIPPY), RUST_ACCEL_CLIPPY),
        (has_run_command(block, RUST_ACCEL_TEST), RUST_ACCEL_TEST),
        (has_run_command(block, RUST_ACCEL_BENCH), RUST_ACCEL_BENCH),
        (
            has_run_command(
                block, "rustup toolchain install 1.95.0 --profile minimal --component clippy"
            ),
            "rustup toolchain install 1.95.0 --profile minimal --component clippy",
        ),
        (
            has_uses_reference(block, "actions/cache@55cc8345863c7cc4c66a329aec7e433d2d1c52a9"),
            "actions/cache@55cc8345863c7cc4c66a329aec7e433d2d1c52a9",
        ),
        (
            has_run_command(
                block, "cargo fetch --locked --manifest-path rust/geosync-accel/Cargo.toml"
            ),
            "cargo fetch --locked --manifest-path rust/geosync-accel/Cargo.toml",
        ),
        (
            '[[ "${GITHUB_EVENT_NAME}" == "merge_group" ]]' in strip_full_line_comments(block),
            "merge_group diff range",
        ),
        ("MERGE_GROUP_BASE_SHA" in strip_full_line_comments(block), "MERGE_GROUP_BASE_SHA"),
        ("MERGE_GROUP_HEAD_SHA" in strip_full_line_comments(block), "MERGE_GROUP_HEAD_SHA"),
        (RUST_CHANGE_PATTERN in strip_full_line_comments(block), RUST_CHANGE_PATTERN),
    )
    violations.extend(
        Violation("rust-accel-gate-contract", f"rust-accel-gate missing {needle!r}")
        for passed, needle in checks
        if not passed
    )
    return violations


def validate_workflow_triggers(workflow: str) -> list[Violation]:
    violations: list[Violation] = []
    on_block = top_level_block(workflow, "on")
    for trigger in REQUIRED_WORKFLOW_TRIGGERS:
        if not re.search(rf"^  {re.escape(trigger)}", on_block, flags=re.MULTILINE):
            violations.append(
                Violation(
                    "workflow-trigger",
                    f"pr-gate workflow must declare {trigger.rstrip(':')!r} trigger",
                )
            )
    return violations


def validate_repo_policy_invokes_contract(workflow: str) -> list[Violation]:
    block = job_block(workflow, "repo-policy")
    if block is None:
        return []
    violations: list[Violation] = []
    if not has_run_command(block, ACTIONLINT_COMMAND):
        violations.append(
            Violation(
                "repo-policy-actionlint",
                f"repo-policy must invoke {ACTIONLINT_COMMAND!r}",
            )
        )
    if not has_run_command(block, PR_GATE_CONTRACT_COMMAND):
        violations.append(
            Violation(
                "repo-policy-contract-validator",
                f"repo-policy must invoke {PR_GATE_CONTRACT_COMMAND!r}",
            )
        )
    return violations


def validate_rust_toolchain_file() -> list[Violation]:
    try:
        toolchain = DEFAULT_RUST_TOOLCHAIN.read_text(encoding="utf-8")
    except OSError as exc:
        return [Violation("rust-toolchain", f"unable to read rust-toolchain.toml: {exc}")]
    required = (
        f'channel = "{RUST_TOOLCHAIN_VERSION}"',
        'profile = "minimal"',
        'components = ["clippy"]',
    )
    return [
        Violation("rust-toolchain", f"rust-toolchain.toml missing {needle!r}")
        for needle in required
        if needle not in toolchain
    ]


def validate_no_tooling_gaps(workflow: str) -> list[Violation]:
    violations: list[Violation] = []
    forbidden_fragments = (
        "docker run --rm",
        "go install github.com/rhysd/actionlint",
        "proxy.golang.org",
    )
    for fragment in forbidden_fragments:
        if fragment in workflow:
            violations.append(
                Violation(
                    "no-external-validator-gap",
                    f"workflow validation must not depend on {fragment!r}",
                )
            )
    return violations


def validate_rust_accel_contract_manifest(contract_text: str) -> list[Violation]:
    violations: list[Violation] = []
    try:
        contract = json.loads(contract_text)
    except json.JSONDecodeError as exc:
        return [
            Violation(
                "rust-accel-contract-manifest",
                f"validation contract is not valid JSON: {exc}",
            )
        ]

    if contract.get("schema_version") != RUST_ACCEL_CONTRACT_SCHEMA_VERSION:
        violations.append(
            Violation(
                "rust-accel-contract-manifest",
                "validation contract schema_version must be "
                f"{RUST_ACCEL_CONTRACT_SCHEMA_VERSION!r}",
            )
        )
    if contract.get("artifact_id") != RUST_ACCEL_CONTRACT_ARTIFACT_ID:
        violations.append(
            Violation(
                "rust-accel-contract-manifest",
                f"validation contract artifact_id must be {RUST_ACCEL_CONTRACT_ARTIFACT_ID!r}",
            )
        )

    for field in RUST_ACCEL_CONTRACT_REQUIRED_TOP_LEVEL:
        if not contract.get(field):
            violations.append(
                Violation(
                    "rust-accel-contract-manifest",
                    f"validation contract missing top-level field {field!r}",
                )
            )

    readiness = contract.get("readiness", {})
    if not isinstance(readiness, dict):
        violations.append(Violation("rust-accel-contract-readiness", "readiness must be an object"))
    else:
        if readiness.get("status") != "contract_specified":
            violations.append(
                Violation(
                    "rust-accel-contract-readiness",
                    "readiness.status must be 'contract_specified'; PASS readiness is emitted by the runner",
                )
            )
        if readiness.get("critical_gaps") != 0:
            violations.append(
                Violation(
                    "rust-accel-contract-readiness",
                    "readiness.critical_gaps must be 0",
                )
            )

    acceptance_criteria = contract.get("acceptance_criteria", [])
    if not isinstance(acceptance_criteria, list) or not acceptance_criteria:
        violations.append(
            Violation(
                "rust-accel-contract-acceptance",
                "acceptance_criteria must be a non-empty list",
            )
        )
    else:
        for criterion in acceptance_criteria:
            if not isinstance(criterion, dict):
                violations.append(
                    Violation(
                        "rust-accel-contract-acceptance",
                        "acceptance criteria entries must be objects",
                    )
                )
                continue
            for field in ("id", "command", "pass_condition"):
                if not criterion.get(field):
                    violations.append(
                        Violation(
                            "rust-accel-contract-acceptance",
                            f"acceptance criterion missing field {field!r}",
                        )
                    )

    automation = contract.get("automation", {})
    if not isinstance(automation, dict):
        violations.append(
            Violation("rust-accel-contract-automation", "automation must be an object")
        )
    else:
        expected_automation = {
            "runner": RUST_ACCEL_CONTRACT_RUNNER,
            "dry_run": RUST_ACCEL_CONTRACT_DRY_RUN,
        }
        for field, expected in expected_automation.items():
            if automation.get(field) != expected:
                violations.append(
                    Violation(
                        "rust-accel-contract-automation",
                        f"automation.{field} must be {expected!r}",
                    )
                )
        for field in ("evidence", "failure_policy"):
            if not automation.get(field):
                violations.append(
                    Violation(
                        "rust-accel-contract-automation",
                        f"automation missing field {field!r}",
                    )
                )
        if not (ROOT / "scripts/ci/run_rust_accel_contract.py").exists():
            violations.append(
                Violation(
                    "rust-accel-contract-automation",
                    "automation runner script is missing",
                )
            )

    declared_required = tuple(contract.get("required_categories", ()))
    if declared_required != RUST_ACCEL_CONTRACT_REQUIRED_CATEGORIES:
        violations.append(
            Violation(
                "rust-accel-contract-categories",
                "validation contract required_categories drifted from repository floor",
            )
        )

    categories_raw = contract.get("categories", [])
    if not isinstance(categories_raw, list):
        return violations + [
            Violation("rust-accel-contract-categories", "categories must be a list")
        ]
    categories = {item.get("id"): item for item in categories_raw if isinstance(item, dict)}
    for category_id in RUST_ACCEL_CONTRACT_REQUIRED_CATEGORIES:
        item = categories.get(category_id)
        if item is None:
            violations.append(
                Violation(
                    "rust-accel-contract-categories",
                    f"missing validation category {category_id!r}",
                )
            )
            continue
        for field in (
            "category",
            "risk_level",
            "purpose",
            "command",
            "evidence_paths",
            "invariants",
            "failure_action",
        ):
            if not item.get(field):
                violations.append(
                    Violation(
                        "rust-accel-contract-category-shape",
                        f"category {category_id!r} missing field {field!r}",
                    )
                )
        evidence_paths = item.get("evidence_paths", [])
        if not isinstance(evidence_paths, list):
            violations.append(
                Violation(
                    "rust-accel-contract-category-shape",
                    f"category {category_id!r} evidence_paths must be a list",
                )
            )
            continue
        for evidence_path in evidence_paths:
            if not isinstance(evidence_path, str) or not (ROOT / evidence_path).exists():
                violations.append(
                    Violation(
                        "rust-accel-contract-evidence",
                        f"category {category_id!r} evidence path missing: {evidence_path!r}",
                    )
                )

    expected_commands = {
        "property_convolution": RUST_ACCEL_TEST,
        "fuzz_numeric_primitives": RUST_ACCEL_FUZZ_COMMAND,
        "workflow_ast": PR_GATE_CONTRACT_COMMAND,
        "criterion_benchmark_smoke": RUST_ACCEL_BENCH,
    }
    for category_id, command in expected_commands.items():
        if categories.get(category_id, {}).get("command") != command:
            violations.append(
                Violation(
                    "rust-accel-contract-command",
                    f"category {category_id!r} command must be {command!r}",
                )
            )
    return violations


def validate_contract_texts(
    workflow: str,
    branch_protection: str,
    workflows_readme: str,
    rust_accel_contract: str | None = None,
) -> GateReport:
    workflow = strip_full_line_comments(workflow)
    required_jobs, violations = infer_required_jobs(branch_protection, workflows_readme)
    validators = (
        validate_unique_workflow_keys(workflow),
        validate_workflow_triggers(workflow),
        validate_no_tooling_gaps(workflow),
        validate_rust_toolchain_file(),
        validate_repo_policy_invokes_contract(workflow),
        validate_required_jobs(workflow, required_jobs),
        validate_dependency_review(workflow),
        validate_rust_accel_gate(workflow),
    )
    for validator_violations in validators:
        violations.extend(validator_violations)
    if rust_accel_contract is not None:
        violations.extend(validate_rust_accel_contract_manifest(rust_accel_contract))
    return GateReport(required_jobs=required_jobs, violations=tuple(violations))


def documented_required_jobs(heading: str, jobs: Sequence[str] = REQUIRED_JOB_FLOOR) -> str:
    lines = "\n".join(f"{idx}. `{job}`" for idx, job in enumerate(jobs, start=1))
    return f"{heading}\n\n{lines}\n\nAll eight required jobs"


def validate_workflow_text(workflow: str) -> list[Violation]:
    report = validate_contract_texts(
        workflow,
        documented_required_jobs(BRANCH_REQUIRED_HEADING),
        documented_required_jobs(README_REQUIRED_HEADING),
    )
    return list(report.violations)


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--workflow",
        type=Path,
        default=DEFAULT_PR_GATE,
        help="Workflow file to validate (default: .github/workflows/pr-gate.yml)",
    )
    parser.add_argument(
        "--branch-protection",
        type=Path,
        default=DEFAULT_BRANCH_PROTECTION,
        help="Branch-protection manifest to validate",
    )
    parser.add_argument(
        "--workflows-readme",
        type=Path,
        default=DEFAULT_WORKFLOWS_README,
        help="Workflow README contract to validate",
    )
    parser.add_argument(
        "--rust-accel-contract",
        type=Path,
        default=DEFAULT_RUST_ACCEL_CONTRACT,
        help="Rust accelerator validation contract manifest to validate",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format for the validation report",
    )
    return parser.parse_args(argv)


def emit_report(report: GateReport, output_format: str) -> None:
    if output_format == "json":
        print(json.dumps(report.as_dict(), indent=2, sort_keys=True))
        return
    if report.violations:
        for violation in report.violations:
            print(f"ERROR: {violation.format()}", file=sys.stderr)
    else:
        print("PR gate contract validation passed. state=REST action_potential=0")


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        workflow = read_text(args.workflow)
        branch_protection = read_text(args.branch_protection)
        workflows_readme = read_text(args.workflows_readme)
        rust_accel_contract = read_text(args.rust_accel_contract)
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    report = validate_contract_texts(
        workflow,
        branch_protection,
        workflows_readme,
        rust_accel_contract,
    )
    emit_report(report, args.format)
    return 0 if report.state == "REST" else 1


if __name__ == "__main__":
    raise SystemExit(main())
