# ADR 0020 — IERD-PAI-FPS-UX-001 Adoption

**Status.** Accepted, 2026-05-03.
**Supersedes.** Nothing — this ADR adds a governance layer on top of the existing claim/evidence registry.
**Related.**
- [`docs/governance/IERD-PAI-FPS-UX-001.md`](../governance/IERD-PAI-FPS-UX-001.md) (binding directive)
- [`docs/CLAIMS.yaml`](../CLAIMS.yaml) (schema bumped to v2)
- [`docs/yana-response.md`](../yana-response.md) (external-audit response)
- [`docs/audit/ierd_phase0_findings.md`](../audit/ierd_phase0_findings.md) (Phase-0 surface audit)
- [`docs/validation/pai_report_2026_05_03.md`](../validation/pai_report_2026_05_03.md) (first PAI snapshot)
- [`scripts/ci/lint_forbidden_terms.py`](../../scripts/ci/lint_forbidden_terms.py) (Phase-0 warn-mode lint)

---

## Context

On 2026-05-02 an external falsification audit (Yana Levchyshyna) issued seven sharp questions against the way GeoSync uses the terms `physics-aligned`, `first-principles`, `production-ready`, `truth`, `energy`, `law`, `invariant`, `UX-ready`, and `cycle-time acceleration` in its surface documentation:

1. What in the repository is physics-aligned, and how is it distinguished from merely well-written code?
2. On what files and functions does the First-Principles Score rest given partial access?
3. How is the 5-Step Algorithm assessed without documented engineering decisions?
4. How is frontend-integration suitability (API, latency, data contracts) accounted for?
5. Can code be truthful and simple architecturally and still produce a poor user experience?
6. How is "accelerate cycle time" measured without client-side performance analysis?
7. Are user-level edge cases (empty states, error states) part of the assessment?

Q1–Q3 are answerable from the existing physics kernel (`CLAUDE.md` 67-invariant registry, `core/physics`, `core/kuramoto`, `core/neuro`, `tests/unit/physics/`). Q4–Q7 expose a real gap: the repository does not currently ship a frontend or a public HTTP surface that can be audited for OpenAPI contracts, UX states, end-to-end latency budgets, or edge-case coverage.

The audit response was issued on 2026-05-02 in the form of an Institutional Engineering Remediation Directive (IERD-PAI-FPS-UX-001), declaring a binding standard.

## Decision

Adopt IERD-PAI-FPS-UX-001 as a binding standard for GeoSync, layered on top of the existing claim/evidence registry, with the following concrete commitments.

### 1. Tier-labelled claim ledger

`docs/CLAIMS.yaml` schema is bumped from v1 to v2. Every claim now carries a `tier` field:

```
ANCHORED       — every artefact in evidence_paths exists, falsifying
                 test exists and is referenced, surface text matches
                 what the test verifies.
EXTRAPOLATED   — partial evidence: missing evidence is named in the
                 description and a confidence ceiling is given.
SPECULATIVE    — hypothesis only. Forbidden in README, product docs,
                 API docs, reports. Allowed only in research notes.
UNKNOWN        — tier not yet assessed; tracked by an issue with a
                 deadline for re-classification.
```

`scripts/ci/check_claims.py` is extended to accept v1 (tier defaults to `UNKNOWN`) and v2 (tier required). On gated P0/P1 claims, `ANCHORED` and `EXTRAPOLATED` paths must exist; `SPECULATIVE` and `UNKNOWN` paths may be aspirational and warn-only.

### 2. Forbidden-terminology lint

`scripts/ci/lint_forbidden_terms.py` is added. It scans `README.md`, `docs/**/*.md`, `docs/**/*.yaml`, and `reports/**/*.md` for the IERD §3 forbidden-terminology list and reports findings.

* **Phase 0 (this ADR).** Lint runs in warn-only mode. CI does not block on findings. The Phase-0 audit (`docs/audit/ierd_phase0_findings.md`) catalogs current findings and the remediation plan.
* **Phase 5.** Lint is promoted to `--strict` and gates merge.

Allowlist: the directive itself, the audit findings, the lint source, the claim ledger, `KNOWN_LIMITATIONS.md`, and `yana-response.md` are exempt — these documents must quote the forbidden terms verbatim to define and discuss them.

