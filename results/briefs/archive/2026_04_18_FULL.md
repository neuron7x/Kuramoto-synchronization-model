# GeoSync / L2 Kill Test — Morning Brief

**Date:** 2026-04-18
**Session:** overnight 2026-04-17 22:00 → 2026-04-18 18:00 (local)
**Substrate:** Binance USDT-M perpetuals (BTC/ETH/SOL/BNB/XRP/ADA/AVAX/LINK/DOT/POL), depth5@100ms, 5h14m clean + second 8h session in progress.

---

## TL;DR

1. **The edge exists on real L2 substrate.** Ricci cross-sectional κ_min
   predicts 3-min forward mid-return with IC = +0.122 (full window,
   permutation p = 0.002). This is NOT statistical noise.
2. **The edge is intermittent, modulated by volatility.** Rolling
   realized-vol regime filter (threshold calibrated on first half,
   applied to second half OOS) lifts IC to +0.236 — 2.03× uplift.
3. **The edge does not clear taker costs.** With 9.80 bp round-trip
   cost, per-trade net P&L is **negative** (-5 to -7 bp). The signal
   is REAL but SUB-ECONOMIC at taker prices.

---

## The three-decomposition truth

Every significance claim in financial time series needs three
independent audits:

| Axis | Test | Result |
|---|---|---|
| **Temporal** | rolling walk-forward 56 windows | 82% IC > 0, ρ with RV regime +0.352 *** |
| **Structural** | per-symbol IC decomposition | 10/10 symbols positive (range +0.056 to +0.178) |
| **Economic** | P&L sim with real cost model | gross +3-5 bp < cost 9.8 bp → **net negative at taker prices** |

All three are needed. A signal can pass temporal + structural and still
fail economic. The Ricci signal did exactly this. That is not failure;
that is RESOLUTION — we now know precisely what the signal is.

---

## Key numbers

### Full-window gate (all 5h14m, 19,081 rows × 10 symbols)

```
IC_signal            = +0.1223
residual_IC (ortho)  = +0.1130   (orthogonal to vol/return/OFI)
permutation_shuffle  = p 0.002
horizon_IC           = +0.10 to +0.12 across 60-300 s (stable lead)
verdict              = PROCEED  (no gate failures)
```

### 50/50 split OOS (threshold calibrated on train half)

```
TEST unconditional         IC = +0.116   frac_on = 100.0 %
TEST q50  thr from train   IC = +0.202   frac_on =  43.9 %
TEST q75  thr from train   IC = +0.236   frac_on =  36.3 %
→ threshold generalizes within-session; 2.03× uplift confirmed OOS.
```

### Horizon sweep (clean bell shape)

```
h=30s   uncond +0.061   q75 +0.130
h=60s   uncond +0.104   q75 +0.205
h=180s  uncond +0.122   q75 +0.226   ← peak for both
h=300s  uncond +0.103   q75 +0.221
h=600s  uncond +0.100   q75 +0.187
h=900s  uncond +0.066   q75 +0.085
h=1200s uncond +0.004   q75 -0.054   ← edge inverts long-range
```

Design choice `_PRIMARY_HORIZON_SEC = 180` empirically confirmed.

### Walk-forward calibration honest limit

Rolling 60-min calibration + 30-min evaluation: uplift positive in only
1 of 7 (q50) / 1 of 5 (q75) steps. Regime threshold needs **≥ 2 hours**
of recent substrate to stabilize. Short-horizon recalibration fails.

### Trading simulation with realistic costs

```
cost model: 2*(4bp taker) + 2*half_spread = 9.80 bp round-trip

                          n_trades  win%   gross     cost    net     Sharpe
UNCONDITIONAL             86        24 %   +3.3 bp   9.8     -6.5    -0.45
REGIME_Q75                21        38 %   +4.9 bp   9.8     -4.9    -0.23
```

Interpretation: IC=0.22 does **NOT** mean +22 bp per trade. IC is a
scale-free rank correlation. Gross per trade matches theory:
`IC × std(fwd_return)` ≈ 0.22 × 20 bp ≈ 4.4 bp. Observed 3-5 bp.

---

## Architectural truth (the insight)

The next improvement is **not another predictor** — it is **execution**.

Execution-cost sweep (`scripts/l2_execution_cost_sweep.py`) computes
break-even maker-fill fraction at which mean net P&L = 0:

