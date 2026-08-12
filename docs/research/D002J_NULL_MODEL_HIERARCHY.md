# D-002J — Workstream 5: Null Model Hierarchy

Pre-registration anchor: `docs/governance/D002J_PREREGISTRATION.yaml`
Plan reference: §10
Status: **SCAFFOLD** — implementation, eligibility verifiers, and
empirical verdicts ship in downstream PRs (D-002J-W5-*).
Date: 2026-05-14

> Each null model below targets a specific class of false-signal
> failure mode. The null ids are locked at pre-registration; renames
> or deletions require a fresh D-002K pre-registration. Additions
> are permitted in downstream PRs provided the new null carries a
> distinct failure target and the existing null ids stay byte-stable.

---

## §10 — Null-model acceptance contract

Each null model in this hierarchy MUST carry:

- **id** — short stable identifier (e.g. `N1_DEGREE_PRESERVING`).
- **target_failure_mode** — the specific class of false signal this
  null is designed to kill (e.g. degree-driven trivial correlation,
  weight-magnitude artefact, temporal autocorrelation leak).
- **preserved_invariants** — concrete substrate invariants the
  null MUST preserve (e.g. row-sum degree sequence, total weight,
  cardinality of node set).
- **valid_conditions** — pre-declared substrate / W4 cells where
  the null is admissible (does not collapse to a no-op).
- **invalid_conditions** — pre-declared substrate / W4 cells where
  the null is INADMISSIBLE (collapses, violates an invariant it
  should preserve, or trivially equals the precursor).
- **deterministic_replay** — explicit seed contract; identical
  inputs ⇒ identical null cohort (`INV-HPC1` discipline).

---

## N1 — `degree_preserving`

- **target_failure_mode**: degree-driven trivial correlation —
  signal that arises only because high-degree nodes carry more
  weight than low-degree nodes.
- **preserved_invariants**: per-node degree sequence (in- and
  out-degree for directed substrates).
- **valid_conditions**: substrates with non-degenerate degree
  variance.
- **invalid_conditions**: substrates with constant degree (e.g.
  regular lattice, complete graph) — degree shuffling is a no-op.
- **deterministic_replay**: required (locked seed offset).

## N2 — `weight_preserving`

- **target_failure_mode**: edge-weight-magnitude artefact — signal
  driven by raw weight scale rather than structural relation.
- **preserved_invariants**: multiset of edge weights (sum of edge
  weights is invariant; per-edge weight is permuted across topology).
- **valid_conditions**: substrates with non-degenerate edge-weight
  distribution.
- **invalid_conditions**: substrates with constant edge weight —
  weight shuffle is a no-op.
- **deterministic_replay**: required.

## N3 — `temporal_block_bootstrap`

- **target_failure_mode**: temporal autocorrelation leak — signal
  that emerges only because adjacent timestamps share state.
- **preserved_invariants**: marginal distribution within each block;
  block size ≥ autocorrelation scale.
- **valid_conditions**: time-series substrates with finite
  autocorrelation horizon.
- **invalid_conditions**: cross-sectional substrates (no temporal
  axis); substrates with unbounded long-memory autocorrelation.
- **deterministic_replay**: required (locked block offset and
  block-permutation seed).

## N4 — `window_shift_placebo`

- **target_failure_mode**: crisis-window-label artefact — signal
  that survives only because the analyst placed the window where
  the signal happened to be.
- **preserved_invariants**: window WIDTH; all other temporal
  structure is preserved.
- **valid_conditions**: each `CW1..CW6` crisis window from W2 —
  the null shifts the window by ±Δ days across a pre-declared
  placebo grid.
- **invalid_conditions**: windows whose ±Δ shift would overlap a
  different declared crisis window — those shifts are excluded
  from the placebo grid by construction.
- **deterministic_replay**: required.

## N5 — `label_permutation`

