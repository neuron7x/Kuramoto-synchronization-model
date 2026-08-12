# Shadow validation · Drift / envelope method

## Method

Block-bootstrap of the demo-ready OOS integrated log-return
series (2166 bars; sourced read-only from `results/cross_asset_kuramoto/demo/equity_curve.csv`). No new
backtest is run; the OOS stream is the already-validated one.

## Parameters (locked)

- seed = `20260422`
- block length = **20** bars (≈ one
  trading-month block; chosen once and frozen)
- number of bootstrap paths = **500**
- forward horizon = **90** bars
- quantiles reported: p05, p25, p50, p75, p95

## Why this is descriptive, not optimisation

1. No parameter of the strategy is changed, selected, or varied.
2. The envelope is a non-parametric summary of the **validated**
   OOS return distribution with its own short-range structure
   preserved by block sampling.
3. The envelope is used only to label the live cumulative path
   relative to historical expectation. It has no feedback loop
   into signal generation.

## Reproducibility

Given the same demo OOS stream, the same seed, the same block
length, and the same number of paths, the envelope is
bit-identical across runs. The test suite asserts this.
