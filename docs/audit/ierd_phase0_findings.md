# IERD Phase-0 Audit Findings

**Date.** 2026-05-03
**Auditor.** internal (IERD-PAI-FPS-UX-001 self-audit)
**Scope.** Full repository surface — Markdown documentation, README, reports, agent docs.
**Method.** `grep -rEni` for the §4.1 forbidden-terminology list against the worktree at branch `ierd-phase0-adoption` (parent `origin/main` @ `26c30f7`).

---

## Summary

| Forbidden phrase | Count | Surface |
|---|---|---|
| `production-ready` (any form) | **52 occurrences across 35 files** | README + docs + reports + agent surfaces |
| `physics-aligned` | 0 | — |
| `truth function` | 0 | — |
| `thermodynamic invariant` (literal) | 0 (only "thermodynamic" cited via Friston/Callen) | — |
| `serotonin_gain` (literal) | 0 (the symbol is `serotonin_*` modulator parameters, not bare gain) | — |
| `first-principles` | 1 | benign (`paper/ricci_microstructure/paper.md` line 275, CC-BY context) |
| `neuro truth` | 0 | — |
| `universal intelligence law` | 0 | — |

**Headline.** The dominant institutional risk in the surface text is **`production-ready`**, used 52× in 35 files across README, design docs, release process, agent ARCHITECTURE, and the SEROTONIN documentation set.

## Existing infrastructure

The repository **already** carries a non-trivial claim-governance layer:

* [`docs/CLAIMS.yaml`](../CLAIMS.yaml) — 8 P0/P1/P2 entries with required `evidence_paths`
* [`scripts/ci/check_claims.py`](../../scripts/ci/check_claims.py) — fail-closed schema + evidence verifier
* [`.github/workflows/claims-evidence-gate.yml`](../../.github/workflows/claims-evidence-gate.yml) — CI gate
* [`docs/CLAIM_INVENTORY.md`](../CLAIM_INVENTORY.md) — Phase-0 claim inventory with citations
* [`docs/KNOWN_LIMITATIONS.md`](../KNOWN_LIMITATIONS.md) — 6 explicit caveats (L-1 … L-6)
* 19 ADRs in `docs/adr/`

The IERD layer **extends** this; it does not replace it.

## Gap classification — `production-ready` surfaces

Each file is classified by whether its `production-ready` mention is anchored to a `CLAIMS.yaml` entry and/or a `KNOWN_LIMITATIONS.md` caveat.

| Class | Meaning | Treatment |
|---|---|---|
| **A — ANCHORED** | Mention is bracketed by a citation, a claim_id, or an explicit limitation that scopes the term | Keep the literal phrase; add `[claim_id=…]` annotation |
| **B — EXTRAPOLATED** | Mention is qualified (e.g. `production-ready *for paper trading*`, `production-ready Kubernetes manifests`) but the claim ledger has no matching `tier` field yet | Keep but downgrade to `EXTRAPOLATED` label and pointer to L-N |
| **C — SPECULATIVE** | Mention is a banner-style decoration ("✅ PRODUCTION-READY", verdict-style with no falsifying test) | Replace with neutral language; move to research notes if needed |
| **D — UNKNOWN** | Mention is in archived / legacy text | Annotate with archive notice and date |

### Class C — Phase-0 immediate downgrade list (representative, not exhaustive)

| File | Line | Current text | Proposed downgrade |
|---|---|---|---|
| `docs/SEROTONIN_IMPLEMENTATION_COMPLETE.md` | 16, 65, 217, 372, 378, 441 | `**Production-Ready**` / `✅ PRODUCTION-READY` (banner verdict) | `Status: tested under controlled fixtures; live-trading caveat per L-1` + tier `EXTRAPOLATED` |
| `docs/SEROTONIN_PRACTICAL_SUITABILITY_ASSESSMENT.md` | 12, 407, 471, 477 | `**PRODUCTION-READY** with high practical suitability` | `Tested + observability + conformal-CI surface present; live-venue evidence absent — see L-1` |
| `docs/SEROTONIN_DEPLOYMENT_GUIDE.md` | 11 | `**Status**: Production-Ready` | `Status: deployable to paper account; live deployment requires the gate in L-1` |
| `docs/NEURO_OPTIMIZATION_SUMMARY.md` | 437 | `**complete and production-ready**` | `feature-complete with the L-3 / L-4 gates` |
| `docs/digital_governance_framework.md` | 4 | `**Status:** ✅ Production Ready` | `Status: framework spec present; enforcement pending the controls listed below` |

### Class B — Already qualified but tier missing

| File | Line | Treatment |
|---|---|---|
| `README.md` | 637 | `CORE ENGINE  stable  production-ready` table — add tier `EXTRAPOLATED` link to L-1 |
| `docs/operational_readiness_runbooks.md` | 4 | `…to declare GeoSync production-ready for a live trading session` — already gates on the runbook; tag `EXTRAPOLATED` |
| `docs/P0_IMPLEMENTATION_SUMMARY.md` | 36, 500 | `production-ready Kubernetes deployments` — narrow scope, real artefact in `infra/` — tag `ANCHORED` w/ infra evidence |
| `docs/RELEASE_PROCESS.md` | 8 | `main — production-ready код` — process statement; tag `ANCHORED` w/ release-process tests |
| `docs/GITHUB_METADATA.md` | 16 | `production-ready infrastructure` — marketing surface; tag `EXTRAPOLATED` |
| `docs/project-status.md` | 15, 26-28 | maturity table per component — tag `EXTRAPOLATED` per row, link to closest L-N |
| `docs/METRICS_CONTRACT.md` | 184 | `OTHER_CORE_STABLE` row already says "partial" — tag `EXTRAPOLATED` |

### Class A — ANCHORED retention

| File | Line | Why it stays |
|---|---|---|
| `docs/KNOWN_LIMITATIONS.md` | 31 | quotes the README *to refute it* — tag `EXTRAPOLATED` with explicit pointer |
| `infra/terraform/eks/README.md` | (single occurrence) | infra-specific scope, real Terraform output | tag `ANCHORED` |
| `reports/release_readiness.md`, `reports/AUDIT_*` | release/audit reports — historical record | retain as `ANCHORED at date X`, no rewrite |

### Class D — Archive

`docs/archive/LEGACY_20241211_MODULE_ORCHESTRATION_SUMMARY.md` — annotate with `[ARCHIVED · pre-IERD]`, no rewrite.

## CI integration plan

1. `scripts/ci/check_claims.py` — extend to validate optional `tier` field; tier becomes mandatory once CLAIMS.yaml schema bumps to v2.
2. `scripts/ci/lint_forbidden_terms.py` — new lint, **warn-only** in Phase 0, fail-closed in Phase 5.
3. `.github/workflows/claims-evidence-gate.yml` — add the lint as a separate job; do not couple it to the existing evidence gate.

## Phase-0 PR scope

* Add `docs/governance/IERD-PAI-FPS-UX-001.md` (binding directive)
* Add `docs/adr/0020-ierd-adoption.md`
* Extend `docs/CLAIMS.yaml` schema v2 with `tier` field; backfill existing 8 entries
* Add `scripts/ci/lint_forbidden_terms.py` (warn mode)
* Touch the **highest-risk Class C** SEROTONIN documentation set (downgrade banners)
* Add `docs/yana-response.md`
* Add `docs/validation/pai_report_2026_05_03.md`
* Open 4 GitHub issues for Q4–Q7 (API contract, UXRS, E2E latency, ECC)

The remaining 28 Class B/C surfaces are tracked as `IERD-FOLLOWUP-*` issues — not bundled into Phase 0.
