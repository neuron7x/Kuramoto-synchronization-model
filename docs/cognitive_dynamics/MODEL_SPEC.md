# MODEL_SPEC.md

## System question

Where does an internal dynamic model converge too early, diverge into noise, lose E/I balance, waste compute, or become less realistic than the target environment?

## Minimal dynamic model

```text
env_t = observed_state + hidden_state + perturbation + constraint + feedback
x_next = f(x_t, control_t, theta_t, env_t) + noise_t
prediction_t = model_prediction(x_t)
prediction_error_t = observed_t - prediction_t
excitation_t = alpha_novelty * novelty_t + alpha_error * abs(prediction_error_t) + alpha_explore * entropy_t + alpha_gain * activation_gain_t
inhibition_t = beta_sparsity * sparsity_t + beta_stability * instability_t + beta_energy * cost_t + beta_invalid * invalid_mass_t
ei_balance_t = excitation_t / (inhibition_t + epsilon)
convergence_t = error_reduction_t + variance_reduction_t + attractor_stability_t
divergence_t = novelty_t + coverage_t + hypothesis_diversity_t
realism_gap_t = trajectory_distance + distribution_distance + transition_mismatch
energy_efficiency_t = useful_error_reduction / compute_cost
```

## Core variables

```json
{
  "state": "x_t",
  "environment": "env_t",
  "prediction": "prediction_t",
  "prediction_error": "prediction_error_t",
  "excitation": "excitation_t",
  "inhibition": "inhibition_t",
  "balance": "ei_balance_t",
  "convergence": "convergence_t",
  "divergence": "divergence_t",
  "energy": "compute_cost_t",
  "realism_gap": "realism_gap_t"
}
```

## Control variables

```text
alpha_error
alpha_novelty
alpha_explore
alpha_gain
beta_sparsity
beta_stability
beta_energy
beta_invalid
update_density
reality_weight_vector
```

## Non-goals

No AGI claim. No brain-equivalence claim. No metaphor without metric. No confidence above evidence. No scaling without energy accounting.
