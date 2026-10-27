# Offline execution-forensics import (instrumentation v0.1)

**Status:** sample-only input, not real market evidence, trading performance, or a product readiness claim. This adds a strict read-only ingestion/reconciliation boundary to the existing GeoSync analytical modules (`analytics/tca.py`, `analytics/execution_quality.py`). It does not replace their richer TCA/market-structure methods.

## Reproduce

From the repository root (Python 3.11+, standard library only for this module):

```bash
python -m analytics.execution_forensics \
  --fills examples/execution_forensics/fills_sample.csv \
  --out /tmp/geosync-forensics-example.json
python -m analytics.execution_forensics \
  --fills examples/execution_forensics/fills_sample.csv \
  --verify /tmp/geosync-forensics-example.json
python -m pytest -q tests/unit/test_execution_forensics.py
```

Remove any pre-existing output file before running the first command; the tool refuses to overwrite a report.

## Input

CSV headers are **exactly**:

```text
venue,symbol,quote_asset,trade_id,order_id,executed_at_utc,side,quantity,price,fee_amount,fee_asset,fee_quote_value,fee_conversion_source,arrival_price,arrival_at_utc,arrival_source
```

This is a **canonical normalized** fill table, **not** a direct parser for every format of a Binance export. Source-specific mapping is deliberately external and must be audited before any client use.

- `trade_id` uniquely identifies a fill within venue/symbol; duplicate rows fail.
- `quantity` is base units, `price` is units of `quote_asset` per base unit.
- `side` is uppercase `BUY` or `SELL`; timestamps are explicit UTC ISO 8601 ending in `Z`.
- `fee_amount` is the nonnegative amount in `fee_asset`; explicit `0` is different from blank/unknown. For a fee in the quote asset, the quote value is identical to the fee amount.
- For other fee assets (e.g. BNB), `fee_quote_value` must be independently sourced in the row's quote asset and `fee_conversion_source` must identify that valuation. An unsupported or missing conversion stays `null` in totals, even if the native fee amount is known.
- `arrival_price` can be populated only when `arrival_at_utc` and `arrival_source` identify a real benchmark observed no later than the fill. Missing arrival data make slippage `null`, not zero.
- A single order cannot have conflicting arrival benchmarks. Different quote currencies are kept in separate groups and never summed into fictitious portfolio totals.

For **a complete report with two demonstration fills**, notional is 18,005 USDT, valued fees 0.9 USDT, signed adverse arrival slippage 5 USDT, and combined execution-cost components 5.9 USDT. The fee conversion is illustrative, not sourced to an actual venue transaction.

## Output and boundaries

One deterministic JSON report contains input SHA-256, exact method-source SHA-256, method version, grouped amount/reconciliation fields, missing-data counts, and a canonical report SHA-256. The report checksum detects changes; it is **not** an authenticated signature or confirmation of externally supplied valuations.

The calculation is per fill and **does not** infer funding, realized PnL, capital saved, exchange rebates outside documented fields, opportunity cost, portfolio risk, market alpha, or an executable strategy. Arrival slippage can be negative when the fill is better than the reference price. Fee-plus-slippage is a cost component, **not trading PnL**. Transaction timestamps and source claims are only validated syntactically; an independent order-book/order-submission archive is required to audit their truth.

**Evidence status:** INSTRUMENTED / NO CLIENT OR REAL-TRADE VALIDATION. No trades are submitted, no API keys are read, and no network requests are performed.

## Commercial follow-on, not this PR's claim

A future externally audited adapter can map a venue export to this contract, with an explicit fee-asset FX conversion and verified order arrival snapshots. Only then can the existing `analytics.tca.TransactionCostAnalyzer` and liquidity/risk reports consume the normalized evidence after their own financial invariants are tested. Forensic validation must precede a client-facing invoice or financial conclusion.
