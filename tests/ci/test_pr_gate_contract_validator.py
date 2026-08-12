from __future__ import annotations

import json
import importlib.util
import sys
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[2] / "scripts" / "ci" / "check_pr_gate_contract.py"
spec = importlib.util.spec_from_file_location("check_pr_gate_contract", MODULE_PATH)
assert spec is not None and spec.loader is not None
validator = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = validator
spec.loader.exec_module(validator)


def workflow_text(
    *,
    severity: str = "high",
    include_rust: bool = True,
    docker: bool = False,
    invoke_contract_validator: bool = True,
    include_merge_group: bool = True,
    spoof_merge_group_outside_on: bool = False,
    duplicate_top_level_on: bool = False,
    duplicate_repo_policy: bool = False,
) -> str:
    if docker:
        repo_policy_steps = "      - run: docker run --rm rhysd/actionlint:1.7.8 -color\n"
    elif invoke_contract_validator:
        repo_policy_steps = (
            "      - run: python scripts/ci/run_actionlint.py\n"
            "      - run: python scripts/ci/check_pr_gate_contract.py\n"
        )
    else:
        repo_policy_steps = (
            "      - run: python scripts/ci/run_actionlint.py\n"
            "      - run: python scripts/ci/check_inventory_sync.py\n"
        )
    merge_group = "  merge_group:\n" if include_merge_group else ""
    spoofed_trigger = "env:\n  merge_group: spoof\n" if spoof_merge_group_outside_on else ""
    duplicate_on = "on:\n  workflow_dispatch:\n" if duplicate_top_level_on else ""
    duplicate_repo_policy_block = (
        ""
        if not duplicate_repo_policy
        else """
  repo-policy:
    name: repo-policy
    runs-on: ubuntu-latest
    continue-on-error: true
    steps:
      - run: false
"""
    )
    rust_job = "" if not include_rust else f'''
  rust-accel-gate:
    name: rust-accel-gate
    runs-on: ubuntu-latest
    continue-on-error: false
    steps:
      - uses: actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1
        with:
          python-version: '3.12'
      - run: |
          if [[ "${{GITHUB_EVENT_NAME}}" == "merge_group" ]]; then
            changed=$(git diff --name-only "${{MERGE_GROUP_BASE_SHA}}...${{MERGE_GROUP_HEAD_SHA}}")
          fi
          if printf '%s\\n' "$changed" | grep -qE '{validator.RUST_CHANGE_PATTERN}'; then
            echo applicable=true >> "$GITHUB_OUTPUT"
          fi
      - run: python -m pip install numpy==2.3.3
      - run: python scripts/ci/emit_pyo3_env.py
      - run: rustup toolchain install 1.95.0 --profile minimal --component clippy
      - uses: actions/cache@55cc8345863c7cc4c66a329aec7e433d2d1c52a9
      - run: cargo fetch --locked --manifest-path rust/geosync-accel/Cargo.toml
      - run: {validator.RUST_ACCEL_CLIPPY}
      - run: {validator.RUST_ACCEL_TEST}
      - run: {validator.RUST_ACCEL_BENCH}
'''
    simple_jobs = "".join(
        f'''
  {job}:
    name: {job}
    runs-on: ubuntu-latest
    continue-on-error: false
    steps:
      - run: true
'''
        for job in (
            "python-quality",
            "python-fast-tests",
            "frontend-gate",
            "secrets-supply-chain",
            "go-workspace-integrity",
        )
    )
    return f'''
name: PR Gate
{spoofed_trigger}on:
  pull_request:
    branches: [main]
{merge_group}permissions:
  contents: read
{duplicate_on}jobs:
  repo-policy:
    name: repo-policy
    runs-on: ubuntu-latest
    continue-on-error: false
    steps:
{repo_policy_steps}{simple_jobs}{rust_job}
  dependency-review:
    name: dependency-review
    runs-on: ubuntu-latest
    continue-on-error: false
    steps:
      - uses: actions/dependency-review-action@a1d282b36b6f3519aa1f3fc636f609c47dddb294
        if: github.event_name == 'pull_request'
        with:
          fail-on-severity: {severity}
      - run: {validator.DEPENDENCY_REVIEW_MERGE_GROUP_PASS}
        if: github.event_name == 'merge_group'
{duplicate_repo_policy_block}'''

