# FX-native foundation · relation to cross-asset Kuramoto line

**Prepared by:** Claude Code (MODE_A, §5 of FX-native protocol).
**Binding caveat (§K7):** this file **does not** decide portfolio
priority. It frames the four required questions and recommends a
label. Yaroslav resolves the human gate.

---

## The competing line, stated concretely

`~/spikes/cross_asset_sync_regime/` — "v2" cross-asset Kuramoto
regime strategy. Key artefacts (from project memory, replay-hashed):

- Universe (8 assets): **BTC, ETH, SPY, QQQ, GLD, TLT, DXY, VIX** (Binance + yfinance). **No FX majors.**
- Method: 60-day detrended log returns → Hilbert phases → Kuramoto
  `R(t) = |(1/N) Σ exp(iφ_k)|` smoothed 30 days → train-only q33/q66
  quantile regimes → risk-parity within regime bucket + 15 % vol target
  + 1.5× cap → daily rebalance, 10 bps costs, strict no-look-ahead.
- OOS (2023-10 → 2026-04, 651 days):
  **Sharpe +1.262** vs B&H BTC +0.802, **Max DD −16.76 %** vs BTC
  −49.53 % (66 % reduction), bootstrap Sharpe CI95 [+0.019, +2.616].
- Walk-forward 5-split: median Sharpe +0.942, beats BTC in 4/5 splits.
- Live paper-trading started 2026-04-11, day-90 gate ≈ 2026-07-10.
- Production engine `core/kuramoto/` in GeoSync (PR #136 merged
  2026-04-05) — 12 modules, 100+ tests, mypy --strict clean. Used in an
  EUREKA attempt that **lost** to the simpler v2 toy ("more physics ≠
  more alpha" — documented in spike annex, not buried).
- Track-A equities-only (SPY, QQQ, DIA, IWM, EFA, EEM, GLD, TLT):
  **MARGINAL** (Sharpe +1.05 beats 60/40 but loses to SPY). Lesson:
  v2 is specifically a **multi-vol-grade cross-asset strategy** — the
  headroom comes from crypto 50 % vol + TLT 15 % vol diversification.

---

## K1. Does cross-asset Kuramoto already subsume the relevant FX opportunity?

**Label: PLAUSIBLE, not PROVEN.**

- Cross-asset Kuramoto as currently published is *not* run on the FX
  majors panel. DXY is in its universe as one of 8 nodes, but no
  EUR/GBP/JPY/AUD/CAD/CHF cross is included.
- The Track-A equities-only result (MARGINAL, underperforms SPY) is
  the right precedent for an "FX-only" variant: FX majors are
  **mono-vol-grade** (all ~6–15 % annualised), much narrower than the
  6–50 % vol range that gave v2 headroom. Mechanistically this predicts
  an FX-only Kuramoto run would be MARGINAL at best and would not
  dominate v2's cross-asset numbers.
- FX-native *mechanisms* that are not price-phase-sync — carry,
  rate-differential, central-bank policy-path residuals, DXY-residual
  mean-reversion — are categorically distinct from phase-synchronisation
  and would not be captured by Kuramoto on FX prices.

Conclusion: cross-asset Kuramoto **does not literally cover** the
8-FX panel today. Whether it *mechanistically* subsumes the FX
opportunity depends on which FX mechanism is proposed (see K2).

## K2. Is there a reason to believe an FX-native line captures a distinct mechanism not already covered by cross-asset Kuramoto?

**Label: PLAUSIBLE — conditional on data availability.**

Only if the proposed FX-native mechanism is **not** another
phase-synchronisation / topology feature on prices. Concretely:

| candidate FX-native mechanism | distinct from cross-asset Kuramoto? | input available in repo? |
|---|:---:|:---:|
| Carry (rate-differential forward-rate-bias) | YES — uses rate-curve inputs, not phases | **NO** — only price parquets (no spot rates) |
| Central-bank policy-path residual | YES — uses policy/term-premium proxies | **NO** |
| DXY-residual cross-sectional mean-reversion | YES — relies on factor removal, not sync | YES (DXY is in `/Downloads/аскар` as `US_Dollar_Index_GMT+0_NO-DST.parquet`) |
| FX term-structure / realised-vol skew | YES — uses option-surface proxies | **NO** — no options data |
| FX regime-classification via phase-sync on 8 FX only | **NO** — this is Kuramoto on FX | YES |
| FX microstructure (L2-inferred, OFI-driven) | YES — needs bid/ask depth | **NO** on the current Askar panel (OHLC only per `data_audit_report.md`) |

Three of six rows are **distinct mechanism AND require unavailable
inputs**. Two are available. One is not distinct.

Implication: the **only mechanistically-distinct FX-native line that
has its data inputs already in the repo** is DXY-residual
cross-sectional mean-reversion. That is the narrow corridor worth
considering before ABORT. Everything else either collapses into
Kuramoto (same family) or is blocked by missing data (§14.S4).

## K3. Would time spent on FX-native foundation build currently displace a higher-ROI integration task?

**Label: SUPPORTED — yes, in the current demo window.**

- Memory `project_demo_deadline.md`: all 4 repos must be
  100 % production-ready for the Sutskever/Karpathy demo. Critical path
  is active.
- Cross-asset Kuramoto v2 is **the publishable demo artefact** (per
  `project_cross_asset_sync.md`): PUBLIC_REPORT.md + 4 PNG figures
  trader-readable in 5 min, replay-hashed, live paper trading on day
  11/90. Every hour spent here instead of on demo polish or on
  promoting the v2 spike into `core/strategies/cross_asset_sync.py`
  (the mentioned PR #203 path) is hour-for-hour displacement.
- An FX-native foundation build that leads to a new preregistration,
  a MODE_B 5.5–8 h diagnostics pass, a family memo, and a prereg draft
  is a multi-day workstream at minimum. None of that produces demo
  artefacts before the window closes.

## K4. Recommended outcome label

**`DEFER_TO_CROSS_ASSET_KURAMOTO` — pending post-demo re-evaluation.**

Rationale (numerically anchored):

1. The closed combo_v1 × 8-FX line failed at Sharpe ≈ 0 (−0.05 net,
   −0.005 gross). Cross-asset Kuramoto ships **Sharpe +1.262 OOS**,
   walk-forward validated, publishable, live-paper-traded. The gap is
   not a gap — it is a category mismatch.
2. The only mechanistically-distinct FX-native candidate with
   in-repo inputs is DXY-residual cross-sectional mean-reversion. It
   is not preregistered, not diagnosed, not prototyped. Even under an
   optimistic plan, its earliest honest verdict is weeks out.
3. Demo priority is active. FX-native work cannot be promoted over
   demo polish without an explicit directive.
4. If after the demo the FX-native line is revived, the right entry
   point is **first** an honest 8-FX cross-asset Kuramoto run
   (Track-B analogue to Track-A equities-only) to empirically set the
   floor, **then** DXY-residual work if the Kuramoto floor is not
   enough. That sequence requires no new preregistration-era effort
   today.

## Human-gate obligation (§K7)

Claude Code does not resolve priority. This file recommends
`DEFER_TO_CROSS_ASSET_KURAMOTO` with the caveat that the DXY-residual
corridor is legitimately distinct and worth revisiting post-demo.
Yaroslav decides in `HUMAN_GATE_MEMO.md`.
