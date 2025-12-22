# FACT_AUDIT

| Claim | Where it appears | Current factual status | Evidence command/output | Fix |
| --- | --- | --- | --- | --- |
| “All 62 unit tests passing” | `docs/SEROTONIN_IMPLEMENTATION_COMPLETE.md` (previous text) | Replaced with generated test inventory and explicit pytest invocation note | `python tools/audit/serotonin_test_stats.py` → JSON count of collected serotonin tests | Link doc to `docs/_generated/serotonin_stats.md` and remove hardcoded counts |
| “Controller Version: v2.4.0” with no code source | `docs/SEROTONIN_IMPLEMENTATION_COMPLETE.md` | Anchored to code constant | `python - <<'PY'\nfrom tradepulse.core.neuro.serotonin import __version__\nprint(__version__)\nPY` | Added `__version__` in `src/tradepulse/core/neuro/serotonin/__init__.py` and surfaced via generated stats |
| “Zero breaking changes / 100% backward compatible” | `docs/SEROTONIN_IMPLEMENTATION_COMPLETE.md` | Marked as design target (no automated proof) | Regression proof requires `python -m pytest`; tracked via `docs/_generated/serotonin_stats.md` | Rewrote claim as target and pointed to CI evidence |
| “Production-ready/validated” assertions | `docs/SEROTONIN_IMPLEMENTATION_COMPLETE.md`, `docs/thermodynamics/README.md` | Rephrased as conditional on current CI outputs | `.github/workflows/doc-truth.yml` runs audit scripts and fails on drift | Added automation guard, linked docs to generated stats, and removed unconditional readiness wording |
| Thermodynamics benchmarks (<1ms, <100μs, etc.) | `docs/thermodynamics/README.md` | Labelled as targets pending measurement | Benchmark rerun required; no automated output yet | Tagged benchmarks/scaling as targets and routed readers to generated stats for test evidence |
