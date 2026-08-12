# AESVP-2026 Validation Rationale — GeoSync

**Status:** supporting validation rationale  
**Parent record:** `docs/audit/AESVP_2026_VALUATION_APPENDIX.md`  
**Machine record:** `artifacts/audit/aesvp_2026_valuation_summary.json`  
**Repository:** `neuron7xLab/GeoSync`  
**Measured commit:** `2d2f638f6db1e4ab6d6b4928da3ac3564920a5f3`  
**Audit timestamp:** `2026-06-04T08:05:53Z` UTC

This file explains why the AESVP-2026 valuation record is admissible as an engineering work-product valuation artifact, what evidence supports it, and what claims remain blocked. It does not expand the valuation into sale price, revenue value, official accounting value, or strategic premium.

---

## 1. Evidence taxonomy

| Evidence class | Meaning | Examples in this audit | Valuation use |
| --- | --- | --- | --- |
| Measured fact | Directly collected from the checked-out repository snapshot. | `tracked_files`, `source_sloc`, `python_functions`, `test files`, `branch_nodes`, `complexity_over_10_count`. | May enter formulas directly. |
| Derived metric | Computed deterministically from measured facts. | `source_ksloc`, `D_idx`, `V_bounds`, `C_inv`, `Ψ_AQI`, debt factors. | May enter formulas if inputs are disclosed. |
| Declared assumption | Protocol parameter selected before/inside the valuation model. | `A = 2.94`, `H_pm = 152`, labor-rate scenarios, EM scenarios, scale factors. | May enter scenario models only. |
| Blocked claim | A stronger claim lacking evidence in this snapshot. | Official capitalization, sale value, revenue value, verified risk-mitigation dividend. | Must not enter central valuation. |
| Falsifier | Condition that invalidates or downgrades the record. | Non-reproducible metrics, undisclosed generated/vendor SLOC, markdown/JSON divergence. | Must be preserved. |

---

## 2. Why the repository has material engineering mass

The valuation is not based on narrative claims. It is anchored to repository-scale measurements:

| Measurement | Value | Rationale |
| --- | ---: | --- |
| Tracked files | 5,360 | Indicates broad repository surface rather than a small proof-of-concept. |
| Source SLOC | 582,058 | Primary size driver for replacement-cost modeling. |
| Python SLOC | 552,036 | Confirms that most measured source mass is Python implementation surface. |
| Python functions | 32,497 | Indicates high implementation granularity and review burden. |
| Python test files | 1,484 | Supports the claim that verification work exists as code, not only prose. |
| Assert statements | 29,860 | Strong signal of executable checks across the tree. |
| CI workflows | 27 | Supports integration/governance overhead in rebuild cost. |
| Security workflows | 15 | Supports dedicated security and compliance surface. |
| Audit/governance artifacts | 378 | Supports non-trivial audit traceability work. |
| Claims/evidence artifacts | 205 | Supports claim-boundary and evidence-management maturity. |

**Inference:** the measured state is a multi-surface engineering artifact: source code, tests, CI, security, governance, audit records, claims/evidence files, and documentation. A valuation that counts only runtime source would understate the actual work product; a valuation that treats every line as production-grade would overstate it.

---

## 3. Why the central AESVP TCAV is formula-admissible

The central AESVP value is admissible only under the declared model boundary:

```text
V_RC = A × KSLOC_equ^E × EM × H_pm × R_labor
TCAV = (V_RC × Ψ_AQI) + Φ_RMD_verified - Ω_TDB
```

| Component | Central value | Evidence status | Comment |
| --- | ---: | --- | --- |
| `KSLOC_equ` | 582.058 | Measured | Direct source-size input. |
| `E` | 1.1138 | Derived from declared scale factors | Explicit exponent, not hidden multiplier. |
| `EM` | 1.00 | Scenario assumption | Neutral central multiplier. |
| `R_labor` | $120/hour | Scenario assumption | Senior US engineering-rate scenario. |
| `V_RC` | $64,415,679 | Formula-derived | Replacement-cost contour before quality/debt adjustment. |
| `Ψ_AQI` | 0.734780376084 | Derived | Reduces value for low invariant/property-test density. |
| `Φ_RMD_verified` | $0 | Blocked | No verified incident-risk register included. |
| `Ω_TDB` | $2,111,143 | Derived | Explicit technical-debt discount. |
| `TCAV_central` | $45,220,234 | Formula-derived | Central engineering work-product valuation. |

