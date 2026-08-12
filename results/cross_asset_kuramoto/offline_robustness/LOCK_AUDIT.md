# Offline Robustness · Lock Audit (Phase 0)

Performed UTC: 2026-04-22.
Result: **PASS.** All 28 protected artefacts read successfully; hashes frozen at `SOURCE_HASHES.json`.

## What was hashed

28 paths, grouped:
- 9 documentation / verification artefacts under `results/cross_asset_kuramoto/`
- 7 demo artefacts under `demo/`
- 5 frozen-module Python files under `core/cross_asset_kuramoto/`
- 5 live-rail scripts under `scripts/` (read-only from this protocol)
- 2 systemd unit files under `ops/systemd/`

Shadow-validation files (`results/cross_asset_kuramoto/shadow_validation/`) are **deliberately excluded** from SOURCE_HASHES — they are append-only live artefacts and will legitimately change while the timer runs. Interference against them is verified in Phase 8 by path-based write-auditing, not by hash-diff.

## Guardrails against §17 stop conditions

- `core/cross_asset_kuramoto/` — read-only import only; no function under `offline_robustness/` mutates module state.
- `PARAMETER_LOCK.json` · `INPUT_CONTRACT.md` — read-only consume via `load_parameter_lock` or `json.load`.
- `demo/` — read-only input to envelope-stress and benchmark family.
- `ops/systemd/` · cron · `paper_state/` — not read, not touched.
- `combo_v1` registry · FX-native foundation — not touched.

## End-of-protocol recheck

Phase 8 reloads `SOURCE_HASHES.json` and rehashes every listed path; any byte-level change in a protected artefact flips the `NO_INTERFERENCE_REPORT.md` verdict to FAIL. Test `tests/analysis/test_cak_source_hashes_frozen.py` enforces the same.
