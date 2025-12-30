# TradePulse Structure (Canonical vs Legacy)

## Canonical Roots
- Runtime namespace: `src/tradepulse` (all packages carry `__CANONICAL__ = True`)
- Shim namespace: `tradepulse/__init__.py` (`__CANONICAL__ = False`, re-export only)

## Entrypoints
- **Control CLI (canonical):** `cli/tradepulse_cli.py`
- **API server (canonical):** `cortex_service/app/__main__.py`
- **Calibration (canonical):** `scripts/calibrate_controllers.py`
- Legacy/utility entrypoints (kept for backward compatibility): `cli/amm_cli.py`, `tacl/__main__.py`, `scripts/__main__.py`, `tools/vendor/fpma/__main__.py`, `src/tradepulse/sdk/mlsdm/__main__.py`

## Configuration Sources
- Canonical configs: `config/default_config.yaml`, `config/dopamine.yaml`, `config/thermo_config.yaml`
- Legacy duplicates (explicit opt-in only): `configs/dopamine.yaml`
- Other top-level config dirs (`configs/`, `conf/`) are treated as legacy and may not be extended without updating the guardrail.
- Config precedence (MLSDM): CLI overrides (`--override key=value`) > environment (`MLSDM__...`) > YAML file > defaults.

## Guardrails
- `scripts/check_namespace_integrity.py` — ensures canonical/shim markers are present and exclusive to `src/tradepulse`.
- `scripts/check_single_entrypoint.py` — blocks proliferation of new entrypoints outside the canonical set.
- `scripts/check_config_single_source.py` — enforces single-source configs per subsystem and rejects undeclared config roots.
- CI job: `.github/workflows/architecture-validation.yml` runs the above checks; `make arch-validate` runs them locally.
