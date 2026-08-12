# D-002J-P6 — Null Model Contracts v1

Phase: **D002J-P6**. Parent: **D002J-P5** (`SUBSTRATE_CANDIDATES_READY`).
Decision: **NULL_HIERARCHY_READY**.

This document is the operator-locked contract for the D-002J null-model
hierarchy. It defines ten null families, each a FALSIFIER targeting ONE
named false explanation, the substrate→null applicability matrix, the
H_I2 forward-declared conditional on the topology-conditioned nulls, and
the anti-decorative rejection rule. P6 builds the null-generator hierarchy
contract and the deterministic generators; it does NOT execute nulls
against real substrate data at scale (P7/P8) and authorises no canonical
run.

---

## §0 Null-as-falsifier philosophy

A null model is **not decorative rigor**. Every null in this hierarchy is
a FALSIFIER that targets exactly ONE named false explanation of the form
*"the detected signal is merely an artifact of X."* The discipline:

> A result that "survives" a null only counts as information if the null
> genuinely **could have killed it**.

Each null therefore declares, and the implementation **numerically
verifies in code**, two things:

1. **preserves** — the structure the null keeps intact (its admission
   test; e.g. `N5` asserts the post-rewire degree sequence is *exactly*
   equal to the pre-rewire degree sequence).
2. **destroys** — the structure the null removes (its rejection test; if
   the "destroyed" structure is still present the null is a no-op and is
   REJECTED).

A null whose preserve/destroy claims are merely declared but not
numerically checked, or that has no genuine target false explanation, is
**decorative and is REJECTED** (see §4).

---

## §1 The ten null families

### N1 — `label_permutation`  (class: outcome_alignment)

- **Target false explanation:** the detected signal is merely an artifact
  of attaching *any* structure to the outcome labels, not of the specific
  outcome-aligned structure.
- **Preserves:** label multiset, label count.
- **Destroys:** label-to-position alignment.
- **Applicability:** all three P5 substrates.
- **Admission test:** post-null `sorted(labels) == sorted(labels)` (exact
  multiset).
- **Rejection test:** if position-wise alignment is preserved → no-op →
  REJECT.
- **Expected failure mode:** if the substrate signal survives, it is NOT
  an artifact of arbitrary structure attachment.

### N2 — `time_window_shift_placebo`  (class: temporal_alignment)

- **Target false explanation:** the signal is just a window-alignment
  artifact; it would appear under any equally-sized window placement.
- **Preserves:** marginal distribution, series length.
- **Destroys:** window-onset alignment.
- **Applicability:** `funding_liquidity_rollover`,
  `volatility_credit_spread_regime`. **Non-applicable:**
  `cross_exposure_contagion_proxy` — a graph/cascade substrate with no
  single onset-aligned window to shift (its temporal null is N9).
- **Admission test:** post-null `sorted(series) == sorted(series)`.
- **Rejection test:** identity roll (no-op) → REJECT.
- **Expected failure mode:** survival ⇒ signal is NOT a window-placement
  artifact.

### N3 — `temporal_block_bootstrap`  (class: temporal_dependence)

- **Target false explanation:** the signal is just iid noise; its
  apparent temporal dependence is spurious.
- **Preserves:** series length, lag-1 autocorrelation band.
- **Destroys:** global trajectory order.
- **Applicability:** `funding_liquidity_rollover`,
  `volatility_credit_spread_regime`. **Non-applicable:**
  `cross_exposure_contagion_proxy` — a network-cascade observable, not an
  autocorrelated scalar series.
- **Admission test:** surrogate lag-1 autocorrelation stays within the
  source autocorrelation band.
- **Rejection test:** surrogate == source (no reordering) → REJECT.
- **Expected failure mode:** survival ⇒ dependence beyond iid noise.

### N4 — `iaaft_surrogate`  (class: spectral)

- **Target false explanation:** the signal is a linear-spectral artifact
  fully explained by power spectrum + amplitude distribution.
- **Preserves:** power-spectrum band, amplitude distribution.
- **Destroys:** nonlinear phase structure.
- **Applicability:** `funding_liquidity_rollover`,
  `volatility_credit_spread_regime`. **Non-applicable:**
  `cross_exposure_contagion_proxy` — no single periodogram to surrogate.
- **Admission test:** spectral correlation(surrogate, source) ≥ 0.90 AND
  exact value-distribution match (IAAFT's terminal amplitude-adjustment
  preserves the spectrum up to high correlation, not elementwise
  equality).
- **Rejection test:** surrogate == source (no phase randomisation) →
  REJECT.
- **Expected failure mode:** survival ⇒ nonlinear structure beyond the
  linear spectrum.

### N5 — `degree_preserving_graph_null`  (class: graph_degree)

- **Target false explanation:** the detected signal is merely an artifact
  of the node degree distribution, not of the specific edge placement.