- **target_failure_mode**: outcome-label artefact — signal that
  arises only because the analyst attached the right label to the
  right precursor.
- **preserved_invariants**: outcome-label marginal distribution;
  per-node feature vectors are unchanged.
- **valid_conditions**: supervised / labelled evaluation contexts.
- **invalid_conditions**: unsupervised contexts (no label to permute).
- **deterministic_replay**: required.

## N6 — `configuration_model`

- **target_failure_mode**: structural-graph artefact — signal driven
  by the joint degree / weight distribution rather than higher-order
  topology.
- **preserved_invariants**: joint (degree, weight) distribution.
- **valid_conditions**: substrates where the degree / weight joint
  is non-degenerate.
- **invalid_conditions**: substrates with degenerate joint (constant
  degree OR constant weight) — collapses to N1 or N2 respectively
  and is excluded fail-closed.
- **deterministic_replay**: required.

## N7 — `sparse_maximum_entropy_reconstruction`

- **target_failure_mode**: low-coverage-reconstruction artefact —
  signal that arises only because the analyst reconstructed missing
  edges via a particular prior.
- **preserved_invariants**: observed marginals (row / column sums);
  total network density.
- **valid_conditions**: sparse-observation substrates (e.g. partial
  interbank exposure data) where reconstruction is part of the
  pipeline.
- **invalid_conditions**: fully observed substrates where no
  reconstruction step is invoked — the null degenerates to the
  identity.
- **deterministic_replay**: required.

## N8 — `shock_time_placebo`

- **target_failure_mode**: shock-timing artefact — signal that
  survives only because the analyst placed the synthetic shock
  exactly when stress was already detectable.
- **preserved_invariants**: shock MAGNITUDE; shock duration;
  network topology.
- **valid_conditions**: substrates with an explicit shock-injection
  parameter (e.g. `planted_repo_haircut_spiral`).
- **invalid_conditions**: substrates without a shock-injection
  parameter — null is N/A.
- **deterministic_replay**: required.

## N9 — `IAAFT_surrogate`

- **target_failure_mode**: spectral-content artefact — signal
  driven by the power spectrum rather than higher-order
  non-linearity.
- **preserved_invariants**: amplitude spectrum (Fourier power
  spectrum); approximate distributional marginal (iterative
  amplitude-adjusted Fourier transform).
- **valid_conditions**: stationary or weakly non-stationary
  time-series substrates.
- **invalid_conditions**: strongly non-stationary substrates with
  regime shifts that violate IAAFT's stationarity assumption.
- **deterministic_replay**: required.

---

## Hierarchy semantics

The hierarchy is **NOT** a strict ordering — it is a battery. A
substrate / W4 cell that survives N1..N9 (each in its valid
conditions) is **NOT** automatically promoted to signal. Promotion
requires the W6 power-first canonical design report PLUS at least
one positive control (W3) detecting signal under the same null
battery.

A null model that **destroys an invariant it should preserve** is
fail-closed at the W5 verifier and is excluded from the audit for
that cell. This mirrors the D-002G `INELIGIBLE_M2_*` discipline.

---

## Forbidden interpretations (global)

This hierarchy, in its present scaffold form, does **NOT**
constitute:

- a claim that any null is implemented,
- a claim that any null has been admissibility-verified against
  a D-002J substrate,
- a claim that this hierarchy is exhaustive (the list is the
  locked initial battery; expansion is a downstream PR, not a
  freelance addition),
- a claim that surviving the hierarchy is sufficient for signal
  detection (W6 power-first canonical design is required, see
  `D002J_POWER_FIRST_PROTOCOL.md`).

---

## Lock anchors

This scaffold inherits the locked-governance anchors recorded in
`docs/governance/D002J_PREREGISTRATION.yaml` `locked_anchors`. Any
edit to N1..N9 ids, hierarchy semantics, or per-null acceptance
contract constitutes a fresh D-002K pre-registration, not a patch.
