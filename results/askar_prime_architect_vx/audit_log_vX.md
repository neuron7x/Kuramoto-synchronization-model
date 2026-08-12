# PRIME_ARCHITECT_vX — audit_log
**target:** `ASKAR / OTS CAPITAL`
**prime_architect_pass_any:** `False`
**tradable_configurations:** `[]`

## narrow — 3-asset {XAUUSD, USA_500, SPY}
- source: `data/askar/*.parquet  (OHLC only)`
- n_assets = 3, n_bars = 15848
- l2_full_depth_available = **False**
- prime_architect_pass (unconditional) = **False**
- prime_architect_pass (regime-gated) = **False**

### unconditional gates
| gate | value | threshold | dir | passed |
|---|---|---|---|---|
| `permutation_p` | +0.449000 | +0.010000 | less_than | **False** |
| `r2_max_vs_factors` | +0.002403 | +0.050000 | less_than | **True** |
| `gamma_psd` | +1.394800 | +1.000000 | equal_to | **False** |
| `ic_test` | +0.007630 | +0.120000 | greater_than | **False** |
| `sharpe_test` | +0.973700 | +1.700000 | greater_than | **False** |
| `crr_test` | +1.157300 | +2.500000 | greater_than | **False** |

### regime-gated gates (λ₂ > train-median)
| gate | value | threshold | dir | passed |
|---|---|---|---|---|
| `gated_permutation_p` | NaN | +0.010000 | less_than | **False** |
| `gated_ic_test` | NaN | +0.120000 | greater_than | **False** |
| `gated_sharpe_test` | +1.651100 | +1.700000 | greater_than | **False** |
| `gated_crr_test` | +2.138700 | +2.500000 | greater_than | **False** |

<details><summary>stages</summary>

```json
{
  "find": {
    "n_bars": 15788,
    "median": 0.0,
    "p05": 0.0,
    "p95": 3.0,
    "fraction_below_1e-8": 0.539207,
    "freeze_out_detected": true
  },
  "prove": {
    "permutation_ic": 0.001297,
    "permutation_p": 0.449,
    "permutation_sigma": 0.121,
    "permutation_n_shuffles": 1000,
    "jitter_plus_ic": 0.002302,
    "jitter_minus_ic": -0.001583,
    "micro_noise_ic": -0.000352,
    "clean_ic": 0.001297
  },
  "measure": {
    "r2_momentum": 0.000968,
    "r2_volatility": 0.002403,
    "r2_mean_reversion": 0.000157,
    "r2_max_vs_factors": 0.002403,
    "gamma_psd": 1.3948,
    "gamma_target": 1.0,
    "gamma_tol": 0.05
  },
  "reproduce": {
    "ic_train": -0.001203,
    "ic_test": 0.00763,
    "sharpe_test": 0.9737,
    "maxdd_test": -0.134689,
    "ann_return_test": 0.155874,
    "crr_test": 1.1573
  },
  "reproduce_regime_gated": {
    "gate_threshold_lambda2": 0.0,
    "n_train_active": 5242,
    "n_test_active": 2032,
    "ic_train": NaN,
    "ic_test": NaN,
    "sharpe_test": 1.6511,
    "maxdd_test": -0.085253,
    "ann_return_test": 0.182333,
    "crr_test": 2.1387,
    "insufficient_active_bars": false,
    "permutation_p_active": null,
    "permutation_sigma_active": null
  }
}
```

</details>

## wide — 53-asset panel_hourly
- source: `data/askar_full/panel_hourly.parquet  (53 assets, hourly)`
- n_assets = 53, n_bars = 26930
- l2_full_depth_available = **False**
- prime_architect_pass (unconditional) = **False**
- prime_architect_pass (regime-gated) = **False**

### unconditional gates
| gate | value | threshold | dir | passed |
|---|---|---|---|---|
| `permutation_p` | +0.220000 | +0.010000 | less_than | **False** |
| `r2_max_vs_factors` | +0.002968 | +0.050000 | less_than | **True** |
| `gamma_psd` | +1.640300 | +1.000000 | equal_to | **False** |
| `ic_test` | +0.025219 | +0.120000 | greater_than | **False** |
| `sharpe_test` | +0.523800 | +1.700000 | greater_than | **False** |
| `crr_test` | +0.372000 | +2.500000 | greater_than | **False** |

### regime-gated gates (λ₂ > train-median)
| gate | value | threshold | dir | passed |
|---|---|---|---|---|
| `gated_permutation_p` | +0.043000 | +0.010000 | less_than | **False** |
| `gated_ic_test` | +0.026608 | +0.120000 | greater_than | **False** |
| `gated_sharpe_test` | +0.565000 | +1.700000 | greater_than | **False** |
| `gated_crr_test` | +0.365100 | +2.500000 | greater_than | **False** |

<details><summary>stages</summary>

```json
{
  "find": {
    "n_bars": 26870,
    "median": 7.159833,
    "p05": 1.869848,
    "p95": 12.429725,
    "fraction_below_1e-8": 0.016115,
    "freeze_out_detected": true
  },
  "prove": {
    "permutation_ic": 0.004631,
    "permutation_p": 0.22,
    "permutation_sigma": 0.752,
    "permutation_n_shuffles": 1000,
    "jitter_plus_ic": 0.00643,
    "jitter_minus_ic": 0.006512,
    "micro_noise_ic": 0.004632,
    "clean_ic": 0.004631
  },
  "measure": {
    "r2_momentum": 0.000676,
    "r2_volatility": 0.002968,
    "r2_mean_reversion": 0.000269,
    "r2_max_vs_factors": 0.002968,
    "gamma_psd": 1.6403,
    "gamma_target": 1.0,
    "gamma_tol": 0.05
  },
  "reproduce": {
    "ic_train": -0.004039,
    "ic_test": 0.025219,
    "sharpe_test": 0.5238,
    "maxdd_test": -0.141824,
    "ann_return_test": 0.052761,
    "crr_test": 0.372
  },
  "reproduce_regime_gated": {
    "gate_threshold_lambda2": 7.205277,
    "n_train_active": 9395,
    "n_test_active": 3959,
    "ic_train": 0.009857,
    "ic_test": 0.026608,
    "sharpe_test": 0.565,
    "maxdd_test": -0.094598,
    "ann_return_test": 0.034542,
    "crr_test": 0.3651,
    "insufficient_active_bars": false,
    "permutation_p_active": 0.043,
    "permutation_sigma_active": 1.647
  }
}
```

</details>

## adversarial self-audit
- **Zero-Hallucination ruling:** L2 depth inputs are not present in any committed parquet. Order-book invariants (I₀₃, depth freeze-out, microstructure liquidity tensor) are marked `substrate_unavailable` and excluded from every `prime_architect_pass` flag.
- **Curve-fit guard:** window=60 / threshold=0.30 inherited from PR #194 — no re-tuning per substrate. Verdict is gated on the held-out 30 % of each pipeline's own divergence series.
- **Substrate upgrade rule:** the narrow pipeline's regime-gated slice collapsed to a single unique combo value (3-node graph has too few variance modes). The wide pipeline re-runs the identical signal construction on 53 assets → 1326 possible edges vs. 3 in the narrow graph — if Ricci has topological content on Askar's data, the wide pipeline is where it must appear.
- **No partial credit:** `prime_architect_pass` in either block requires ALL listed gates to read `True`. Substrate-limited gates (NaN) force False. Any non-finite γ_PSD, R², IC, Sharpe, CRR or permutation-p fails the block.
