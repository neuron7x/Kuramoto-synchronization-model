# Dopamine RPE / Expectile Value Research Surface

Status labels:

- `P2_RESEARCH_SURFACE`
- `NON_PRODUCTION`
- `NO_MARKET_CLAIM`
- `STRUCTURAL_NEUROSCIENCE_TRANSFER_ONLY`

Current claim state: `STRUCTURAL`.

This PR establishes a bounded research substrate only. It does not claim market
edge, cognitive value, production intelligence, or brain-level function.

## Core boundary

The canonical dopamine invariant remains the TD(0) anchor:

```text
delta = reward + gamma * next_value - value
```

This PR does not replace `DopamineController.compute_rpe`, does not rewrite
INV-DA1 / INV-DA3 / INV-DA7, and does not route any output into trading,
execution, forecast, policy, application, or production controller paths.

Science licenses architecture only:

- TD(0) anchor;
- expectile distributional value;
- asymmetric learning;
- average-reward baseline;
- risk-sensitive readout.

Science does **not** license:

- copied neural parameters;
- cosmetic neuroscience language;
- trading claims;
- production policy wiring;
- intelligence claims without falsification.

Dopamine neuron reversal points, p-values, alphas, and R² are not market
parameters.

## Module roles

### `experimental_rpe.py`

Role:

- stateless algebraic probes;
- pure TD(0)-anchored helper functions;
- finite-output rejection after arithmetic;
- no learner state;
- no market claim;
- no controller integration.

Non-role:

- not a production policy component;
- not a market-output component;
- not an evidence artifact;
- not a claim-promotion mechanism.

### `expectile_value.py`

Role:

- deterministic online distributional value learner;
- expectile ensemble with sorted tau channels;
- deterministic replay from input sequence alone;
- finite-output rejection on deltas, TD targets, updated values, and readouts;
- no controller integration.

Non-role:

- not a market-output component;
- not an execution gate;
- not a claim registry entry;
- not evidence of performance.

## Layer taxonomy

| Layer | Current component | Claim class | Boundary |
| --- | --- | --- | --- |
| Canonical TD(0) | `canonical_td_error` | structural | identity anchor only |
| Distributional RPE | `distributional_td_error` | structural | affine TD projection over reward quantiles |
| Expectile value | `ExpectileEnsembleValue` | structural | online learner, no production routing |
| Asymmetric learning | `ExpectileChannel.alpha_pos/alpha_neg` | structural | defines tau; no copied biological alpha |
| Risk-sensitive readout | `risk_adjusted_value(tau)` | structural | primary risk mechanism via low-tau expectile |
| Risk penalty helper | `risk_adjusted_reward` | engineering baseline | control helper, not neuroscience-primary |
| Vigor helper | `average_reward_vigor` | placeholder control transform | no tonic-dopamine maturity claim |

The primary risk mechanism is the low-`tau` expectile readout. The linear
volatility/drawdown penalty is an engineering baseline used for comparison and
control, not a biological risk mechanism.

`average_reward_vigor` is a placeholder control transform. It is not a model of
tonic dopamine. Promotion requires future latency/vigor evaluation before any
claim stronger than `STRUCTURAL`.

## Structural neuroscience transfer only

Each neuroscience statement below is a structural-transfer statement only. It
licenses form, not parameter values and not performance claims.

- Scalar TD(0)-like reward prediction error supports the anchor form.
- Distributional dopamine coding supports a multi-channel value form.
- Asymmetric learning supports expectile channels.
- Average-reward theory supports a baseline/vigor hypothesis to test later.
- Utility/risk dopamine literature supports risk-sensitive readouts to test later.

Dopamine neuron reversal points, p-values, alphas, and R² are not market
parameters.

## Invariants and falsifiers

