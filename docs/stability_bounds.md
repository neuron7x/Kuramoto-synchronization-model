# Stability bounds for damped phase synchronization

## FACT
Model equation:

\[
\dot{\theta_i}=K\sin(\theta_i^*-\theta_i)
\]

Discrete Euler step:

\[
\theta_i^{t+1}=\theta_i^t+\Delta t K \sin(\theta_i^*-\theta_i^t)
\]

Potential:

\[
V(\theta)=\frac{1}{N}\sum_i(1-\cos(\theta_i^*-\theta_i))
\]

## MODEL
`run_reset_wave` is a numerical relaxation solver on compact phase manifold \([-\pi,\pi)\) with lock threshold `max_phase_error`.

## ANALOGY
Terms like "reset-wave" or "homeostasis" are interpretation only.

## Empirical bound (tested)
For this implementation and stress tests, monotone potential decrease is reliable in practical regimes:

`0 < coupling_gain * dt <= 0.2`

Outside this region, nonconvergence/oscillatory behavior can occur and is covered by negative tests.
