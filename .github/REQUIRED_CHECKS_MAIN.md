# Required Checks for `main`

Machine-readable single source of truth for scripts, Renovate, and automation
that need the canonical list of required status checks for the `main` branch.

Human-readable context and the full branch-protection ruleset live in
[`BRANCH_PROTECTION_MAIN.md`](./BRANCH_PROTECTION_MAIN.md).

## Required status checks

```yaml
required_checks:
  - repo-policy
  - python-quality
  - python-fast-tests
  - frontend-gate
  - dependency-review
  - secrets-supply-chain
```

Every name above must exactly match a job name in
[`workflows/pr-gate.yml`](./workflows/pr-gate.yml). The `repo-policy` job
enforces the pin/permissions invariants that protect this contract from
silent drift.