| ID | Type | Statement |
| --- | --- | --- |
| INV-EXP1 | algebraic | `tau == alpha_pos / (alpha_pos + alpha_neg)` to 1e-12. |
| INV-EXP2 | algebraic | the `0.5` expectile equals the arithmetic mean. |
| INV-EXP3 | asymptotic | a symmetric channel converges to the sample mean. |
| INV-EXP4 | monotonic | `tau_a < tau_b` implies `V_a <= V_b` at convergence. |
| INV-EXP5 | universal | every value estimate stays inside the target hull. |
| FIN-EXP1 | fail-closed | overflowed deltas, TD targets, and updated values are rejected. |
| MUT-EXP1 | mutation | quantile substitution fails the expectile residual. |
| MUT-EXP2 | mutation | alpha swap reverses risk ordering. |
| COLLAPSE-EXP1 | dynamics | constant target stream collapses dispersion to ~0. |
| EXTREME-EXP1 | stability | tau in `{0.01, 0.05, 0.95, 0.99}` stays finite and ordered. |

## Claim state machine

Allowed states:

1. `DECORATIVE`
2. `STRUCTURAL`
3. `TESTED`
4. `EXTRAPOLATED`
5. `ANCHORED`

Current PR state: `STRUCTURAL`.

Acceptance for `TESTED`:

- unit tests;
- falsifier tests;
- deterministic evaluation script.

Acceptance for `EXTRAPOLATED`:

- walk-forward improvement;
- null-model survival;
- parameter lock.

Acceptance for `ANCHORED`:

- repeated independent runs;
- stable regime performance;
- claim registry entry;
- rollback plan.

This PR must not add a claim registry entry. Claim promotion belongs to a later
evidence PR.

## Required next PR

Title:

```text
Add dopamine RPE extension evaluation harness and falsifier reports
```

Required paths:

```text
scripts/evaluate_dopamine_rpe_extension.py
results/dopamine_rpe_extension/EVAL_SUMMARY.json
results/dopamine_rpe_extension/WALKFORWARD_REPORT.md
results/dopamine_rpe_extension/PARAMETER_LOCK.json
results/dopamine_rpe_extension/ABLATION_MATRIX.csv
results/dopamine_rpe_extension/NULL_MODEL_REPORT.md
results/dopamine_rpe_extension/FALSIFIER_REPORT.md
```

Required model comparison:

- `canonical_td0`
- `td0_plus_distributional_helper`
- `td0_plus_asymmetric_alpha`
- `td0_plus_risk_penalty`
- `td0_plus_vigor_helper`
- `expectile_ensemble_low_tau`
- `expectile_ensemble_mid_tau`
- `expectile_ensemble_high_tau`
- `combined_surface`

Required protocol:

- at least 5 chronological walk-forward folds;
- fixed seed;
- fail-closed if data are unavailable;
- IC, Sharpe, MaxDD, turnover, hit-rate, calibration error, regime stability,
  null-model delta, and parameter sensitivity;
- null baselines: shuffled returns, sign-flipped reward, random tau assignment,
  constant reward, lagged reward, no-RPE baseline;
- parameter grids: `[0.1, 0.3, 0.5, 0.7, 0.9]`,
  `[0.05, 0.25, 0.5, 0.75, 0.95]`,
  `[0.01, 0.1, 0.5, 0.9, 0.99]`.

`PARAMETER_LOCK.json` must contain gamma, tau levels, learning rate, risk penalty
coefficients, vigor gain/bounds, data window, seed, commit SHA, timestamp,
promotion status, and config hash.

Dopamine neuron reversal points, p-values, alphas, and R² are not market
parameters. This sentence must also appear in the next evaluation report.

## Merge boundary for this PR

Merge is forbidden if this PR:

- claims intelligence without evidence;
- frames risk/vigor helpers as mature neuroscience;
- wires the learner into production;
- modifies a claim registry;
- adds evaluation artifacts but implies performance before null survival.

Merge can be considered only if:

- the PR is explicitly non-production;
- scope is exactly the seven research-surface files;
- docs separate stateless helper surface from stateful learner;
- tests cover algebra, dynamics, finite guards, and falsifiers;
- CI is green;
- no trading/policy/execution route is touched;
- no market claim is promoted.
