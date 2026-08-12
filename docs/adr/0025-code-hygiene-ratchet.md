# ADR 0025 — Code-hygiene ratchet

- Status: Accepted
- Date: 2026-06-25
- Supersedes: none
- Relates to: ADR 0024 (import-architecture ratchet)

## Context

GeoSync has strong *evidence governance* (claims, invariants, physics
contracts, repo-integrity gate) but weaker *intra-module hygiene*. A
codebase audit on the source tree found a large body of latent debt in the
first-party runtime roots: functions and classes well past any reviewable
size, high-cyclomatic functions, hundreds of broad `except Exception`
handlers (a fail-open hazard in a fail-closed research system), ambient
clock/RNG calls that defeat replay, residual `print` in runtime paths, and a
test suite carrying ~200 silent skip/xfail markers.

A one-shot cleanup of this debt is neither safe nor reviewable, and a
threshold-only linter would either fail the whole build on day one or be set
so loose it enforces nothing. The import-architecture gate (ADR 0024) already
solved the same shape of problem with a **monotone-down ratchet**: freeze
today's reality, fail on anything new, force the frozen set to shrink as debt
is paid down. We extend that proven pattern to intra-module hygiene.

## Decision

Add `scripts/ci/check_code_hygiene.py` and `scripts/ci/check_skip_ratchet.py`
— stdlib-only, AST-based, fail-closed ratchets — plus a config manifest and
frozen baselines:

- `docs/CODE_QUALITY_MANIFEST.json` — runtime roots, excluded roots, thresholds
- `docs/CODE_DEBT_BASELINE.json` — frozen hygiene debt (symbol sets + per-file counts)
- `docs/SKIP_RATCHET_BASELINE.json` — frozen test skip/xfail counts
- `docs/DETERMINISM_POLICY.md` — the determinism contract the RNG/clock dimension enforces

Dimensions tracked: `god_function`, `god_class`, `complexity`, `god_file`
(symbol-set ledgers, keyed `path::qualname`), and `broad_except`,
`runtime_print`, `ambient_nondeterminism` (per-file count ledgers). Both
ledger styles **only shrink**: a new or grown violator fails the build; a
paid-down entry left in the ledger also fails until `--write` retires it.

Enforcement is via a dedicated `code-hygiene-gate.yml` workflow (path-filtered,
required on PRs to `main`), mirroring the import-architecture gate, and a local
`make code-quality` mirror.

## Consequences

- This is a **gate, not a refactor**: it changes no runtime behaviour and adds
  no features, claims or physics maturity. It only freezes and ratchets debt.
- New code must meet the thresholds in `CODE_QUALITY_MANIFEST.json`
  (function ≤ 80 LOC, class ≤ 400 LOC, complexity ≤ 15, file ≤ 800 LOC) or it
  cannot merge.
- The P0/P1 refactors that pay the baseline down (god-module splits, typed
  exception taxonomy, `DeterminismContext` injection) are tracked separately
  and land incrementally; each tightens a baseline rather than touching the gate.
- Thresholds are intentionally not retro-applied to excluded roots (tests,
  benches, demos, drafts, vendored code).
- Deferred to follow-up PRs: dependency-group split (D-08), source-archive
  package-boundary mode (D-09), strict-typing tiers (D-06), and the runtime
  refactors themselves.
