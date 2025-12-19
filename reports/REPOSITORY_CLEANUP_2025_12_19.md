# Repository Cleanup Summary (2025-12-19)

## Removed items
- `artifacts/cns_stabilizer/delta_f_heatmap_sample.csv`: Duplicate of `delta_f_heatmap.csv`; consolidated to single canonical heatmap dataset. Related documentation updated to point to the surviving file.
- `scripts/compare_thermo_states.py`: Duplicate of `scripts/compare_states.py`; operational runbook now references the canonical script.

## Rationale and safety
- Eliminates redundant artifacts that provided no additional value while preserving canonical data and tooling.
- Both removed files were exact duplicates; functionality remains unchanged. Canonical comparator `scripts/compare_states.py` in the repository root (checksum-matched) remains in place.
- Items are tracked in git history and can be restored if future needs arise.

## Follow-up
- Prefer referencing canonical artifacts/scripts to avoid drift (e.g., `delta_f_heatmap.csv` and `scripts/compare_states.py`).
- Include new sample artifacts only when they provide distinct scenarios or schema coverage.
