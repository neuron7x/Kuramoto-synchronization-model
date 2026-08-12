# Co-located test wiring + guard robustness

This change closes three measurement/correctness holes surfaced while triaging
the red `Release coverage gate (90%)` lane on `main`.

## 1. Co-located test suites never ran under the coverage gate
`make coverage-baseline` ran only `pytest tests/`. Seven test suites that
physically live **under production packages** (so the top-level `tests/` root
never collects them) were therefore never executed during release-coverage
measurement, even though they pass and exercise real release surface:

| suite | tests | surface exercised |
|-------|------:|-------------------|
| `core/neuro/tests` | 202 | core neuromodulators |
| `analytics/tests` | 28 | analytics |
| `analytics/fpma/tests` | 9 | analytics/fpma |
| `analytics/regime/tests` | 42 | analytics/regime |
| `analytics/signals/tests` | 16 | analytics/signals |
| `markets/orderbook/tests` | 10 | markets/orderbook |
| `geosync/neural_controller/tests` | 36 | neural_controller |

They are wired in as a **second, `--cov-append` invocation** (not appended to
the `tests/` argument list): under `--import-mode=importlib` several share a
basename with files under `tests/`, so a single combined collection raises
`import file mismatch`. Two isolated collection roots accumulate into one
`.coverage` file with zero collisions. The canonical `junit.xml` is still
written by the `tests/` run (it carries the gated-claim falsifiers); the
co-located run writes `junit_colocated.xml` to avoid clobbering it.

### Avoiding self-inflation (the honest-number fix)
`release_90.coveragerc` declares `[run] source = core analytics markets geosync …`
and its only test-omit (`tests/**`) is **root-anchored**. The co-located test
files live *under* those source roots (e.g. `analytics/signals/tests/test_igs_core.py`
is under `analytics`), so coverage.py records the execution of the **test file
bodies themselves**, and the longest-prefix bucketing in
`tools/coverage/surface_contract.map_file_to_surface` would map those test lines
into the `analytics` / `core` / `markets` / `geosync` production surfaces — i.e.
the suite would partly be *covering itself*. A naive `**/tests/**` omit is
forbidden by `tests/audit/test_coverage_honesty.py` (an omit may not be a child
of a `source` root). The correct fix is therefore in the surface mapper:
`map_file_to_surface` now returns `None` (excluded) for any co-located test file
(`*/tests/test_*.py`, `*/tests/*_test.py`, `*/tests/__init__.py`,
`*/tests/conftest.py`) under a source root, via the new
`is_colocated_test_file` predicate. Test bodies still *execute* production code
(which is what we want counted) but no longer count as production lines.
Regression tests in `tests/tools/test_coverage_surface_contract.py` pin both
directions (production module still maps; co-located test body maps to `None`).

Measured effect (CI `tests/` `coverage.xml` ∪ co-located coverage, surface
honestly excluding co-located test bodies): release line coverage
**77.89% → COVERAGE_TRUE_PCT** (re-derived from `make coverage-baseline`; see
quality gates below). This does not by itself reach the 90% release gate — the
residual is genuine production logic still untested, a separate test-authoring
campaign — but it removes the measurement-completeness defect (suites never run)
*and* the measurement-honesty defect (test bodies counted as production) that
together made the number meaningless.

## 2. `neural_controller` package was un-importable
`core/params.py` is the package's config facade — `__init__`, `bridge`,
`sensory_pipeline`, `adapter` and the test-suite all import every config from
it — but `PredictiveConfig`, `SensoryConfig` and `OBSERVATION_KEYS` physically
live in `core/neuro_params.py` and were never re-exported. `import
geosync.neural_controller` raised `ImportError`, leaving the whole subpackage at
0% coverage and its tests at 4 collection errors. Fixed by re-exporting the
three symbols from the facade (PEP 484 redundant-alias form; no circular import:
`neuro_params` depends only on `dataclasses`).

## 3. `analytics/signals` tests used a pandas alias removed in 2.2
`pd.date_range(..., freq="T")` — the `"T"` minute alias was removed in
pandas ≥ 2.2 in favour of `"min"`. Five tests raised `ValueError: Invalid
frequency: T`. Repointed to `"min"`.

## 4. Namespace-integrity guard false positives on hidden trees
`scripts/check_namespace_integrity.py` rglob-scanned the whole repo, excluding
only `.venv/venv/.tox/node_modules/__pycache__`. It flagged
`.claude/worktrees/agent-*/src/geosync/...` (ephemeral agent worktrees that
carry their own canonical tree) as violations on any developer machine — yet
those paths do not exist on CI's clean checkout, so the bug was invisible where
the guard is enforced. The scan now skips any hidden directory (`startswith
"."`) plus build/dist. Three regression tests pin both directions: hidden trees
are ignored, visible rogue canonical markers are still flagged.

All of the above are integrity/correctness fixes. No market claim, no claim-tier
promotion, no runtime behaviour change, no lint/type suppressions added.
