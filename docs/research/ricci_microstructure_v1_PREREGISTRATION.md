# Ricci Microstructure v1 — Preregistration Contract

> **Status (locked until real data lands):**
> `claim_tier: HYPOTHESIS` · `falsification_status: NOT_RUN` · `decision: OBSERVE`
>
> This document formally constrains the empirical research line **before**
> execution. It fabricates no evidence. The line cannot promote past
> `HYPOTHESIS` until a real, hash-pinned order-book session and a replayable
> inference artifact exist and pass every gate below. Synthetic or placeholder
> data may instrument the pipeline; it may never promote the claim tier.
>
> Machine-checkable mirror: `schemas/research/ricci_microstructure_v1_config.schema.json`
> and `schemas/research/ricci_microstructure_v1_dataset.schema.json`, enforced by
> `tests/research_lines/test_ricci_microstructure_preregistration.py` and the
> promotion guard `tools/research/ricci_preregistration_guard.py`. Companion
> governance: `research_lines/ricci_microstructure_v1/contract.yaml`.

## 1. Hypothesis

Ollivier–Ricci curvature features computed over crypto perpetual order-book
microstructure carry a falsifiable, out-of-sample predictive signal for
short-horizon mid-price direction, beyond what order-flow imbalance and a
last-price-persistence null already explain.

## 2. Forbidden Claims

The following may never be asserted from this line without the full evidence
chain (real data hash ∧ replayable artifact ∧ passed nulls ∧ positive net-of-cost
result across multiple sessions):

- "validated", "profitable", "alpha", "edge", "market-predictive", "deployable";
- any Sharpe / PnL / hit-rate number presented as realized rather than as a
  pre-registered target;
- promotion of `claim_tier` above `HYPOTHESIS` on synthetic or single-session
  data.

## 3. Dataset Contract

Real input is a venue-native crypto-perp **depth-5 order book**, sampled at 100 ms
and resampled to 1 s, immutable and `sha256`-pinned. Contract:
`schemas/research/ricci_microstructure_v1_dataset.schema.json`. A dataset with a
zero or absent `data_sha256` is a placeholder and is treated as **no data**.

## 4. Minimum Data Depth

A promotable session must contain at least **3600 seconds** (1 h) of contiguous,
gap-checked observations. Below this depth the run is `BLOCKED` (insufficient
data), never `OBSERVE`-promoted.

## 5. Observation Window

Each session declares an explicit UTC `[start, end)` observation window. Features
at time *t* may use only information available at or before *t*
(`lag_sweep_no_future_data`); any future-data leak fails the run.

## 6. Null Baselines

Promotion requires the signal to beat **all** of these pre-registered nulls:

- `permutation_null` — label-shuffled curvature features;
- `lag_sweep_no_future_data` — causal lag sweep, no look-ahead;
- `cost_model` — net-of-cost persistence baseline;
- `multi_session_replay` — out-of-sample replay across ≥2 independent sessions.

A null that matches or exceeds the signal **rejects** the hypothesis.

## 7. Primary Metric

Out-of-sample **information coefficient (IC)** = Spearman rank correlation between
the curvature signal and forward mid-price return over the declared horizon.

## 8. Failure Threshold

The run **fails / is rejected** if OOS `IC <= 0.0` (no signal), if any null's IC is
within noise of the signal's, or if the multi-session IC is not stable in sign.

## 9. Cost Model

Net result is computed after an explicit cost model: taker/maker fees (bps) and a
slippage model applied per fill. **Negative net-of-cost result blocks promotion**
regardless of raw IC.

## 10. Replay Command

Every promotable artifact declares a deterministic, seeded `replay_command` that
regenerates the result from the pinned data + config hashes. A missing or empty
replay command blocks promotion.

## 11. Artifact Schema

Inference artifacts conform to the canonical envelope
`schemas/research/research_inference_artifact.schema.json` (non-zero `data_sha256`,
`config_sha256`, `git_sha`, `seed`, honest `decision`/`claim_tier`/
`falsification_status`).

## 12. Promotion Criteria

`HYPOTHESIS → TESTED_REAL_SINGLE → MEASURED` requires, cumulatively:

- real (non-zero) `data_sha256` and `git_sha`, deterministic seeded config;
- all §6 nulls run and beaten;
- positive §9 net-of-cost result;
- `TESTED_REAL_SINGLE` for one real session; `MEASURED` only after
  `multi_session_replay` across ≥2 independent sessions.

Synthetic data caps the state at `INSTRUMENTED` and never advances `claim_tier`.

## 13. Rejection Criteria

The line is **rejected** (archived as a sha-pinned negative artifact) if: a null
matches/exceeds the signal; OOS IC ≤ failure threshold; net-of-cost result is
negative; the signal sign is unstable across sessions; or any data-leak /
non-determinism is detected.
