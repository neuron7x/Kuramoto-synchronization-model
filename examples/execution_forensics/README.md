# Offline execution-forensics import (instrumentation v0.1)

**Status:** `Instrumented`. Sample-only input: not real market evidence, not trading performance, not a product-readiness claim. This is a strict, read-only ingestion/reconciliation boundary. It does not replace the richer TCA and market-structure methods in `analytics/tca.py` and `analytics/execution_quality.py`; it produces the kind of exact, provenance-bound input those methods would need before any financial conclusion.

The module is standard-library only (`tools/execution_forensics.py`, Python 3.11+). The report contract is `schemas/execution_forensics_report.schema.json`.

## Reproduce

From the repository root:

```bash
python -m tools.execution_forensics \
  --fills examples/execution_forensics/fills_sample.csv \
  --out /tmp/geosync-forensics-example.json
python -m tools.execution_forensics \
  --fills examples/execution_forensics/fills_sample.csv \
  --verify /tmp/geosync-forensics-example.json
python -m pytest -q --noconftest -c /dev/null \
  tests/unit/test_execution_forensics.py tests/tools/test_execution_forensics_gate.py
python -m pytest -q tests/property/test_execution_forensics_properties.py
python scripts/ci/execution_forensics_falsifier.py
```

Remove any pre-existing output file before the first command; the tool refuses to overwrite a report and refuses to write onto its input.

Exit codes: `0` success · `2` input refused (the message names the row and field) · `3` verification failed (the message names the reason: source bytes, method bytes, forged digest, or content).

## Input contract

CSV header, **exact names in exact order**:

```text
venue,symbol,quote_asset,trade_id,order_id,executed_at_utc,side,quantity,price,fee_amount,fee_asset,fee_quote_value,fee_conversion_source,arrival_price,arrival_at_utc,arrival_source
```

This is a **canonical normalized** fill table, not a parser for any venue's native export. Source-specific mapping is deliberately external and must be audited before client use.

### Lexical canon: one byte string, one meaning

The source digest can only bind a meaning if the grammar admits exactly one spelling per value. Anything else is refused with the row and field named.

| Field | Grammar | Refused examples |
| --- | --- | --- |
| amounts (`quantity`, `price`, `fee_amount`, `fee_quote_value`, `arrival_price`) | `(0\|[1-9][0-9]*)(\.[0-9]+)?` | `1e3`, `1_000`, `+1`, `-0`, `.5`, `5.`, `01`, non-ASCII digits |
| timestamps (`executed_at_utc`, `arrival_at_utc`) | `YYYY-MM-DDTHH:MM:SS[.ffffff]Z` | `2026-10-20 10:00:01Z`, `20261020T100001Z`, `…+00:00`, date-only, 7+ fraction digits, leap second |
| `venue` | `[a-z0-9][a-z0-9_.-]*` | `Binance` |
| `symbol` | `[A-Z0-9][A-Z0-9_./-]*` | `btcusdt` |
| `quote_asset`, `fee_asset` | `[A-Z0-9]+` | `usdt` |
| `trade_id`, `order_id` | printable ASCII, no whitespace | empty, `T 1` |
| `side` | `BUY` or `SELL` | `buy` |

Outer ASCII whitespace (space, tab, CR, LF) around a value is formatting and is stripped; any other whitespace is part of the value and is refused. Trailing fractional zeros (`0.10000000`) are canonical input; the report normalizes them (`0.1`).

### Semantic rules

- `trade_id` is unique within `(venue, symbol)`; a duplicate row fails.
- `quantity` is base units; `price` is units of `quote_asset` per base unit; both positive.
- `fee_amount` is the non-negative amount in `fee_asset`. Explicit `0` is a known zero; blank is unknown. Fee metadata without a fee amount fails.
- A fee in the quote asset needs no conversion and must not declare one. A fee in any other asset (e.g. `BNB`) needs **both** `fee_quote_value` and `fee_conversion_source`, or the quote-fee total stays `null` even though the native amount is reported.
- `arrival_price` (positive) is admissible only with `arrival_at_utc` **no later than** `executed_at_utc` and an `arrival_source`. Missing arrival data make slippage `null`, not zero. One order cannot carry two different benchmarks.
- Groups are keyed by `(venue, symbol, quote_asset)`; distinct quote assets are never summed.

