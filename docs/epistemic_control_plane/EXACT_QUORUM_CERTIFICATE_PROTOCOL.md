# ECP-AS Exact Quorum Certificate Protocol — Iteration 006

## Objective

Iteration 005 produced exact LP bounds but still required trusting an optimization implementation. Iteration 006 converts the two decisive worst-case bounds for the best Iteration 005 triplet into **proof-carrying certificates** independently checkable with exact rational arithmetic.

## Frozen quorum

Evaluators:

1. `LLaMA-3.3-70B-Instruct::standard`
2. `Claude-Opus-4-6::aggressive`
3. `GPT-5.4-Mini::aggressive`

Decision rule: `2-of-3` support.

Published low-soundness false-positive marginals:

- `0.980 = 49/50`
- `0.278 = 139/500`
- `0.000 = 0`

Published high-soundness true-positive marginals:

- `0.994 = 497/500`
- `0.664 = 83/125`
- `0.002 = 1/500`

## Unsafe-promotion maximum

Constructive primal witness:

```text
P(000) = 1/50
P(100) = 351/500
P(110) = 139/500
```

It exactly reproduces the FP marginals and gives:

```text
P(quorum promotes | low soundness) = 139/500 = 0.278
```

Dual inequality, valid for every binary state:

```text
1{X1 + X2 + X3 >= 2} <= X2 + X3
```

Taking expectations gives:

```text
P(promote) <= E[X2] + E[X3]
           = 139/500 + 0
           = 139/500.
```

The primal witness attains the dual upper bound. Therefore the maximum is exactly `139/500 = 0.278`.

## False-block maximum

Constructive primal witness:

```text
P(010) = 3/500
P(100) = 42/125
P(110) = 82/125
P(111) = 1/500
```

It exactly reproduces the TP marginals and gives:

```text
P(quorum blocks | high soundness) = 171/500 = 0.342
```

Dual inequality, valid for every binary state:

```text
1{X1 + X2 + X3 < 2} <= 2 - X1 - X2
```

Taking expectations gives:

```text
P(block) <= 2 - E[X1] - E[X2]
         = 2 - 497/500 - 83/125
         = 171/500.
```

The primal witness again attains the dual upper bound. Therefore the maximum is exactly `171/500 = 0.342`.

## Verification architecture

`geosync.epistemic.rational_certificates` checks:

- nonnegative joint masses;
- total probability exactly one;
- exact marginal recovery;
- exact event probability;
- the dual affine inequality on every binary state;
- equality between primal objective, dual objective, and declared optimum.

The verifier uses Python `fractions.Fraction` only for arithmetic and has no SciPy or NumPy dependency.

## Inference

For this frozen quorum, there exist joint evaluator-error structures fully consistent with the published marginal benchmark rates that produce **27.8% unsafe promotion** and **34.2% false blocking**. Those values are not solver artifacts: explicit feasible distributions attain them, while exact dual inequalities prove they cannot be exceeded.

This proves non-certifiability under the configured `10% / 20%` risk budget from these marginals alone.

## Boundary

The certificates do not assert that either extremal distribution occurs in deployment. They do **not** prove the deployment distribution equals either witness. It proves that the published marginals do not rule those distributions out. Therefore a safety guarantee stronger than the bounds requires additional dependence evidence.
