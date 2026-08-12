# Invariant teeth — from refuted hand-classification to reproducible instrument (2026-07-21)

The vertical-inference L0 layer was **REFUTED** (system verdict UNVERIFIED): its
`123 teeth / 9 hollow / 0 gap` split was an unprovenanced hand-classification with no
generator, an inconsistent teeth/hollow criterion, and skipped bindings mislabelled
hollow. This replaces it with two reproducible instruments.

## Instrument 1 — deterministic binding classifier (`scripts/ci/audit_invariant_teeth.py`)
One stated criterion, skip-aware, keyed on the AUTHORITATIVE `.claude/physics/INVARIANTS.yaml`
`tests` binding (not a loose grep). Deterministic result over all 132 invariants:

| status | count | meaning |
|---|---:|---|
| **BOUND_GREEN** | **49** | witness collects, is not skip-only, and passes |
| **GAP_UNBOUND** | **78** | the registry declares NO witness at all |
| **GAP_SOURCE** | 4 | declared source file does not exist |
| **GAP_SKIPONLY** | 1 | collects but every node skipped (skip-aware — was mislabelled hollow) |
| GAP_DANGLING / BOUND_RED | 0 | — |

**The hand-classification's 123-with-teeth is refuted: only 49 invariants have a passing
bound witness** — consistent with `check_physics_law_witness_index` (which independently
reports ~53 invariants with existing witnesses), and nowhere near 123. The 78 unbound are
a real registry-completeness gap (the invariant may be tested elsewhere, but the
authoritative registry does not bind it). Floor frozen at BOUND_GREEN=49 in
`.github/invariant_teeth_baseline.json`; `--check` fail-closes on any regression.

## Instrument 2 — mutation firing-evidence (`tools/physics_mutation_check.py --all`)
"Would the test FAIL if the physics were wrong?" is proven by mutation, not asserted.
Ran all 6 registered contract mutants — every one KILLED (the witness test flipped RED,
`test_rc=1`, then the source was restored):

```
anchored_ignores_arrow        killed=YES   anchored_ignores_bekenstein  killed=YES
failure_axes_drops_arrow      killed=YES   bandwidth_inverted           killed=YES
cosmo_above_passes            killed=YES   sim_threshold_inverted       killed=YES
Killed: 6/6   (0 survivors)
```

**`bandwidth_inverted` (INV-OBSERVER-BANDWIDTH) is KILLED** — directly refuting the L0
hand-classification, which had labelled INV-OBSERVER-BANDWIDTH *hollow*. Its witness has
proven teeth: inverting the bandwidth comparison in the source makes the test fail.

## Net — L0 is no longer a hand-wave
The physics foundation is now backed by (1) a deterministic, reproducible, skip-aware
binding classifier with a frozen floor, and (2) mutation firing-evidence that the
registered physics witnesses actually catch contract regressions. The system-conformance
verdict can now be re-derived on the instrument's numbers (49 witnessed / 78 unbound),
not on the refuted 123/9/0. The honest residual is real and stated: 78 invariants carry
no registry witness binding — a coverage target, not a hidden claim.
