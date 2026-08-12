# AESVP-2026 Hardening Requirements — GeoSync

**Status:** required hardening plan for stronger audit defensibility  
**Parent valuation record:** `docs/audit/AESVP_2026_VALUATION_APPENDIX.md`  
**Validation rationale:** `docs/audit/AESVP_2026_VALIDATION_RATIONALE.md`  
**Machine record:** `artifacts/audit/aesvp_2026_valuation_summary.json`

This document defines the remaining work required to move the AESVP-2026 valuation package from a medium-confidence internal engineering valuation record toward a high-confidence independently reproducible audit package.

The target is not “unfalsifiable.” The target is **reproducible, externally reviewable, falsification-resistant, and claim-boundary safe**.

---

## 1. Current defensibility level

| Area | Current status | Reason |
| --- | --- | --- |
| Numeric valuation record | Strong | Central values exist in both markdown and JSON. |
| Formula disclosure | Strong | Replacement cost, AQI, debt discount, scenarios, and blockers are explicit. |
| Claim boundary | Strong | Sale price, revenue value, startup valuation, and official accounting capitalization are excluded. |
| Machine-readable evidence | Good | JSON summary exists as numeric SSOT. |
| Independent reproducibility | Partial | Command log exists upstream, but a standalone reproduction capsule is not yet complete in this PR. |
| Generated/vendor classification | Partial | Source SLOC may include generated/vendor-like surfaces unless classified. |
| External rate validation | Partial | Labor-rate scenarios are declared assumptions, not externally benchmarked in-repo. |
| Accounting traceability | Partial | Candidate capitalization is engineering-only; no ASC-style stage ledger exists. |
| CI validation | Partial | PR body still says no tests; no schema consistency gate yet validates markdown/JSON alignment. |
| Technical debt | Fail/Partial | G10 fails because 811 functions exceed complexity 10. |

---

## 2. Required hardening artifacts

| Priority | Artifact | Path | Purpose | Acceptance condition |
| --- | --- | --- | --- | --- |
| P0 | Reproduction capsule | `artifacts/audit/aesvp_2026_reproduction_manifest.json` | Bind commit, commands, tool versions, outputs, and artifact hashes. | Contains measured commit, branch, timestamp, dirty-state, commands, output paths, SHA-256 for each artifact. |
| P0 | Markdown/JSON consistency checker | `tools/audit/check_aesvp_valuation_record.py` | Prevent drift between human appendix and JSON SSOT. | Exits non-zero if central TCAV, SLOC, AQI, debt, or scenario values diverge. |
| P0 | CI gate | `.github/workflows/aesvp-valuation-record.yml` | Make valuation record machine-checked in PRs. | Runs checker on PR and blocks mismatch. |
| P0 | Generated/vendor classifier | `artifacts/audit/aesvp_2026_sloc_classification.json` | Separate authored source, generated source, vendored code, data, docs, configs. | Every high-volume path class has explicit classification and inclusion/exclusion rationale. |
| P0 | Dirty-state disclosure | `artifacts/audit/aesvp_2026_git_state.txt` | Preserve `git status --porcelain` and audit-time mutation state. | Records modified/untracked files and whether each affects valuation. |
| P1 | Rate-card rationale | `docs/audit/AESVP_2026_RATE_CARD_RATIONALE.md` | Justify $90/$120/$150 labor-rate scenarios. | Lists role assumptions, rate basis, and why values are scenario parameters. |
| P1 | Accounting-stage ledger | `artifacts/audit/aesvp_2026_accounting_stage_ledger.json` | Support or block capitalization candidates with line-item stage mapping. | Each surface is Research / Development / Verification / Security / Governance / Maintenance with evidence and blocker. |
| P1 | Complexity hotspot ledger | `artifacts/audit/aesvp_2026_complexity_hotspots.json` | Make G10 failure concrete and remediable. | Top complexity functions include path, line, score, risk, remediation class, waiver status. |
| P1 | Evidence-class schema | `schemas/audit/aesvp_valuation_summary.schema.json` | Validate JSON structure. | JSON summary validates against schema. |
| P2 | External review packet | `EXTERNAL_REVIEW_PACKET/AESVP_2026_REVIEW_BRIEF.md` | Provide reviewer-facing minimal packet. | Includes claim boundary, commands, artifacts, formulas, falsifiers, and review checklist. |

