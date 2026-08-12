# ⊛ RVG-1 — Repository Verification Gate (GeoSync deployment)

Deterministic, fail-closed audit harness. It produces a **verified evidence
vector** — not a vibe score — answering seven questions with explicit
numerators, denominators, reproduction commands, and hash-bound artifacts.

## What it computes

| Metric | Formula | Raw source |
|---|---|---|
| `test_pass_rate` | `passed / collected × 100` | `artifacts/rvg/junit.xml` |
| `line_coverage` | `covered_lines / num_statements × 100` | `artifacts/rvg/coverage.json` |
| `branch_coverage` | `covered_branches / num_branches × 100` | `artifacts/rvg/coverage.json` |
| `mutation_score` | `killed / (killed + survived) × 100` | `artifacts/rvg/mutation.json` |
| `oracle_gap` | `branch_coverage − mutation_score` | derived |
| `verified_test_strength` | `min(branch_coverage, mutation_score)` | derived |

**Core principle:** coverage ≠ correctness. Line coverage says what executed;
branch coverage says which paths executed; mutation score says whether the tests
*detect wrong behavior*. `oracle_gap` exposes where execution outruns
verification. `verified_test_strength` is the conservative floor and is the only
number allowed to be quoted as "test strength".

## Fail-closed law

`verdict = PASS` **only if every** critical gate passes (see
`audit/thresholds.json`). Missing evidence, zero denominator, unparseable
artifact, or schema-invalid verdict ⇒ `FAIL`. There is no partial-credit path.

Critical gates: tests pass · line ≥ 90 · branch ≥ 85 · mutation ≥ 75 ·
oracle_gap ≤ 15 · ruff clean · mypy clean · 0 high/critical vulns · SBOM present
· hash manifest present.

> RVG thresholds are a **floor** and are intentionally independent of GeoSync's
> repo-wide `coverage.report.fail_under = 98`. RVG never lowers an existing
> gate; it adds an orthogonal, hash-bound verdict layer.

## Reproduce

```bash
make rvg                              # clean → coverage → lint → typecheck → security → sbom → mutation → verify
make rvg-assert-bootstrap             # blocking CI gate: instrument integrity (FAIL verdict allowed)
make rvg-assert-enforce               # blocking CI gate: verdict must PASS + real mutation
```

Individual stages: `make rvg-coverage rvg-lint rvg-typecheck rvg-security
rvg-sbom rvg-mutation rvg-verify`. `make rvg` produces **sound** artifacts even
when the verdict is `FAIL` (a FAIL verdict does not abort the manifest re-bind);
the PASS/FAIL policy is enforced separately by the `rvg-assert-*` gates.
Artifacts land under `artifacts/rvg/` (git-ignored); the verdict is
`artifacts/rvg/RVG_VERDICT.json` (+ `.md`), bound by `artifacts/rvg/audit.hashes`.

## Integrity guarantees

1. **Recompute, never trust.** `rvg_audit.py` derives every percentage from raw
   counts; `rvg_verify_artifacts.py` independently recomputes them from the
   stored raw pairs and fails if any delta > 0.01.
2. **Hash binding.** Every verdict is tied to a sha256 manifest of the source +
   artifacts it was computed from.
3. **Determinism.** No wall-clock / randomness in the tools; the only varying
   fields are `timestamp_utc`, `commit`, `python_version`. Run `make rvg`
   twice and diff — anything else differing is a `FAIL`.

## CI rollout stance (bootstrap → ratchet)

The `rvg` CI job runs in an **explicit bootstrap posture** and its pass/fail
signal is decided by exactly one blocking gate: `rvg_assert_verdict.py
--mode bootstrap`. Bootstrap proves **instrument integrity** — the verdict
artifact must be schema-valid, arithmetic-recomputed, hash-bound to real files,
reproducible, and free of placeholder evidence (empty SBOM, or a `tool: none`
mutation record pretending to a score). A structurally-sound `FAIL` verdict
passes the job; a tampered or placeholder artifact does not. The PASS/FAIL
**threshold verdict itself is reported, not enforced repo-wide** — enforcing
line/branch/mutation thresholds across the whole codebase (with a real mutation
run) is a follow-up ratchet that would red every PR against gates the repo does
not yet satisfy. The PR must therefore claim *"instrument integrity PASS,
repository verdict FAIL"* — never *"gate PASS"*.

To flip to enforcement, switch the workflow's assert step to
`--mode enforce`: the verdict must be `PASS` **and** the mutation evidence must
be a real run (`bootstrap_report_only` is rejected). The default `make rvg`
audit surface is the RVG harness itself; widen it with `RVG_LINT_PATHS`,
`RVG_MYPY_TARGETS`, and `RVG_MUTATION_MODE=real` for a full-repo verdict.

## Mutation policy (§6)

`valid_mutants = killed + survived`. Timeout and incompetent/equivalent mutants
are reported separately and never silently folded into `killed`. Timeouts count
as killed only under `--timeout-stable` (fixed, non-hung runtime asserted).
`valid_mutants == 0` with a real tool is **fail-closed** (no oracle signal).

`make rvg-mutation` has three explicit modes — never a fabricated `tool: none`
score:

| `RVG_MUTATION_MODE` | Behaviour |
|---|---|
| `real` (default) | run `mutmut`, normalize its results into a real score |
| `explicit` | measured counts via `RVG_MUTATION_ARGS` (deterministic re-runs) |
| `bootstrap` | explicit **non-enforcing** evidence: `bootstrap_report_only: true`, **no score claimed** — the honest posture while the repo cannot yet run a campaign |

Bootstrap evidence is accepted by `--mode bootstrap` and rejected by
`--mode enforce`. It is *honest absence*, not a placeholder score.

## Hash binding & self-reference (§8)

`audit.hashes` is `sha256sum` output whose paths are relative to the audited
root. `rvg_verify_artifacts.py` **recomputes every digest**, rejects any entry
that escapes the root (path-traversal), and requires the verdict file to appear
(and therefore hash-match) in the manifest — an edit to `RVG_VERDICT.json` after
the manifest is emitted fails the verifier. The manifest's own line is skipped:
`sha256sum` writes the manifest while listing it, so its self-hash is
intrinsically stale (a separate `audit.hashes.sha256` strategy would be needed
to bind it, and is out of scope).

## Forbidden pseudo-metrics

"looks clean", "tests exist so it's covered", "CI is green so it's correct",
"100% line = 100% correct", "one LLM opinion = an audit", "a global quality %
with no open formula". Only metrics with an explicit numerator, denominator,
reproduction command, and artifact are admissible.
