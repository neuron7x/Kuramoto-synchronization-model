# D-002K-P1 — Source & Observable Contract for Funding-Liquidity

## §0 Mission (narrow funding-liquidity binding, NOT broad)

D-002K-P1 binds the six D-002K-P0-locked observable families to
P1B-audit-surviving **funding-liquidity-relevant** public sources, the
three D-002K crisis windows (CW3/CW4/CW5), point-in-time release/vintage
boundaries, and the single P0-locked primary metric
`pre_post_standardized_mean_shift`.

This is a **narrow** contract by design. D-002K is funding-liquidity
**ONLY**. No contagion / balance-sheet / cross-asset / interbank-network
sources are bound. The narrowing is the structural design response to
the inherited `effect_too_small` axis (D-002J-P7 `POWER_GATE_REFUSED_
UNDERPOWERED`). Narrowing scope is legitimate design; loosening
statistics at fixed scope would be laundering and is forbidden.

**This phase ingests no data, fetches no bytes, runs no scoring, fits
no model, and authorises no canonical run.** It is a manifest only.

- Parent prereg: `docs/governance/D002K_PREREGISTRATION.yaml`
  (sha256 `2cd923810bf64547cd86ecb403bfd3f12a799cb16c3d10ebc07bc05865fee43f`, frozen)
- Parent P1B source registry: `artifacts/d002j/data_registry/source_registry_v1.json`
  (sha256 `f1899b7a882b4b3efbebb54e3dc942c079839f77f981273e2dd09757973b14ec`, frozen)
- Parent P1B audit: `artifacts/d002j/data_registry/source_provenance_audit_v1.json`
  (sha256 `1e6f89299315bdc85d7929aa0883b44eee24af4474e33d4a2db95da446f7786c`, frozen)
- Parent P2 window registry: `artifacts/d002j/crisis_windows/crisis_window_registry_v1.json`
  (sha256 `41f281d9e97fbf49725f0eb1a1bb7b45865c14cdc5c525ea96231ef0aa651e8f`, frozen)

## §1 Per-family observable table (6 families)

All bound sources are P1B-audit-surviving (audit_status ∈
{VERIFIED, PARTIAL}). Window legend: CW3 = `CW3_US_REPO_SPIKE_2019`,
CW4 = `CW4_COVID_DASH_FOR_CASH_2020`, CW5 = `CW5_UK_GILT_LDI_2022`.

| P0 family | observable_id | source (audit) | series | windows | vintage_req |
|---|---|---|---|---|---|
| level_shift | obs_sofr_level_shift | NYFED_SOFR (VERIFIED) | SOFR daily | CW3, CW4 | no |
| level_shift | obs_alfred_tedrate_vintage_level_shift_uk_gilt | ALFRED (PARTIAL) | ALFRED vintage of TEDRATE/OIS-Treasury funding-spread proxy | CW5 | **yes** |
| spread_widening | obs_sofr_ois_spread_widening | FED_H15 (VERIFIED) | H.15 secured-vs-unsecured overnight spread | CW3, CW4 | no |
| volatility_burst | obs_ofr_repo_haircut_volatility_burst | OFR_REPO_DATA (VERIFIED) | OFR tri-party haircut dispersion / dealer-money-fund volume | CW3, CW4 | no |
| volatility_burst | obs_vix_control_covariate | CBOE_VIX (PARTIAL) | VIXCLS — **CONTROL covariate only** | CW3, CW4, CW5 | no |
| recovery_time | obs_ofr_fsi_funding_recovery_time | OFR_FSI (VERIFIED) | OFR-FSI **funding subcomponent only** | CW3, CW4, CW5 | no |
| transition_steepness | obs_sofr_99pct_transition_steepness | NYFED_SOFR (VERIFIED) | SOFR 99th-percentile daily series | CW3, CW4 | no |
| stress_persistence | obs_stlfsi_funding_stress_persistence | STLFSI (VERIFIED) | STLFSI4 US financial-stress composite | CW3, CW4 | **yes** |

Every one of the six P0-locked families
(`level_shift`, `spread_widening`, `volatility_burst`, `recovery_time`,
`transition_steepness`, `stress_persistence`) is covered by ≥1
funding-liquidity observable.

## §2 Release-boundary / point-in-time discipline

The D-002I/D-002J look-ahead lesson is applied at the **observable
layer**. Every observable carries explicit look-ahead invariants:

```
observation_date <= decision_date
release_date     <= decision_date
```

For **revisable** series the contract additionally requires
`vintage_required = true` with `vintage_field = release_date`, so the
point-in-time value as it stood on the decision date is used — never a
post-hoc revised value:

- `obs_stlfsi_funding_stress_persistence` — STLFSI is a constructed
  composite whose constituents are re-estimated (STLFSI → STLFSI2 →
  STLFSI4); vintaged.
- `obs_alfred_tedrate_vintage_level_shift_uk_gilt` — ALFRED is the
  archival real-time lens; the CW5 funding-spread proxy is read at its
  point-in-time vintage (Croushore 2011 look-ahead-bias argument).

This makes the point-in-time invariant **executable**, not asserted by
stub. ≥1 vintage_required observable is a hard floor (here: 2).

## §3 Control covariates separated

`obs_vix_control_covariate` is bound with `role = control_covariate`,
NOT `funding_liquidity_observable`. VIX (VIXCLS) is a market-wide
implied-volatility control used only to condition / de-confound
market-wide risk-off — it never feeds the funding-liquidity endpoint.

This echoes the cross-asset ≠ interbank discipline: a market-wide
volatility index is not a Kuramoto-style coherence observable and
cross-asset coherence does not prove interbank contagion. The
control/observable separation is enforced by
`test_vix_class_marked_control_not_observable`.

## §4 Primary-metric mapping

Every observable — funding-liquidity observable and control covariate
alike — maps to the single P0-locked primary metric:

```
primary_metric_mapping = pre_post_standardized_mean_shift
```

defined (P0 lock) as the standardized mean shift (Cohen's-d form) of the
`funding_stress_index` observable between the locked pre-window baseline
and the locked in-crisis window, computed identically for every crisis
window and every matched placebo window. Exactly one primary endpoint.

## §5 Forbidden interpretations + no-rescue boundary

Every observable carries an explicit `forbidden_use` list. Across the
contract the following are forbidden:

- D-002K is **not** a systemic-risk predictor.
- D-002K is **not** bank-level validation.
- Cross-asset coherence does **not** prove interbank contagion.
- A control covariate is **not** a funding-liquidity observable.
- Post-hoc revised data is **not** usable for in-window prediction
  (vintage discipline).

**No-rescue boundary.** D-002J remains terminally **REFUSED** at P7
(`POWER_GATE_REFUSED_UNDERPOWERED`, axis `effect_too_small`). D-002K-P1
does NOT reopen, mutate, amend, or rescue D-002J and does NOT authorise
any D-002J-P8. D-002K is narrow **by design**, not by relaxed
statistics. D-002J-P1A and D-002J-P7 stay `TERMINAL_REJECTED` /
`TERMINAL_REFUSED` and retained in the DAG.

**Decision: `D002K_SOURCE_OBSERVABLE_CONTRACT_READY`.**
Next legal node: `D-002K-P2` (matched placebo windows).