- **Preserves:** degree sequence, node count.
- **Destroys:** edge placement.
- **Applicability:** `cross_exposure_contagion_proxy` ONLY.
  **Non-applicable:** the two time-series substrates have no graph
  adjacency to rewire (see §2, §3).
- **Admission test:** post-null degree sequence == pre-null degree
  sequence, **EXACT** (not approximate), verified in code.
- **Rejection test:** post-null preserves edge placement → no-op →
  REJECT.
- **Expected failure mode:** survival ⇒ signal is NOT degree-driven.

### N6 — `weight_preserving_shuffle`  (class: graph_weight)

- **Target false explanation:** the signal is driven only by the multiset
  of edge-weight magnitudes, not by which edge carries which weight.
- **Preserves:** weight multiset, binary topology.
- **Destroys:** weight placement.
- **Applicability:** `cross_exposure_contagion_proxy` ONLY.
  **Non-applicable:** time-series substrates have no weighted edge set.
- **Admission test:** post-null `sorted(edge_weights)` unchanged AND
  binary topology unchanged.
- **Rejection test:** weight vector unchanged → REJECT.
- **Expected failure mode:** survival ⇒ signal depends on weight
  placement, not just magnitudes.

### N7 — `configuration_model`  (class: graph_topology_conditioned, **H_I2-CONDITIONAL**)

- **Target false explanation:** the signal is generic to any random graph
  with this degree sequence, not specific to the observed network.
- **Preserves:** degree sequence, node count.
- **Destroys:** specific edge structure.
- **Applicability:** `cross_exposure_contagion_proxy` ONLY.
  **Non-applicable:** time-series substrates have no degree sequence.
- **Admission test:** post-null degree sequence == pre-null degree
  sequence (EXACT).
- **Rejection test:** post-null edge set == observed edge set → REJECT.
- **Expected failure mode:** survival ⇒ signal is specific to the
  observed network, not generic to its degree sequence.
- **H_I2 conditional:** see §3.

### N8 — `sparse_maximum_entropy_reconstruction`  (class: graph_topology_conditioned, **H_I2-CONDITIONAL**)

- **Target false explanation:** the signal is an artifact of a
  dense-network representation and disappears under a realistic sparsity
  budget.
- **Preserves:** total edge count, node count.
- **Destroys:** dense edge placement.
- **Applicability:** `cross_exposure_contagion_proxy` ONLY.
  **Non-applicable:** time-series substrates have no network density.
- **Admission test:** post-null total edge count == pre-null total edge
  count (sparsity budget held).
- **Rejection test:** post-null edge set == observed edge set → REJECT.
- **Expected failure mode:** survival ⇒ signal is NOT a dense-network
  artifact.
- **H_I2 conditional:** see §3.

### N9 — `shock_time_placebo`  (class: temporal_alignment)

- **Target false explanation:** the signal exists at any arbitrary time,
  not specifically at the true crisis/shock onset time.
- **Preserves:** underlying series values, single onset count.
- **Destroys:** crisis-time alignment.
- **Applicability:** all three P5 substrates (every substrate has a true
  onset index; this is the contagion substrate's applicable temporal
  null in place of N2/N3/N4).
- **Admission test:** exactly one onset in the placebo indicator AND
  series values unchanged.
- **Rejection test:** placebo onset == true onset → REJECT.
- **Expected failure mode:** survival ⇒ signal is tied to the true
  crisis time, not arbitrary times.

### N10 — `vintage_leakage_trap_null`  (class: leakage_trap, **INVERTED PASS SEMANTICS**)

- **Target false explanation:** the signal is a look-ahead (vintage
  leakage) artifact that only exists because future information bled into
  the present feature.
- **Preserves:** present-arm marginal distribution, series length.
- **Destroys:** the causal-information boundary (look-ahead arm differs
  from causal arm).
- **Applicability:** all three P5 substrates. This is the **P3/PC5
  leakage-sentinel bridge null**.
- **Admission test:** the look-ahead arm differs from the causal arm (the
  trap is genuinely re-introducing leakage).
- **Rejection test:** look-ahead arm == causal arm → no-op → REJECT.
- **INVERTED PASS SEMANTICS:** PASS iff the signal **DISAPPEARS** in the
  leakage-free (causal) arm. A signal that persists only in the
  look-ahead arm is a leakage artifact. This inverts the normal "survival
  = good" convention and is the bridge to the P3 leakage sentinel / PC5.

---

## §2 Substrate → null applicability matrix (3 P5 substrates × 10 nulls)

`A` = applicable, `–` = non-applicable.

| Null | funding_liquidity_rollover | cross_exposure_contagion_proxy | volatility_credit_spread_regime |
|---|---|---|---|
| N1  label_permutation                       | A | A | A |
| N2  time_window_shift_placebo               | A | – | A |
| N3  temporal_block_bootstrap                | A | – | A |
| N4  iaaft_surrogate                         | A | – | A |
| N5  degree_preserving_graph_null            | – | A | – |
| N6  weight_preserving_shuffle               | – | A | – |
| N7  configuration_model                     | – | A | – |
| N8  sparse_maximum_entropy_reconstruction   | – | A | – |
| N9  shock_time_placebo                      | A | A | A |
| N10 vintage_leakage_trap_null               | A | A | A |
| **Applicable count** | **6** | **7** | **6** |

