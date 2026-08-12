# CNS Alignment Deep Tasks (Compact Canon)

## Law

$$
\text{Truth}(S) \propto \text{Coherence}(\text{Intent},\text{Time},\text{Energy},\text{Error},\text{Control})
$$

$$
\text{Ugly}(S) \equiv \text{HiddenContradiction}(S)
$$

Tests prove `∃t` correctness. Architecture must enforce `∀t` coherence.

## Non-negotiable principles

1. **Witness ≠ Actor** (observe and act are separate planes).
2. **Coherence is derived, never assigned**.
3. **Cross-layer mismatch is a first-class failure signal**.
4. **Failure must produce structured witness telemetry**.
5. **Beauty = minimal mechanics for maximal function**.

## L0 — Contract kernel (implemented)

**Deliverables**
- `schemas/cns/control_ontology.schema.json`
- `configs/cns/control_ontology.v1.json`
- `configs/cns/stream_registry.v1.json`
- `scripts/check_cns_ontology_usage.py`
- `tests/test_cns_ontology_guard.py`
- `docs/architecture/cns_ontology.md`

**Acceptance rules**
- Ontology covers all 5 coherence axes.
- Ontology covers all 4 control roles.
- Each variable has canonical contradiction event (`HiddenContradiction.*`).
- Each variable has dynamic stream contract (`source_stream`, `cadence_ms`, `max_staleness_ms`, `lag_tolerance_ms`).
- Stream contracts must match registry SLA bounds.

## L1 — Coherence derivation discipline

- Protect derived coherence variables from manual assignment in runtime paths.
- Require units + timestamp provenance for each coherence term.
- Emit contradiction events for derivation breaks.

## L2 — Failure intelligence

- Every incident must emit replayable witness bundle.
- Bundle must include 5-axis coherence gap vector.
- Measure MTTR and contradiction density trend.

## L3 — Traceability

- Build law → code → telemetry → alert map for each invariant.
- No critical runtime gate without linked invariant witness.

## L4 — Elegance pressure

- Add/remove symmetry audits for irreducibility.
- Complexity increases require explicit coherence gain.

## 90-day sequence

1. **Days 1–14:** lock L0 in CI and enforce registry-coupled flow contracts.
2. **Days 15–45:** add coherence-derivation protection and contradiction telemetry.
3. **Days 46–90:** complete invariant traceability map + elegance budgets.

## KPIs

- Boundary integrity violations = 0.
- Missing-axis or missing-role ontology violations = 0.
- Unregistered stream references = 0.
- Replay-complete incident bundles ≥ 95%.
- Contradiction density trending down release-over-release.
