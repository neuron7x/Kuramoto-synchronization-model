# ECP-AS Exact Quorum Viability Protocol — Iteration 007

## Objective

Iteration 006 proved exact worst-case maxima for one frozen `2-of-3` quorum. Iteration 007 asks the stronger question:

> Can **any** dependence structure compatible with the published marginal evaluator rates satisfy the configured risk budget?

This is a feasibility question, not merely a worst-case certification question.

## Exact closed-form bounds

For three Bernoulli evaluator decisions with marginals `p1,p2,p3`, the probability of a `2-of-3` event has exact Fréchet bounds:

```text
lower = max(
    0,
    p1+p2-1,
    p1+p3-1,
    p2+p3-1,
    (p1+p2+p3-1)/2
)

upper = min(
    1,
    (p1+p2+p3)/2,
    p1+p2,
    p1+p3,
    p2+p3
)
```

For `3-of-3`:

```text
lower = max(0, p1+p2+p3-2)
upper = min(p1,p2,p3)
```

False-block bounds are the complements of the promotion bounds computed from true-positive marginals.

The implementation uses `fractions.Fraction`; no LP solver or floating-point optimization is required.

## Frozen Iteration 006 quorum

Evaluators:

1. `LLaMA-3.3-70B-Instruct::standard`
2. `Claude-Opus-4-6::aggressive`
3. `GPT-5.4-Mini::aggressive`

For low-soundness cases, the published false-positive marginals are:

```text
49/50, 139/500, 0
```

Therefore:

```text
P(unsafe promotion) ∈ [129/500, 139/500]
                     = [25.8%, 27.8%]
```

The 10% unsafe-promotion budget is violated even at the **best possible** compatible dependence structure.

For high-soundness cases, true-positive marginals are:

```text
497/500, 83/125, 1/500
```

Therefore:

```text
P(false block) ∈ [167/500, 171/500]
               = [33.4%, 34.2%]
```

The 20% false-block budget is also violated at the best possible compatible dependence structure.

Hence the frozen quorum is not merely non-certifiable. It is **structurally impossible** under the configured risk budget given the published marginals.

## Global exact scan

All distinct-model triplets from the frozen SoundnessBench aggregate leaderboard were evaluated under both `2-of-3` and `3-of-3` rules: **3,520 configurations**.

Classification semantics:

- `CERTIFIED`: every compatible dependence structure satisfies both budgets.
- `IMPOSSIBLE`: at least one risk lower bound already exceeds its budget; no dependence structure can satisfy both budgets.
- `UNRESOLVED`: some compatible dependence structures pass and others fail; aligned per-case joint observations are required.

Result:

```text
CERTIFIED:     0
UNRESOLVED:  122
IMPOSSIBLE: 3398
```

Thus **96.534%** of the scanned policies are impossible under the declared `10% unsafe / 20% false-block` budget regardless of evaluator dependence. The remaining 122 are not certified; they require joint evidence.

## Evidence boundary

This result does not estimate real deployment dependence and does not claim that any unresolved policy is safe. It uses published aggregate SoundnessBench FP/FN rates only. Public SoundnessBench code/data expose benchmark labels and evaluation code; the official repository does not commit the aligned per-case outputs of the leaderboard models. Therefore empirical covariance remains a separate proof obligation.
