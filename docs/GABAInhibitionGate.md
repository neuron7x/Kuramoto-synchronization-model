# GABA Inhibition Gate — Design Notes

**Purpose.** Inhibit impulsive actions under threat (volatility), modulate by gamma/theta cycles, adapt weights by STDP and LTP/LTD. Telemetry exported to TACL.

**Inputs**: vix, vol, ret, pos, rpe, delta_t_ms.  **Outputs**: gated_action, metrics.

**Safety**
- Clamp risk_weight ∈ [0.5, 1.5]
- Clamp inhibition ≤ 0.95
- All updates under @torch.no_grad() to avoid gradient leaks into policy.

**TACL hooks**
- Emit metrics: inhibition, gaba_level, risk_weight.
- MFD policy: if `ΔF > 0` after enabling gate (latency + incoherence), auto-fallback to pass-through and alert.

**Falsification tests** (Popper):
1. Disable inhibition ⇒ drawdown and trading frequency increase. Expect ≥30% rise in trade count on same signals.
2. Spike VIX to 2× ⇒ inhibition ↑ and leverage ↓. Expect position notional ↓ by ≥40%.
3. Positive timing (Δt>0) in stable regime ⇒ risk_weight increases; negative timing ⇒ decreases.
