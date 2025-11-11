# Release Gates - Dopamine Loop (TD(0) RPE, DDM, Go/No-Go)

## Overview

This document describes the comprehensive release gate system for TradePulse, combining progressive rollout quality gates with dopamine-based reinforcement learning mechanisms (TD(0) Reward Prediction Error, Drift-Diffusion Models, and Go/No-Go decision making) to ensure the highest code quality and reliability.

## Core Quality Requirements (NEW)

### 1. Code Coverage Gate (98% minimum)
All pull requests must maintain **98% code coverage** across critical modules:
- `core/`, `backtest/`, `execution/`
- Configured in `pyproject.toml`: `fail_under = 98`
- Enforced in: `.github/workflows/ci.yml`, `.github/workflows/coverage.yml`

**Local check:**
```bash
pytest tests/ --cov=core --cov=backtest --cov=execution --cov-fail-under=98
```

### 2. Mutation Testing Gate (90% kill rate minimum)
All PRs must achieve **90% mutation kill rate**:
- Ensures test quality, not just coverage
- Configured in `pyproject.toml`: `[tool.mutmut]`
- Enforced by: `tools/mutation/kill_rate_guard.py`

**Local check:**
```bash
mutmut run --paths-to-mutate=core,backtest,execution --tests-dir=tests
python -m tools.mutation.kill_rate_guard --threshold=0.9
```

### 3. Risk-Based Review Requirements
PRs are automatically assigned risk levels (low/medium/high) based on:
- Coverage gap (up to 40 points)
- Mutation gap (up to 40 points)
- Critical files modified (up to 20 points)
- PR size (10 points for >500 lines)

High-risk changes require senior review and extensive testing.

## Progressive Release Gates

The Progressive Rollout pipeline promotes builds through additional quality gates:

1. **Latency Gate** – uses `observability.release_gates.ReleaseGateEvaluator`
   with the following thresholds (milliseconds):
   - median ≤ 60
   - p95 ≤ 85
   - max ≤ 120
2. **Coverage Gate (Legacy)** – superseded by 98% requirement above
3. **Performance Budget Gate** – asserts that each component listed in
   `configs/perf_budgets.yaml` stays within its budget.  Budgets are expressed in
   milliseconds measured by the synthetic benchmark harness.
4. **Energy Regression Gate** – reuses the TACL validator to ensure the selected
   scenario stays under the free energy limit (1.35).  Negative scenarios must
   fail validation; otherwise the job fails loudly to prevent silent regressions.

## Metrics Sources

- Latency samples originate from the link activator replay harness and are
  recorded in `ci/release_gates.yml`.
- Coverage data comes from the merged coverage report published by the test
  pipeline.
- Performance metrics come from the offline benchmark runner that writes the
  latest observations into `configs/perf_budgets.yaml`.
- Energy metrics reuse the same fixtures as the thermodynamic validation step
  (`tacl/link_activator_test_scenarios.yaml`).

## Automated PR Feedback

The system provides comprehensive feedback on all PRs:

1. **Release Gate Assessment** (`.github/workflows/pr-release-gate.yml`)
   - Quality metrics, risk score, recommendations
2. **Mutation Testing Results** (`.github/workflows/mutation-testing.yml`)
   - Kill rate, mutant breakdown, pass/fail status
3. **Merge Guard Status** (`.github/workflows/merge-guard.yml`)
   - Merge approval/block status, requirements checklist
4. **Quality Summary** (`.github/workflows/pr-quality-summary.yml`)
   - Aggregated metrics from all workflows

## PR Labels

The system automatically applies labels:
- `quality-gate-failed` (red): Merge blocked
- `risk: low/medium/high` (green/yellow/red): Risk level
- `missing-coverage`, `test-needed`: Specific issues

## Branch Protection

Configure branch protection on `main` to require:
- `Aggregate coverage & enforce guardrail` ✓
- `Mutation Testing Gate (90% kill rate)` ✓
- `Merge Guard Quality Check` ✓

## Failure Semantics

When any gate fails:

### Quality Gates (Coverage/Mutation)
- Workflow posts detailed comment to PR
- Applies `quality-gate-failed` label
- Blocks merge automatically
- Uploads artifacts: `coverage.xml`, `mutation_summary.json`

### Progressive Release Gates
- Workflow emits structured artifacts in `.ci_artifacts/release_gates.json` and `.ci_artifacts/release_gates.md`
- Contains: failing gate name, raw metrics, energy/entropy data
- Exits with code **1**, pipeline halts

### Resolution
- Fix identified issues locally
- Push changes to re-trigger checks
- All required checks must pass before merge
- Consult `docs/OPERATIONS.md` for remediation guidance

---
**Updated:** 2025-11-11 - Added dopamine loop quality gates (coverage 98%, mutation 90%, risk assessment)
