# Dependency Security-Floor Policy

## Source of truth

`constraints/security.txt` is the **single source of truth** for the patched
floor of every security-critical package. Each entry pins the lowest version
that is not subject to a known advisory.

## Invariant

For every package in `SECURITY_CRITICAL`, the declared lower bound in each
manifest must be **`>=` the `constraints/security.txt` floor**. A lower bound
below the floor silently re-admits a vulnerable version.

`pip install .` resolves against `pyproject.toml`, so a stale `pyproject` floor
bypasses any floor raised only in `requirements.txt`. The gate exists to make
that drift fail closed.

## Security-critical packages

```
pyjwt  cryptography  aiohttp  starlette  tornado  python-multipart  fastapi
```

## Manifest ownership & enforcement scope

| Manifest | Owner | Gate scope |
| --- | --- | --- |
| `constraints/security.txt` | security policy | source of truth |
| `pyproject.toml` | this gate | **strict** (exit 1 on violation) |
| `requirements.txt` | this gate | **strict** (exit 1 on violation) |
| `requirements-backend.txt` | this gate | **strict** (exit 1 on violation) |

**All-strict (P0-1).** The security-sweep lane (PR #1111) that previously owned
`requirements*.txt` has landed, so the advisory carve-out is closed: every
manifest is now enforced strict. No install path — `pip install .` via
`pyproject.toml`, or `pip install -r requirements*.txt` for deployment — may
resolve a security-critical package below its `constraints/security.txt` floor.
The live test `test_all_manifests_consistent_with_security_floor` asserts zero
violations across all manifests, and the CLI is strict by default. The
deprecated `--advisory-requirements` flag restores reporting-only mode for
`requirements*.txt` (diagnostics, not a correctness bypass).

## Gate

```bash
python tools/security/check_dependency_manifest_consistency.py              # strict, all manifests
python tools/security/check_dependency_manifest_consistency.py --advisory-requirements  # legacy reporting mode
pytest -q tests/security/test_dependency_manifest_consistency.py
```

The pytest test is collected by the fast PR gate, so the pyproject invariant is
enforced on every PR without a dedicated workflow step.

## Exception policy

No security-floor exception is admitted without:

```
package · advisory id · affected versions · is the vulnerable code path used? ·
mitigation · scanner/gate that enforces the mitigation · expiry/recheck date · owner
```

Record exceptions in `docs/security/vulnerability_exception_ledger.md` (create
on first exception).

## Related existing controls (not duplicated here)

- `scripts/security/check_dependency_drift.py` — validates manifest specifiers
  against the **lockfile** (orthogonal: lock satisfaction, not cross-manifest
  floor consistency).
- `tests/security/test_checkpoint_loading.py` — asserts the `geosync_*`
  checkpoint loaders pass `torch.load(..., weights_only=True)` at runtime
  (behavioural, two call sites).
- `tools/security/check_forbidden_torch_jit.py` — repo-wide **static** gate
  (P0-3) that fails closed on `torch.jit.{script,trace,load}` and on any
  `torch.load` call lacking the literal `weights_only=True`. This is the
  control that *enforces* the torch deserialization-advisory dismissal across
  every call site, not just the two covered by the behavioural test. Policy:
  `docs/security/forbidden_torch_jit_policy.md`; reviewed exemptions:
  `tools/security/forbidden_torch_jit_allowlist.json`.
