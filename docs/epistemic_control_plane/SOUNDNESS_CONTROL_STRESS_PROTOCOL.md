# ECP-AS Soundness Control Stress Protocol — Iteration 004

## Objective

Iteration 004 tests a narrower question than scientific reasoning accuracy:

> Can an epistemic control plane reduce unsafe claim promotion when several research/evaluator agents are optimistic, correlated, or only nominally independent?

The benchmark deliberately separates **external scientific labels** from **synthetic evaluator-error models**.

## External grounding

Ground-truth proposal-stage rigor labels come from SoundnessBench (`hosytuyen/SoundnessBench`, arXiv:2605.30329), a 2026 benchmark of 1,099 machine-learning research proposals reconstructed from ICLR submissions and labeled with reviewer soundness sub-scores.

Iteration 004 freezes a minimal public-preview slice of 39 rows:

- 19 `low` rigor labels;
- 20 `high` rigor labels;
- only `pair_id`, `soundness_score`, and `rigor_bucket` are retained;
- proposal text is intentionally excluded from the control-plane benchmark.

The slice is a convenience sample from the public viewer, not an IID or representative sample of all 1,099 proposals.

Source dataset commit frozen in the manifest:

`aab542f4db705a120e9130d0a0e3c720822a304d`

Dataset license: Apache-2.0.

## No label leakage

`rigor_bucket` is never passed to `LineageQuorumPolicy`.

The gate sees only:

- evaluator support/dissent;
- oracle identity;
- P/C/A/I independence metadata;
- declared lineage ancestors.

The external label is used only after the decision for scoring `unsafe promotion` and `false block`.

## Research-plane versus control-plane authority

Two nominal research evaluators are modeled as sharing one research-family lineage. Their agreement therefore cannot create independent authorization.

Three external evaluator paths are modeled as separately declared lineages. ECP-AS requires:

- at least three admissible external lineages;
- at least two supporting votes;
- no declared pairwise lineage overlap;
- explicit lineage metadata.

Research-plane clones may advise. They cannot authorize.

## Exact probability engine

The stress harness uses exhaustive Bernoulli outcome enumeration, not Monte Carlo sampling. Reported rates are therefore deterministic probabilities under the declared synthetic error model.

### Profile: `optimistic_correlated`

Research-family support probability:

- low-soundness proposal: `0.934`;
- high-soundness proposal: `0.970`.

The two research-plane agents share one common-mode outcome.

Each declared-independent external evaluator:

- false support on low-soundness: `0.115`;
- true support on high-soundness: `0.855`.

### Profile: `balanced_independent`

A lower-bias control profile.

### Profile: `hidden_common_cause`

The three external evaluators have disjoint **declared** lineage metadata, but a latent common-mode error is injected outside the lineage graph:

- low-soundness common false-support event: `0.15`;
- high-soundness common false-block event: `0.08`.

This profile is a mandatory falsification boundary. ECP-AS is expected to remain vulnerable because the causal dependency is not represented in its evidence graph.

## Compared policies

### `raw_majority`

All five nominal evaluator votes count equally.

### `ecp_as_lineage_quorum`

Only the maximum pairwise-independent admissible external set can authorize. A 2-of-3 support quorum is required.

### `strict_external_unanimity`

All three external evaluators must support. This is a safety-heavy baseline that exposes availability cost.

## Primary deterministic result

On `optimistic_correlated`:

| Policy | Unsafe promotion | False block | Balanced error |
| --- | ---: | ---: | ---: |
| raw majority | 28.6694% | 1.4206% | 15.0450% |
| ECP-AS lineage quorum | 3.6633% | 5.6978% | 4.6806% |
| strict external unanimity | 0.1521% | 37.4974% | 18.8247% |

ECP-AS therefore reduces unsafe promotion by about 87.2% relative to raw majority under this declared stress model, while avoiding the extreme false-block cost of unanimity.

## Mandatory failure boundary

On `hidden_common_cause`:

- ECP-AS unsafe promotion: **15.1006%**;
- ECP-AS false block: **10.5760%**.

This is not a regression to hide. It demonstrates the architectural limit:

> Lineage-aware authorization can reject **declared** common ancestry. It cannot infer an unobserved common cause from metadata that falsely appears independent.

## Integration architecture

A successful quorum can emit a deterministic aggregate authorization oracle whose digest binds:

- selected oracle IDs;
- source digests;
- support bits.

That aggregate oracle can be consumed by the existing `AdmissionController`, keeping evaluator-consensus semantics separate from claim-state transition contracts.

## What Iteration 004 proves

It establishes that:

1. the ECP-AS quorum implementation mechanically excludes self/sibling research-plane validation;
2. declared pairwise lineage overlap cannot multiply authorization weight;
3. exact synthetic stress probabilities show a materially safer safety/availability trade-off than raw majority for the declared optimistic-correlated profile;
4. hidden undeclared common causes remain a measurable failure mode.

## What Iteration 004 does not prove

It does **not** prove that ECP-AS judges scientific proposals better than frontier LLMs.

It does **not** reproduce the SoundnessBench paper's model evaluations.
It does not reproduce actual LLM evaluations.

It does **not** claim the 39-row preview slice is representative of the full 1,099-row benchmark.

It does **not** establish that real evaluator errors follow the declared Bernoulli profiles.

The external labels are real; the evaluator-noise profiles are controlled stress models.

## Next proof obligation

Run actual heterogeneous evaluator outputs on a full externally labeled benchmark and estimate empirical error covariance/lineage dependence instead of injecting it synthetically. Then calibrate quorum rules from held-out data and evaluate on a locked test split.
