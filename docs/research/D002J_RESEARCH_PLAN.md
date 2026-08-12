# D-002J — Financial Mechanistic Substrate Benchmark (research plan)

Project: GeoSync
Direction: systemic risk, financial networks, null-model validation, crisis-window detectability
Status: research continuation plan (pre-registered)
Date: 2026-05-14

> D-002J opens a fresh pre-registration lineage AFTER D-002H closed
> REFUSED (PR #692, sha `669d4458`) and D-002I (investigation lineage,
> PR #693, sha `2e55b73a`) was opened. D-002J does NOT rescue D-002H —
> D-002H REFUSED stays the truthful canonical verdict.

Goal: move from weak `ricci_flow` signal to research-grade benchmark
lineage on financially motivated substrates, real crisis windows,
positive controls, strong null models, power-first design.

---

## §1 — Justification

D-002H REFUSED_NULL_AUDIT_FAIL; D-002I diagnosis showed sub-threshold
signal + insufficient grid power (n_seeds=20, median n_min≈93, H_I3
CONFIRMED, H_I1/H_I4 REJECTED, H_I2 UNKNOWN due to M3 audit gap).
Conclusion: do NOT rescue `ricci_flow` post-hoc — open new lineage with
substrates that carry direct financial mechanics.

## §2 — Central goal

Build GeoSync as benchmark engine for financial systemic-risk
mechanisms:

> financial substrate → crisis window → mechanistic signal → null
> hierarchy → power analysis → canonical run → claim ledger.

Do not prove a chosen hypothesis. Do not tune parameters. Do not
"rescue" negative results. Build a system where only signal that
survives null models + power analysis + crisis-grounded validation
survives.

## §3 — Central thesis

Financial systemic-risk signal must be sought in mechanisms with
economic causality (repo collateral chains, liquidity rollover stress,
interbank exposure concentration, haircut shock propagation,
rehypothecation loops, funding maturity mismatch, market-wide
deleveraging, crisis-window synchronisation). If signal exists, it
manifests as detectable deviation from strong nulls inside known
stress windows.

## §4 — Research questions (locked at pre-registration)

| ID  | Question |
|-----|----------|
| RQ1 | Can financially motivated substrates yield stronger signal/null separation than `ricci_flow`? |
| RQ2 | Does detectable precursor signal emerge before real crisis windows? |
| RQ3 | Which null models best kill false signal? |
| RQ4 | What minimum sample/seed/bootstrap/shuffle budget yields power ≥ 0.8? |
| RQ5 | Can we build a reproducible benchmark where negative results carry equal value to positive ones? |

## §5 — Architecture (7 workstreams)

| ID | Name | Plan section | Scaffold doc (this PR) |
|----|------|--------------|-------------------------|
| W1 | Data Source Matrix              | §6  | `docs/research/D002J_DATA_SOURCE_MATRIX.md` |
| W2 | Crisis Window Registry          | §7  | `docs/research/D002J_CRISIS_WINDOW_REGISTRY.md` |
| W3 | Synthetic Positive Controls     | §8  | (downstream PR) |
| W4 | Financial Mechanistic Substrates| §9  | (downstream PR) |
| W5 | Null Model Hierarchy            | §10 | `docs/research/D002J_NULL_MODEL_HIERARCHY.md` |
| W6 | Power-First Canonical Design    | §11 | `docs/research/D002J_POWER_FIRST_PROTOCOL.md` |
| W7 | Benchmark Package               | §12 | (downstream PR) |

## §6 — Workstream 1: Data Source Matrix

Sources (initial set, expanded in `D002J_DATA_SOURCE_MATRIX.md`):

- BIS banking statistics
- FRED / ALFRED
- OFR / repo / short-term funding
- ECB money-market / secured funding literature
- public bank balance-sheet proxies
- public crisis timelines
- rates / FX / liquidity stress indicators

Acceptance: each source has provenance, license boundary, coverage
window, frequency, known limitations.

## §7 — Workstream 2: Crisis Window Registry

Initial set:

- 2007–2009 GFC
- 2011–2012 Eurozone Sovereign
- 2019 US Repo Spike
- 2020 COVID Dash-for-Cash
- 2022 UK Gilt / LDI
- 2023 Regional Banking Stress

Each window: `start_date`, `end_date`, justification, observable
stress indicators, related data sources, forbidden interpretations.

## §8 — Workstream 3: Synthetic Positive Controls

Substrates:

- `planted_precrisis_synchronisation`
- `planted_liquidity_contagion`
- `planted_repo_haircut_spiral`
- `planted_network_concentration_shock`

Acceptance: known effect size, known onset time, known null
expectation, known topology, known failure mode; pipeline detects
planted signal AND refuses corrupted positive control.

## §9 — Workstream 4: Financial Mechanistic Substrates

Candidates:

- `repo_collateral_haircut_network`
- `rehypothecation_chain`
- `liquidity_rollover_stress`
- `DebtRank_contagion`
- `interbank_exposure_reconstruction`
- `Barabasi_balance_sheet_constrained`
- `FX_rates_shock_propagation`

Acceptance: explicit economic mechanism; interpretable parameters;
null-admissibility testable; failure modes predeclared; NO substrate
is promoted without positive-control survival.

## §10 — Workstream 5: Null Model Hierarchy

Models:

- `degree_preserving`
- `weight_preserving`
- `temporal_block_bootstrap`
- `window_shift_placebo`
- `label_permutation`
- `configuration_model`
- `sparse_maximum_entropy_reconstruction`
- `shock_time_placebo`
- `IAAFT_surrogate`

Acceptance: each null has a concrete failure target; the null does
NOT destroy invariants it should preserve; non-trivial; deterministic
replay; documented invalid conditions.

## §11 — Workstream 6: Power-First Canonical Design

Mandatory metrics:

- `minimal_detectable_effect`
- `n_min`
- `power_target` ≥ 0.8
- `runtime_budget`
- `false_negative_risk`
- `metric_specific_power`
- `null_specific_power`

Hard gate: NO canonical run without a power report; NO grid with a
majority of underpowered cells; explicit runtime budget; explicit
false-negative risk; predeclared stopping rule.

## §12 — Workstream 7: Benchmark Package

Documents to ship (in downstream PRs, not this one):

- `README_RESEARCH`
- `DATA_CARD`
- `MODEL_CARD`
- `BENCHMARK_CARD`
- `NEGATIVE_RESULTS`
- `REPRODUCE`
- `LEADERBOARD`
- `CLAIM_LEDGER`

Required content: research question, data sources, substrates, null
models, positive controls, crisis windows, power design, results,
negative results, claim boundaries, reproduction commands.

Acceptance: one-command reproduction; deterministic outputs; no
hidden data dependency; no unbounded claim; negative results
preserved; an external reader understands the benchmark without
reading 20 PRs.

## §13 — Main line

D-002J = Financial Mechanistic Substrate Benchmark.

Focus: repo collateral; liquidity contagion; funding stress;
interbank exposure; crisis-window detectability.

D-002J is **NOT** a `ricci_flow` rescue. The new lineage opens
AFTER the honestly-preserved D-002H negative result.

## §14 — Forbidden claims

The following claims are pre-emptively out of scope under D-002J:

- "D-002J rescues D-002H"
- "D-002J invalidates D-002H REFUSED"
- "D-002J proves systemic-risk prediction"
- "D-002J claims real-bank validation without real-bank data"
- "D-002J generalises across substrates without evidence"
- "D-002J promotes positive controls as real-world proof"
- "D-002J allows post-hoc parameter tuning"

## §15 — Allowed claims

The following claims are permitted within D-002J scope:

- "D-002J builds a financial-mechanistic benchmark lineage"
- "D-002J tests whether financially motivated substrates improve signal/null separation"
- "D-002J uses crisis windows as external stress anchors"
- "D-002J requires positive controls before real-data interpretation"
- "D-002J requires power-first design before canonical sweep"
- "D-002J treats negative results as retained evidence"

## §16 — Success criteria (10)

1. source registry assembled
2. crisis-window registry created
3. known-positive controls created
4. ≥ 2 financial-mechanistic substrates implemented
5. null hierarchy implemented
6. power-first design executed
7. canonical run only after power approval
8. all results → append-only ledger
9. benchmark reproducible by one command
10. external reader sees research-grade system, not chaos of PRs

## §17 — Failure criteria

- positive controls undetected
- null models trivial / no-op
- majority of grid cells underpowered
- signal survives only after post-hoc tuning
- crisis-window labels ambiguous
- data provenance incomplete
- claims exceed boundary
- negative results hidden / off-ledger

## §18 — Expected result framing

Build a system where any result carries weight:

- Positive → survives strong nulls + power design.
- Negative → retained as bounded evidence.
- Null result → informs substrate/model redesign.
- Failure → becomes guardrail.

## §19 — Canonical formula

> real data + crisis windows + planted positive controls +
> mechanistic substrates + null hierarchy + power-first design +
> deterministic CI + claim ledger = research-grade systemic-risk
> benchmark.

## §20 — Official decision

OPEN D-002J. Primary objective: build a research-grade benchmark
lineage that tests financial systemic-risk mechanisms using real
data sources, crisis windows, planted positive controls, strong null
models, power-first canonical design, deterministic reproducibility,
and append-only claim governance.

## §21 — First-PR scope

This PR (`docs/x10r-d002j-financial-benchmark-prereg`). Files shipped
in this PR are listed under `first_pr_files` in
`docs/governance/D002J_PREREGISTRATION.yaml`. NO source code edits;
NO artifact JSON edits beyond the new D-002J prereg lock; NO D-002H
verdict edits; NO D-002I edits; NO D-002C/G/H ledger or prereg edits.

## §22 — Final framing

D-002J turns GeoSync from a system that checks one substrate
hypothesis into a reproducible research bench for financial
systemic-risk mechanisms. The goal is NOT to avoid falsification —
the goal is to build data, null, power, and governance quality such
that falsification becomes the main source of scientific power, not
a destruction of work.

---

## Lineage chain

```
D-002G  (structural closure, merge sha 8cf5364a, PR #682)
  └── D-002H  (ricci_flow canonical sweep REFUSED, merge sha 669d4458, PR #692)
        ├── D-002I  (investigation lineage, merge sha 2e55b73a, PR #693)
        │           — locks H_I1..H_I4 around the D-002H REFUSED axes;
        │           — investigation only; never rewrites D-002H REFUSED.
        └── D-002J  (this lineage — financial-mechanistic benchmark)
                    — opens fresh substrate / null / power / crisis-window
                      research bench; never rescues D-002H.
```

## Locked-anchor cryptographic identities (read-only at this PR)

| File | sha256 |
|------|--------|
| `docs/governance/D002G_PREREGISTRATION.yaml`        | `1ab91f09370e4705a8b0849467bc1f56df2e58d58d5623d3b6d905cbd110bb04` |
| `docs/governance/D002G_ACCEPTANCE_RULES.md`         | `875b1e3eb031b8e5333dc8b455454f0a30419ead1ebe787aa01d5882e7d6ad31` |
| `docs/governance/D002H_PREREGISTRATION.yaml`        | `44b18b5a40ce9d188a9c3bd49339621f81a65a15f97a683247902450dd54acec` |
| `docs/governance/D002C_CLAIM_LEDGER.yaml`           | `eb0b7151d76e5409e6dc9bb4a023551de5e0704673d5ac9f726319ef84a32387` |

All four remain byte-exact at their pinned values across the D-002J
pre-registration PR.
