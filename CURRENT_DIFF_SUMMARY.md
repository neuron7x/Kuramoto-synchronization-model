# CURRENT_DIFF_SUMMARY.md

State of the working tree at the start of the post-audit execution-hardening
pass (audit tasks B1–B6 / T1–T10). Branch: `fix/honest-spine-and-truth-gates`,
based on `main` after `#910` (`e7709042`).

## Provenance of this branch

A prior session opened `#911` for the audit's B1/B2/B3 honest downgrade. While
it was in CI, the maintainer merged `#910`, which fixed the same two C3
false-confidence findings by *strengthening the tests* (no exemption). That made
`#911`'s manifest-waiver approach redundant cruft. Rather than rebase the cruft,
this branch **consolidates**: it cherry-picks only the clean B1/B2/B3 commit from
`#911`, drops the C3 waivers / fcd-c8 re-pin / secrets pragma entirely (main
already handles C3), and adds the T1–T10 second-layer hardening. `#911` is closed
in favour of this branch.

## Files already modified (carried from B1/B2/B3, no overwrite of others' work)

| File | Audit task | Nature |
| --- | --- | --- |
| `core/indicators/__init__.py` | B3 | lazy PEP 562 re-exports |
| `core/data/feature_store.py` | B3 | lazy `cryptography` import |
| `observability/__init__.py` | B3 | lazy PEP 562 re-exports |
| `observability/notifications.py` | B3 | lazy `httpx` import |
| `.importlinter` | B3 | Contract 6 (`core.indicators ⊬ core.data.feature_store`) |
| `tools/research/research_cli.py` | B1 | documented provenance-stamp-only gateway |
| `research_lines/ricci_microstructure_v1/contract.yaml` | B2 | `INSTRUMENTED` / `HYPOTHESIS` |
| `artifacts/runs/ricci_microstructure_v1/example_artifact.json` | B2 | explicit `NOT_RUN` placeholder |
| `README.md` | B1/B4 | de-spined; substrate stated honestly |

## Audit tasks in progress / completed on this branch

| Task | Status | Evidence |
| --- | --- | --- |
| T1 truth gate | done | `scripts/ci/check_research_artifact_truth.py` + 11 tests |
| T2 semantic validator | done | `validate_artifact_semantics()` + `--semantic` + tests |
| T3 Ricci downgrade | done (honest) | no L2 data exists → HYPOTHESIS placeholder, not fabricated |
| T4 python matrix | done | `pr-gate.yml` PyO3 `3.13 → 3.12` |
| T5 namespace policy | done | 3 shims repaired to local-src, `risk_factory` → `Any` |
| T6 manifest non-vacuous | done | `--min-artifacts` / `--require-artifacts` + tests |
| T7 release harness | done | `ricci_schema_semantic` + `research_artifact_truth` gates |
| T8 claim→artifact graph | done | `scripts/ci/check_claim_artifact_graph.py` + 8 tests |
| T9 one-command proof | done | `scripts/ci/prove_repo_integrity.sh` |
| T10 benchmark protocol | done | `MODEL_AUDIT_BENCHMARK.md` |

## Safe to continue

Everything above is additive or a strict honesty-downgrade. No unrelated
subsystem was rewritten. The only deletions are of `#911`'s now-redundant C3
governance artefacts, which `#910` superseded on `main`.

## What was explicitly NOT done (honest scope)

- `ricci_microstructure_v1` was **not** promoted. No real L2/order-book session
  exists; fabricating one is forbidden. It stays a HYPOTHESIS placeholder.
- `MANIFEST_PROOF` is reported `NOT_PROVEN` — there is no real hash-pinned
  artifact graph yet, and the proof script says so rather than faking success.
