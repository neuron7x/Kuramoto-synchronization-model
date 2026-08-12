# D-002J-P5 — Financial-Mechanistic Substrate Design Space v1

Phase: **D002J-P5**. Parent: **D002J-P4** (`POSITIVE_CONTROLS_READY`).
Decision: **SUBSTRATE_CANDIDATES_READY**.

This document is the operator-locked rationale for the three admitted
financial-mechanistic substrate candidates. It is a declaration surface:
forbidden-claim phrases that appear here are *negated* inside the
forbidden / scope-guard blocks (§4, §5) and are excluded from the strict
forbidden-phrase scan; the substrate **summary** JSON carries no
forbidden phrases at all.

---

## §0 What is a financial-mechanistic substrate (vs an abstract graph)

A **substrate** is a *mechanism-bearing generative model* of a financial
network or process whose observable outputs can be (a) measured against
P2 crisis windows and (b) attacked by P6 null families. The defining
property is an **explicit economic mechanism**: every state variable and
every parameter has an economic meaning, and the update rule encodes a
named financial channel (rollover, cascade, regime switch).

This is the opposite of an *abstract graph aesthetic* — a generic
synchronisation/curvature model with no economic referent, where
"nodes" and "edges" carry no balance-sheet interpretation. Abstract
graph models are explicitly NOT admissible here: they cannot bind a P4
positive control nor state a non-identifiability boundary in economic
terms.

A substrate is a **generative** model. Calibration / fitting to real
series is P7+ territory and is out of scope for P5.

---

## §1 The seven candidate families surveyed

| Family | Class | Mechanism | PC analogue |
|---|---|---|---|
| `balance_sheet_pressure` | contagion | capital-ratio degradation + portfolio-overlap spillover | PC3 |
| `funding_liquidity_rollover` | funding/liquidity | short-term funding rollover stress on a funding graph | PC1 |
| `cross_exposure_contagion_proxy` | contagion | DebtRank cascade on a reconstructed exposure network | PC2 |
| `repo_collateral_stress` | funding/liquidity | haircut / collateral-chain propagation | PC1 |
| `volatility_credit_spread_regime` | market/info | vol / credit-spread regime detection | PC4 |
| `information_constraint_vintage_model` | market/info | point-in-time / vintage-aware state model | PC5 |
| `official_response_intervention_layer` | market/info | intervention-event regime-shift overlay | PC6 |

---

## §2 Selection criterion (operator-locked)

The criterion is **operator-locked** and is encoded verbatim in
`substrate_candidate_manifest_v1.json.selection_criterion`. No loosening
to fit.

1. **EXACTLY 3** substrates admitted — not 2, not 4.
2. **≥1 contagion-class** (`cross_exposure_contagion_proxy` OR
   `balance_sheet_pressure`) — maps PC2/PC3.
3. **≥1 funding/liquidity-class** (`funding_liquidity_rollover` OR
   `repo_collateral_stress`) — maps PC1.
4. **≥1 market-wide or information-class**
   (`volatility_credit_spread_regime` OR
   `information_constraint_vintage_model`) — maps PC4/PC5.
5. The 3 chosen must collectively cover **≥4 of 6** P2 crisis windows.
6. **NO** substrate that requires real interbank transaction microdata
   (D-002J is public-source only; cross-asset coherence ≠ interbank
   funding network per Brunetti e-MID).

**Admitted set:**

- `funding_liquidity_rollover` (funding/liquidity — PC1)
- `cross_exposure_contagion_proxy` (contagion — PC2)
- `volatility_credit_spread_regime` (market/info — PC4)

Each binds ≥2 P1B-surviving (VERIFIED/PARTIAL) sources, ≥1 P2 window,
≥1 P3 adapter, ≥1 P4 control, and forward-declares ≥2 P6 null families.
Collective window coverage = **6/6** (≥4 floor met). No admitted
substrate requires real interbank transaction microdata. The honest
2-with-INCOMPLETE fallback was NOT needed: all three bind cleanly.

