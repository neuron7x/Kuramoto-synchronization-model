# Dopamine TD-Error — Physics Contract

> Ground truth for all dopamine-related code in GeoSync.
> Read BEFORE modifying src/geosync/core/neuro/dopamine/,
> core/neuro/dopamine_execution_adapter.py, rl/core/reward_prediction_error.py,
> or any test involving RPE/TD-error.

## 1. The Model

GeoSync's dopamine controller implements Temporal Difference learning
(Schultz 1997, Sutton & Barto 2018). Dopamine neurons encode the
**reward prediction error** (RPE) — the difference between received
and expected reward.

### Core equation (TD(0)):

    δ(t) = r(t) + γ·V(s_{t+1}) - V(s_t)

where:
- δ(t) = reward prediction error (RPE, "dopamine signal")
- r(t) = observed reward at time t
- V(s) = estimated value of state s
- γ ∈ (0, 1] = discount factor
- s_t = state at time t

### Value update:

    V(s_t) ← V(s_t) + α·δ(t)

where α > 0 is the learning rate.

### GeoSync mapping:
- r(t) = execution P&L (profit/loss from trade)
- V(s) = expected future return from market state s
- δ > 0 = better than expected → increase position
- δ < 0 = worse than expected → decrease position
- δ ≈ 0 = as expected → maintain

## 2. Physics Invariants

### INV-DA1: RPE sign semantics
    δ = r + γ·V' - V
    - r > V - γ·V' → δ > 0 (positive surprise)
    - r < V - γ·V' → δ < 0 (negative surprise)
    - r = V - γ·V' → δ = 0 (predicted correctly)
    Type: ALGEBRAIC (exact, follows from definition)
    Test: compute δ for known (r, V, V', γ), verify sign and value
    Falsification: δ has wrong sign for given inputs

### INV-DA2: RPE finiteness
    δ is finite for all finite inputs (r, V, V', γ)
    Type: UNIVERSAL
    Proof: sum of finite values is finite (barring overflow)
    The implementation has explicit overflow protection.
    Falsification: NaN or Inf from finite inputs

### INV-DA3: Discount factor bounds
    γ ∈ (0, 1]
    Type: UNIVERSAL (hard constraint)
    γ = 0 → no future value (myopic)
    γ = 1 → no discounting (undiscounted, may diverge)
    γ > 1 → FORBIDDEN (amplifies future, unstable)
    Falsification: γ ≤ 0 or γ > 1 accepted without error

### INV-DA4: Value convergence (asymptotic)
    Under stationary reward distribution and appropriate α decay:
    V(s) → V*(s) as t → ∞ (Robbins-Monro conditions)
    Type: ASYMPTOTIC
    Conditions: Σα = ∞, Σα² < ∞ (standard stochastic approximation)
    In practice: fixed α means V oscillates near V*, doesn't converge exactly.
    Test: check V stabilizes within bounds after many updates with fixed reward.

### INV-DA5: RPE zero at equilibrium
    When V = V* (converged), δ ≈ 0 in expectation
    E[δ] = E[r] + γ·E[V(s')] - V(s) = 0 at optimality
    Type: STATISTICAL (holds in expectation)
    Test: after convergence, |mean(δ)| < ε for ε ~ O(α)

### INV-DA6: Learning rate effect
    Larger α → faster adaptation but more variance
    Smaller α → slower adaptation but more stability
    Type: QUALITATIVE
    Test: sweep α, check convergence speed vs variance trade-off

### INV-DA7: RPE linear in reward
    ∂δ/∂r = 1 (exactly)
    δ is linear in r, holding V, V', γ constant.
    Type: ALGEBRAIC
    Test: δ(r=2) - δ(r=1) = 1.0 exactly

## 3. What Tests MUST Check

### Algebraic (P0, exact):
- δ = r + γ·V' - V for known inputs (verify exact computation)
- γ ∈ (0, 1] enforced (ValueError for invalid γ)
- δ is finite for all finite inputs
- ∂δ/∂r = 1 (linearity in reward)

### Convergence (P1):
- V stabilizes after many updates with constant reward
- |E[δ]| → 0 as V approaches optimal

### Property (P0):
- NaN/Inf inputs raise RuntimeError (not silently propagate)
- Overflow protection works for extreme values

### Anti-patterns:
- Testing δ == specific_float without exact (r, V, V', γ) — δ is deterministic
  given inputs, so DO use exact equality here (unlike stochastic Kuramoto R)
- Testing V convergence with fixed α and expecting exact V* — fixed α means
  perpetual oscillation around V*
- Confusing RPE with reward — δ is the SURPRISE, not the reward itself

## 4. Relationship to Other Modules

| Signal | Source | Consumed by |
|---|---|---|
| δ (RPE) | dopamine_controller | Learning rate modulation, position sizing |
| r (reward) | Execution engine P&L | dopamine_controller |
| V (value) | Internal state | dopamine_controller, risk assessment |
| α modulation | NAk arousal, PWPE | dopamine_controller learning rate |

### With serotonin:
- High serotonin (patience) + negative δ (loss) → strong hold signal
- Low serotonin (risk-tolerant) + positive δ (gain) → increase position
- The NeuroSignalBus coordinates these: dopamine provides δ, serotonin provides inhibition

### With GABA:
- GABA gate independently inhibits based on volatility
- Dopamine δ does not directly affect GABA gate
- But GABA-gated position × δ → effective learning signal

## 5. Common Bugs This Theory Prevents

1. **Confusing δ sign**: δ > 0 means BETTER than expected, not "good outcome."
   If V is already high and reward matches, δ ≈ 0 (no surprise).

2. **Testing V convergence with fixed α**: V will oscillate. Test that
   oscillation amplitude is bounded, not that V = V* exactly.

3. **Ignoring γ sensitivity**: Small changes in γ near 1.0 have large effects
   on V for long-horizon problems. Always test with explicit γ values.

4. **Overflow on extreme inputs**: r = 1e308, V = -1e308 → δ overflows.
   The implementation has explicit protection. Tests should verify it works.

5. **Asymmetric learning**: Some implementations use different α for δ>0 vs δ<0
   (optimism/pessimism). If present, test both branches explicitly.
