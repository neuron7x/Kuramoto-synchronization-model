# Environment Charter

This charter defines the deterministic, secure, and reproducible environment rules for GeoSync. All dependency, configuration, and data changes must conform to these guardrails.

## Toolchain & Runtimes
- Supported Python versions: **3.11** and **3.12** (CI matrix). Prefer 3.12 for local development.
- Container builds use pinned bases (`python:3.12-slim` for scans, `python:3.11-slim` for runtime).
- Package manager: `pip` with explicit constraints; virtual environments are required (`python -m venv .venv`).

## Dependency Policy
- Install exclusively from lockfiles with security constraints:
  - Runtime: `pip install -c constraints/security.txt -r requirements.lock`
  - Development: `pip install -c constraints/security.txt -r requirements-dev.lock`
  - Scan profile (no GPU/CUDA): `pip install -c constraints/security.txt -r requirements-scan.lock`
- Never rely on floating ranges in active environments; regenerate locks with `make lock` or `make deps-update` when versions need to move.
- Regenerate SBOM after dependency updates via `make sbom`.
- Security-critical pins live in `constraints/security.txt`; do not relax these without a documented CVE review.

## Configuration & Secrets Policy
- No secrets in source control. All sensitive values must be provided via environment variables or a secrets manager.
- `.env.example` documents required settings (including `GEOSYNC_TWO_FACTOR_SECRET` and `GEOSYNC_BOOTSTRAP_STRATEGY`). Copy it to `.env` locally; never commit the populated file.
- Service configuration defaults reside under `configs/` and application settings modules. Avoid “magic” parameters—add named config values with documented defaults.
- When adding new configuration flags, document them in `.env.example` and ensure safe defaults.

## Data Policy
- Repository data is limited to minimal, reproducible samples in `data/` (see `data/README.md`). Golden fixtures live under `data/golden/`.
- Generate new sample datasets with `scripts/generate_sample_ohlcv.py` and commit only minimal, representative fixtures.
- Large or proprietary datasets must stay outside the repo and be referenced via documented acquisition steps.

## Validation & CI
- Primary workflow: `.github/workflows/tests.yml` (lint, type-check, unit/integration/e2e) with coverage gate (`--cov-fail-under=98`).
- Security and supply-chain checks: `make audit`, `make deps-audit`, and `make supply-chain-verify`; the Dockerfile scan stage uses the scan lock profile.
- Use `make test-fast` for quick local validation and `make test-ci-full` to mirror CI before merging.

## Change Control
- Any deviation from this charter (e.g., temporary pin relaxations) must include an explicit justification in the changelog or PR description and a follow-up task to restore compliance.
