# ECP-AS Iteration 007 — Exact Quorum Viability Report

## Result

Iteration 007 upgrades the Iteration 006 conclusion from worst-case non-certifiability to exact feasibility classification.

For the frozen `2-of-3` quorum:

- unsafe promotion: **[129/500, 139/500] = [25.8%, 27.8%]**
- false block: **[167/500, 171/500] = [33.4%, 34.2%]**
- configured budgets: unsafe **10%**, false-block **20%**
- verdict: **IMPOSSIBLE**

Both *lower* risk bounds exceed their budgets. Therefore no joint dependence structure compatible with the published marginals can make this quorum acceptable.

## Global exact scan

Distinct-model triplets under `2-of-3` and `3-of-3`: **3,520** policies.

- `CERTIFIED`: **0**
- `UNRESOLVED`: **122**
- `IMPOSSIBLE`: **3,398**
- impossible fraction: **1699/1760 = 96.534%**

`IMPOSSIBLE` means even the best compatible dependence structure violates at least one risk budget. `UNRESOLVED` means marginal rates alone do not decide the policy and aligned per-case evaluator outputs are still required.

## Verification

- 80 targeted epistemic-kernel unittest methods: PASS
- exact viability runner: PASS
- exact closed forms vs prior LP: **3,520/3,520 MATCH**
- maximum exact-vs-LP absolute difference: **2.22e-16** (floating-point representation only)
- compileall: PASS
- exact viability implementation imports no SciPy/NumPy/linprog

## Evidence boundary

The official SoundnessBench repository publishes benchmark labels, evaluation code, prompts, and aggregate leaderboard rates. Its README states model-specific per-case predictions are generated locally under `results/`; those aligned leaderboard outputs are not committed in the public repository. Iteration 007 therefore does not claim empirical evaluator covariance or deployment dependence.