### 3. Definition of Done (per module)

A module is **DONE** when it has all of the following:

```
1. equation or specification mapping
2. dimensional or contract test
3. invariant test (conservation / monotonic / stability)
4. analytical or limit-case test
5. convergence or stability evidence
6. ADR
7. API contract if exposed
8. UX state contract if user-facing
9. edge-case tests
10. traceable claim ledger entry
```

Items 1–6 and 10 are in scope for Phase 0 → Phase 2; items 7–9 require the frontend/API integration tracked under Q4–Q7 issues.

### 4. Phased adoption

| Phase | Scope | Exit gate |
|---|---|---|
| 0 (this PR) | Directive published; CLAIMS v2; lint warn-mode; Phase-0 audit; first PAI snapshot; Q4–Q7 issues opened | `check_claims.py` PASS, `lint_forbidden_terms.py` runs warn-only |
| 1 | PAI ≥ 0.90 on `core/kuramoto`, `core/physics`, `core/neuro` | PAI report v2 |
| 2 | ADR + convergence test for every numerical module | 5-step coverage ≥ 0.90 |
| 3 | OpenAPI 3.1 + JSON Schema for every exposed endpoint; async simulation workflow; standard error envelope | Schemathesis green |
| 4 | UX state matrix; E2E latency budgets; edge-case matrix | UXRS ≥ 0.95, all 4 latency layers green, ECC ≥ 0.90 |
| 5 | Lint moves to `--strict`, all 7 governance rules fail-closed | Full IERD compliance |

## Consequences

### Positive

* External claims now traceable to falsifying tests at the surface level (terminology audit) and at the artefact level (CLAIMS.yaml `tier` + `evidence_paths`).
* Q4–Q7 frontend/UX gaps are converted from informal "we'll get to that" to tracked claim entries with `UNKNOWN` tier and explicit re-classification deadlines.
* The 67-invariant CLAUDE.md kernel is now mirrored in the public claim ledger, so the strength of the physics kernel is visible to external auditors without requiring full repo access.

### Costs

* Phase 0 introduces 4 new `UNKNOWN`-tier claims (frontend gaps) that will sit in the registry until Phase 3/4 evidence lands. This is the cost of being honest about the gap rather than hiding it.
* All future claim additions must declare `tier` explicitly. PRs touching `docs/CLAIMS.yaml` will get an additional review check.
* The forbidden-terminology lint will produce ongoing warnings during Phase 0–4 across the 35 surface files identified in the Phase-0 audit. These warnings are tracked under `IERD-FOLLOWUP-*` issues and are not a regression.

### Risks

* If Phase 1 PAI ≤ 0.90 on any of the core modules, the IERD adoption itself becomes an EXTRAPOLATED-tier claim until brought into compliance. The PAI report tracks the per-module score so this risk is observable.
* The directive's frontend-integration tasks (Q4–Q7) require resources outside the current physics-kernel scope. The ADR explicitly does not commit a delivery date for Phase 3–4; only the entry gates and the tracking discipline.

## Alternatives considered

1. **Reject the directive as out-of-scope marketing concern.** Rejected — the audit questions are technically valid and Q4–Q7 expose real institutional risk in calling the repository "production-ready" without an end-to-end stack.
2. **Adopt the directive without phasing.** Rejected — strict-mode lint on day one would block 35 surface files and prevent any PR from landing. Phased adoption keeps the repository shippable while raising the floor.
3. **Keep CLAIMS.yaml v1 and add `tier` as a side document.** Rejected — splitting the ledger creates a drift surface. A schema bump with backward-compatible parsing in `check_claims.py` is the cheapest discipline.

## References

* IERD-PAI-FPS-UX-001 directive: `docs/governance/IERD-PAI-FPS-UX-001.md`.
* External-audit response: `docs/yana-response.md`.
* Existing physics kernel: `CLAUDE.md` (67-invariant registry).
* Existing claim infrastructure: `docs/CLAIMS.yaml`, `docs/CLAIM_INVENTORY.md`, `docs/KNOWN_LIMITATIONS.md`, `scripts/ci/check_claims.py`, `.github/workflows/claims-evidence-gate.yml`.
