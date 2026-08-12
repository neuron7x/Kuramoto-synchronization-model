# CI governance lane 989

Status: active remediation lane for the PR Gate repo-policy blocker.

Purpose
- Integrate PR 988, Issue 989, and PR 990 into one delivery control plane.
- Encapsulate repository-wide workflow cleanup outside the runtime refactor PR.
- Orchestrate debt remediation as small evidence-bound batches.

Root cause
- PR 988 runtime gates are green.
- The remaining blocker is the repository workflow reference policy.
- The blocker is global repository governance debt, not a runtime defect in PR 988.

Current topology
- PR 988: runtime refactor lane for tests/conftest.py and related acceptor evidence.
- Issue 989: governance remediation tracker for workflow reference cleanup.
- PR 990: documentation and orchestration lane for Issue 989.

Current branch
- infra/ci-policy-lane-989

Confirmed canonical repo-local mappings from prior green-main remediation
- actions/checkout: df4cb1c069e1874edd31b4311f1884172cec0e10, documented as v6.0.3
- actions/setup-python: a309ff8b426b58ec0e2a45f0f869d46889d02405, documented as v6
- actions/upload-artifact: 043fb46d1a93c77aae656e7c1c64a875d1fc6a0a, documented as v7.0.1

Encapsulation boundary
- PR 988 must not absorb repository-wide workflow cleanup.
- PR 990 owns the remediation plan and evidence trail.
- Issue 989 remains the canonical tracker for governance debt state.

Orchestration sequence
1. Keep PR 988 focused on runtime refactor evidence.
2. Use Issue 989 as the global remediation ledger.
3. Use PR 990 as the controlled lane for documentation and batch planning.
4. Apply workflow reference batches only after every external ref has a resolved immutable target.
5. Rerun PR Gate after each batch.
6. Merge PR 988 only after required gates are green.

Remediation strategy
1. Batch first-party actions already resolved by prior repository precedent.
2. Resolve remaining third-party action refs separately before mutation.
3. Keep each batch small enough to diagnose from CI output.
4. Do not merge PR 988 until its required gate is green.

Invariant
- No runtime regression identified in PR 988.
- Governance remediation must be evidence-bound and batch-scoped.
- No release promotion with a red required gate.

Verdict
INTEGRATED_CONTROL_PLANE
ENCAPSULATED_GOVERNANCE_LANE
ORCHESTRATED_REMEDIATION_QUEUE
PR_988_RUNTIME_GREEN
GLOBAL_POLICY_REMEDIATION_ACTIVE
