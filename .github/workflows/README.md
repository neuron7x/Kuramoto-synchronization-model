# GitHub Actions Workflows

Canonical workflow set for the GeoSync repository. Every workflow is pinned
to a single, unambiguous responsibility so the branch-protection contract
for `main` stays auditable.

## Workflows

| Workflow | Trigger | Purpose | Blocks merge? |
|---|---|---|---|
| [`pr-gate.yml`](./pr-gate.yml) | `pull_request` → `main`, `merge_group` | Synchronous merge gate — lint, types, fast tests, frontend, deps, secrets | **Yes** (required checks) |
| [`main-validation.yml`](./main-validation.yml) | `push` → `main` | Post-merge deep validation (slow/heavy suites, integration) | No |
| [`codeql.yml`](./codeql.yml) | `push` → `main`, weekly cron, manual | CodeQL SAST — Python, JavaScript, Go | No (reports to Security tab) |
| [`security-deep.yml`](./security-deep.yml) | Weekly cron, manual | Out-of-band security scans — `pip-audit`, `gitleaks`, `trivy-fs` | No |
| [`connectome-gate.yml`](./connectome-gate.yml) | `pull_request` → `main`, `merge_group`, `push` → `main` | AST-enforced neuro-architectural import boundaries from `docs/architecture/connectome.yaml`; design model documented in [`../architecture/CONNECTOME_GATE.md`](../../docs/architecture/CONNECTOME_GATE.md) | No (advisory until branch protection adopts `enforce-connectome`) |

Any additional workflow **must** define a distinct decision boundary that is
not already covered by the workflows above. Overlapping gates are rejected.

## Required status checks for `main`

The branch-protection ruleset enforces exactly the job names emitted by
`pr-gate.yml` — see [`../BRANCH_PROTECTION_MAIN.md`](../BRANCH_PROTECTION_MAIN.md).

1. `repo-policy`
2. `python-quality`
3. `python-fast-tests`
4. `frontend-gate`
5. `rust-accel-gate`
6. `dependency-review`
7. `secrets-supply-chain`
8. `go-workspace-integrity`

All eight jobs are fail-closed (`continue-on-error: false`). Merge queue is
supported because every required job declares the `merge_group` trigger.


## Local contract validation

Before changing `pr-gate.yml`, `.github/BRANCH_PROTECTION_MAIN.md`, or this
README, run the repository-local contract validator from the repository root:

```bash
python scripts/ci/check_pr_gate_contract.py
```

A valid artifact emits `state=REST action_potential=0`. Any ACTION state is
policy drift and must be fixed before merge. The contract validator is intentionally self-contained for branch-protection
drift checks, while `repo-policy` also invokes `python scripts/ci/run_actionlint.py`
for real GitHub Actions syntax/expression validation when an actionlint binary
or Docker runtime is available.

## Runtime hardening

All canonical workflows opt into GitHub's Node.js 24 runtime for JavaScript
actions via:

```yaml
env:
  FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: 'true'
```

Frontend workflows additionally pin `actions/setup-node` to `node-version:
'24'` to avoid mixed-runtime drift. Python environments are provisioned
through the composite action [`../actions/setup-geosync`](../actions/setup-geosync),
which enforces pinned `pip` and `pytest` versions from `requirements-dev.lock`
for reproducible CI.

## Supply-chain hygiene

Every third-party action reference **must** be pinned to a 40-character commit
SHA (`uses: owner/repo@<sha> # vX.Y`). The `repo-policy` job in `pr-gate.yml`
fails the build if any unpinned reference is introduced. Re-pinning happens
via the vetted [Renovate rules](../dependabot.yml) or explicit maintainer commits.

## Adding a new workflow

1. Confirm it does not duplicate an existing gate.
2. Declare least-privilege `permissions:` at the top level.
3. Never use `pull_request_target:` — `repo-policy` will reject it.
4. Pin every `uses:` reference by SHA.
5. Update this README and `../BRANCH_PROTECTION_MAIN.md` if the change affects
   required status checks.
