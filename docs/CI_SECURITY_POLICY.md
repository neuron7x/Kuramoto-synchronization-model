<!-- Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab) -->
<!-- SPDX-License-Identifier: MIT -->

# CI Security Policy (SEC-011)

A GitHub Actions workflow is a **capability surface**. This policy governs the
permissions granted to that surface and the boundary between trusted repository
context and untrusted pull-request code. It is enforced mechanically by
`scripts/ci/check_ci_permissions.py`, whose verdict is reproduced in
`artifacts/security/workflow_security_report.json`.

## Threat model

Two structural failure modes account for essentially every CI-mediated repo
compromise:

1. **Over-broad default token.** A workflow with no `permissions:` block — or a
   `write-all` default — gives every job a read-write `GITHUB_TOKEN`. One
   compromised action, transitive dependency, or injected step can then push
   commits, cut releases, or open its own PRs.
2. **`pull_request_target` "pwn request".** `pull_request_target` runs in the
   **base** repository context, so the workflow token and every `secrets.*`
   value are in scope, while the event is authored by a fork. If such a workflow
   **checks out the PR head** (`actions/checkout` with a `ref` resolving to
   `github.event.pull_request.head.*` / `github.head_ref` / `refs/pull/…`) and
   then executes any of that code, a malicious PR exfiltrates the repository's
   secrets.

## Rules (fail-closed)

The checker parses **every** `.github/workflows/*.yml` as real YAML — never
grep. The use/mention distinction matters: a workflow that merely *names*
`pull_request_target` in a comment or in its own policy-check text is not *using*
it, and `detect-secrets.baseline` is not a `secrets.*` reference. The following
conditions exit non-zero:

| Code | Condition | Rationale |
|------|-----------|-----------|
| `MISSING_PERMISSIONS` | no top-level `permissions:` block | default token is read-write |
| `WRITE_ALL_DEFAULT` | top-level `permissions: write-all` | grants every scope |
| `UNSAFE_PRT_CHECKOUT` | `pull_request_target` trigger **and** checkout of the PR head | secrets always in scope under `pull_request_target`; running fork code leaks them |
| `UNJUSTIFIED_WRITE_SCOPE` | any `write` scope (top- or job-level) not on the justification allowlist | keeps least-privilege honest — a new, unexplained write grant breaks CI |

Reported for provenance but **non-fatal**: `JUSTIFIED_WRITE_SCOPE` (an
allowlisted write scope + its reason), `SECRETS_IN_SCOPE` (explicit `secrets.*`
references excluding `GITHUB_TOKEN`), `OIDC_ID_TOKEN` (`id-token: write`).

## Least-privilege default

Every workflow **must** declare an explicit top-level block. The default is:

```yaml
permissions:
  contents: read
```

Write scopes are granted **only** on the single job that needs them, and **only**
with a recorded justification. A workflow that legitimately needs a write scope
is **kept, not downgraded** — its scope is registered in the allowlist below (the
`JUSTIFIED_WRITE_SCOPES` table in the checker) with the reason.

## Justified write scopes (allowlist)

These are the only write grants in the tree. Each is scoped to one job (except
the SARIF upload, which is a whole-workflow concern) and documented:

| Workflow | Location | Scope | Justification |
|----------|----------|-------|---------------|
| `codeql.yml` | top-level | `security-events: write` | Upload CodeQL SARIF analysis to the Security tab (`github/codeql-action`). |
| `pr-gate.yml` | job `dependency-review` | `pull-requests: write` | Post the dependency-review summary comment (`actions/dependency-review-action`, `comment-summary-in-pr: on-failure`). Trigger is `pull_request`, **not** `pull_request_target`; fork tokens are read-only regardless. |
| `ricci-microstructure-gate.yml` | job `supply-chain` | `id-token: write` | OIDC token for keyless SLSA build-provenance attestation (`actions/attest-build-provenance`). No secrets in scope. |
| `ricci-microstructure-gate.yml` | job `supply-chain` | `attestations: write` | Write the SLSA build-provenance attestation to the attestations store. |

### OIDC (`id-token: write`)

Only `ricci-microstructure-gate.yml`'s `supply-chain` job requests OIDC, and it
is consumed by `actions/attest-build-provenance` (Sigstore keyless signing). No
custom OIDC audience is configured, so no cloud-role trust policy is exposed;
the job carries no `secrets.*` and runs only after the lane gate. If a future
job adds `id-token: write` for cloud auth, its `aud` (audience) must be pinned to
the specific role/provider — a wildcard audience is rejected in review.

### Environment approvals for publish/sign

The tree currently ships **no** package-publish or artifact-signing job that
pushes to an external registry, so no protected `environment:` is wired. When
one is added (PyPI/GHCR publish, release signing), it MUST run in a GitHub
`environment:` with required reviewers so a malicious or accidental PR cannot
publish or sign. This is a forward-looking requirement, tracked here rather than
enforced, because there is no such job to gate yet.

### Artifact trust

`upload-artifact` / `download-artifact` cross the trust boundary between jobs.
Downstream jobs must treat downloaded artifacts as untrusted input (verify SHA /
schema before use), exactly as `ricci-microstructure-gate.yml` verifies its
committed canonical artifact's SHA chain before trusting it.

## Adding or changing a workflow

1. Start from `permissions: {contents: read}`.
2. If a job needs a write scope, add it **at job level** and register
   `(workflow_basename, job_id, scope)` in `JUSTIFIED_WRITE_SCOPES` with a
   one-line reason. Update the table above.
3. Never use `pull_request_target` to check out and run PR-head code. If you
   need fork-code plus repo context, split it: run untrusted code under
   `pull_request` (read-only token, no secrets), and do the privileged step in a
   separate `workflow_run` job that does not check out fork code.
4. Run the gate locally:

   ```bash
   python scripts/ci/check_ci_permissions.py \
     --report artifacts/security/workflow_security_report.json
   python -m pytest tests/ci/test_ci_permissions.py -q
   ```

## Enforcement

- **Gate:** `scripts/ci/check_ci_permissions.py` (exit 1 on any fatal flag, exit
  2 fail-closed on an unparseable workflow).
- **Tests:** `tests/ci/test_ci_permissions.py` — positive (the real tree passes)
  + negatives (pwn-request, missing block, `write-all`, unjustified write scope)
  + a fail-closed parse-error case.
- **Report:** `artifacts/security/workflow_security_report.json` — per-workflow
  permissions and flags.

`pr-gate.yml`'s `repo-policy` job already enforces a coarser grep-based invariant
(every workflow has a `permissions:` line; no `pull_request_target`). This gate
is the YAML-parsing, use/mention-aware superset and is the authoritative check.