def rust_accel_contract_text() -> str:
    return (
        Path(__file__).resolve().parents[2]
        / "rust"
        / "geosync-accel"
        / "validation_contract.json"
    ).read_text(encoding="utf-8")

def documented_jobs(
    jobs: tuple[str, ...] = validator.REQUIRED_JOB_FLOOR,
    *,
    heading: str = validator.BRANCH_REQUIRED_HEADING,
    count_word: str = "eight",
) -> str:
    lines = "\n".join(f"{idx}. `{job}`" for idx, job in enumerate(jobs, start=1))
    return f"{heading}\n\n{lines}\n\nAll {count_word} required jobs"


def violation_keys(workflow: str) -> set[str]:
    return {violation.invariant for violation in validator.validate_workflow_text(workflow)}


class PrGateContractValidatorTests(unittest.TestCase):
    def test_rust_accel_validation_contract_manifest_is_valid(self) -> None:
        self.assertEqual(
            validator.validate_rust_accel_contract_manifest(rust_accel_contract_text()),
            [],
        )

    def test_rust_accel_validation_contract_command_drift_is_fatal(self) -> None:
        contract = json.loads(rust_accel_contract_text())
        contract["categories"][0]["command"] = "cargo test"
        violations = validator.validate_rust_accel_contract_manifest(json.dumps(contract))
        self.assertIn(
            "rust-accel-contract-command",
            {violation.invariant for violation in violations},
        )


    def test_rust_accel_validation_contract_readiness_drift_is_fatal(self) -> None:
        contract = json.loads(rust_accel_contract_text())
        contract["readiness"]["critical_gaps"] = 1
        violations = validator.validate_rust_accel_contract_manifest(json.dumps(contract))
        self.assertIn(
            "rust-accel-contract-readiness",
            {violation.invariant for violation in violations},
        )

    def test_rust_accel_validation_contract_requires_acceptance_criteria(self) -> None:
        contract = json.loads(rust_accel_contract_text())
        contract["acceptance_criteria"] = []
        violations = validator.validate_rust_accel_contract_manifest(json.dumps(contract))
        self.assertIn(
            "rust-accel-contract-acceptance",
            {violation.invariant for violation in violations},
        )

    def test_parse_workflow_ast_extracts_contract_keys(self) -> None:
        ast = validator.parse_workflow_ast(workflow_text())
        self.assertIn("on", ast.top_level_keys)
        self.assertIn("jobs", ast.top_level_keys)
        self.assertIn("repo-policy", ast.job_ids)
        self.assertIn("rust-accel-gate", ast.job_ids)

    def test_valid_contract_has_no_violations(self) -> None:
        self.assertEqual(validator.validate_workflow_text(workflow_text()), [])

    def test_missing_rust_gate_is_fatal(self) -> None:
        self.assertIn("required-job", violation_keys(workflow_text(include_rust=False)))

    def test_dependency_review_must_fail_on_high(self) -> None:
        self.assertIn(
            "dependency-review-severity",
            violation_keys(workflow_text(severity="critical")),
        )

    def test_docker_validator_dependency_is_forbidden(self) -> None:
        self.assertIn("no-external-validator-gap", violation_keys(workflow_text(docker=True)))

    def test_documentation_drift_creates_action_potential(self) -> None:
        drifted_jobs = tuple(
            job for job in validator.REQUIRED_JOB_FLOOR if job != "rust-accel-gate"
        )
        report = validator.validate_contract_texts(
            workflow_text(),
            documented_jobs(validator.REQUIRED_JOB_FLOOR),
            documented_jobs(
                drifted_jobs,
                heading=validator.README_REQUIRED_HEADING,
                count_word="seven",
            ),
        )
        self.assertEqual(report.state, "ACTION")
        self.assertGreater(report.action_potential, 0)
        self.assertIn(
            "required-job-source-drift",
            {violation.invariant for violation in report.violations},
        )

    def test_valid_contract_report_rests(self) -> None:
        report = validator.validate_contract_texts(
            workflow_text(),
            documented_jobs(),
            documented_jobs(heading=validator.README_REQUIRED_HEADING),
        )
        self.assertEqual(report.state, "REST")
        self.assertEqual(report.action_potential, 0)
        self.assertEqual(report.required_jobs, validator.REQUIRED_JOB_FLOOR)

    def test_missing_merge_group_trigger_is_fatal(self) -> None:
        self.assertIn(
            "workflow-trigger",
            violation_keys(workflow_text(include_merge_group=False)),
        )


    def test_repo_policy_must_invoke_actionlint(self) -> None:
        spoofed = workflow_text().replace(
            "      - run: python scripts/ci/run_actionlint.py\n",
            "",
            1,
        )
        self.assertIn("repo-policy-actionlint", violation_keys(spoofed))

    def test_dependency_review_job_level_pull_request_if_is_fatal(self) -> None:
        spoofed = workflow_text().replace(
            "  dependency-review:\n    name: dependency-review",
            "  dependency-review:\n    name: dependency-review\n    if: github.event_name == 'pull_request'",
        )
        self.assertIn("required-job-merge-group", violation_keys(spoofed))

    def test_dependency_review_requires_merge_group_pass_step(self) -> None:
        spoofed = workflow_text().replace(
            f"      - run: {validator.DEPENDENCY_REVIEW_MERGE_GROUP_PASS}\n        if: github.event_name == 'merge_group'\n",
            "",
        )
        self.assertIn("dependency-review-merge-group", violation_keys(spoofed))

    def test_rust_gate_requires_merge_group_diff_detection(self) -> None:
        spoofed = workflow_text().replace(
            "          if [[ \"${GITHUB_EVENT_NAME}\" == \"merge_group\" ]]; then\n",
            "",
        )
        self.assertIn("rust-accel-gate-contract", violation_keys(spoofed))

    def test_rust_toolchain_file_is_required(self) -> None:
        self.assertEqual(validator.validate_rust_toolchain_file(), [])

    def test_repo_policy_must_invoke_contract_validator(self) -> None:
        self.assertIn(
            "repo-policy-contract-validator",
            violation_keys(workflow_text(invoke_contract_validator=False)),
        )

    def test_required_job_count_text_must_match_inferred_jobs(self) -> None:
        report = validator.validate_contract_texts(
            workflow_text(),
            documented_jobs(count_word="seven"),
            documented_jobs(heading=validator.README_REQUIRED_HEADING),
        )
        self.assertEqual(report.state, "ACTION")
        self.assertIn(
            "required-job-count-drift",
            {violation.invariant for violation in report.violations},
        )

    def test_trigger_spoof_outside_on_block_is_ignored(self) -> None:
        self.assertIn(
            "workflow-trigger",
            violation_keys(
                workflow_text(
                    include_merge_group=False,
                    spoof_merge_group_outside_on=True,
                )
            ),
        )

    def test_unique_workflow_key_validator_reports_all_duplicate_classes(self) -> None:
        violations = validator.validate_unique_workflow_keys(
            workflow_text(duplicate_top_level_on=True, duplicate_repo_policy=True)
        )
        self.assertEqual(
            {violation.invariant for violation in violations},
            {"workflow-duplicate-top-level-key", "workflow-duplicate-job"},
        )

    def test_duplicate_top_level_workflow_key_is_fatal(self) -> None:
        self.assertIn(
            "workflow-duplicate-top-level-key",
            violation_keys(workflow_text(duplicate_top_level_on=True)),
        )

    def test_duplicate_workflow_job_id_is_fatal(self) -> None:
        self.assertIn(
            "workflow-duplicate-job",
            violation_keys(workflow_text(duplicate_repo_policy=True)),
        )

    def test_required_job_fail_closed_cannot_be_spoofed_in_run_body(self) -> None:
        original = (
            "    continue-on-error: false\n"
            "    steps:\n"
            "      - run: python scripts/ci/run_actionlint.py\n"
            "      - run: python scripts/ci/check_pr_gate_contract.py"
        )
        spoofed = workflow_text().replace(
            original,
            "    continue-on-error: true\n    steps:\n      - run: |\n"
            "          continue-on-error: false\n"
            "          python scripts/ci/check_pr_gate_contract.py",
            1,
        )
        self.assertIn("fail-closed", violation_keys(spoofed))

    def test_dependency_severity_cannot_be_spoofed_in_run_body(self) -> None:
        spoofed = workflow_text(severity="critical").replace(
            "      - uses: actions/dependency-review-action",
            "      - run: |\n"
            "          fail-on-severity: high\n"
            "      - uses: actions/dependency-review-action",
        )
        self.assertIn("dependency-review-severity", violation_keys(spoofed))

    def test_rust_gate_must_run_benchmark_smoke(self) -> None:
        spoofed = workflow_text().replace(
            f"      - run: {validator.RUST_ACCEL_BENCH}\n",
            "",
        )
        self.assertIn("rust-accel-gate-contract", violation_keys(spoofed))

    def test_comment_spoofed_rust_command_is_ignored(self) -> None:
        spoofed = workflow_text().replace(
            f"      - run: {validator.RUST_ACCEL_CLIPPY}",
            f"      # - run: {validator.RUST_ACCEL_CLIPPY}",
        )
        self.assertIn("rust-accel-gate-contract", violation_keys(spoofed))

    def test_echo_spoofed_rust_command_is_ignored(self) -> None:
        spoofed = workflow_text().replace(
            f"      - run: {validator.RUST_ACCEL_TEST}",
            f"      - run: echo {validator.RUST_ACCEL_TEST}",
        )
        self.assertIn("rust-accel-gate-contract", violation_keys(spoofed))

    def test_echo_spoofed_repo_policy_validator_is_ignored(self) -> None:
        spoofed = workflow_text(invoke_contract_validator=False).replace(
            "python scripts/ci/check_inventory_sync.py",
            "echo python scripts/ci/check_pr_gate_contract.py",
        )
        self.assertIn("repo-policy-contract-validator", violation_keys(spoofed))

    def test_duplicate_documented_required_job_is_fatal(self) -> None:
        duplicate_jobs = validator.REQUIRED_JOB_FLOOR + ("repo-policy",)
        report = validator.validate_contract_texts(
            workflow_text(),
            documented_jobs(duplicate_jobs),
            documented_jobs(heading=validator.README_REQUIRED_HEADING),
        )
        self.assertEqual(report.state, "ACTION")
        self.assertIn(
            "required-job-duplicates",
            {violation.invariant for violation in report.violations},
        )

    def test_required_count_in_wrong_section_is_ignored(self) -> None:
        branch_doc = (
            "## Wrong Section\n\nAll eight required jobs\n\n"
            + documented_jobs(count_word="seven")
        )
        report = validator.validate_contract_texts(
            workflow_text(),
            branch_doc,
            documented_jobs(heading=validator.README_REQUIRED_HEADING),
        )
        self.assertEqual(report.state, "ACTION")
        self.assertIn(
            "required-job-count-drift",
            {violation.invariant for violation in report.violations},
        )


if __name__ == "__main__":
    unittest.main()
