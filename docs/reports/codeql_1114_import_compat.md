# CodeQL #893/#894 import-cycle fix (#1114) — behavioural-compatibility proof (P0-4)

## Problem

PR #1114 broke the `core.indicators.multiscale_kuramoto` <-> `core.indicators.cache`
import cycle that CodeQL flagged as `py/unsafe-cyclic-import` (alerts #893/#894).
The cycle was:

```
multiscale_kuramoto  --(runtime)-->        cache
cache                --(TYPE_CHECKING)-->  multiscale_kuramoto   # TimeFrame annotation
```

The #1114 fix extracted the self-contained `TimeFrame` enum into a new **leaf**
module `core/indicators/timeframe.py` (imports nothing from the package):

- `multiscale_kuramoto.py` now does `from .timeframe import TimeFrame`
  and **re-exports** it, so the public API is unchanged.
- `cache.py` changed its `TYPE_CHECKING` import from
  `from .multiscale_kuramoto import TimeFrame` to `from .timeframe import TimeFrame`.

Neither module depends on the other; the cycle is removed at its root.

**Removing a CodeQL alert is not the same as proving behaviour is unchanged.**
This report records the executable proof that the refactor is behaviour-preserving.

## What the fix actually changed (read from `e8e77851`)

| File | Change |
|---|---|
| `core/indicators/timeframe.py` | **new** leaf module; `TimeFrame` enum verbatim (M1/M5/M15/H1, `seconds`, `pandas_freq`, `__str__`) |
| `core/indicators/multiscale_kuramoto.py` | enum class deleted; replaced by `from .timeframe import TimeFrame` re-export; `from enum import Enum` dropped |
| `core/indicators/cache.py` | `TYPE_CHECKING` import re-pointed from `.multiscale_kuramoto` to `.timeframe` (one line) |

No call sites, no key derivation, no compute logic were touched.

## Behavioural-compatibility proof

`tests/unit/indicators/test_timeframe_compatibility.py` (26 tests) proves, by
execution, every axis along which the move could have drifted:

1. **Import-path identity** — `TimeFrame` resolved via the leaf path, the legacy
   `multiscale_kuramoto` path, and the package-level lazy `__getattr__` are the
   **same class object** (`is`), and each member (M1/M5/M15/H1) is the same
   singleton across all three paths. Enum members are singletons, so `is`
   identity rules out duplicate-enum-class drift that `==` could mask. Member
   set and semantics (`value`, `seconds`, `pandas_freq`, `str`) are pinned.
2. **Legacy import paths still resolve** — `from core.indicators.multiscale_kuramoto import TimeFrame`
   and `from core.indicators import TimeFrame` both resolve to the leaf class;
   the historical import statement is executed live, not just inspected.
3. **Cache-key stability** — `FileSystemIndicatorCache._timeframe_key` returns the
   enum **member name**, so the key is identical whether produced from the leaf
   path, the legacy path, or the plain `"M5"` string. A store/load round-trip
   stores under the leaf-path `TimeFrame` and loads under the legacy-path
   `TimeFrame` and a plain string — same fingerprint, same value. This is the
   tested invalidation/stability contract: cache entries written before the
   refactor remain addressable after it.
4. **Cycle is gone** — AST inspection asserts `cache.py` contains **zero**
   imports of `multiscale_kuramoto` (any form), and the `TYPE_CHECKING` edge now
   points at `.timeframe`. A **fresh subprocess** imports only
   `core.indicators.cache` and asserts `core.indicators.multiscale_kuramoto`
   is absent from `sys.modules` — proving the runtime edge is gone (the
   subprocess prevents a session-cached `multiscale_kuramoto` from masking a
   reintroduced edge). The leaf module is asserted to import nothing from the
   `core.indicators` package, so it cannot re-couple.
5. **No runtime drift in the indicator path** — a deterministic
   `MultiScaleKuramoto.analyze` (seed-7, 4000×60s synthetic series) is run with
   `TimeFrame` keys taken from the leaf path and again from the legacy path:
   the per-timeframe order parameters, mean phases, windows, dominant scale, and
   consensus are **bit-exact** equal, and the results are keyed by the same
   singleton members. A golden-value lock pins the post-#1114 output
   (M1/M5/M15 order parameters and mean phases to 1e-9) so any future drift in
   the affected path fails closed.

## Result

The import-cycle fix is proven behaviour-preserving by executable tests, not
only by the CodeQL alert disappearing. No behavioural drift was found.

## Verification

```
pytest -q tests/unit/indicators/test_timeframe_compatibility.py   # 26 passed
python -m compileall core                                          # clean
python -m mypy --strict tests/unit/indicators/test_timeframe_compatibility.py
ruff check tests/unit/indicators/test_timeframe_compatibility.py
```

ruff/black format-check excludes `tests/`; the new file carries zero `noqa` /
`type: ignore` suppressions (debt-ratchet neutral).
