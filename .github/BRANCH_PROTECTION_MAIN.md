# Branch Protection / Ruleset Manifest for `main`

Single source of truth for the `main` branch-protection ruleset in GitHub
repository settings. Apply these values **exactly** — deviations are
considered policy drift and must be reverted.

> Required check names must match job names in
> [`.github/workflows/pr-gate.yml`](./workflows/pr-gate.yml) character-for-character.

## Branch targeting

- Target branch: `main`
- Include: repository default branch

## Pull request requirements

| Setting | Value |
|---|---|
| Require a pull request before merging | **enabled** |
| Required approving reviews | **1** |
| Dismiss stale pull request approvals when new commits are pushed | **enabled** |
| Require review from Code Owners | **enabled** |
| Require approval of the most recent reviewable push | **enabled** |
| Require conversation resolution before merging | **enabled** |
| Allow specified actors to bypass required pull requests | **disabled** |

## Required status checks (strict, fail-closed)

| Setting | Value |
|---|---|
| Require status checks to pass before merging | **enabled** |
| Require branches to be up to date before merging | **enabled** |

Required check names (must match `pr-gate.yml` job names exactly):

1. `repo-policy`
2. `python-quality`
3. `python-fast-tests`
4. `frontend-gate`
5. `rust-accel-gate`
6. `dependency-review`
7. `secrets-supply-chain`
8. `go-workspace-integrity`

All eight are fail-closed (`continue-on-error: false` in `pr-gate.yml`).

## Branch safety

| Setting | Value |
|---|---|
| Allow force pushes | **disabled** |
| Allow deletions | **disabled** |
| Require signed commits | **recommended** |
| Require linear history | **enabled** (merge queue enforces this) |
| Lock branch | **disabled** |

## Bypass

- Bypass list: **empty** — no actors, no apps, no teams.
- Break-glass: documented administrator-only procedure in the on-call runbook;
  every bypass is audit-logged and retro-reviewed.

## Merge queue compatibility

Merge queue is **optional** but fully supported: every required job in
`pr-gate.yml` declares the `merge_group` trigger, so checks are emitted in
both `pull_request` and `merge_group` contexts.

## Out-of-band checks (non-blocking)

These workflows produce security telemetry but are **not** required checks.
They surface findings in the Security tab and fail their own runs:

- `codeql.yml` — SAST on `main` and weekly cron
- `security-deep.yml` — `pip-audit`, `gitleaks`, `trivy-fs` (weekly cron)

## Drift detection

The `repo-policy` job in `pr-gate.yml` enforces:

- every workflow file passes actionlint syntax/expression validation
- every workflow file declares a `permissions:` block
- no workflow uses `pull_request_target`
- every `uses:` reference is pinned to a 40-character commit SHA
- `pr-gate.yml`, this branch-protection manifest, and
  `.github/workflows/README.md` agree on required job names and counts
- `dependency-review` fails on `high` severity
- `rust-accel-gate` keeps its Rust/PyO3 clippy-and-test contract intact

Run the same contract check locally before editing the merge gate:

```bash
python scripts/ci/check_pr_gate_contract.py
```

A valid artifact emits `state=REST action_potential=0`. Any PR that breaks
these invariants fails `repo-policy` and cannot merge.
