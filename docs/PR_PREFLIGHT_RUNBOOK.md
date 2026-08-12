# PR Preflight Runbook

This runbook defines the operating contract for the local PR preflight gate after the legacy shell gate was promoted into a structured Python evidence runner.

The gate answers one narrow question with machine-readable evidence: can this checkout execute the local PR safety checks without hiding critical failures?

The answer is expressed through process exit code, per-check logs, and `artifacts/pr_preflight/preflight_report.json`.

## Operating principles

1. Critical failures must never become success.
2. Unknown execution state must become `BLOCKED`, not `PASS`.
3. stderr must remain observable.
4. The shell wrapper must not duplicate the check logic.
5. `--skip-install` may test control flow, but it is not a full preflight pass.
6. Coverage observation must not substitute for quick test success.
7. The JSON report must be written even when the run fails, blocks, or times out.
8. The report contract must be treated as a machine contract, not decorative output.
9. Repository-system documentation must not be truncated by full-file edits.

## User-facing command

```bash
scripts/test-pr-locally.sh
```

The shell script is only a compatibility wrapper. It locates the repository root, selects `python3` or `python`, calls `tools/ci/pr_preflight.py`, prints `FIRST_FILE_TO_OPEN`, and forwards the Python runner exit code.

The wrapper is intentionally small. Do not add critical check commands back into the shell script.

## Direct runner commands

```bash
python tools/ci/pr_preflight.py --root . --report-dir artifacts/pr_preflight
python tools/ci/pr_preflight.py --root . --report-dir artifacts/pr_preflight --skip-install
python tools/ci/pr_preflight.py --root . --report-dir artifacts/pr_preflight --json
python -m tools.ci.pr_preflight --root . --report-dir artifacts/pr_preflight --skip-install
```

Use `--skip-install` only when validating runner control flow without dependency installation. Do not claim a full local preflight pass from a skip-install run.

## Evidence outputs

The runner writes deterministic evidence under:

```text
artifacts/pr_preflight/preflight_report.json
artifacts/pr_preflight/logs/<check_id>.stdout.log
artifacts/pr_preflight/logs/<check_id>.stderr.log
```

The JSON report is written even when the preflight fails or blocks. The first file to open is always the report path printed by the wrapper and stored in `first_file_to_open`.

## Report contract

The report must include: `schema_version`, `status`, `root`, `started_at`, `finished_at`, `duration_seconds`, `checks`, `summary`, `failure_count`, `next_action`, and `first_file_to_open`.

Each check entry must include enough evidence to reproduce the decision: `id`, `name`, `critical`, `status`, `command`, `exit_code`, `duration_seconds`, `stdout_log`, `stderr_log`, and `failure_reason`.

Extended check metadata should remain stable when present: `tool_available`, `cwd`, `timeout_seconds`, `success_exit_codes`, and `optional_if_missing`.

The report is the first diagnostic artifact. Individual stdout and stderr logs are the second diagnostic layer.

## Report contract guard

The runner should fail closed if its own evidence shape drifts.

A machine guard for the report contract must verify:

1. all required top-level report keys exist;
2. final `status` is one of `PASS`, `FAIL`, or `BLOCKED`;
3. every check status is one of `PASS`, `FAIL`, `SKIPPED_OPTIONAL`, `BLOCKED`, or `TIMEOUT`;
4. no critical check is `SKIPPED_OPTIONAL`;
5. `summary` counts match the actual check statuses;
6. `failure_count` equals the number of critical checks that are not `PASS`;
7. `first_file_to_open` points to the report path;
8. stdout and stderr log paths are non-empty strings.

If this guard fails, the runner itself is broken. Do not treat the emitted report as trusted evidence until the contract is repaired.

## Status model

Allowed check statuses:

```text
PASS
FAIL
SKIPPED_OPTIONAL
BLOCKED
TIMEOUT
```

Allowed final statuses:

```text
PASS
FAIL
BLOCKED
```

| Status | Meaning | Merge interpretation |
| --- | --- | --- |
| `PASS` | The check executed and returned an allowed success code. | Accept for that check only. |
| `FAIL` | The check executed and returned a disallowed code. | Stop and repair the failing invariant. |
| `SKIPPED_OPTIONAL` | The check was intentionally optional and its tool was absent. | Accept only for explicitly optional checks. |
| `BLOCKED` | The runner could not execute a required check or critical tool. | Stop and repair environment/tool availability. |
| `TIMEOUT` | The check exceeded its timeout. | Stop and inspect logs, command, and timeout policy. |

Unknown states must not become pass. Missing critical tools become `BLOCKED`. Nonzero critical checks become `FAIL`. Missing optional `detect-secrets` becomes `SKIPPED_OPTIONAL`.

## Check registry

The runner defines checks as data through `CheckSpec` and `build_check_registry`. Required checks:

```text
pip_bootstrap
project_dependencies
ruff
black
mypy
detect_secrets
quick_tests
coverage_artifact
```