```
strategy        maker%   rtc_bp   mean_net_bp   SR_ann (raw)
UNCONDITIONAL    0 %     +9.80    -6.51         -187
UNCONDITIONAL   54 %     +3.29     0.00              0   ← break-even
UNCONDITIONAL   70 %     +1.40    +1.89            +54
UNCONDITIONAL  100 %     -2.20    +5.49           +158
REGIME_Q75       0 %     +9.80    -4.89            -95
REGIME_Q75      41 %     +4.93     0.00              0   ← break-even
REGIME_Q75      70 %     +1.40    +3.51            +69
REGIME_Q75     100 %     -2.20    +7.11           +139
```

(SR_ann raw assumes trade independence — divide by ~10 for a
realistic impact/latency/inventory haircut.)

### Business criterion (ultra-concrete)

> If Askar's Binance execution stack delivers **≥ 45 % maker fills** on
> a 10-perp basket rotation every 3 min → deploy `REGIME_Q75` at
> paper-trade first (SR_ann realistic ≈ 5-7).
> If maker fraction < 40 % → **shelf the signal** and look elsewhere.

The regime filter is not just a predictor enhancement — it
**lowers the break-even maker fraction by 14 percentage points**
(54.3 % → 40.7 %) because gross-per-trade is higher in active regimes.

---

## What was ruled out

- **Full-window PROCEED as sufficient evidence.** Recursive bisection
  revealed 3/8 octiles with IC < −0.05 hidden inside the average.
- **circular_shift as a gating test at halved samples.** It loses
  statistical power on autocorrelated signals — AE-audit removed it
  as a gate (kept as advisory) in PR #236.
- **`IC_signal > max(IC_baselines)` as a gate.** Non-AE addition;
  produces false KILLs on purely-orthogonal signals. Removed in
  PR #236.
- **Single-horizon myopia.** Edge exists across 60-600 s; sharpest
  at 180 s; inverts past 900 s.

---

## Session 2 (in progress) — EARLY SIGNAL CHECK

Fresh 8h L2 collection in `data/binance_l2_perp_v2/`, started
2026-04-18 00:00 local. ETA finish 08:00 local.

**Pilot cross-session on first 0.9 h of Session 2 data** (subject to
revision at full-session completion):

```
Session 1  (5h14m, daytime): unconditional IC = +0.1223  p < 0.01
Session 2  (  0.9h, overnight): unconditional IC = -0.2174  p < 0.01
                                 → signal POLARITY INVERTED
```

**RV-decile analysis on Session 1** (`scripts/l2_rv_decile_analysis.py`)
reveals a non-monotonic U-shape:

```
bucket   rv_upper   frac    IC       p_perm   verdict
D1       6.7e-5     9.8%   +0.3236   0.002    PROCEED   ← lowest-RV decile
D2       7.4e-5     9.8%   -0.0815   0.200    KILL
D3       8.1e-5     9.8%   -0.0226   0.728    KILL
D4       8.8e-5     9.8%   +0.0100   0.880    KILL
D5       9.7e-5     9.8%   +0.0276   0.639    KILL
D6       1.1e-4     9.8%   +0.1210   0.038    KILL    ← borderline
D7       1.2e-4     9.8%   +0.0562   0.323    KILL
D8       1.5e-4     9.8%   +0.1298   0.038    KILL    ← borderline
D9       2.1e-4     9.8%   +0.1646   0.010    PROCEED
D10      3.7e-4     9.8%   +0.4009   0.002    PROCEED ← highest-RV decile
```

D1 AND D10 both strongly positive; middle deciles dead. The naive
"higher RV → higher IC" story (Spearman ρ=+0.35) hid this U-shape.

Session 2's RV range sits entirely inside Session 1's D1–D5 band
(quieter even than D1). Yet Session 2 shows **strongly negative** IC.
This suggests the regime axis is **NOT purely RV magnitude** — there is
also a diurnal / liquidity-schedule component. Session 2 being overnight
(Friday 00:00 local onward) may be in a fundamentally different
microstructure regime that inverts the sign of the edge.

**Revised (preliminary) architectural hypothesis:**

```
Overnight/quiet regime:  Ricci predicts mean reversion → trade OPPOSITE
Daytime/active regime:   Ricci predicts continuation  → trade WITH signal
Middle regime:           no tradeable polarity
```

If this hypothesis holds as Session 2 accumulates more data, the
architecture evolves from "filter on RV" to **"sign-flip on regime"**,
potentially doubling the effective coverage (use edge in both modes
instead of filtering one out).

**[Revised when v2 reaches ≥ 4 h of data]**

---

## Next one step

Maker-side execution simulator. Inputs: existing substrate + fill-rate
distribution assumption. Output: blended net P&L at various maker/
taker mixes. If blended net > 2 bp at 70/30 maker/taker → greenlight a
Binance testnet paper-trade.

No more predictor research until execution-path is proven out.
