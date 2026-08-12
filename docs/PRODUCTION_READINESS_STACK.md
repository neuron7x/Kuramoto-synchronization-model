# Production Readiness Stack

Status: repository readiness contract.
Scope: GeoSync release promotion.

## Core rule

A readiness claim is accepted only when it has this shape:

```text
claim -> check -> command -> artifact -> hash -> verdict
```

Documentation can describe readiness, but machine evidence decides promotion.

## Source hierarchy

1. Repository-local gates: PR Gate, Readiness Gate, Mutation Kill Gate, Claim Boundary Gate, Physics Invariants, Commit Acceptor Gate, Repo Integrity Gate.
2. Google SRE: SLI, SLO, error budget, production readiness review, release engineering.
3. NIST AI RMF / TEVV: metrics, test sets, tools, validation, verification, risk measurement.
4. Supply-chain assurance: SBOM, dependency audit, provenance, release artifacts.
5. OpenSSF Scorecard, CodeQL, dependency scanning, branch protection, required checks.
6. Agentic software engineering evaluation: process discipline, long-horizon repo evolution, production-like evaluation, installable repository completion.

## Readiness layers

| Layer | Required evidence | Promotion value |
| --- | --- | --- |
| Structure | files, docs, static contracts | STRUCTURAL |
| Tests | unit, invariant, contract tests | TESTED |
| Evaluation | walk-forward, ablation, null models, deterministic reports | EXTRAPOLATED |
| Operations | SLO, runbook, rollback, incident drill, release verdict | ANCHORED |

## Required machine fields

```yaml
claim_id: string
scope: repository | package | module | workflow | docs | artifact
check_command: string
expected_artifact: string
artifact_hash: string
commit_sha: string
verdict: PASS | FAIL | BLOCKED
```

## Minimum gate families

- tests
- lint
- type checking
- import architecture
- security scan
- dependency audit
- claim boundary
- commit acceptor presence
- release artifact presence
- deterministic release verdict generation

If evidence is missing, stale, skipped, or not tied to the current commit, the release verdict must not report readiness as complete.
