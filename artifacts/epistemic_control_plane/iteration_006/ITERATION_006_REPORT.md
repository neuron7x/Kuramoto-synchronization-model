# ECP-AS Iteration 006 — Exact Certificate Report

## Result

The best Iteration 005 `2-of-3` triplet now has independently checkable exact proof objects.

- unsafe-promotion maximum: **139/500 = 0.278**
- false-block maximum: **171/500 = 0.342**
- both primal witnesses: feasible with exact published marginals
- both dual affine majorants: valid on all 8 binary evaluator states
- primal objective = dual objective = declared optimum in both cases
- external solver required for verification: **no**

## Verification

- 73 targeted epistemic-kernel unittest methods: PASS
- exact certificate runner: PASS
- compileall: PASS
- exact verifier uses `fractions.Fraction`, no SciPy/NumPy
- tampered primal witness: rejected
- tampered dual certificate: rejected

## Inference

The Iteration 005 bounds are not numerical LP artifacts. There are explicit joint evaluator-error distributions consistent with the published marginals that attain 27.8% unsafe promotion and 34.2% false blocking, and exact dual inequalities prove those values are maxima.

Under the configured 10% unsafe / 20% false-block risk budget, this frozen quorum is therefore **provably non-certifiable from marginal benchmark rates alone**.

## Boundary

The certificates do not assert that either extremal distribution occurs in deployment. Additional joint/dependence evidence is required to narrow the identified risk set.
