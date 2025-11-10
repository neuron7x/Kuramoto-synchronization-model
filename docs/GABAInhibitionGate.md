# GABA Inhibition Gate — Technical Specification

## 1. Purpose and Scope
The **`GABAInhibitionGate`** module converts threat and timing information into a risk-aware action multiplier. It models dual-time-constant GABAergic inhibition, spike-timing-dependent plasticity (STDP), and long-term potentiation/depression (LTP/LTD) to regulate trading aggressiveness. This specification formalises the biophysical assumptions, the discrete-time implementation, interfaces, telemetry, and validation requirements for the gate.

This document applies to:
- `modules/gaba_inhibition_gate.py` implementation and its exported dataclasses.
- Downstream systems consuming the gate (execution policies, risk overlays, telemetry collectors).

## 2. System Context
```
┌─────────────────────┐     ┌──────────────────────┐
│ Market Feature Bus  │────▶│ GABAInhibitionGate   │────▶ Action sent to
│ (vol, ret, vix, …)  │     │  (torch.nn.Module)   │     execution stack
└─────────────────────┘     └──────────────────────┘
          ▲                            │
          │                            ▼
       PnL/RPE                   TACL Telemetry
```
The gate is evaluated immediately before portfolio deltas are transmitted to execution. Telemetry is exported on every forward pass and stored in the TACL monitoring plane.

## 3. Inputs and Outputs
| Symbol | Field | Type | Shape | Description |
| --- | --- | --- | --- | --- |
| $v_{ix}$ | `vix` | `torch.Tensor` | scalar | Realised/expected volatility proxy (VIX-like). |
| $σ$ | `vol` | `torch.Tensor` | scalar | Realised asset volatility used as presynaptic activity. |
| $r$ | `ret` | `torch.Tensor` | scalar | Recent return used as postsynaptic activity. |
| $p$ | `pos` | `torch.Tensor` | scalar | Position inventory (reserved for future extensions). |
| $δ$ | `delta_t_ms` | `torch.Tensor` | scalar | Spike time difference in milliseconds (post minus pre). |
| $a$ | `action` | `torch.Tensor` | `(N,)` or scalar | Proposed portfolio delta vector. |

Outputs:
- `gated_action` (`torch.Tensor`): regulated action vector.
- `GateMetrics`: structured telemetry with inhibition strength, GABA level, cycle multiplier, and plasticity deltas.

All tensors must be finite; violations raise `ValueError`. Missing market keys raise `KeyError`.

## 4. State Variables and Invariants
| Variable | Meaning | Initial Value | Constraints |
| --- | --- | --- | --- |
| `gaba_fast` | Fast ($τ_{A}$) inhibitory pool (GABA<sub>A</sub>). | 0 | $[0, 2]$ after clamping. |
| `gaba_slow` | Slow ($τ_{B}$) inhibitory pool (GABA<sub>B</sub>). | 0 | $[0, 2]$. |
| `risk_weight` | Plastic risk multiplier. | 1 | `[risk_min, risk_max] = [0.5, 1.5]` by default. |
| `t_ms` | Internal simulation time (ms). | 0 | Monotonic, resettable. |

Invariants:
1. Inhibition is clamped to `[0, 0.95]` to avoid complete shutdown.
2. MFD safety: when `gaba_level > 0.1`, the magnitude of the gated action never exceeds the proposal.
3. Plasticity updates use `torch.no_grad()` to avoid gradient bleed into policy training loops.

## 5. Mathematical Formulation
### 5.1 Volatility to GABA drive
Normalized volatility: $\hat{v} = \mathrm{clip}(v_{ix} / 40, 0, 1.5)$. Dual pool update per step ($Δt = 0.1$ ms default):
$$
G_A[t] = G_A[t-1] e^{-Δt/τ_A} + 0.5 \hat{v} (1 - e^{-Δt/τ_A}),
$$
$$
G_B[t] = G_B[t-1] e^{-Δt/τ_B} + 0.5 \hat{v} (1 - e^{-Δt/τ_B}).
$$
Combined level: $G = \mathrm{clip}(G_A + 0.5 G_B, 0, 2)$.

### 5.2 Inhibition and firing proxy
Action norm proxy $F = \mathrm{clip}(\lVert a \rVert, 0, 10)$. Inhibition before clamping:
$$
I = k_{inh} \cdot G \cdot \tanh(F), \quad k_{inh}=0.4.
$$

### 5.3 Oscillatory modulation
If enabled, gamma/theta modulation is
$$
M = 1 + 0.2\sin(2π f_γ t) + 0.15\sin(2π f_θ t),
$$
with $f_γ=40$ Hz and $f_θ=8$ Hz. Otherwise $M=1$.