**Validation argument:** the value is not a free-form appraisal. It is a deterministic output of disclosed inputs. The calculation is valid as a protocol-bound engineering estimate, not as an official financial reporting value.

---

## 4. Why the practical rebuild model is lower than AESVP TCAV

| Model | Value | Why it is lower/higher |
| --- | ---: | --- |
| Lean rebuild | $646,304 | Counts useful core reconstruction only; excludes full audit/governance/documentation mass. |
| Enterprise rebuild | $2,789,200 | Counts core, tests, CI, audit, and docs using staffing logic. |
| Full tracked-tree reconstruction | $6,116,480 | Counts all tracked surfaces, still assumes competent rebuild rather than formulaic full-source effort. |
| AESVP central TCAV | $45,220,234 | Uses KSLOC-driven COCOMO-style expansion and quality/debt transforms. |

**Interpretation:** these models answer different questions. Practical rebuild estimates a realistic team path. AESVP TCAV estimates protocol-bound engineering work-product mass from full repository scale. The difference is not an error if both are kept in separate columns and not mixed into a sale-price claim.

---

## 5. Validity constraints

| Constraint | Current status | Effect |
| --- | --- | --- |
| Metrics are tied to a measured commit | Satisfied | Snapshot is auditable. |
| Scope is declared as `git ls-files` | Satisfied | File-selection boundary is explicit. |
| Formula inputs are disclosed | Satisfied | Calculation is reviewable. |
| Risk dividend is verified | Not satisfied | Central `Φ_RMD` remains `$0`. |
| Generated/vendor classification is complete | Not satisfied | Confidence capped at Medium. |
| Accounting-stage ledger exists | Not satisfied | Official capitalization claim blocked. |
| G10 technical debt control passes | Not satisfied | Premium-compliance claim blocked. |
| Markdown and JSON agree | Required | Divergence falsifies the record. |

---

## 6. Why stronger claims are blocked

| Blocked claim | Reason |
| --- | --- |
| Official US-GAAP capitalization | No full accounting-stage ledger, owner approval, time records, or management intent evidence included. |
| Revenue-grade valuation | No revenue model, customer contracts, realized revenue, or market transaction evidence included. |
| Sale price / startup valuation | No buyer, market comparable, IP transfer terms, revenue, or strategic premium basis included. |
| Fully premium AESVP compliance | G10 fails because 811 functions exceed estimated McCabe complexity 10; several gates remain Partial. |
| Verified risk-mitigation dividend | No verified incident probability/loss register is included. |
| Current-branch guarantee | Record applies only to the measured commit and timestamp. |

---

## 7. Evidence-to-claim mapping

| Claim | Supporting evidence | Counterweight / limitation | Supported wording |
| --- | --- | --- | --- |
| Repository has material engineering mass. | 5,360 tracked files, 582,058 source SLOC, 32,497 Python functions. | Generated/vendor classification unresolved. | Supported. |
| Repository has executable verification surface. | 1,484 Python test files, 150 property-test files, 29,860 asserts. | Property-test density remains low. | Supported with limitation. |
| Repository has audit/governance surface. | 378 audit/governance artifacts, 205 claims/evidence artifacts. | Not all governance content maps to capitalizable software. | Supported with limitation. |
| Central AESVP TCAV is $45,220,234. | Disclosed formula and inputs. | Protocol-bound estimate only. | Supported as AESVP engineering TCAV. |
| Official accounting value is $1,213,302. | None. | Candidate only, not official. | Not supported. |
| Practical enterprise rebuild is $2,789,200. | Staffing cross-check model. | Not a market price. | Supported as practical rebuild estimate. |

---

## 8. Review checklist

A reviewer should accept this valuation record only if all checks below pass:

- [ ] The measured commit exists and matches the recorded SHA.
- [ ] The metrics were produced from tracked files, not a hand-picked subset.
- [ ] The markdown appendix and JSON summary contain the same central numeric values.
- [ ] `Φ_RMD_verified` remains `$0` unless a risk register is added.
- [ ] Generated/vendor code is either disclosed or excluded in a future revision.
- [ ] Official capitalization language remains excluded.
- [ ] Practical rebuild values are not merged into AESVP TCAV.
- [ ] G10 remains visible as Fail until complexity remediation evidence exists.

---

## 9. Final validation statement

The AESVP-2026 record is valid as a **medium-confidence, formula-bound engineering work-product replacement-cost assessment** for the measured GeoSync snapshot. The supported central result is **$45,220,234 AESVP engineering TCAV**. The record is not valid as product sale price, revenue valuation, official capitalization, or proof of fully premium compliance.