### Exact arithmetic

All totals are computed in a decimal context with `Inexact` and `Rounded` trapped (50 significant digits). A figure the context cannot carry exactly is refused with `exact arithmetic budget … exceeded`; nothing is ever rounded. The property suite checks every total against an independent `fractions.Fraction` oracle.

## Output

One deterministic JSON report (`schema_version: execution-forensics/0.1`, `claim_tier: Instrumented`) containing `source_sha256` (the CSV bytes), `method_source_sha256` (the exact bytes of the module), per-group amounts and missing-data counts, and `report_sha256`, the SHA-256 of the canonical JSON (sorted keys, no whitespace, UTF-8) of every other field. Every amount is a decimal string; the only JSON numbers are counts. The digest detects change; it is **not** a signature and does not vouch for externally supplied valuations.

Per group: `notional_quote`, `buy_notional_quote`, `sell_notional_quote`, `fee_totals_native_by_asset`, `fee_quote_total`, `arrival_slippage_quote` (signed: positive is adverse for both sides, the same convention as `implementation_shortfall`), `execution_shortfall_plus_fees_quote`, `missing_fee_valuation_fills`, `missing_arrival_benchmark_fills`, `evidence_state` (`COMPLETE_EXECUTION_COMPONENTS` or `PARTIAL_UNKNOWN_COST`).

For the two-fill demonstration fixture: notional `18005` USDT, valued fees `0.9` USDT, adverse arrival slippage `5` USDT, combined execution-cost components `5.9` USDT. The BNB fee conversion is illustrative, not sourced to a venue transaction.

`--verify` recomputes the report from the current bytes of the CSV and of the module and compares it with the saved file; a change to either, a forged digest, or an edited total fails with the reason named.

## Boundaries

The calculation is per fill and **does not** infer funding, realized PnL, capital saved, rebates outside the declared fields, opportunity cost, portfolio risk, market alpha, or an executable strategy. Fee-plus-slippage is a cost component, **not trading PnL**. Timestamps and source names are validated syntactically only; an independent order-submission or order-book archive is required to audit their truth.

**Evidence status:** INSTRUMENTED / NO CLIENT OR REAL-TRADE VALIDATION. No trades are submitted, no API keys are read, no network requests are performed.

## Verification layers in this PR

| Layer | Where | What it would catch |
| --- | --- | --- |
| Refusal controls | `tests/unit/test_execution_forensics.py` | any grammar escape, rounding, duplicate, conflict, tamper, forged digest |
| Exact oracle | `tests/property/test_execution_forensics_properties.py` | any arithmetic drift versus `Fraction`; order dependence; sign asymmetry |
| Schema | `schemas/execution_forensics_report.schema.json` | floats, `-0`, trailing zeros, unknown keys, wrong tier |
| Falsifier | `scripts/ci/execution_forensics_falsifier.py` | a boundary that starts accepting fabrications (checked live: two hand mutants fail it) |
| Mutation ratchet | `docs/MUTATION_KILL_BASELINE.json` | tests weakened below the measured kill-rate floor |
| Acceptor | `.claude/commit_acceptors/execution-forensics-evidence-boundary.yaml` | scope creep into forbidden paths |

## Commercial follow-on, not this PR's claim

A future externally audited adapter can map a venue export to this contract with a sourced fee-asset conversion and verified arrival snapshots. Only then can `analytics.tca.TransactionCostAnalyzer` and the liquidity/risk reports consume the normalized evidence after their own financial invariants are tested. Forensic validation must precede any client-facing invoice or financial conclusion.
