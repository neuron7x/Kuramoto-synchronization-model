# D-002G — Negative Space Map

## Excluded null-mechanism families under D-002G locked substrate grid

Companion artifact to `D002G_STRUCTURAL_CLOSURE_REPORT.md`. This
document enumerates the five null-mechanism families empirically
exhausted by PRs #677 / #679 / #680 / #681 against the two
M1-INELIGIBLE substrates (`block_structured`, `temporal_coupling`)
under the locked D-002G pre-registration.

Each row records (i) what was tried, (ii) what the mechanism preserves
by construction, (iii) the empirical failure mode, and (iv) the
generalisable rule-out lesson for downstream pre-registrations.

| Mechanism | Tried | Preserved | Failure mode | Rule-out lesson |
|---|---|---|---|---|
| M1 independent seed | drawing K_null from substrate at λ=0 with offset null_seed | substrate API | bit-identical K_p == K_null when substrate discards seed | independent-seed null requires substrate stochasticity in K_p |
| M2 edge-weight permutation | permuting ΔK support values | topology hash + support count | constant ΔK payload → no-op permutation | edge-weight permutation requires ΔK with ≥ 2 distinct support values |
| M2 node-payload permutation | permuting node labels under fixed topology | topology + node count | node identity IS the topology (block label = node label space) | node-payload permutation requires substrate where node identity is decoupled from topology semantics |
| M2 injection-sequence permutation | permuting injection event order under fixed topology | event multiset | injection IS the precursor (sequence is the causal hypothesis) OR sequence length < 2 | injection-sequence permutation requires non-trivial event sequence outside causal hypothesis |
| M3 topology-conditioned independent realisation | matched-marginal generator at locked marginal set | degree + block + spectral/N + density | marginals seed-invariant by substrate construction | mechanisms conditioned on marginal set X cannot identify precursor-specificity if substrate signal lies OUTSIDE X |

The five rows above span the full closed null-mechanism design space
that conditions only on quantities derivable from `(N, λ)` for a
seed-deterministic substrate. There is no sixth mechanism in this
family — any further mechanism that conditions only on `(N, λ)`-driven
quantities is structurally equivalent to one of the five rows.

## Design rule for future mechanism families

> Any future null-mechanism family proposed under a fresh
> pre-registration MUST first demonstrate that the substrate's
> `realize(seed)` produces seed-dependent variation in a quantity the
> mechanism CONDITIONS on. If the substrate is seed-deterministic and
> the proposed null conditions on quantities that depend ONLY on
> (N, λ), the mechanism is structurally INVALID a priori.

The rule is intentionally substrate-first: it is a *prerequisite check
on the substrate*, not a property of the mechanism. A mechanism that
would be valid on a different substrate is not therefore valid on the
locked D-002G substrate; the mechanism's admissibility is conditional
on the substrate's stochastic content along the axis the mechanism
conditions on.

Concretely:

- A mechanism conditioning on **edge-weight distributions** requires
  the substrate to produce seed-dependent edge weights at λ > 0.
- A mechanism conditioning on **node identity** requires the substrate
  to expose a node-label space decoupled from topology semantics.
- A mechanism conditioning on **injection event timing/order**
  requires injection events that are NOT themselves the causal
  hypothesis under test.
- A mechanism conditioning on **graph marginals** (degree, density,
  spectral radius, block histogram) requires substrate stochasticity
  in at least one marginal axis.

For the locked D-002G `block_structured` and `temporal_coupling`
substrates, none of these prerequisites hold, by substrate-class
design. The five rows in the table above record the exhaustive
empirical demonstration of that fact.

## Scope

This document does NOT impugn `ricci_flow`, which carries
seed-dependent stochastic content and admits ELIGIBLE_M1 / ELIGIBLE_M2
(edge-weight) / ELIGIBLE_M3 verdicts on the same grid. It does NOT
universally invalidate the listed mechanism families on substrate
designs outside the D-002G locked grid. It does NOT authorise a
canonical run on the partial `ricci_flow`-only coverage.

The negative space mapped here is bounded by:

1. The locked D-002G pre-registration substrate set (3 substrates).
2. The locked marginal set (degree + block + spectral/N + density).
3. The M1 / M2 / M3 mechanism family pursued in PRs #677 / #679 /
   #680 / #681.

Outside that conjunction the map is silent.
