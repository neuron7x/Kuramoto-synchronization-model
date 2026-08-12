# Separation Finding · robust regime core, fragile value extraction

Canonical intellectual output of the offline robustness cycle. Entry
point for any future extraction-layer-v2 design. Live shadow rail
untouched (28/28 SOURCE_HASHES match). Commit of record: offline
packet `b8fbccd`.

## Finding, one line

> The synchronisation core is structurally stable; its current
> monetisation layer is not.

## Core is robust (regime detection)

| perturbation | OOS Sharpe | reading |
|---|---:|---|
| regime-LOO, 8/8 omissions | range **[1.23, 1.62]** | no single node load-bearing |
| four omissions (BTC / ETH / SPY / DXY) | +0.24..+0.36 Sharpe each | those add phase-sync noise |
| `ffill(limit=1)` vs `ffill(limit=3)` | bit-exactly identical | no gap ≥ 1 day in data |

Source: `LEAVE_ONE_ASSET_OUT.md`, `DATA_TREATMENT_AUDIT.md`.

## Extraction is fragile (position construction)

| stressor | impact | reading |
|---|---:|---|
| drop **GLD** from tradable | Sharpe 1.26 → **0.53**, DD −6 pp | single load-bearing asset |
| drop **TLT** from tradable | Sharpe 1.26 → **1.73** | TLT net-drags **−13.5 %** (hit rate 47.5 %) |
| **SPY** weight | **≡ 0** on every bar | in no bucket; spec-residual |
| strict-drop fill vs ffill | ΔSharpe **0.22** | sample-geometry, not algorithmic |

Source: `ASSET_ATTRIBUTION.md`, `LEAVE_ONE_ASSET_OUT.md` (tradable LOO).

## What this does not imply

- Not a redesign trigger — the 90-bar truth gate (≈ 2026-07-10)
  governs any such decision.
- Not a claim that GLD is a forever-source of extraction; its
  dominance over 2023-10 → 2026-04 may reverse.
- Not a change to `PARAMETER_LOCK.json`, any bucket, the cost model,
  the lag, or the universe.

## Admissible post-90-bar trajectory

If the truth gate permits downstream work, it is a **new line**:

- **line_id**: `cross_asset_kuramoto_extraction_v2` (proposed).
- **Scope**: redesign only `regime_buckets → weights`.
  Signal side (`build_panel → R(t) → classify_regimes`) stays
  frozen, imported read-only.
- **Forbidden carry-over**: tuning the current bucket spec.
  Extraction-concentration laundered as "optimisation" is rescue,
  not research.
- **Pre-register falsifiers before any run:**
  - tradable-LOO: ≥ 4 of k omissions must stay within ±0.2 Sharpe
  - GLD contribution share must drop below 50 %
  - TLT must move from net-drag to non-negative
  - Sharpe premium over BF1 equal-weight must survive bootstrap CI
    at a pre-committed p-threshold

New `line_id` in `config/research_line_registry.yaml`, new fold
manifest, new lock SHA. This is **not** a Wave 2 of the current line.

## Cross-references

- `ROBUSTNESS_SUMMARY.md` · 590-word synthesis, all five phases
- `LEAVE_ONE_ASSET_OUT.md` · regime + tradable LOO table
- `ASSET_ATTRIBUTION.md` · per-asset contribution and DD anatomy
- `DATA_TREATMENT_AUDIT.md` · fill-policy Δ
- `BENCHMARK_FAMILY.md` · matched cost/lag ranking
- `ENVELOPE_STRESS.md` · early-dip recovery probabilities
- `../WALKFORWARD_VERIFICATION.md` · 5-fold WF match
- `../shadow_validation/ACCEPTANCE_GATES.md` · 90-bar truth gate

## Governance

- `combo_v1 × 8-FX` closure preserved (registry-blocked, exit 2).
- FX-native line remains deferred.
- Zero writes to protected paths during this finding's authorship.
