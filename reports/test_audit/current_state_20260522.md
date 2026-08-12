# GeoSync Stage-1 Current State Audit (2026-05-22)

- git_sha: `818274830761ae451bb017d7218c980ff4322641`
- branch: `work`
- generated_at_utc: `2026-05-22T14:54:01.884313Z`
- test_directories_count: 191
- top_level_test_suites: adapters, admin, adversarial, agent, agents, analysis, analytics, api, apps, archive, askar, audit, backtest, benchmarks, canary, chaos, connectors, contracts, core, data, demos, deps, disha_artifact_v2, e2e, edge_cases, evolution, execution, experiments, fixtures, formal, fuzz, generated, geosync_hpc, geosync_hydro, governance, helm, infra, instrument_validation, integration, interfaces

## pytest markers
fast, slow, optional, arm, heavy_math, flaky, nightly, integration, smoke, canary, live_balance, L0, L1, L2, L3, L4, L5, L6, L7, UNSTABLE, monotonic

## CI workflows related to tests
- claims-evidence-gate.yml
- commit-acceptor-gate.yml
- l2-demo-gate.yml
- main-validation.yml
- physics-2026-gate.yml
- physics-kernel-gate.yml
- pr-gate.yml
- reality-validators-gate.yml
- research-integrity-gate.yml
- schemathesis-contract.yml
- security-deep.yml

## Coverage claims (from METRICS_CONTRACT)
- COV_98_CI_GATE: status=goal
- COV_BACKTEST_74: status=proven
- COV_EXECUTION_44: status=proven
- COV_CORE_32: status=proven
- COV_BACKTEST_100: status=goal
- COV_EXECUTION_100: status=goal
- COV_CORE_90_95: status=goal
- COV_AGENT_95: status=goal
- COV_DATA_95: status=goal
- COV_INDICATORS_90: status=goal
- COV_METRICS_95: status=goal
- COV_PHASE_95: status=goal
- COV_GOLDEN_PATH: status=proven
- COV_PAPER_TRADING: status=proven
- MUTATION_90_KILL: status=partial

## Mutation claims
- MUTATION_90_KILL: status=partial

## Performance claims
- PERF_1M_BARS_SEC: status=goal
- PERF_SUB5MS_ORDER: status=goal
- PERF_SUB1MS_SIGNAL: status=partial
- PERF_200MB_MEMORY: status=goal
- PERF_GPU_ACCEL: status=goal
- PERF_FLOAT32_50PCT: status=partial
- PERF_FRONTEND_LCP: status=goal
- PERF_FRONTEND_TTFB: status=goal
- PERF_LATENCY_P95_85MS: status=partial
- PERF_LATENCY_P99_120MS: status=partial

## Security/compliance claims
- SEC_NO_EXTERNAL_AUDIT: status=proven
- SEC_NIST_800_53: status=partial
- SEC_ISO_27001: status=partial
- SEC_SEC_FINRA: status=partial
- SEC_GDPR_CCPA: status=partial
- SEC_SOC2: status=partial
- SEC_EU_AI_ACT: status=partial
- SEC_PIP_AUDIT: status=partial
- SEC_BANDIT_SCAN: status=proven
- SEC_SECRETS_SCAN: status=proven
- SEC_CONTAINER_SCAN: status=partial
- SEC_TLS_13: status=partial
- SEC_AES_256: status=partial
- SEC_VAULT_SECRETS: status=partial
- SEC_MFA_ADMIN: status=partial
- SEC_AUDIT_400_DAY: status=partial
- SEC_7_YEAR_THERMO: status=partial

## Claim status totals
- proven: 23
- partial: 34
- goal: 21
- remove: 0
- quarantine: 0

## Stage-1 closure blockers
- Baseline run in `reports/test_audit/baseline_run_20260522/` has `exit_code.txt=1`; environment missing optional dependencies.
- `coverage.xml` is absent in `baseline_run_20260522`; coverage summary is not evidence-complete.
- Proven coverage claims (`COV_BACKTEST_74`, `COV_EXECUTION_44`, `COV_CORE_32`) point to historical artifacts, not fresh baseline artifacts.
- Mutation claim `MUTATION_90_KILL` lacks fresh `reports/mutmut/summary.json` in this stage.
