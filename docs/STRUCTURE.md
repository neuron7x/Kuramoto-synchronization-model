# GeoSync Structure (Canonical vs Legacy)

## Canonical Roots
- Canonical install root: top-level `geosync/` — `import geosync` resolves here
  (per [ADR 0024](adr/0024-import-architecture-canonicalization.md), Accepted
  2026-06-09). This is the authoritative architectural decision.
- Retired fork: `src/geosync/` — being migrated out under the staged plan. It
  still carries legacy `__CANONICAL__ = True` namespace markers that predate
  ADR 0024 and are tracked (not trusted as the decision) until the code collapse
  lands. Do not add new `src.*` imports; the import-architecture gate fails on
  any new one.

## Entrypoints
- **Control CLI (canonical):** `geosync/cli/geosync_cli.py`
- **API server (canonical):** `cortex_service/app/__main__.py`
- **Calibration (canonical):** `scripts/calibrate_controllers.py`
- Legacy/utility entrypoints (kept for backward compatibility): `geosync/cli/amm_cli.py`, `tacl/__main__.py`, `scripts/__main__.py`, `tools/vendor/fpma/__main__.py`, `src/geosync/sdk/mlsdm/__main__.py`

## Configuration Sources
- Canonical configs: `config/default_config.yaml`, `config/dopamine.yaml`, `config/thermo_config.yaml`
- Legacy duplicates (explicit opt-in only): `configs/dopamine.yaml`
- Other top-level config dirs (`configs/`, `conf/`) are treated as legacy and may not be extended without updating the guardrail.
- Config precedence (MLSDM): CLI overrides (`--override key=value`) > environment (`MLSDM__...`) > YAML file > defaults.

## Guardrails
- `scripts/ci/check_import_architecture.py` — **authoritative** import-architecture
  ratchet (ADR 0024): fail-closed, monotone-down debt ledger for `src.*` imports
  and runtime `sys.path` mutations. Wired into CI via
  `.github/workflows/import-architecture-gate.yml`.
- `scripts/ci/check_docs_consistency.py` — fails the build if any doc reasserts
  the retired `src/geosync` fork as canonical, contradicting ADR 0024. Wired via
  `.github/workflows/docs-consistency-gate.yml`.
- `scripts/check_namespace_integrity.py` — validates the **legacy** `__CANONICAL__`
  markers (still flagging `src/geosync` during the transition). Retained until the
  staged code collapse retires those markers.
- `scripts/check_single_entrypoint.py` — blocks proliferation of new entrypoints outside the canonical set.
- `scripts/check_config_single_source.py` — enforces single-source configs per subsystem and rejects undeclared config roots.
- Local: `make arch-validate` runs the namespace + entrypoint checks.
