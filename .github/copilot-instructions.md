# TradePulse repository instructions

## Build and test baseline
- Python: `python -m pip install -e .[dev]`
- Fast checks: `ruff check . && black --check . && mypy src application execution core`
- Fast tests (path-based): `pytest tests/unit tests/api tests/runtime tests/execution -q`
- Security fast lane: `bandit -r execution application/security application/runtime` and `semgrep scan --config p/security-audit --error execution application/security application/runtime`

## Required checks for merge to `main`
- `pr-gate / final`
- `CodeQL / CodeQL`
- `Dependency Review / Dependency Review`

## PR and merge expectations
- Use focused PRs with risk notes and rollback plan for execution/risk/security changes.
- Never bypass PR checks, never push directly to `main`.
- Keep secrets out of code, fixtures, logs, comments, and artifacts.

## Path-based safety rules
- `execution/**`, `application/security/**`, `application/runtime/**`, `application/api/**`, `.github/workflows/**` are high-risk and require strict review and tests.
- Workflow changes must keep minimal permissions and avoid broad tokens.
