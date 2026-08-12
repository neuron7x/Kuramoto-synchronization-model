# Post-Merge Stage 1 Triage — 2026-05-22

## Baseline run status (`baseline_run_20260522`)
- exit_code: `1`
- total_tests_recorded: `71`
- errors: `50`
- failures: `0`
- skipped: `21`
- top_failure_classes:
  - ImportError / ModuleNotFoundError during collection
  - optional dependency import failures in test modules

## Dependency failure classification
- missing `hypothesis`: detected
- missing `jax`: detected
- missing `pytest_httpx`: detected
- missing `matplotlib`: detected
- other missing test deps: present in `junit.xml` collection tracebacks

## Claim impact
- remain `goal`: `COV_98_CI_GATE`, `COV_BACKTEST_100`, `COV_EXECUTION_100`, `COV_CORE_90_95`, `PERF_1M_BARS_SEC`
- remain `partial`: `MUTATION_90_KILL`, `PERF_SUB1MS_SIGNAL`, reliability/security partial claims
- must be `quarantine`: claims that rely only on failed baseline-success interpretation
- blocked from release use: any success claim tied to non-zero baseline evidence

## Stage 1 status
- `BLOCKED`
- reason: baseline exit code is non-zero, dependency surface is incomplete for reproducible success proof.
