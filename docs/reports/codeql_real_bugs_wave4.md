# CodeQL Real-Bug Wave 4

Date: 2026-06-10 · Branch: `fix/codeql-real-bugs-wave4`

After the bulk-FP dismissals (681 dismissed), the board's *tail* — subtle
rule classes below the top-15 fold — was re-triaged for genuine defects. Five
were real enough to fix; the rest of the tail is FP-by-idiom (heapq-only
`__lt__`, Pydantic `cls` validators, enum iteration, deferred cycle-break
imports) and was dismissed.

## Fixed

| # | Rule | File | Severity of impact |
|---|------|------|--------------------|
| **#221** | py/unreachable-except | `execution/live_loop.py` | **Real** — `except OrderError` preceded `except (TransientOrderError, …)`; since `TransientOrderError ⊂ OrderError`, every transient error was caught by the generic handler and mis-logged `fetch_failed` instead of `poll_retry`. Telemetry/alerting on the transient path was effectively dead. Reordered (specific-before-broad). Verified locally across all four error types (TransientOrderError/ConnectionError/TimeoutError → `poll_retry`, plain OrderError → `fetch_failed`); a routing assertion is enforced by the acceptor falsifier, since the architectural guard forbids new `tests/` files from importing `execution.*`. |
| **#285** | py/call/wrong-named-argument | `bench/bench_indicators.py` | **Real** — `compute_phase(coupling=0.3, …)`; `compute_phase` has no `coupling` parameter → `TypeError` whenever the benchmark runs. Removed. |
| **#286** | py/call/wrong-named-argument | `examples/integrated_risk_management_example.py` | **Real** — `update_position_limits(symbol=…)`; the parameter is `market_state_or_symbol` → `TypeError` on run. Corrected. |
| #274 | py/mixed-returns | `core/data/materialization.py` | Smell — `return []` inside a generator (value discarded by Python). → bare `return`. |
| #275 | py/mixed-returns | `src/audit/stores.py` | Smell — same generator `return []`. → bare `return`. |

## Tail verified as FP (dismissed)

- `py/incomplete-ordering` (`ScheduledTask`) — defines only `__lt__`, which is
  all `heapq` requires; intentional.
- `py/call-to-non-callable` — `Callable`-typed params and a conditionally
  defined `PIIFilterSpanProcessor`.
- `py/call/wrong-arguments` (`backups.py`) — call matches the `CommandRunner`
  `Callable` contract.
- `py/exit-from-finally` (`cli`) — the enclosing `except BaseException`
  already captured the error before the `finally: return`; nothing propagates.

## Verification

`ruff` · `black --check` · `mypy --strict` clean on all changed modules ·
physics-code-audit clean · 5 new regression tests + targeted suites green ·
commit-acceptor bound.
