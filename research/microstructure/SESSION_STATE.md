# SESSION STATE — L2 Ricci edge (demo-ready snapshot)

**Frozen at:** 2026-04-18
**Commit ref:** see `git log main -- research/microstructure/`
**Substrate:** Binance USDT-M perp depth5@100ms, 10 symbols, 19,081 rows (~5.3 h)

---

## 1 · Headline verdict

| | |
|---|---|
| Edge verdict | **PROCEED** |
| Validation axes passed | **10 / 10** |
| Ablation / stress axes | **5 / 5** bounded and documented |
| Regime-conditional decomposition | **VOL_DRIVEN** (3.16× high/low) |
| Test base | **345 passed, 1 opt-in skip** |
| Deterministic replay | confirmed bit-exact across two runs |
| CI protection | `.github/workflows/l2-demo-gate.yml` |
| One-command demo | `make l2-demo` (~85 s) |
| Dashboard | `results/figures/index.html` (self-contained 7.5 KB) |
| Flat headline metrics | `results/L2_HEADLINE_METRICS.json` (44 keys) |

---

## 2 · Ten validation axes — all green

| # | Axis | Metric | Outcome |
|---|---|---|---|
| 1 | Kill test | IC = 0.122 | p = 0.002 |
| 2 | Block-bootstrap CI | [0.029, 0.210] | excludes 0 |
| 3 | Deflated Sharpe | DSR = 15.1 | Pr(real) ≈ 1.0 |
| 4 | Purged K-fold CV | mean IC = 0.122 | 5/5 folds positive |
| 5 | Mutual information | 0.078 nats | concordant with Spearman |
| 6 | Spectral β | 1.80 | RED regime |
| 7 | DFA Hurst | 1.014 | R² = 0.982 |
| 8 | Transfer Entropy | 45/45 pairs | BIDIRECTIONAL |
| 9 | Conditional TE (BTC) | 33/36 pairs | PRIVATE_FLOW |
| 10 | Walk-forward stability | 82.1% windows pos | STABLE_POSITIVE |

---

## 3 · Five ablation / stress axes — honest envelope

| Axis | Verdict | Honest interpretation |
|---|---|---|
| Hyperparameter (quantile × window) | SENSITIVE | f* drifts ±60%; all 9 cells < 0.50 ceiling |
| Leave-one-symbol-out | MIXED | min IC = 0.070; edge not BTC-concentrated |
| Hold-time (60–600 s) | ROBUST | 3/5 cells already profitable at f = 0 |
| Slippage stress | BOUND | max viable +3 bp/side; typical prod +0.5–1.5 bp |
| Taker-fee tier (3–6 bp) | RESILIENT | every VIP tier brackets below 0.50 |

---

## 4 · Canonical demo artifacts

| Path | Purpose |
|---|---|
| `research/microstructure/FINDINGS.md` | 10-axis + 5-ablation narrative |
| `research/microstructure/CHANGELOG.L2.md` | PR-by-PR session record |
| `research/microstructure/visualize.py` | figure renderer |
| `research/microstructure/dashboard.py` | HTML renderer |
| `scripts/run_l2_full_cycle.py` | one-command pipeline |
| `scripts/render_l2_figures.py` | figure CLI |
| `scripts/render_l2_dashboard.py` | dashboard CLI |
| `results/figures/fig{0..4}_*.png` | 5 canonical figures |
| `results/figures/index.html` | browsable HTML dashboard |
| `results/L2_FULL_CYCLE_MANIFEST.json` | SHA-256 replay audit |
| `results/gate_fixtures/*.json` | 3 bit-frozen gate values |

---

## 5 · Makefile entry points

```bash
make l2-help            # list every target
make l2-demo            # full pipeline (~85 s, needs substrate)
make l2-figures         # re-render figures from JSON (fast, no substrate)
make l2-dashboard       # regenerate HTML dashboard
make l2-open            # open dashboard in browser
make l2-smoke           # one-gate demo-readiness test
make l2-deterministic   # bit-identical replay audit (~170 s)
make l2-ablations       # run all 5 ablation axes
make l2-test            # every tests/test_l2_*.py
```

Protection: `.github/workflows/l2-demo-gate.yml` runs `l2-test` +
`l2-smoke` + Makefile audit on every PR touching the L2 surface.

Override substrate: `L2_DATA_DIR=/path/to/parquets make l2-demo`

---

## 6 · Coherence gates

Seven independent gate suites prevent silent drift:

1. **Deterministic replay** — two full cycles must produce bit-identical SHA-256
2. **Doc-data consistency** — README numbers match artifact JSON to 3 decimals
3. **Per-axis invariants** — algebraic identities per axis (11 assertions)
4. **Artifact schema registry** — required keys per L2_*.json (14 files)
5. **CLI discoverability** — every script has --help, --data-dir, --output (46 assertions)
6. **Performance budget** — cycle ≤ 240 s; stages ≤ 120 s each
7. **E2E demo smoke** — all artifacts + gates + figures + verdict match

Plus 7 property-based tests (Hypothesis) covering DFA scale-invariance,
TE non-negativity, CTE determinism, walk-forward quantile monotonicity.

---

## 7 · Honest limitations

Documented in FINDINGS.md §8. Key points:

- **Single session.** All numbers from one ~5-hour window. Multi-session
  stability not yet measured at publishable level.
- **No live-paper P&L.** Simulation only; no exchange fills, no queue
  position modeling, no adverse selection on taker legs.
- **Hyperparameter f\* not robust** (SENSITIVE ablation verdict). Read
  f\* = 0.232 as "likely achievable", not "precisely calibrated."
- **Slippage ceiling +3 bp/side** (BOUND). Production typically stays
  below this, but above it the strategy collapses.
- **Single asset class.** USDT-M crypto perps only.

These are documented, not hidden. Every verdict sits alongside its bound.

---

## 8 · What would change this snapshot

- Multi-session substrate (3–7 days) → elevates walk-forward verdict
  from "Session 1" to "cross-session stable"
- Live-paper testnet results → converts simulation numbers into
  exchange-verified fills
- U2 execution engine (post-only maker with queue position) → turns
  f\* from a statistical target into an operational number
- Cross-asset transfer (USD-margined futures) → tests generalization

None of these are in scope for this snapshot. Everything above this line is
**observed**, not forecast.