---

## §3 The three admitted substrates

### §3.1 `funding_liquidity_rollover` — funding/liquidity-class (PC1)

- **Mechanism**: maturing short-term funding is rolled over each period
  at the prevailing market funding rate; the rollover ratio degrades as
  the funding rate rises above baseline, and the funding gap accumulates
  whenever rollover falls below the solvency-feasible floor.
- **State**: `funding_gap`, `rollover_ratio`.
- **Observables**: `funding_stress_index`, `rollover_failure_count`.
- **Sources**: `NYFED_SOFR` (VERIFIED), `OFR_REPO_DATA` (VERIFIED),
  `FED_H15` (VERIFIED).
- **Windows**: CW3 (2019 repo spike — primary), CW4 (COVID
  dash-for-cash), CW5 (UK gilt/LDI).
- **PC analogue**: `PC1_LIQUIDITY_SHOCK_INJECTION`.
- **Parameters**: `base_rollover_ratio`, `rollover_solvency_floor`,
  `funding_rate_baseline`, `funding_rate_stress_jump`, `stress_decay`
  (each economic; see manifest).
- **Non-identifiability**: cannot separate a genuine rollover-stress
  episode from an equal-magnitude exogenous policy-rate hike using the
  rate path alone.
- **Power path**: step + accumulating-count signature; detectable at
  horizon ≥ ~60 and stress-jump ≥ ~1× baseline-spread; P7 computes
  `n_min`.

### §3.2 `cross_exposure_contagion_proxy` — contagion-class (PC2)

- **Mechanism**: a DebtRank-style impact cascade propagates a seed
  balance-sheet shock across a max-entropy-**reconstructed** exposure
  network in damped rounds until the cascade saturates.
- **State**: `equity_loss_fraction`, `impaired_indicator`.
- **Observables**: `cascade_impaired_fraction`, `systemic_loss_index`.
- **Sources**: `LIT_NETWORK_RECON` (VERIFIED),
  `LIT_INTERBANK_CONTAGION` (VERIFIED), `BIS_QR_NETWORK` (VERIFIED).
- **Windows**: CW1 (GFC), CW2 (Eurozone), CW6 (2023 regional banking).
- **PC analogue**: `PC2_CONTAGION_CASCADE_INJECTION`.
- **Parameters**: `exposure_intensity`, `recovery_rate`,
  `seed_shock_fraction`, `seed_shock_magnitude`, `damping`.
- **Non-identifiability**: the reconstructed network is a max-entropy
  guess from public aggregates; a cascade pattern is observationally
  equivalent to a shared-asset shock and does NOT identify the true
  interbank topology.
- **Power path**: saturation gap vs no-default null is large above the
  percolation threshold; detectable with `n_nodes` ≥ ~20; P7 computes
  `n_min`.

### §3.3 `volatility_credit_spread_regime` — market/info-class (PC4)

- **Mechanism**: a sticky latent two-regime (calm vs stressed) process
  governs the conditional variance of a market-wide stress index and
  the mean-reverting target of a composite credit-spread level.
- **State**: `regime_indicator`, `credit_spread_level`.
- **Observables**: `realised_volatility`, `credit_spread_level`.
- **Sources**: `CBOE_VIX` (PARTIAL), `STLFSI` (VERIFIED), `OFR_FSI`
  (VERIFIED).
- **Windows**: CW1 (GFC market-wide leg), CW4 (COVID dash-for-cash).
- **PC analogue**: `PC4_MARKET_WIDE_VOLATILITY_REGIME_SWITCH`.
- **Parameters**: `calm_vol`, `stress_vol`, `calm_spread`,
  `stress_spread`, `regime_persistence`.
- **Non-identifiability**: detects the market-wide regime *state*, not
  its mechanism; cannot localise stress to any institution.
