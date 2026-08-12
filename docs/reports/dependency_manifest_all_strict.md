# Dependency manifest consistency — advisory → all-strict (P0-1)

## Claim

No install path can resolve a security-critical package below its
`constraints/security.txt` floor.

## Source → failure mode

`constraints/security.txt` is the single source of truth for patched lower
bounds. A manifest that declares a *lower* floor silently re-admits a vulnerable
version. PR #1113 made `pyproject.toml` (the `pip install .` path) strict but
left `requirements.txt` / `requirements-backend.txt` **advisory**, because the
security-sweep lane (PR #1111) owned those files and a concurrent strict promote
would have caused a cross-branch write conflict. **Failure mode:** a deployment
that installs via `pip install -r requirements.txt` could still resolve below
the floor while CI stayed green.

## Adapt (smallest closing unit)

- **#1111 has landed**, so the advisory carve-out is closed.
- `tools/security/check_dependency_manifest_consistency.py` is now **strict by
  default** for every manifest; `--advisory-requirements` restores the legacy
  reporting-only mode (diagnostics, not a correctness bypass). `--all-strict` is
  retained as a backward-compatible no-op.
- `requirements.txt` `fastapi` floor raised `>=0.120.0` → `>=0.136.3` (the one
  manifest that lagged the policy).
- `tests/security/test_dependency_manifest_consistency.py` gains
  `test_all_manifests_consistent_with_security_floor` (asserts `strict + advisory
  == []`), `test_main_is_strict_by_default`, and a flag-parse guard.

## Verification chain

| Link | Evidence |
|---|---|
| command | `python tools/security/check_dependency_manifest_consistency.py` → exit 0 |
| test | `pytest -q tests/security/test_dependency_manifest_consistency.py` → green |
| static | `ruff` + `black` + `mypy --strict` clean on changed sources |
| acceptor | `.claude/commit_acceptors/dependency-manifest-all-strict.yaml`, diff-binding EXIT 0 |
| failure mode | a below-floor requirements pin makes the **default** gate exit 1 |

## Blocked claims

- This gate proves **floor consistency across declared manifests**. It does not
  prove the *installed environment* is floor-consistent (that is `pip-audit` /
  lockfile attestation, tracked separately) and makes **no** runtime, market, or
  predictive claim.
