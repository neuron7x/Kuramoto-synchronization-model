# 03 — Evidence Matrix

Every contribution mapped to repo file → PR → CI gate → artifact → failure mode
caught → remaining limitation. All references are committed on `main`.

## Contribution → evidence

| C | Repo file(s) | PR | CI gate | Artifact | Failure mode caught | Remaining limitation |
|---|---|---|---|---|---|---|
| C1 falsifier ledger | `governance/FALSIFIER_LEDGER.yaml`, `scripts/ci/check_falsifier_ledger.py` | #1302 | release-gate `H.falsification` | ledger (6 resolved) | decorative/rotted falsifier (renamed symbol, missing witness) | falsifier *adequacy* (does each null have power?) not yet measured on real data |
| C2 wheel/artifact contract | `scripts/ci/check_wheel_contract.py`, `.github/bwheel_baseline.json`, `scripts/ci/check_package_boundary.py` | #1302 | `wheel-contract-gate`, `package-boundary-gate` | `artifacts/wheel_contract.json` | 70 latent broken imports; stale `build/` re-ship; dead entrypoints | B.wheel≠0 (13 legacy packages remain) |
| C3 claim-tier governance | `scripts/ci/lint_forbidden_terms.py`, `check_claim_boundary.py`, `check_claim_artifact_graph.py` | pre-existing + #1302 | release-gate A, `claim-boundary-gate` | claim graph | unsupported promotion terms | narrow scope; bare-word bans over-reject disclaimers (by design) |
| C4 import/package ratchet | `scripts/ci/check_import_architecture.py`, `check_package_boundary.py`, `geosync/{kuramoto,runtime}/*`, `tests/ci/test_wrapper_laziness.py` | #1302, #1303 | `import-architecture-gate`, `package-boundary-gate` | `.github/import_architecture_baseline.json`, `artifacts/import_graph/*.json` | new `src.*`/`sys.path` debt; non-lazy wrapper import | core/application BLOCKED by import graph |
| C5 negative-evidence | `governance/NEGATIVE_EVIDENCE.yaml`, `scripts/ci/check_negative_evidence.py` | pre-existing | release-gate, `repo-integrity-gate` | negative-evidence ledger | rewritten/lost negatives | small seeded corpus; coverage not exhaustive |

## Dissertation artifact table

| Artifact | Path / ref | Role | Verifier |
|---|---|---|---|
| Infrastructure-gates PR | PR #1302 (merge `7928b3a9`, 47/47 CI green) | the gate suite + drains + wrapper-first | full CI |
| Laziness-invariant PR | PR #1303 (merged on green) | locks wrapper import-time-side-effect-free contract | `tests/ci/test_wrapper_laziness.py` |
| Wheel contract report | `artifacts/wheel_contract.json` | measured packaging truth (13 pkgs / 70 debt / 0 dead-script / PASS ratchet, FAIL strict) | `check_wheel_contract.py` |
| B.wheel ledger | `.github/bwheel_baseline.json` | monotone legacy-package + import-debt ledger | `check_wheel_contract.py`, `check_package_boundary.py` |
| Import-graph blockers | `artifacts/import_graph/tp_kuramoto.json`, `geosync_server.json` | machine BLOCKED evidence (35M/21I/INV; 93M/runtime) | committed, referenced |
| Falsifier ledger | `governance/FALSIFIER_LEDGER.yaml` | 6 executable nulls/kill-tests | `check_falsifier_ledger.py` |

## Methodological note

Every quantitative figure in this matrix is regenerable. The canonical commands
are in `05` and `docs/architecture/bwheel_zero_act.md`. No figure is asserted
without a reproducing command (RQ-discipline: command output > prose).
