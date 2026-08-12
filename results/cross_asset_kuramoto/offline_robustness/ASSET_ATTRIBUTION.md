# Phase 3 · Asset attribution & drawdown anatomy

OOS 70/30 test (2023-10-13 → 2026-04-10). Frozen strategy reproduced
bit-exactly; per-asset gross / cost / net reconstructed against the
engine's scalars (`max_abs_dev < 1e-9`). Full data:
`asset_contribution.csv`, `drawdown_anatomy.csv`, `fold_asset_attribution.csv`.

## Per-asset OOS contribution

| asset | net log-ret | gross | cost | % of portfolio net | bars active | hit rate when active |
|---|---:|---:|---:|---:|---:|---:|
| GLD | **+0.382** | +0.403 | −0.020 | **62.8 %** | 472 | 55.1 % |
| BTC | +0.175 | +0.183 | −0.008 | 28.7 % | 332 | 52.4 % |
| ETH | +0.134 | +0.139 | −0.005 | 22.0 % | 332 | 51.8 % |
| SPY | 0.000 | 0.000 | 0.000 | 0.0 % | 0 | — |
| TLT | **−0.082** | −0.060 | −0.022 | **−13.5 %** | 472 | **47.5 %** |

Shares >100 % because TLT drags net down; GLD/BTC/ETH over-contribute to compensate. **Returns consolidate in GLD** (63 %). BTC+ETH add ~51 % between them. **TLT removes 13.5 %** — OOS hit rate 47.5 %, cost drag 2.2 pp on ~22 pp of turnover. **SPY trades zero bars** (no bucket contains SPY). **TLT is a structural net drag** on this OOS window; Phase 1 tradable-LOO raising Sharpe 1.26→1.73 when TLT is dropped has its mechanism here.

## Top-3 drawdown anatomy (OOS portfolio equity)

| rank | window | depth | top-3 asset contributors (share of window loss) |
|---:|---|---:|---|
| 1 | 2024-12-10 → 2025-04-08 | 16.76 % | **ETH 61 %**, BTC 40 %, TLT 28 % |
| 2 | 2024-03-06 → 2024-05-01 | 11.38 % | **ETH 50 %**, BTC 39 %, TLT 23 % |
| 3 | 2026-02-26 → 2026-03-26 | 9.36 % | **TLT 52 %**, BTC 4 %, ETH −2 % |

DD-1 and DD-2 are crypto events (ETH dominant >50 %, BTC secondary; 2024 crypto bear affecting low/mid buckets). DD-3 is a TLT event (51.6 % of window loss from TLT alone; Feb–Mar 2026 bond drawdown; crypto ~flat).

## §AA8 answers

- **Which assets carry most of the return?** GLD (63 %), BTC (29 %), ETH (22 %). GLD alone dominates.
- **Which assets dominate drawdowns?** ETH (top contributor in the two largest DDs), BTC (consistent #2), TLT (dominant in DD-3).
- **Overly dependent on one asset / regime?** Yes on the return side (GLD), and Phase 1 tradable-LOO reinforces this: losing GLD drops Sharpe to 0.53. On the drawdown side, dependency is mixed — the regime that matters for DDs shifts across episodes (crypto for 2024, bonds for 2026).

Fold-level attribution (`fold_asset_attribution.csv`) is consistent: fold-3 (2022) losses are crypto-concentrated, fold-5 (2024-2026) has the 2026 TLT episode inside it.