| Check | Criticality | Notes |
| --- | --- | --- |
| `pip_bootstrap` | Critical | Required unless install checks are skipped. |
| `project_dependencies` | Critical when dependency files exist | Failing dependency installation is a real failure. |
| `ruff` | Critical | Lint failures must fail the run. |
| `black` | Critical | Formatting failures must fail the run. |
| `mypy` | Critical | Type failures must fail the run. |
| `detect_secrets` | Critical only when executable exists | Missing executable is `SKIPPED_OPTIONAL`; present-and-failing is `FAIL`. |
| `quick_tests` | Critical | Test failure must fail the run. |
| `coverage_artifact` | Optional observation | Must not substitute for quick test success. |

## Triage decision tree

Start with `artifacts/pr_preflight/preflight_report.json`.

1. If final `status` is `PASS`, confirm every critical check is `PASS` and no check is unexpectedly absent.
2. If final `status` is `FAIL`, inspect the first critical check with `status: FAIL`.
3. If final `status` is `BLOCKED`, inspect the first critical check with `status: BLOCKED` or `TIMEOUT`.
4. Open that check's stderr log first, then stdout log.
5. Repair the smallest invariant that explains the first critical failure.
6. Re-run the same command. Do not skip ahead to broader cleanup.

Log paths are stored inside each check result. Prefer the report over guessing file names.

## Failure class mapping

| Failure class | Usual signal | Deterministic response |
| --- | --- | --- |
| Missing critical tool | `BLOCKED`, `exit_code: null` | Install or expose the required tool on `PATH`. |
| Tool returns nonzero | `FAIL`, nonzero `exit_code` | Fix the specific lint/type/test/dependency failure. |
| Timeout | `TIMEOUT` | Inspect logs and decide whether command scope or timeout is wrong. |
| Optional tool absent | `SKIPPED_OPTIONAL` | Accept only for `detect_secrets` absence. |
| Report absent | Runner bug or interrupted process | Fix report-writing path before trusting the gate. |
| Report schema drift | report guard failure | Restore the report contract before trusting any result. |
| stderr suppressed | Governance regression | Restore stderr preservation. |

## Repository map anti-truncation guard

`docs/REPOSITORY_SYSTEM.md` is a canonical map and must retain its full structure.

A test or review guard should verify that the file still contains:

```text
## 1. Canonical Surfaces
## 2. System Layers
## 3. Claim Promotion Automaton
## 4. Evidence-Bearing Artifact Requirements
## 5. Ricci Microstructure Boundary
## 6. MFN Gateway Boundary
## 7. Release Evidence Boundary
## 8. Reviewer Protocol
## 9. Implementation-Agent Rules
## 10. Definition of Repository Completion
```

It should also verify that `docs/PR_PREFLIGHT_RUNBOOK.md` remains linked from the canonical surfaces table and reviewer protocol. This guard exists because full-file edits can silently amputate lower sections. Apparently documents also require seatbelts now.

## Local validation contract

Before opening or updating a PR that touches the runner, execute the runner behavioral tests, shell syntax check, script-mode skip-install command, and module-mode skip-install command.

If the non-skip preflight is required, run the same runner without `--skip-install`.

Do not hide stderr. Do not use exit-neutral lint flags. Do not wrap critical checks in unconditional success logic. Do not make the wrapper always exit zero.

## Behavioral test expectations

The test suite should preserve these invariants:

1. All critical stubs passing yields process exit `0`.
2. `ruff` failure yields nonzero process exit.
3. `black` failure yields nonzero process exit.
4. `mypy` failure yields nonzero process exit.
5. `pytest` failure yields nonzero process exit.
6. dependency installation failure yields nonzero process exit.
7. missing `detect-secrets` yields `SKIPPED_OPTIONAL`.
8. present-and-failing `detect-secrets` yields nonzero process exit.
9. missing critical tools yield `BLOCKED`.
10. report JSON is written on failure.
11. stdout and stderr logs are preserved.
12. wrapper forwards the Python runner exit code.
13. report contract drift is rejected by a machine guard.
14. repository-system truncation is caught before merge.

## Acceptance boundary

A runner change is acceptable only when:

1. The shell wrapper remains only a delegation layer.
2. Checks remain registry-driven.
3. Critical failures return nonzero process exit.
4. The report is emitted on pass, fail, block, and timeout paths.
5. Per-check stdout and stderr are written to deterministic files.
6. Missing optional `detect-secrets` is explicit, not silent.
7. No critical unknown state is treated as success.
8. Behavioral tests prove the exit semantics.
9. The report contract guard rejects invalid status, summary drift, and critical optional skip.
10. The repository map retains sections 1 through 10 after any documentation update.

A documentation-only change is acceptable only when it does not alter runtime code and its acceptor binds exactly the changed files.

## Rollback protocol

If a runner change corrupts local preflight behavior:

1. Revert the runner and wrapper changes together.
2. Re-run the shell syntax check.
3. Re-run the behavioral tests.
4. Confirm the report path is either restored or intentionally removed by the rollback.
5. Do not leave the wrapper pointing at a missing runner.

For this runbook alone, rollback is limited to removing the runbook and its acceptor, then verifying those paths have no remaining diff.

## Anti-regression rules

Do not introduce unconditional success fallbacks around critical checks, exit-neutral lint mode, stderr suppression around critical checks, wrapper success regardless of runner status, coverage as a quick-test replacement, missing critical executables treated as success, schema drift in `preflight_report.json`, or truncated canonical repository maps.

The runner is allowed to be small. It is not allowed to be ambiguous.