- **Power path**: separation large for `stress_vol/calm_vol` ≥ ~3 and
  `stress_spread/calm_spread` ≥ ~3 at horizon ≥ ~80; P7 computes
  `n_min`.

---

## §4 Cross-asset vs interbank distinction — Brunetti e-MID scope guard

This is a **hard invariant** and an **executable** test, not narrative.

Brunetti et al. (e-MID study) document that in a crisis the **physical
interbank funding network CONTRACTS** (banks pull bilateral lines)
**while cross-asset correlation networks EXPAND** (everything co-moves).
The two networks move in *opposite* directions. Therefore:

> Cross-asset coherence does **NOT** prove interbank funding contagion.
> A correlation-network result is **NOT** evidence of the physical
> interbank funding topology.

Enforcement:

- No admitted substrate may require real interbank transaction
  microdata. Each substrate's
  `metadata["requires_real_interbank_transaction_data"]` is `false`,
  asserted by `test_no_substrate_requires_real_interbank_transaction_data`.
- `cross_exposure_contagion_proxy` runs on a **reconstructed** network
  from public aggregates only; its non-identifiability boundary states
  it cannot identify the true interbank topology.
- The forbidden-phrase scan
  (`test_cross_asset_interbank_distinction_documented`) fails on any
  `cross-asset … interbank … (proves|validates|confirms)` sequence
  outside the forbidden/scope-guard declaration blocks, reusing the
  strict/safe-files split pattern from P2's
  `test_no_cross_asset_interbank_overclaim`.

---

## §5 Forbidden claims aggregate

The following claims are forbidden for every admitted substrate (negated
declaration block — strict scan excludes this file):

- "cross-asset coherence proves interbank contagion"
- "cross-asset interbank validated" / "cross-asset interbank proves" /
  "cross-asset interbank confirms"
- "this substrate validates real-bank systemic risk"
- "a reconstructed-network cascade proves the true interbank exposure
  topology"
- "public funding-rate spread proves a physical interbank funding
  network"
- "a market-wide vol/spread regime proves institution-level distress"
- "passing this substrate authorises a canonical run"

P5 does NOT implement nulls (P6), does NOT compute power (P7), does NOT
run canonically (P8), does NOT fit real data, and does NOT edit the
D-002J prereg.

---

## §6 Mapping table: substrate × {sources, windows, PC analogue, required nulls}

| Substrate | Class | Sources (P1B status) | Windows | PC analogue | Required P6 null families (fwd-decl) |
|---|---|---|---|---|---|
| `funding_liquidity_rollover` | funding/liquidity | NYFED_SOFR (V), OFR_REPO_DATA (V), FED_H15 (V) | CW3, CW4, CW5 | PC1 | `phase_shuffled_funding_rate_null`, `block_bootstrap_rollover_null` |
| `cross_exposure_contagion_proxy` | contagion | LIT_NETWORK_RECON (V), LIT_INTERBANK_CONTAGION (V), BIS_QR_NETWORK (V) | CW1, CW2, CW6 | PC2 | `degree_preserving_rewired_network_null`, `constant_payload_no_cascade_null` |
| `volatility_credit_spread_regime` | market/info | CBOE_VIX (P), STLFSI (V), OFR_FSI (V) | CW1, CW4 | PC4 | `single_regime_constant_variance_null`, `iid_shuffled_spread_null` |

(V = VERIFIED, P = PARTIAL — both P1B-surviving.) Collective window
coverage = {CW1, CW2, CW3, CW4, CW5, CW6} = **6/6**.

---

Lineage: `D-002G → D-002H REFUSED → D-002I → D-002J prereg #694 → P1
#695 → P1A #697 REJECTED → P1B #698 → P2 #699 → P2.5 #700 → P3 #701 →
P4 #702 → P5 this PR (SUBSTRATE_CANDIDATES_READY)`.

Next legal PR: `feat(x10r,D-002J-P6): implement null model hierarchy v1`.
