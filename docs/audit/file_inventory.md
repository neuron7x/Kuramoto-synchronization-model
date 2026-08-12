# Physics File Inventory Baseline

Status: BOOTSTRAP_INVENTORY
Scope: GeoSync repository / branch `physics-validation-v3`
Generated from connector-visible repository search and inspected files. A full local scan must be run by `tools/physics_score.py --write` before CP0 can pass.

## Inventory verdict

```text
CP0_OBSERVATION_GATE: BLOCKED_FOR_FULL_LOCAL_SCAN
GEOSYNC_T1_SURFACE: PRESENT
BN_SYN_SOURCE_TREE: NOT_PRESENT_IN_THIS_REPO_SCOPE
MFN_PLUS_SOURCE_TREE: NOT_PRESENT_IN_THIS_REPO_SCOPE
PHYSICAL_RANK_CLAIM: FORBIDDEN
```

## Physics-relevant files discovered

| file | class | subsystem | evidence role | status | required action |
|---|---|---|---|---|---|
| `core/kuramoto/kuramoto_ricci_engine.py` | code | GeoSync / Kuramoto-Ricci | RHS, boundary, trajectory, order parameter, potential | ACTIVE_CORE_CANDIDATE | keep as canonical candidate; test through scoring oracle |
| `tests/unit/physics/test_T1_kuramoto_ricci_boundary.py` | test | GeoSync / Kuramoto-Ricci | boundary, null, invariant, determinism, negative controls | ACTIVE_TEST_SURFACE | include in falsification score |
| `docs/laws/T1_kuramoto_ricci_boundary.md` | theory doc | GeoSync / Kuramoto-Ricci | equation, threshold, invariant table, references | ACTIVE_THEORY_DOC | map claims into claim ledger |
| `core/kuramoto/ricci_flow_engine.py` | code | GeoSync / Ricci | Ricci-related implementation surface | UNINSPECTED_IN_THIS_PASS | classify as experimental until bridge proof is audited |
| `core/kuramoto/__init__.py` | code | GeoSync / Kuramoto | export surface | UNINSPECTED_IN_THIS_PASS | verify exported API matches canonical object |
| `core/kuramoto/lyapunov_calibration.py` | code | GeoSync / Lyapunov calibration | T3 calibration surface | UNINSPECTED_IN_THIS_PASS | link only after T2/T3 claim ledger entry exists |
| `core/physics/lyapunov_spectrum.py` | code | GeoSync / Lyapunov | dependency for T1 tests | REFERENCED_NOT_FETCHED | inspect in Phase 0 local scan |
| `.claude/commit_acceptors/law-T1-kuramoto-ricci-boundary.yaml` | governance | GeoSync / T1 | acceptor contract | UNINSPECTED_IN_THIS_PASS | verify against current tests |
| `.claude/physics/INVARIANTS.yaml` | governance | GeoSync invariants | invariant registry | UNINSPECTED_IN_THIS_PASS | reconcile with claim ledger |
| `docs/laws/T2_lyapunov_spectrum.md` | theory doc | GeoSync / Lyapunov | dependent theory law | UNINSPECTED_IN_THIS_PASS | classify claims |
| `governance/PHYSICS_RELIABILITY.yaml` | governance | repo physics reliability | policy surface | UNINSPECTED_IN_THIS_PASS | map merge gates |
| `physics_contracts/catalog.yaml` | contract | repo physics contracts | contract catalog | UNINSPECTED_IN_THIS_PASS | include in interface-contract score |
| `docs/math/inventory.md` | doc | math inventory | existing inventory | UNINSPECTED_IN_THIS_PASS | compare with this file |
| `tools/physics/clamp_registry.yaml` | config | physics clamp registry | bounds/guards | UNINSPECTED_IN_THIS_PASS | classify as dimensional/range evidence |
| `docs/CLAIMS.yaml` | claim registry | repo claims | claim source | UNINSPECTED_IN_THIS_PASS | compile into `claim_ledger.md` |
| `BASELINE.md` | baseline doc | repo baseline | baseline source | UNINSPECTED_IN_THIS_PASS | verify whether it contains machine-computed physics baseline |
| `pyproject.toml` | project config | repo | deps, python range, scripts | INSPECTED | record dependency/runtime constraints |

## Runtime/package evidence

| fact | evidence | status |
|---|---|---|
| project name is `geosync` | `pyproject.toml` | VERIFIED_STATIC |
| python range is `>=3.11,<3.13` | `pyproject.toml` | VERIFIED_STATIC |
| JAX is a runtime dependency | `pyproject.toml` | VERIFIED_STATIC |
| pytest is available under `dev` extra | `pyproject.toml` | VERIFIED_STATIC |
| `tp-kuramoto` entrypoint exists | `pyproject.toml` | VERIFIED_STATIC |

## Scope blocks

| block_id | target | reason | resolution |
|---|---|---|---|
| BLOCK-BNSYN-001 | BN-Syn validation | no BN-Syn source tree discovered in GeoSync search surface | attach BN-Syn repo/commit or vendor immutable source snapshot |
| BLOCK-MFN-001 | MFN+ validation | no MFN+ reaction-diffusion source tree discovered in GeoSync search surface | attach MFN+ repo/commit and explicit `f(u,v), g(u,v)` definitions |
| BLOCK-LOCAL-001 | CP0 full pass | connector search is not equivalent to full local tree walk | run `python tools/physics_score.py --write` on checkout |

## CP0 decision

```text
CP0_STATUS: BLOCKED
PASS_REASON: none
BLOCK_REASON: full file discovery must be produced by local deterministic scan
NEXT_ACTION: run tools/physics_score.py --write and commit generated artifacts
```
