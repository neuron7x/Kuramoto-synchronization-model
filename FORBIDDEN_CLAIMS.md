# Forbidden Claims Contract

GeoSync claims are limited to falsifiable research statements with explicit evidence, nulls, and failure modes. This document is a repository-level claim-space firewall for README text, PR bodies, release notes, papers, and generated artifacts.

## Product Category Boundary

This firewall governs *status* wording. The orthogonal **product-category**
boundary — GeoSync is a verification-first research platform, **not** a
live-trading system, alpha engine, or investment-advice product — is declared
canonically in [`PRODUCT_CATEGORY.md`](PRODUCT_CATEGORY.md) and enforced over
the whole canonical doc surface by `scripts/ci/check_claim_boundary.py`
(workflow: `.github/workflows/claim-boundary-gate.yml`). Product-level
phrasing such as `live trading`, `trading signal`, `signal generation`, or
`alpha engine/product/signal` is admissible only as reviewed *mechanism*
(code symbols, ops runbooks, research disclaimers, honest negations) recorded
in `.github/claim_boundary_allow.json`; new unreviewed occurrences fail CI.

## Banned Status Language

The following phrases are forbidden unless they appear inside this policy file as examples of prohibited wording:

- `validated alpha`
- `production trading`
- `market physics proven`
- `guaranteed edge`
- `deployable strategy`
- `risk-free signal`
- `law of markets`
- `proven predictor`

## Allowed Status Language

Use only status terms that disclose the evidence boundary:

| Status | Meaning |
| --- | --- |
| `Active` | The invariant or gate is implemented and checked. |
| `Not Measured` | No qualifying real-data measurement exists. |
| `Not Deployable` | Evidence is incomplete, single-session, cost-model limited, or not externally replicated. |
| `Instrumented` | Pipeline mechanics are present; synthetic data may only reach this boundary. |
| `Measured-Single` | One immutable real-data artifact passed schema, nulls, and falsifiers. |
| `Measured-Multi` | Multiple independent real-data artifacts passed the same gates. |
| `Blocked` | A named gate prevents promotion. |

## Promotion Invariants

1. Synthetic-only evidence cannot promote any claim beyond `Instrumented`.
2. A claim without a falsifier cannot be promoted.
3. A dirty git state is allowed only if the artifact explicitly reports `git_dirty: true`; it cannot support a signoff tier.
4. A negative cost-model result must be recorded as `BLOCKED_COST_MODEL`, not hidden behind alternate filtering.
5. Real-data promotion requires dataset SHA-256, config SHA-256, deterministic seed, UTC timestamp, null-baseline result, and schema-valid artifact.

## Current Claim Allowlist

| Claim | Evidence Boundary | Falsifier | Status |
| --- | --- | --- | --- |
| Invariant Registry | Script/check coverage of registered invariant witnesses | Missing invariant count or unlinked `INV-*` witness | Active |
| Systemic-Risk Phase Signal | Protocol and synthetic/controlled checks only | Real-data gate failure | Not Measured |
| Ricci Microstructure Predictor | One crypto-perps L2 session | Multi-session failure, null superiority, or cost-model failure | Not Deployable |
