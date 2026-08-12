# D-002J-P1A — Audit Boundary

Explicit scope contract for the P1A source registry provenance audit. Companion to the prereg `forbidden_claims` block (`docs/governance/D002J_PREREGISTRATION.yaml` §14).

## ALLOWED

P1A audits the 25 sources committed by PR #695 in `artifacts/d002j/data_registry/source_registry_v1.json` against 10 verification dimensions:

1. **provider identity** — provider field matches the official organisation (BIS / Fed / OFR / ECB / FRED / NBER / BoE / FDIC / academic publishers).
2. **official URL** — HEAD probe returns 2xx/3xx, OR the parent domain is reachable and the substantive product exists at a related path (PARTIAL/DOWNGRADED outcome).
3. **documentation URL** — same standard as official_url.
4. **access method** — matches what the provider actually offers (api / csv / bulk_download / per_bank_download / preprint / etc.).
5. **license boundary** — explicit text OR explicitly `unknown` with rationale.
6. **coverage window** — `coverage_start` and `coverage_end` plausible per provider documentation.
7. **frequency** — matches source documentation (daily / quarterly / etc.).
8. **variables** — listed variable names plausibly source-supported; flag obvious mismatches.
9. **crisis-window relevance** — narrative claim bound to at least one observable mapping.
10. **mechanistic relevance** — narrative claim bound to at least one observable.

Outputs:

- `artifacts/d002j/data_registry/source_provenance_audit_v1.json` — schema `D002J-SOURCE-PROVENANCE-AUDIT-v1`, per-source audit entries.
- `artifacts/d002j/data_registry/source_access_smoke_v1.json` — HTTP HEAD probe ledger.
- `artifacts/d002j/data_registry/source_evidence_lock_v1.json` — claim ↔ evidence_url pinning for VERIFIED sources.
- `artifacts/d002j/data_registry/source_registry_audit_summary_v1.json` — aggregate counts + decision.
- `docs/research/D002J_SOURCE_PROVENANCE_AUDIT.md` — narrative.
- `docs/research/D002J_SOURCE_DOWNGRADE_LOG.md` — DOWNGRADED/REJECTED entries.
- `docs/research/D002J_P1A_AUDIT_BOUNDARY.md` — this file.
- `tests/systemic_risk/test_d002j_source_provenance_audit.py` — 22 fail-closed assertions.
- `.claude/commit_acceptors/x10r-d002j-p1a-source-provenance-audit.yaml` — diff-bound acceptor.
- `docs/governance/D002G_CANONICAL_RUN_BLOCKERS.md` — append-only audit lineage record.

## FORBIDDEN

P1A does NOT:

- ingest any data (no large downloads — bytes_downloaded bound; `no_large_downloads: true`, `no_private_data: true` in the smoke JSON)
- run any analysis (no signal computation, no statistical test on data)
- authorise any canonical run (`canonical_run_authorized: false`)
- edit any source code under `research/systemic_risk/*.py` or `scripts/x10r_d002*.py`
- edit any D-002J prereg (`docs/governance/D002J_PREREGISTRATION.yaml` byte-exact preserved)
- edit any D-002C/D-002G/D-002H/D-002I governance YAML/MD (forbidden_paths in acceptor)
- edit any D-002C claim ledger (`docs/governance/D002C_CLAIM_LEDGER.yaml` byte-exact preserved)
- claim real-bank validation
- make systemic-risk prediction claims
- refactor the SHA registry (explicitly deferred per master document §16)
- close H_I2 (explicitly deferred per master document)
- touch power logic (explicitly deferred — P7 owns power)
- add new sources to fix weak existing ones (audit-only)

## Decision taxonomy (canonical)

- `SOURCE_REGISTRY_VERIFIED` — all 25 sources VERIFIED, no partial/downgraded/rejected.
- `SOURCE_REGISTRY_PARTIALLY_VERIFIED` — some PARTIAL or DOWNGRADED, floors hold.
- `SOURCE_REGISTRY_REJECTED` — any floor fails: total_sources < 25, verified_or_partial < 18, verified_usable_now < 12, any crisis_window retains < 3 verified/partial, or any mechanism family retains < 2 verified/partial.

This audit's decision is **`SOURCE_REGISTRY_REJECTED`** — the `information_constraint` mechanism family has only 1 verified/partial source (ALFRED, PARTIAL). The fix requires a follow-up `fix(x10r,D-002J-P1)` PR (registry repair). P2 cannot open until decision flips.

## Drift sentinels enforced in tests

The 22 tests in `tests/systemic_risk/test_d002j_source_provenance_audit.py` enforce:

- locked governance sha256 byte-exact (5 anchors)
- source code under `research/systemic_risk/` unchanged
- D-002J prereg byte-exact
- D-002C claim ledger byte-exact
- audit JSON parses and carries correct schema_version
- all 25 registry source_ids present in audit
- canonical_run_authorized never true
- no_large_downloads and no_private_data flags both true in smoke JSON
- per-source audit_status one of VERIFIED/PARTIAL/DOWNGRADED/REJECTED
- every VERIFIED source has at least one evidence_ref
- every VERIFIED source carries license_boundary
- every VERIFIED source has forbidden_use_confirmed=true
- summary counts match per-source audit counts
- crisis-window retention ≥3 verified/partial each
- mechanism families retention ≥2 verified/partial each (the failure of this floor is what triggers REJECTED)
- downgrade log exists with at least one entry per DOWNGRADED audit entry
- no unresolved merge markers in any artifact

## What success looks like

Success is NOT "all 25 sources verified". Success is **HONEST audit**. P1A surfaced 5 stale URL pins and 1 structural single-point-of-failure on mechanism families. The decision is REJECTED — the system is working as designed. The next legal PR repairs the registry rather than building on top of it.
