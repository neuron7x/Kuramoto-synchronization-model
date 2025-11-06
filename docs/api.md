# API Overview

## FHMC

- `FHMC.from_yaml(path)`
- `FHMC.update_biomarkers(action_scalar_series, internal_latents, fs_latents)`
- `FHMC.compute_orexin(exp_return, novelty, load)`
- `FHMC.compute_threat(maxdd, volshock, cp_score)`
- `FHMC.flipflop_step()`
- `FHMC.next_window_seconds()`

## ActorCriticFHMC

- `ActorCriticFHMC.act(state_np)`
- `ActorCriticFHMC.learn(s, a, r, s_next, done)`

## SleepReplayEngine

- `SleepReplayEngine.observe_transition(...)`
- `SleepReplayEngine.sample(batch_size)`
- `SleepReplayEngine.dgr_batch(generator, m)`

## CFGWO

- `CFGWO.optimize()`
