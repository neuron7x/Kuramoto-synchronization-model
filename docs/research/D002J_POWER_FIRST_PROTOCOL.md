# D-002J — Workstream 6: Power-First Canonical Design Protocol

Pre-registration anchor: `docs/governance/D002J_PREREGISTRATION.yaml`
Plan reference: §11
Status: **SCAFFOLD** — power calculator implementation, report
artefact, and canonical-grid sign-off ship in downstream PRs
(D-002J-W6-*).
Date: 2026-05-14

> The W6 protocol exists because D-002I confirmed that the D-002H
> grid was **insufficiently powered** (median `n_min` ≈ 93 against
> the deployed `n_seeds = 20`). W6 makes that failure unrepeatable
> by gating any future D-002J canonical sweep behind an explicit
> power report.

---

## §11 — Mandatory metrics

Every D-002J canonical sweep proposal MUST emit a power report
carrying all of:

- **`minimal_detectable_effect`** — the smallest effect size (per
  metric, per null) that the proposed grid can detect at the
  declared `power_target` and the declared alpha.
- **`n_min`** — the minimum sample / seed / bootstrap budget that
  satisfies `power_target`. Quoted per substrate, per metric, per
  null model.
- **`power_target`** — pre-committed scalar; the D-002J floor is
  `0.8` (one-sided). Proposals with `power_target < 0.8` are
  REJECTED at the W6 gate.
- **`runtime_budget`** — explicit wall-clock budget (seconds) for
  the full canonical sweep. Proposals whose `n_min × per-cell-cost`
  exceeds the budget are REJECTED at the W6 gate.
- **`false_negative_risk`** — explicit β = 1 − power_target.
  Quoted alongside `power_target` to make the trade-off legible.
- **`metric_specific_power`** — per-metric power table. A grid
  cell that is powered for ONE metric but underpowered for the
  conjunction (e.g. R1 ∧ R2 ∧ R3) is NOT a powered cell.
- **`null_specific_power`** — per-null power table. A grid cell
  that is powered against ONE null but underpowered against
  another N1..N9 null is NOT a powered cell.

---

## §11 — Hard gates

The W6 gate is fail-closed. A D-002J canonical sweep authorisation
artefact CANNOT be emitted unless ALL of the following hold:

1. **Power report exists** — emitted by a downstream W6
   implementation PR, sha-pinned in the authorisation artefact.
2. **No-majority-underpowered** — strictly less than 50% of the
   declared canonical grid cells are flagged as underpowered.
   A grid where the majority of cells are underpowered is
   structurally invalid under the W6 contract.
3. **Explicit runtime budget** — `runtime_budget` is declared
   AND the projected runtime under `n_min` is ≤ `runtime_budget`.
4. **Explicit false-negative risk** — `false_negative_risk` is
   declared (NOT inferred). A missing β makes the report
   non-falsifiable at the W6 gate.
5. **Predeclared stopping rule** — the report MUST declare a
   stopping rule BEFORE the sweep starts. Permitted rules:
   - "stop at fixed `n_min` per cell" (no early termination);
   - "stop at pre-declared alpha-spending boundary" with the
     boundary defined.
   Forbidden: "stop when significance is reached" (this is the
   garden-of-forking-paths failure mode the protocol exists to
   prevent).

---

## §11 — Relationship to W5 null hierarchy

The W6 power report MUST cross-reference the W5 null hierarchy:

- For each W4 substrate × W5 null pair, the report MUST state
  whether the cell is powered AT THE NULL-SPECIFIC POWER FLOOR.
- A cell whose `null_specific_power` falls below `power_target`
  for ANY admissible null in the W5 hierarchy is NOT a powered
  cell. The cell may still be RUN, but its result is descriptive
  only and CANNOT be promoted under W7 claim ledger discipline.

---

## §11 — Relationship to W3 positive controls

The W6 protocol BLOCKS canonical-sweep authorisation unless the
W3 positive-control battery has DETECTED its planted signal under
the same null hierarchy:

- `planted_precrisis_synchronisation` → detected by ≥ 1 metric at
  power ≥ `power_target` against ≥ 1 null in W5.
- `planted_liquidity_contagion` → same contract.
- `planted_repo_haircut_spiral` → same contract.
- `planted_network_concentration_shock` → same contract.

If ANY of the four planted positive controls fails to detect its
planted signal under the W6 gate, the W6 authorisation is REFUSED.
This makes positive-control survival a hard prerequisite for any
real-data interpretation, mirroring the discipline declared in
`D002J_PREREGISTRATION.yaml` `allowed_claims`.

---

## §11 — Relationship to D-002H failure mode

The D-002H REFUSED verdict (PR #692, merge sha `669d4458`) carried
two operative failure axes per the D-002I diagnosis:

- **H_I3 CONFIRMED** — signal was genuinely sub-threshold.
- **insufficient grid power** — `n_seeds = 20` against median
  `n_min ≈ 93`.

The W6 protocol closes the second axis structurally: a D-002J
proposal that re-creates the D-002H mistake (`n_seeds = 20` when
median `n_min` indicates ≥ 90) is REFUSED at the W6 gate by
construction.

The W6 protocol does **NOT** close the first axis — sub-threshold
signal is closed by the W4 (financial-mechanistic substrates) and
W3 (positive controls) discipline, NOT by power analysis. W6 is
necessary but not sufficient.

---

## §11 — Stopping-rule discipline

The protocol pre-commits to the following stopping-rule shape for
any D-002J canonical sweep proposal:

```
stopping_rule:
  type: "fixed_n_min_per_cell"      # OR "alpha_spending_with_boundary"
  fixed_n_min_per_cell: <int>       # if type == fixed_n_min_per_cell
  alpha_spending:
    boundary: "OBrien-Fleming"      # or "Pocock"; document choice
    n_looks: <int>                  # if type == alpha_spending
    alpha_total: 0.05               # canonical D-002J alpha
```

Any deviation from this shape at canonical-sweep time constitutes
a fresh D-002K pre-registration.

---

## Forbidden interpretations (global)

This protocol, in its present scaffold form, does **NOT**
constitute:

- a claim that a W6 power calculator has been implemented,
- a claim that a W6 power report has been emitted,
- a claim that the D-002J canonical grid has been authorised
  (it has NOT — see `canonical_run_authorized: false` in
  `D002J_PREREGISTRATION.yaml`),
- a claim that D-002J has run any sweep.

---

## Lock anchors

This scaffold inherits the locked-governance anchors recorded in
`docs/governance/D002J_PREREGISTRATION.yaml` `locked_anchors`. Any
edit to the mandatory metrics list, the hard gates list, or the
stopping-rule shape constitutes a fresh D-002K pre-registration,
not a patch.
