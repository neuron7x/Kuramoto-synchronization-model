# GAP_SOURCE closure — teeth floor 49 → 53 (2026-07-21)

The deterministic teeth instrument (`scripts/ci/audit_invariant_teeth.py`) reported
**GAP_SOURCE=4** — four invariants that bind a witness test yet were classified as having a
non-existent source file. Investigation showed all four source files **exist**; GAP_SOURCE=4
was a **classifier defect**, not a registry defect:

| invariant | declared source | real cause |
|---|---|---|
| INV-CBR1 | `coherence_bridge/physics_contract.py::validate_physics_contract` | `::symbol` suffix not stripped before existence check |
| INV-HOM1 | `geosync/neuroeconomics/homeostatic_stabilizer.py::NeuroHomeostaticStabilizer` | same |
| INV-AC1-rev | `geosync/estimators/dfa_gamma_estimator.py::AdaptiveCriticalityGate` | same |
| INV-OA2 | *(absent)* | registry incompleteness — group header documented the source but the invariant had no `source:` field |

## Fix
1. **Classifier** (`classify()`): strip the `::symbol` suffix before the source file-existence
   check, mirroring the tests branch which already does `p.split("::", 1)[0]`. A symbol-qualified
   source (`foo.py::Bar`) was being read as the literal path `foo.py::Bar`, which never exists.
2. **Registry** (`.claude/physics/INVARIANTS.yaml`): add `source: core/kuramoto/ott_antonsen.py`
   to INV-OA2.

## Result
All four reclassify from GAP_SOURCE to **BOUND_GREEN** (verified per-invariant: their witness
tests collect and pass). `bound_green_floor` raised 49 → **53** in
`.github/invariant_teeth_baseline.json`. This **reconciles the discrepancy the fractal health
map flagged** — `check_physics_law_witness_index` independently reports ~53 witnessed invariants,
while the teeth instrument had said 49; the 4-invariant gap was exactly this classifier bug.

The honest residual is unchanged in kind: GAP_UNBOUND=78 invariants still carry no registry
witness binding — a real coverage target, not a hidden claim.
