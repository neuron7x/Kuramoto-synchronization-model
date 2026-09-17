# ECP-AS Distributionally Robust Quorum Protocol — Iteration 005

## Purpose

Iteration 005 attacks the residual failure exposed by Iteration 004: evaluators can look independent in declared lineage metadata while still sharing an unobserved common cause.

The control question is therefore stronger than "are the evaluator names different?":

> Given only externally measured false-positive and false-negative marginals, can the quorum be certified safe under every joint error distribution compatible with those marginals?

## External grounding

The frozen input contains the public SoundnessBench leaderboard FP/FN rates for 24 model/prompt configurations. SoundnessBench evaluates proposal-stage research soundness and reports strong prompt-dependent error asymmetry.

These are real published aggregate marginals. No per-case cross-model prediction matrix is assumed or reconstructed.

## Why marginals are insufficient

For three evaluators, let binary variables `X_i=1` mean evaluator `i` supports promotion. On low-soundness proposals, the published false-positive rates determine only:

`P(X_i=1)=FP_i`.

They do not determine:

`P(X_1, X_2, X_3)`.

The same marginals can therefore correspond to independent errors, anti-correlated errors, or a shared common-mode failure.

## Exact robust bound

For every candidate evaluator set, ECP-AS enumerates all binary quorum states and solves a linear program over joint state probabilities `p_s`.

Constraints:

- `p_s >= 0`;
- `sum_s p_s = 1`;
- each evaluator marginal equals the externally published FP or TP rate.

Unsafe-promotion bound:

`max P(sum_i X_i >= q)`

subject to the low-soundness FP marginals.

False-block bound:

`max P(sum_i X_i < q)`

subject to the high-soundness true-positive marginals.

This optimization makes **no independence assumption**.

## Configured engineering risk limits

Iteration 005 uses explicit design targets, not scientific universals:

- maximum unsafe-promotion bound: `0.10`;
- maximum false-block bound: `0.20`.

These thresholds are policy parameters and can be changed by downstream deployments.

## Exhaustive search

The benchmark searches all three-evaluator combinations with distinct base model names and quorum thresholds `2-of-3` and `3-of-3`.

Total evaluated candidate quorum configurations: **3,520**.

## Result

Number certified under the configured robust limits: **0**.

Best minimax candidate:

- `LLaMA-3.3-70B-Instruct::standard`;
- `Claude-Opus-4-6::aggressive`;
- `GPT-5.4-Mini::aggressive`;
- quorum: `2-of-3`.

Exact robust bounds:

- unsafe promotion: `[25.8%, 27.8%]`;
- false block: `[33.4%, 34.2%]`;
- minimax error: `34.2%`.

Therefore even the best triplet cannot be certified from marginals alone under the declared risk budget.

## Architectural consequence

ECP-AS adds a `RiskCertifiedLineageQuorumPolicy`.

A live lineage quorum is necessary but not sufficient. If the available calibration evidence cannot certify worst-case risk under dependence uncertainty, the runtime forces:

`PROMOTE -> HOLD`.

Thus model diversity, vendor diversity, or nominal agent count cannot substitute for measured dependence evidence.

## What this proves

It proves a mathematical statement about the frozen published marginals and the configured quorum family:

> No searched three-evaluator quorum is guaranteed to meet the configured safety/availability limits for all joint error structures compatible with those marginals.

## What this does not prove

It does not claim that the actual SoundnessBench evaluators realize the worst-case joint distributions.

It does not estimate their real pairwise or higher-order error covariance.

It does not claim that no larger or differently structured ensemble can perform well.

It does not claim that the configured 10%/20% engineering limits are universal scientific thresholds.

## Next proof obligation

Obtain per-case outputs from heterogeneous evaluators or run the public evaluation harness. Estimate dependence on a calibration split, construct a dependence certificate with confidence bounds, and test the resulting policy on a locked holdout.
