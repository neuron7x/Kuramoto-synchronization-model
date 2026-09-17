# ECP-AS Iteration 002 — Adversarial Promotion Benchmark Protocol

## Purpose

Iteration 002 tests the first empirical engineering claim of ECP-AS:

> A claim-promotion controller that enforces evidence completeness, executed falsifiers,
> negative-evidence preservation, and oracle independence should produce fewer unsafe
> promotions than weaker promotion policies on adversarially constructed cases.

The benchmark is a **controlled policy benchmark**, not a claim of real-world scientific
validity. Scenario labels are hand-declared from the benchmark contract and are not generated
by ECP-AS itself.

## Benchmark population

The canonical suite contains:

- 31 synthetic adversarial/control scenarios;
- 4 repository-grounded negative-evidence probes sourced from
  `governance/NEGATIVE_EVIDENCE.yaml`;
- 35 total cases;
- 12 safe-to-promote controls;
- 23 unsafe-to-promote cases.

Repository-grounded probes preserve the semantics of real negative records already present in
GeoSync. They are **not** represented as exact historical counterfactual replays of the original
research decisions.

## Behavioral baselines

These are behavior classes, not reproductions or performance claims about named external
products:

1. `required_evidence_only` — promote when required positive artifacts are present.
2. `self_review` — additionally require the declared falsifier to have executed.
3. `multi_agent_vote` — additionally require two verifier reports, without lineage analysis.
4. `artifact_chain_no_lineage` — evidence + falsifier + negative-evidence gate + oracle presence,
   but no oracle-lineage independence analysis.
5. `ecp_as_no_negative_gate` — ECP-AS ablation without active-negative blocking.
6. `ecp_as_no_lineage_gate` — ECP-AS ablation without lineage independence.
7. `ecp_as` — full Iteration 002 controller.

## Primary metrics

For a policy `p`:

`UnsafePromotionRate(p) = unsafe_promotions / unsafe_cases`

`FalseBlockRate(p) = blocked_safe_cases / safe_cases`

No p-values or confidence intervals are reported because the benchmark cases are deliberately
constructed adversarial cases rather than IID draws from a natural population.

## Independent conformance surface

A separate 128-state exhaustive truth-table test covers the `OBSERVED -> REPLICATED` gate across
all Boolean combinations of:

- required evidence completeness;
- falsifier execution;
- active blocking negative evidence;
- oracle presence;
- full P/C/A/I independence axes;
- hidden shared lineage;
- explicit oracle admissibility.

The expected decision is calculated from an explicit Boolean reference rule and compared with the
runtime controller for every state.

## Primary falsifier

Iteration 002 fails if any of the following occurs:

- full ECP-AS produces an unsafe promotion on the canonical suite;
- full ECP-AS blocks any declared safe control;
- the 128-state replication truth table disagrees with the explicit reference rule;
- removing lineage or negative-evidence gates produces no measurable loss on cases designed to
  exercise those mechanisms;
- repository-grounded active negative evidence is promoted through a stronger maturity state.

## Claim boundary

A PASS supports only this bounded statement:

> On the declared Iteration 002 adversarial benchmark, the full ECP-AS policy prevented the unsafe
> promotions exercised by the suite while preserving all declared safe controls, and its lineage
> and negative-evidence gates contributed independently under ablation.

It does **not** establish:

- real-world reduction of scientific error;
- external-domain generalization;
- calibrated scientific truth probabilities;
- statistical independence of arbitrary real-world oracles;
- superiority to any named autonomous-science product.
