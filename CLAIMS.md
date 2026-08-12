# GeoSync — Claims & Evidence Ledger

> **Single source of truth** for every quantitative claim that appears in
> user-facing documentation (README, papers, pitch decks, slide-deck
> screenshots, social posts). Each row maps a claim to its evidence tier
> per the 2026-04-30 external audit
> ([`docs/audit/2026-04-30-external-audit.md`](docs/audit/2026-04-30-external-audit.md)).

## Evidence tiers

| Tier | Meaning | Allowed in README headline |
|------|---------|----------------------------|
| `FACT` | Mathematically proven; verifiable from definitions | yes |
| `MEASURED` | Reproducible from a signed audit artefact (commit + data hash) | yes |
| `DERIVED` | Computed from `MEASURED` quantities by an explicit formula | yes |
| `SIMULATION` | Reproducible from synthetic data with declared seed | yes, prefixed "(simulation)" |
| `SYNTHETIC_DEMO` | Demo only, parameters chosen for illustration | NO — not in headline |
| `HYPOTHESIS` | Plausible, falsifiable, not yet tested | NO |
| `SPECULATIVE` | Analogy or aspirational framing | NO |
| `RETIRED` | Previously claimed, withdrawn under audit | NO; must show retraction line |

---

## Active claims

| ID | Claim | Tier | Evidence pointer | Last verified |
|----|-------|------|------------------|---------------|
| C-INV-COUNT | "132 invariants in `.claude/physics/INVARIANTS.yaml`" | `FACT` | `python scripts/count_invariants.py` | 2026-06-25 |
| C-PHYS-KERNEL | "Physics-inspired research platform with partially machine-checkable invariant layer" | `MEASURED` | `physics-kernel-gate.yml`, `BASELINE.md` | 2026-04-30 |
| C-TLA-PROOF | "Four-barrier admission gate model-checked in TLA⁺ with 3 invariants" | `FACT` | `formal/tla/AdmissionGate.tla`, `formal-verification.yml` | 2026-04-30 |
| C-SYSRISK-PHASE | "Interbank phase-locking precedes banking-crisis events" | `HYPOTHESIS` | `research/systemic_risk/falsification.py` v2: pre-registered Mann-Whitney AUC with stratified percentile-bootstrap CI (n=10000) + one-sided permutation p + Bonferroni FWER. `HARD_PASS` requires `auc_ci_low` ≥ 0.70 AND `p_BONF` ≤ 0.01 on ≥ 2 crises; `HARD_FAIL` if any AUC ≤ 0.55 OR any `auc_ci_low` ≤ 0.5. Asymmetric directed coupling via `coupling_from_exposures`; BA null calibrated by MLE per `fit_barabasi_albert` (Clauset-Shalizi-Newman 2009, *SIAM Rev.* 51: 661). `research/systemic_risk/README.md` | 2026-05-08 |
| C-EPI-RHOMBUS | "Epistemic Rhombus manifest maps 4 governance criteria to schema-validated external gates" | `FACT` | `python scripts/validate_epistemic_rhombus_manifest.py`, `.github/workflows/epistemic-rhombus-gate.yml`, and `tests/scripts/test_validate_epistemic_rhombus_manifest.py` validate `governance/epistemic_rhombus_manifest.jsonl` against `schemas/governance/epistemic_rhombus_manifest.schema.json`. | 2026-06-04 |
| C-RICCI-MICROSTRUCTURE-V1 | "Ollivier-Ricci curvature on real L2 order-book microstructure may contain falsifiable signal beyond null baselines" | `HYPOTHESIS` | `ricci_microstructure_v1`; T3 / NOVEL / EXPLORATORY / FALSIFIABLE — it is NOT alpha, NOT a production system, NOT proven market physics, NOT a trading signal; it is only a falsification lane. Source is recorded honestly in `data_manifest.json` from the `ALLOWED_SOURCES` allowlist (`BINANCE_FUTURES_DEPTH` public REST depth, or `LOBSTER_LICENSED_L2`) and is NEVER relabelled; the committed substrate is real Binance USD-M depth. Falsifier is `p_value >= 0.01 OR abs(cliffs_delta) < 0.147 OR invalid schema/provenance`; allowed falsification_status values are `SUPPORTED`, `HYPOTHESIS_NOT_SUPPORTED`, `INVALID`; the canonical run is `HYPOTHESIS_NOT_SUPPORTED` and that negative result must be preserved. | 2026-06-20 |

## Retired claims (pending re-validation under tier rules)

| ID | Original claim | Retracted because | Path back to active |
|----|----------------|-------------------|---------------------|
| R-VERIFIED-PHYS | "GeoSync is a verified physical system" | Confuses analogy + simulation evidence + invariant docs with validated physical mechanism (audit S5) | Decompose into per-mechanism `MEASURED` claims, each cleared against `ALTERNATIVE_HYPOTHESES.md` H1–H6 |
| R-OOS-78 | "+78% OOS walk-forward alpha vs equal-weight, drawdown -53%" | No signed audit artefact, dataset provenance, cost model, factor-neutral baseline (audit S4) | Re-emit as `MEASURED` only after signed `artifacts/audit/SCIENTIFIC_VERIFICATION_REPORT.json` with declared `data_provenance`, `cost_model`, `null_models`, `multiple_testing_correction` |
| R-CRITICALITY | "Phase-transition / criticality detection" | Threshold crossing without finite-size scaling, susceptibility, scaling collapse (audit S4) | Implement FSS battery in `experiments/criticality_fss/` and require `H5` pass per `ALTERNATIVE_HYPOTHESES.md` |
| R-MARKET-CONS | "Market energy / momentum conservation" | Category error: no proven mapping `volume → mass`; VWAP-residual term ≈ 0 by construction (audit S5) | Already demoted in code to `*_proxy` names; documentation re-introduction would require an explicit microstructure mapping proof |

## Update protocol

1. New claim → add row in **Active claims** with tier `HYPOTHESIS`.
2. Run `experiments/<claim_slug>/` against `ALTERNATIVE_HYPOTHESES.md`
   battery; emit signed `result.json`.
3. Promote tier (`HYPOTHESIS → MEASURED` etc.) only after the
   `claims-evidence-gate.yml` workflow accepts the artefact.
4. Demoting / retracting: move the row to **Retired** with a `Retracted because` reason and a `Path back to active` requirement. Never silently delete.
