# ECP-AS Iteration 005 — Verification Report

## Objective
Replace the hidden assumption "different evaluators are independent" with an exact distributionally robust risk bound based on externally published evaluator marginals.

## External evidence
- Source: SoundnessBench public leaderboard / arXiv:2605.30329
- Frozen evaluator configurations: **24**
- Inputs: published aggregate FP/FN rates
- Per-case joint outputs: **not available in this artifact**

## Exact search
- Distinct-model triplet quorum configurations: **3,520**
- Quorums tested: `2-of-3`, `3-of-3`
- Risk target: unsafe <= **10%**, false-block <= **20%**
- Robustly certified configurations: **0**

## Best minimax candidate
`LLaMA-3.3-70B-Instruct::standard` + `Claude-Opus-4-6::aggressive` + `GPT-5.4-Mini::aggressive`, `2-of-3`.

- robust unsafe range: **25.8%–27.8%**
- robust false-block range: **33.4%–34.2%**
- minimax error: **34.2%**

## Engineering consequence
`RiskCertifiedLineageQuorumPolicy` now makes a live lineage quorum insufficient by itself. If worst-case dependence risk exceeds deployment limits, promotion is forced to `HOLD`.

## Boundary
This is an exact bound on uncertainty induced by missing joint dependence information. It is not an estimate of actual model covariance and does not claim the worst-case coupling is realized.

## Remaining proof obligation
Per-case heterogeneous evaluator outputs + calibrated dependence certificate + locked holdout evaluation.
