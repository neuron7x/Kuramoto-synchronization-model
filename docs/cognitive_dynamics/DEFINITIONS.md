# COGNITIVE DYNAMICS LABORATORY — DEFINITIONS

Source contract: Convergence-Divergence Auditor × E/I Balance Engineer × Reality-Weighted Dynamic Simulation Producer.

## Objective

Convert cognitive theory into measurable dynamic-simulation architecture: define variables, simulate environments, detect convergence/divergence holes, estimate E/I balance, assign reality weights, measure energy cost, falsify claims, and emit testable patches.

## Operational definitions

| Concept | Observable signal | Failure mode | Measurement | Patch implication |
| --- | --- | --- | --- | --- |
| Cognition | context encoded, next state predicted, error compared, model updated | no feedback loop, decorative language | prediction error, update magnitude, action/simulation output | add encode→predict→compare→update cycle |
| Convergence | prediction error↓, state variance↓, entropy↓, attractor stability↑ | premature convergence, false attractor lock, mode collapse | rolling error slope, variance slope, entropy, attractor drift | decrease inhibition or increase exploration when PE remains high |
| Divergence | entropy↑, hypothesis diversity↑, novelty↑, coverage↑ | noise explosion, unbounded search, irrelevant novelty | state entropy, variance growth, novelty realism gain | increase inhibition or reduce novelty gain |
| Excitation | activation, novelty drive, PE gain, exploration mass | noise amplification, unstable recursion | `E_t = novelty + PE_gain + entropy + activation` | reduce alpha terms or add gates |
| Inhibition | suppression, sparsity, error gate, stability, energy penalty | blocked adaptation, rigid attractor | `I_t = stability_risk + energy + invalid_mass + sparsity` | lower beta terms or schedule inhibition |
| E/I balance | `E_t / (I_t + eps)` | chaos if high, rigidity if low | mean, p10/p90, time outside target range | retune alpha/beta weights |
| Reality weight | causal relevance × observability × prediction impact × decision cost | compute spent on low-value variable or missing causal variable | weighted contribution to prediction and gap | reweight high-impact dimensions |
| Realism gap | distance between simulated and target trajectories | static fit fails dynamic transition | trajectory error, distribution distance, transition mismatch | add perturbation-aware calibration |
| Energy efficiency | useful error reduction per compute unit | cost rises faster than realism gain | `Δerror / compute_time_or_steps` | sparse/event-triggered updates |
| Simulation fidelity | target-dynamics preservation under perturbation | overfit to baseline | stability across noise, delay, shift, scarce data | add adversarial matrix and fail-closed confidence |

## Rejection rule

A definition is invalid unless it contains:

```text
observable signal
failure mode
measurement method
patch implication
```
