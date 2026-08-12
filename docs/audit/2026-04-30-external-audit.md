# 2026-04-30 External Audit — Verdict & Repair Trace

> **Source.** Independent external audit of the `neuron7xLab/GeoSync` repository
> conducted on 2026-04-30. Verdict (verbatim): **FAIL** — current top-level
> claim of "verified physical system" is not supported.
>
> **Refined classification (verbatim):** *"PROMISING BUT UNPROVEN
> research-code platform with strong audit/governance ambitions, mixed
> scientific grounding, and several severe overclaims."*

This file preserves the audit-traceability link from every repaired
artefact back to the specific finding it addresses, and from each
finding to the change that closed it (or to the open backlog row that
will close it). The PR that introduces this file (`fix/audit-overclaim-repair`)
is the first remediation pass; subsequent passes append below.

---

## S5 findings (load-bearing claims fail)

| # | Finding | Repair in this PR | Backlog |
|---|---------|-------------------|---------|
| S5.1 | Top-level "verified physical system" claim unsupported | `README.md` rewritten to "physics-inspired quantitative research platform with a partially machine-checkable invariant layer"; `CLAIMS.md` records retirement `R-VERIFIED-PHYS` | – |
| S5.2 | Market "energy / momentum conservation" is a category error (no proven `volume → mass` mapping; VWAP-residual term collapses to zero) | `core/physics/conservation.py` renamed: `compute_market_energy → compute_volatility_energy_proxy`, `compute_market_momentum → compute_flow_momentum_proxy`, `check_*_conservation → check_proxy_drift`. Old names retained as deprecated aliases (zero behaviour change). Module docstring states the demotion explicitly. `__init__.py` exports both name sets. `CLAIMS.md` records retirement `R-MARKET-CONS` | Migrate in-tree call sites (`backtest/physics_validation.py`, `core/indicators/physics.py`) to canonical names; flip ruff to fail-closed on the deprecated names |

## S4 findings (claims exceed evidence tier)

| # | Finding | Repair in this PR | Backlog |
|---|---------|-------------------|---------|
| S4.1 | Criticality / phase-transition claims under-tested (no finite-size scaling, no scaling collapse, no null-model rejection at gate level) | `CLAIMS.md` retirement `R-CRITICALITY`; `ALTERNATIVE_HYPOTHESES.md` H5 ("Threshold artefacts") describes the required FSS battery | Implement `experiments/criticality_fss/` for `N ∈ {8,16,32,64,128}` and gate via `claims-evidence-gate.yml` |
| S4.2 | README OOS "+78% alpha vs equal-weight, drawdown -53%" not backed by signed audit artefact | README headline replaced with "claim retracted pending signed audit artefact"; `CLAIMS.md` retirement `R-OOS-78`; `scripts/build_verification_report.py` scaffolds the artefact path that must contain provenance / cost model / null models before any re-emission | Run real walk-forward / purged-CV / cost-model audit and emit signed `artifacts/audit/SCIENTIFIC_VERIFICATION_REPORT.json` |
| S4.3 | Invariant counts conflict (`57 / 66 / 67 / 87` across same repo) | `scripts/count_invariants.py` is single source of truth; `scripts/check_invariant_count_sync.py` is fail-closed CI gate; README, BASELINE.md, CLAUDE.md headers reconciled to authoritative count of **87** | – |

## S3 findings (silent repair / partial coverage)

| # | Finding | Repair in this PR | Backlog |
|---|---------|-------------------|---------|
| S3.1 | `kuramoto_order()` clipping `R` to `[0, 1]` can mask invariant violations | – | Audit `core/kuramoto/metrics.py`; ensure clip is annotated `# INV-K1: roundoff repair only` and emits a logged event on |R| > 1 + ε |
| S3.2 | `compute_phase()` `nan_to_num` can fabricate phase from missing data | – | Carry NaN masks downstream; reject silent nan→0 in non-test contexts |
| S3.3 | Falsification tools exist but are not tied to the result layer | – | Wire IAAFT / time-shuffle / surrogate p-values into `claims-evidence-gate.yml` and require Holm/BH-FDR correction on every published p-value |

## S2 findings (governance / paperwork load)

| # | Finding | Repair in this PR | Backlog |
|---|---------|-------------------|---------|
| S2.1 | CI/governance architecture large; risks "paperwork cosplay" if not fail-closed | New gates (`invariant-count-sync`, scientific-verification-report scaffold) are explicitly fail-closed; `CLAIMS.md` is single human-readable index | Periodic gate-health audit (manual) — schedule cadence TBD |

---

## Outstanding backlog index

* `experiments/criticality_fss/` — H5 finite-size-scaling battery (S4.1)
* `artifacts/audit/SCIENTIFIC_VERIFICATION_REPORT.json` first signed run (S4.2, S2.1)
* call-site migration off `compute_market_energy` / `compute_market_momentum` / `check_*_conservation` (S5.2)
* `core/kuramoto/metrics.py` clamp-traceability audit (S3.1)
* `core/kuramoto/phase_extractor.py` NaN-mask propagation (S3.2)
* falsification → result-layer wiring with Holm/BH-FDR (S3.3)

Each line above will be closed by a future PR that links back to this
document via "closes audit row Sx.y".
