# CI/CD Overview (Canonical)

## Workflow Topology

### 1) PR Gate (required before merge)
- Workflow: `.github/workflows/pr-gate.yml`
- Triggers: `pull_request` to `main`, `merge_group`
- Decision: whether a PR can merge into `main`
- Required checks:
  - `repo-policy`
  - `python-quality`
  - `python-fast-tests`
  - `frontend-gate`
  - `dependency-review`
  - `secrets-supply-chain`

### 2) Main Validation (post-merge)
- Workflow: `.github/workflows/main-validation.yml`
- Triggers: `push` to `main`, `workflow_dispatch`
- Decision: deeper confidence after merge (broader tests, coverage guardrail, package/frontend build smoke)

### 3) Scheduled / Manual Security Validation
- Workflow: `.github/workflows/security-deep.yml`
- Triggers: weekly schedule + manual dispatch
- Decision: deep security posture (pip-audit, Semgrep, CodeQL) without blocking normal PR velocity

## Design Principles
- Minimal deterministic PR gate.
- Stable check names for branch protection.
- Merge queue compatible (`merge_group` on required-check workflow).
- Least-privilege permissions and no `pull_request_target` execution of untrusted code.
- Lockfile-based reproducible Python setup via `.github/actions/setup-geosync`.

## Old-to-New Mapping (Entropy Reduction)
- `tests.yml`, `ci.yml`, `security.yml`, `semgrep.yml` and all disabled shadow workflows were consolidated into:
  - `pr-gate.yml`
  - `main-validation.yml`
  - `security-deep.yml`

Any workflow that did not make a crisp merge, post-merge, scheduled-security, or release decision was removed.
