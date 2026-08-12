# 12 — Negative Evidence

Rejected, partial, blocked, and non-claim cases are reported here as *scientific
value*, not as omissions. The thesis is admissibility governance (`README`); a
ledger that only ever promotes is unfalsified. The entries below are the cases
where the discipline declined to promote, and *why* — each cross-checked against
`.claude/neuro/NEURO_OPERATIONALIZATION_LEDGER.yaml` and
`artifacts/academy_fellow/law_mechanism_witness_matrix.json`. This chapter
complements the boundary ledger in `04` and the construct-validity section in
`09`.

## N1 — Four reverted over-promotions (admissibility ≠ promotion)

Four mechanisms carry real behaviour and a passing witness test, yet remain
**PARTIAL** (`promotion_allowed: false`, `inv_refs: []`) because no `INV-*`
contract in `CLAUDE.md` names them. Witnessing is not promotion.

| Mechanism (id) | File | Witness landed | Why kept PARTIAL |
|---|---|---|---|
| `dopamine-execution-adapter-tanh` | `core/neuro/dopamine_execution_adapter.py` | out ∈ [−1,1]; ≠ raw TD-error in saturation; INV-DA7 scoped to `DopamineController` only | no INV-* binding ⇒ audit forbids OPERATIONAL (`ADD_FALSIFIER`) |
| `neuro-optimizer-balance-metrics` | `src/geosync/core/neuro/neuro_optimizer.py` | null model (N=3000, seed 20260623) mean ≈0.731 vs configured ≈0.999 at T=0.95 (~2.7σ); DA/5HT and E/I declared uncited engineering ratios | no INV-* binding ⇒ OPERATIONAL forbidden (`ADD_NULL_MODEL`) |
| `hebbian-plasticity-update` | `geosync/neuroeconomics/hebbian_plasticity.py` | BIBO-stable under adversarial input via clamp `min(1,|pnl|*10)`; weight_floor rollback exercised | no INV-* binding; caller eligibility >1 outside witnessed envelope (`ADD_FALSIFIER`) |
| `homeostatic-stabilizer` | `geosync/neuroeconomics/homeostatic_stabilizer.py` | convergence `f(d)=d−gain·sin(d)`, stable for 0<gain<2; Lyapunov descent E_post≤E_pre | no INV-* binding; converges only for coherent common-mode error (`ADD_TEST`) |

The verbatim verdict shared by the first, third, and fourth: *"Classification
stays PARTIAL: no INV-* binding exists in CLAUDE.md, so the repo neuro audit
forbids OPERATIONAL promotion despite the added witness — promotion is blocked on
defining the invariant."* This is the negative result that demonstrates the gate's
teeth (see `11` D2).

## N2 — coherence-bridge-geosync-adapter: an OPEN fail-closed gap

`coherence_bridge/geosync_adapter.py` (PARTIAL, `ADD_FALSIFIER`). The witness
confirms INV-K1 (R ∈ [0,1]) and INV-RC1 on the Ollivier operator are preserved.
The kept-open gap, recorded honestly rather than closed by relabeling:

- the adapter **relays out-of-band negative gamma** and does **not** fail closed
  on it;
- the exposed `ricci_curvature` is an **augmented-Forman blend** that is
  legitimately > 1 — it is **not** the Ollivier κ ≤ 1 field. INV-RC1 is asserted
  on the Ollivier operator; the ledger wording should name that operator.

The mechanism stays PARTIAL precisely because this gap is unresolved.

## N3 — neuro-validation-bounds: QUARANTINE_DOC

`src/geosync/core/neuro/_validation.py` (PARTIAL, `QUARANTINE_DOC`). The
provenance witness pins the DA/5HT and E/I ranges as **engineering numeric
guards with no biological citation**. The utilities are sound; the negative
finding is that the ranges are not derivable from any cited source, so they are
quarantined as engineering bounds rather than promoted as neuro-grounded.

## N4 — adaptive-criticality-kappa: documented derivation, not executed source

`geosync/estimators/dfa_gamma_estimator.py` (OPERATIONAL, `INV-AC1-rev`). Stated
as a negative-of-scope so it is not over-read: the κ_critical / isolation gate is
a **documented derivation** (CLAUDE.md + INV-AC1-rev), **not executed source**.
The witness anchors the closed form to the real `DFAGammaEstimator` λ output; the
`witness_note` flags that an `isolate()` symbol should be bound *if/when the gate
is implemented*. The OPERATIONAL tier here covers the λ-anchored derivation, not
a running isolation gate.

## N5 — Pre-existing, out-of-scope counterexample (test_T28)

A Hypothesis counterexample fails independently of this work: in
`core/kuramoto/ott_antonsen.py` the steady state stalls at the unstable fixed
point for vanishing R0
(`tests/unit/physics/test_T28_wave2_witnesses.py::test_ott_antonsen_unit_disk_bound_property`,
per `ACADEMY_FELLOW_REPORT.md`). It **reproduces on the clean base with all new
files removed**, so it is reported as a pre-existing, out-of-scope negative — not
caused by, and not masked by, the witness-hardening campaign.

## N6 — Quarantined honesty (DECORATIVE / OVERCLAIM / REJECTED)

The remaining non-claims are kept in the tree and classified, not deleted —
deletion would erase the evidence that the term was once over-asserted.

- **2 OVERCLAIM** (`QUARANTINE_DOC`): `docs/neuro_optimization_guide.md`
  (claims neuroscience-verified optimisation with no peer-reviewed source for the
  DA/5HT [1.0,3.0] and E/I [1.0,2.5] ranges); `docs/HPC_AI_V4.md` (neuro/physics
  claims without per-statement source/test links).
- **3 DECORATIVE** (`RENAME`): `src/geosync/core/neuro/neuro_orchestrator.py`
  (configuration builder labelled basal-ganglia / dopamine / TACL);
  `src/geosync/core/neuro/adaptive_calibrator.py` (standard simulated annealing
  labelled "neuromodulator"); `src/geosync/policy/basal_ganglia.py` (three-branch
  lookup labelled basal-ganglia action selection). Naming carries no algorithmic
  content; an explicit non-claim is required.
- **1 REJECTED** (`REJECT`): `docs/exocortex/RESEARCH_TIMELINE.md` "mycelium"
  mention — no measurable graph-optimisation contract for the term exists in
  GeoSync; it cannot be operationalised without inventing unsupported science.

These eight quarantined entries are enumerated in
`law_mechanism_witness_matrix.json::summary.quarantined`. Quarantine *is* the
honest outcome: the label survives as audited non-claim, never as silent claim.

## Status discipline

This chapter is **not** a Distinguished-Professor-level result. It is an artifact
disciplined against Distinguished-Professor-style standards of originality,
evidence, reproducibility, and restraint.

**Binding non-claims (standing):**

- No biological equivalence — all neuro names are engineering analogs.
- No universal physics of markets; observers are not predictors.
- No alpha / profitability claim.
- No real L2 validation — synthetic-only witnesses; no recorded dataset/replay
  implied.
