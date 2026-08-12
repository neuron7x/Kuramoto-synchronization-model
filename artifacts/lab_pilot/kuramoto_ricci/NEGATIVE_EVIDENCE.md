# NEGATIVE EVIDENCE — what this pilot did NOT do

Honest boundary of the slice. No failure is hidden; nothing below is a defect
introduced by this PR.

## Validation: no blockers encountered

All gates ran clean on the touched scope (see VALIDATION_REPORT.json):
ruff, black, mypy --strict (35 source files), 20 new tests, 332-test kuramoto
unit regression (1 pre-existing skip, unrelated). No pre-existing repo debt
blocked the slice.

## Stale premise in the order

The order's Stream 4 targets an `arctan2(std, mean)` proxy phase. **No such
proxy exists in `core/`.** `phase_extractor.py` already extracts phase via
bandpass+Hilbert (primary), CEEMDAN+Hilbert and SSQ-CWT (validation), with
Q1–Q4 quality gates. The `arctan2` calls in `core/indicators/kuramoto.py` are
analytic-signal phase `arg[z] = arctan2(ℋ{x}, x)` — legitimate, not a proxy.
Stream 4 as written does not apply to this repository state.

## Deliberately out of scope (one enforceable slice, not eight)

NOT implemented — each is a candidate for a follow-up PR:

- Stream 2: attractive/signed *regime* split inside the engines (CouplingSpec
  now carries the claim boundary, but engines do not yet consume it to gate
  INV-K theorems).
- Stream 3: Ricci sign preservation / clipped-adjacency information-loss
  metadata. `ricci_flow*.py` not modified.
- Stream 5: multiscale single-series coherence relabeling to a Layer-B
  descriptor.
- Stream 6: weighted / signed / thresholded Forman-Ricci split.
- Stream 7: second-order (swing) solver stability-audit object. `second_order.py`
  already has INV-K8/K9/K10 coverage; a structured audit record is not added.
- Stream 8: higher-order hypergraph/simplicial representation guard.

## Residual risk not closed by this PR

`KuramotoConfig(K=..., adjacency=W)` — the *bare* constructor — still permits
`C = K·W` double-scaling. This PR adds the safe path (`from_coupling_spec`,
which pins `K=1`) and the contract object, but does **not** deprecate or block
the legacy two-argument path, to avoid breaking existing callers and green
tests in a single slice. Migrating call sites and fail-closing the bare path is
the natural next PR. This is stated, not hidden.
