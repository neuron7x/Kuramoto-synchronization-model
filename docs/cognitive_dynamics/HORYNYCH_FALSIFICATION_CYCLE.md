# Weight Falsification Cycle

This document defines a bounded weight-cycle layer for the cognitive dynamics lab. The name Horynych is treated only as a local label for this simulation-only replay surface.

## Objective

Prune unsupported weight assumptions through deterministic replay until only minimally justified synthetic weights remain.

## Scope

Included:
- alpha novelty, error, explore, and gain weights.
- beta sparsity, stability, energy, and invalid hypothesis weights.
- objective weights for realism, accuracy, diversity, stability, and energy.

Excluded:
- market execution.
- decision policy.
- external deployment claims.
- human-state claims.

## Cycle

1. Freeze the baseline weight table.
2. Run deterministic baseline scoring.
3. Run ablation scoring with the weight set to zero.
4. Run amplification scoring with the weight multiplied by 1.5.
5. Compute signal_loss as baseline_score minus ablation_score.
6. Compute risk_delta as excess amplification risk above the fixed risk boundary.
7. Mark the weight as survive only if signal_loss is sufficient and risk_delta stays bounded.
8. Mark every other weight as reject_or_schedule.
9. Write falsification_cycle.json and falsification_table.csv.
10. Keep confidence capped at simulation-only evidence.

## Success metric

Within this synthetic replay only:
- entropy_residual equals 0.0.
- reproducibility equals 1.0.
- every weight has a verdict.
- no claim tier is promoted.

## Key blocker

The blocker is whether each weight creates measurable signal without creating uncontrolled risk.

## Risk control

The cycle is dependency-free, deterministic, and isolated from trading, execution, forecast, and policy modules.