### 5.4 Plasticity update
Let $Δt_{ms}$ be spike timing (positive means presynaptic before postsynaptic).

**STDP component**
$$
Δw_{STDP} =
\begin{cases}
A_+ e^{-Δt_{ms}/τ_+} G & Δt_{ms} > 0 \\
-A_- e^{Δt_{ms}/τ_-} G & Δt_{ms} \le 0
\end{cases}
$$
with $A_+=0.008, A_-=0.006, τ_+=16.8, τ_-=33.7$.

**LTP/LTD gate**
Let $c = σ r$ (co-activity score).
$$
Δw_{LTP/LTD} =
\begin{cases}
0.01 G & c > 0.3 \\
-0.008 G & c < 0.1 \\
0 & \text{otherwise.}
\end{cases}
$$

The plastic risk multiplier is clamped after
$$
Δw = Δw_{STDP} + Δw_{LTP/LTD}, \qquad w_{t+1} = \mathrm{clip}(w_t + Δw, w_{min}, w_{max}).
$$

### 5.5 Action gating
$$
a_{gated} = a \odot (1 - I) \cdot w_{t+1} \cdot M.
$$
If `enforce_mfd=True` and $G > 0.1$, the magnitude of $a_{gated}$ is capped at $|a|$ component-wise.

## 6. Public API Summary
### 6.1 `GABAInhibitionGate`
- **Constructor arguments**: `params: GateParams | None`, `device: str | None`.
- **Methods**:
  - `forward(market_state, action) -> (Tensor, GateMetrics)` (no gradients).
  - `get_state() -> GateState`: clones internal buffers.
  - `set_state(state: GateState)`: restores buffers onto the module device.
  - `reset_state()`: zeroes GABA pools, resets `risk_weight` to 1, rewinds time.
  - `apply_hedge(strength: float)`: multiplicatively boosts GABA pools (`strength ∈ [0, 2]`).

### 6.2 Data Structures
- `GateParams`: tunable parameters for biophysics and safeguards.
- `GateState`: serialisable snapshot for warm-restart/resume.
- `GateMetrics`:
  - `inhibition`: post-clamp inhibition factor.
  - `gaba_level`: combined GABA pool level.
  - `risk_weight`: plastic risk multiplier after update.
  - `cycle_multiplier`: gamma/theta modulation applied this step.
  - `stdp_delta`: contribution from STDP timing rule.
  - `ltp_ltd_delta`: contribution from co-activity gate.

## 7. Telemetry and Observability
- Emit `GateMetrics` to TACL with per-sample tagging (instrument ID, strategy ID, timestamp).
- Recommended dashboards:
  - `inhibition` vs `vix` scatter to confirm monotonicity.
  - `risk_weight` histogram segmented by regime.
  - `stdp_delta`/`ltp_ltd_delta` running sums to detect drift.
- Alert thresholds: if average `cycle_multiplier` deviates from `1 ± 0.4` for >60 seconds, check oscillator timing.

## 8. Error Handling & Edge Cases
- Non-finite inputs ⇒ `ValueError`.
- Missing market keys ⇒ `KeyError`.
- `apply_hedge` with strength outside `[0, 2]` ⇒ `ValueError`.
- `reset_state` is idempotent; safe to call before or after `set_state`.

## 9. Testing & Validation
Implemented unit tests (`tests/test_gaba_inhibition_gate.py`) cover:
1. Volatility → inhibition monotonicity.
2. Risk multiplier bounds under prolonged stimulation.
3. Cycle modulation variability and determinism.
4. Device handling, hedge behaviour, and safety clamps.
5. State persistence (`get_state`/`set_state`) and new `reset_state` behaviour.
6. STDP/LTP/LTD telemetry sign expectations (`test_plasticity_metric_direction`).
7. MFD guarantee correctness for elevated inhibition.

Additional recommended checks:
- Scenario replay using recorded market bursts with `reset_state` at trading-session boundaries.
- Stress: saturate inputs with `vix=120`, `vol=1.2` to confirm clamps hold and telemetry stays finite.

## 10. Integration Guidelines
- Invoke `reset_state()` during strategy initialisation and at daily session open.
- Persist `GateState` snapshots alongside policy checkpoints to ensure continuity across restarts.
- When stacking multiple neuromodulator gates, apply GABA gate first to enforce inhibition before excitatory boosts.
- For reinforcement-learning fine-tuning, wrap the gate in a `torch.nn.Module` sequence but keep gradients off by design.

## 11. Future Extensions (Backlog)
- Adaptive oscillation frequencies conditioned on circadian market patterns.
- Explicit modelling of dopaminergic modulation via `rpe` once data becomes available.
- Batched forward pass for portfolio-level parallel execution.

