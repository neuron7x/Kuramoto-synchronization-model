# ECP-AS Iteration 004 — Verification Report

## Objective
Test whether declared-lineage-aware evaluator authorization reduces unsafe promotion under correlated optimistic evaluators, using externally sourced SoundnessBench rigor labels strictly for scoring.

## External label slice
- 39 public preview rows
- 19 low-soundness
- 20 high-soundness
- source: `hosytuyen/SoundnessBench`, arXiv:2605.30329
- selection is not IID or representative

## Primary exact stress result
`optimistic_correlated`:

- raw majority unsafe promotion: **28.6694%**
- ECP-AS lineage quorum unsafe promotion: **3.6633%**
- ECP-AS false block: **5.6978%**
- strict-unanimity unsafe promotion: **0.1521%**
- strict-unanimity false block: **37.4974%**

Relative unsafe-promotion reduction of ECP-AS versus raw majority under this declared synthetic profile: **87.2%**.

## Mandatory boundary probe
`hidden_common_cause`:

- ECP-AS unsafe promotion: **15.1006%**
- ECP-AS false block: **10.5760%**

The architecture therefore does not claim immunity to causal dependence that is absent from its lineage metadata.

## Engineering result
- research-plane self/sibling reports cannot authorize promotion;
- pairwise declared lineage overlap is collapsed;
- missing lineage fails closed;
- successful quorum emits a deterministic aggregate oracle compatible with the existing admission controller;
- benchmark uses exact probability enumeration, so no random seed uncertainty exists.

## Claim boundary
External labels are real. Judge-error models are synthetic stress assumptions. This iteration does not reproduce actual LLM evaluations and does not establish population-level scientific-soundness accuracy.

## Next proof obligation
Collect actual outputs from heterogeneous evaluators on the full benchmark, estimate dependence empirically, calibrate quorum policy without test leakage, then evaluate on a locked holdout.