The two time-series substrates (`funding_liquidity_rollover`,
`volatility_credit_spread_regime`) honestly do NOT bind the graph nulls
(N5/N6/N7/N8) — they have no graph to rewire. The contagion substrate
honestly does NOT bind the scalar-series nulls (N2/N3/N4) — its observable
is a network-cascade quantity, not an autocorrelated scalar. No null is
padded onto an inapplicable substrate.

---

## §3 H_I2 conditional (N7 / N8)

D-002I **H_I2** (M3 topology-conditioned over-fit) is **UNKNOWN**. The two
topology-conditioned nulls — **N7 `configuration_model`** and **N8
`sparse_maximum_entropy_reconstruction`** — therefore carry an explicit
field `h_i2_conditional: true` in the manifest and on every emitted
`NullInstance.metadata`, plus the note:

> *"If D-002I H_I2 is later SUPPORTED, this null requires fresh
> admissibility justification before canonical use (P8)."*

In one line, verbatim: if D-002I H_I2 is later SUPPORTED, N7 and N8 each
require fresh admissibility justification before canonical use (P8).

This is a **forward-declared conditional, not a blocker**. P6 ships the
nulls as admissible for hierarchy purposes; the conditional only gates
their *canonical* use at P8 and only fires if H_I2 transitions UNKNOWN →
SUPPORTED. The non-topology-conditioned nulls (N1–N6 except none,
specifically N1/N2/N3/N4/N5/N6/N9/N10) carry `h_i2_conditional: false`.

---

## §4 Forbidden: a null with no target false explanation is decorative

A null that does not name a specific false explanation it could
falsify is **decorative rigor and is REJECTED**. This is enforced
mechanically by `test_no_null_without_target_false_explanation`: every
entry in `null_hierarchy_manifest_v1.json` must carry a non-empty
`target_false_explanation`, and every null class must expose a non-empty
`target_false_explanation` attribute. Decorative nulls do not enter the
hierarchy.

Equally forbidden: declaring a preserve/destroy pair without numerically
checking it. Every `NullInstance` records
`preserved_invariants_checked` and `destroyed_structure_checked` as
boolean maps populated by in-code numeric verification; the `admitted`
property is `True` only if every check passed.

---

## §5 Every P5 substrate has ≥2 admissible nulls (proof table)

| P5 substrate | substrate class | applicable nulls | count | ≥2? |
|---|---|---|---|---|
| `funding_liquidity_rollover` | funding/liquidity (time series) | N1, N2, N3, N4, N9, N10 | 6 | ✅ |
| `cross_exposure_contagion_proxy` | contagion (graph-bearing) | N1, N5, N6, N7, N8, N9, N10 | 7 | ✅ |
| `volatility_credit_spread_regime` | market/info (time series) | N1, N2, N3, N4, N9, N10 | 6 | ✅ |

`min_applicable_nulls_per_substrate = 6 ≥ 2`. No substrate was padded
with an inapplicable null to reach the floor. Cross-referenced against
the P5 `substrate_candidate_manifest_v1.json` substrate ids
(`funding_liquidity_rollover`, `cross_exposure_contagion_proxy`,
`volatility_credit_spread_regime`); no null lists a non-existent
substrate.

---

## §6 Scope boundary (repeat for safety)

- D-002J-P6 builds the null-generator **hierarchy contract** and the
  deterministic generators. It does **NOT** execute nulls against real
  substrate data at scale (that is P7/P8 territory).
- D-002J-P6 does **NOT** compute power (P7), run canonically (P8), or
  edit the D-002J prereg (sha256 byte-exact unchanged).
- D-002J-P6 does **NOT** rescue D-002H. D-002H REFUSED remains the
  truthful canonical verdict. `canonical_run_authorized_anywhere: false`
  preserved.
- The ONLY new source files under `research/systemic_risk/` are under
  `research/systemic_risk/nulls/d002j/` (P6 is explicitly allowed to add
  this subtree; all other `research/systemic_risk/*` paths are forbidden
  by the P6 acceptor).

Lineage: `D-002G → D-002H REFUSED → D-002I → D-002J prereg #694 → P1
#695 → P1A #697 REJECTED → P1B #698 → P2 #699 → P2.5 #700 → P3 #701 →
P4 #702 → P5 #703 → P6 this PR (NULL_HIERARCHY_READY)`.

Next legal PR: `feat(x10r,D-002J-P7): implement power-first canonical-run
gate` — P7 may only open after this P6 PR merges with decision
`NULL_HIERARCHY_READY`.
