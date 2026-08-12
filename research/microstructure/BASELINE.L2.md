# BASELINE — L2 Ricci edge snapshot

**Frozen:** 2026-04-18, after the 7-cycle tech-debt elimination loop
**Commit ref:** see \`git log main -- research/microstructure/ | head\`
**Substrate:** Binance USDT-M perp depth5@100ms, 10 symbols, 19,081 rows (~5.3 h)

This file is the **canonical post-cycle baseline** — numbers below are
bit-frozen snapshots of \`results/L2_*.json\` as of the commit that
introduces this file. Any divergence should be accompanied by a commit
message explaining *why* the baseline moves.

---

## Headline verdict

| | |
|---|---|
| Edge verdict | **PROCEED** |
| Validation axes green | **10 / 10** |
| Ablation / stress axes documented | **5 / 5** |
| Test base | **374 passed, 1 opt-in skip** |
| Deterministic replay | bit-exact across two runs |
| CI protection | `.github/workflows/l2-demo-gate.yml` |

## Canonical numbers

| Metric | Value |
|---|---|
| IC pooled | **0.1223** |
| IC high-vol (rv-q75) | 0.2262 |
| IC low-vol | 0.0716 |
| Bootstrap 95% CI | [0.0285, 0.2096] |
| Deflated Sharpe | 15.12 (Pr_real ≈ 1.0) |
| Purged K-fold mean IC | 0.1220 (5/5 folds positive) |
| Mutual information | 0.0784 nats |
| Spectral β | 1.80 (RED) |
| DFA Hurst | 1.014 (R² = 0.982) |
| Transfer Entropy | 45/45 pairs BIDIRECTIONAL |
| Conditional TE (BTC) | 33/36 pairs PRIVATE_FLOW |
| Walk-forward | 82.1% windows positive (STABLE_POSITIVE) |
| Break-even maker fraction (canonical) | **0.23167** |

## Ablation / stress envelope

| Axis | Verdict | Max viable / max drift |
|---|---|---|
| Hyperparameter (q × window) | SENSITIVE | max drift 60.4% |
| Leave-one-symbol-out | MIXED | min IC 0.070 |
| Hold-time (60–600 s) | ROBUST | 3/5 already profitable at f=0 |
| Slippage stress | BOUND | max viable +3 bp/side |
| Taker-fee tier | RESILIENT | all 4 tiers bracket below 0.50 |

## 7-cycle tech-debt elimination (this session)

| # | Cycle | Outcome |
|---|---|---|
| 1 | Shared CLI common module | `l2_cli.py` + 11 tests |
| 2 | Refactor 14 scripts to shared helpers | −258 net LoC |
| 3 | Test-artifact loading consolidation | `l2_artifacts.py` + 6 tests, −64 net LoC |
| 4 | Dead-code audit | 3-gate standing test, 0 dead code found |
| 5 | Doc contradiction audit | 1 typo fixed, 2 gates added |
| 6 | GitHub workflow hygiene | 7 hygiene gates added, trigger paths expanded |
| 7 | Full-cycle integration + baseline freeze | this file |

## Regenerate

```bash
make l2-demo           # full pipeline (~85 s) + figures + dashboard
make l2-ablations      # 5 ablation / stress axes
make l2-test           # 374 tests
make l2-open           # view dashboard
```

Override substrate: `L2_DATA_DIR=/path/to/parquets make l2-demo`