---

## 3. Minimum gate to claim high-confidence internal audit record

The valuation package may be upgraded from **Medium** to **High internal confidence** only if all P0 items are complete.

| Requirement | Required status |
| --- | --- |
| Markdown/JSON consistency checker | PASS |
| CI gate for valuation record | PASS |
| Reproduction manifest | PRESENT and hash-complete |
| Generated/vendor classifier | PRESENT and materially reviewed |
| Dirty-state disclosure | PRESENT and non-ambiguous |
| Central TCAV reproducible from JSON inputs | PASS |
| Claim boundary unchanged | PASS |
| `Φ_RMD_verified` remains `$0` unless risk register is present | PASS |

---

## 4. Minimum gate to claim external-review readiness

External-review readiness requires all P0 and P1 items.

| Requirement | Why it matters |
| --- | --- |
| Rate-card rationale | Prevents labor-rate assumptions from being attacked as arbitrary. |
| Accounting-stage ledger | Prevents the capitalization candidate from looking like accounting fiction, humanity’s favorite spreadsheet disease. |
| Complexity hotspot ledger | Converts G10 failure into an explicit remediation surface. |
| JSON schema | Makes machine-readable evidence stable across future changes. |
| CI gate | Prevents silent numeric drift. |

---

## 5. Non-negotiable falsification rules

The valuation package must be downgraded or invalidated if any condition is true:

1. The central TCAV differs between markdown and JSON.
2. The measured commit cannot be reproduced.
3. Source SLOC includes generated/vendor material without classification.
4. A sale-price, revenue-value, startup-valuation, or official capitalization claim is attached to this record.
5. A verified risk dividend is introduced without a signed probability/loss register.
6. The PR claims tests passed without a fresh CI or local verification artifact.
7. G10 is marked Pass while complexity-over-10 functions remain unresolved or waived without evidence.

---

## 6. Recommended next PR split

| PR | Scope | Files |
| --- | --- | --- |
| PR-A | Schema + consistency gate | `schemas/audit/aesvp_valuation_summary.schema.json`, `tools/audit/check_aesvp_valuation_record.py`, `.github/workflows/aesvp-valuation-record.yml` |
| PR-B | Reproduction capsule | `artifacts/audit/aesvp_2026_reproduction_manifest.json`, `artifacts/audit/aesvp_2026_git_state.txt`, hash manifest |
| PR-C | SLOC classification | `artifacts/audit/aesvp_2026_sloc_classification.json`, generated/vendor policy note |
| PR-D | External-review packet | `EXTERNAL_REVIEW_PACKET/AESVP_2026_REVIEW_BRIEF.md`, reviewer checklist |
| PR-E | Accounting/rate rationale | `docs/audit/AESVP_2026_RATE_CARD_RATIONALE.md`, `artifacts/audit/aesvp_2026_accounting_stage_ledger.json` |

---

## 7. Final hardening verdict

The current PR is acceptable as a **medium-confidence valuation evidence package**. To make it hard to refute in serious review, the next required layer is not more prose. The next layer is machine verification: reproduction manifest, schema validation, markdown/JSON consistency gate, generated/vendor classification, and CI enforcement.

Until those are present, the correct claim is:

> GeoSync has a medium-confidence AESVP-2026 engineering valuation record with disclosed formulas, measured repository metrics, machine-readable summary, and explicit falsification rules.

After P0 completion, the claim may become:

> GeoSync has a high-confidence internally reproducible AESVP-2026 engineering valuation package for the measured repository snapshot.
