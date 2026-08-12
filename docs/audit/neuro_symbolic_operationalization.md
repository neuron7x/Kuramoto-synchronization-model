# Neuro-Symbolic Operationalization Audit

**Status:** First-pass audit, no runtime changes.
**Branch:** `audit/neuro-symbolic-operationalization`
**Repository HEAD at audit time:** `e66946c`
**Generated:** 2026-04-27

---

## Prime directive

> Replace symbolic neuroscience with operational neuroscience-inspired engineering.

Neuroscience and physics naming is allowed in the GeoSync codebase only when the
term satisfies the chain:

```
measurable input → explicit transformation → output witness → falsifier → deterministic test → ledger entry.
```

If a term cannot satisfy that chain, it must be downgraded, renamed,
quarantined as metaphor, or rejected.

This document is the human-readable companion to:

- `.claude/neuro/NEURO_OPERATIONALIZATION_LEDGER.yaml` — machine-readable ledger.
- `tools/audit/neuro_symbolic_audit.py` — fail-closed validator.
- `tests/audit/test_neuro_symbolic_audit.py` — schema and round-trip tests.
- `artifacts/audit/neuro_symbolic_inventory.tsv` — repo-wide term inventory.

---

## Classification taxonomy

| Class         | Meaning                                                                 |
|---------------|-------------------------------------------------------------------------|
| `OPERATIONAL` | Has input, algorithm, output, INV-* falsifier and deterministic test.   |
| `PARTIAL`     | Real behaviour but missing falsifier, null model, non-claim or test.    |
| `DECORATIVE`  | Naming/metaphor with no algorithmic role tied to the term.              |
| `OVERCLAIM`   | Documentation claims biology/physics validity stronger than evidence.   |
| `LEGACY`      | Historical artifact not on the runtime path.                            |
| `REJECTED`    | Cannot be operationalised without inventing unsupported science.        |

The validator (`tools/audit/neuro_symbolic_audit.py`) enforces that:

- `OPERATIONAL` entries declare `input_contract`, `output_contract`,
  `falsifier`, at least one `inv_refs` entry, and at least one
  `existing_tests` path.
- `PARTIAL` entries declare an active `remediation_action` (not `KEEP`) and
  either a falsifier or at least one `missing_tests` entry.
- `DECORATIVE` entries on a runtime path declare an explicit "non-claim".
- `OVERCLAIM` entries do not adopt `KEEP`.
- `id` is unique, `line_range` is `[start, end]`, classifications, runtime
  flags, priorities, and remediation actions are all from closed sets.

The validator fails closed. Any malformed entry exits with code `1`.

---

## How the audit was constructed

1. **Inventory.** A 45-term scan over `*.py`, `*.md`, `*.yaml`, `*.yml`,
   `*.toml`, `*.txt` produced
   `artifacts/audit/neuro_symbolic_inventory.tsv` (3097 files with at least
   one neuro/physics term).
2. **High-signal inspection.** Every file from the audit protocol's
   "FILES THAT MUST BE INSPECTED FIRST" list was read in full or sampled
   with line-range citations.
3. **Cross-reference with `CLAUDE.md`.** Each candidate mechanism was
   matched against the 67 invariants registered in
   `CLAUDE.md` and the per-mechanism module routing table.
4. **Classification.** Every mechanism was assigned to exactly one of the
   six classes, with the strictest defensible label.
5. **Ledger.** 32 entries were written to
   `.claude/neuro/NEURO_OPERATIONALIZATION_LEDGER.yaml` covering the 25
   topic minimum from the audit protocol.

No runtime code was modified. The audit is observation-only.

---

## Distribution of the 32 ledger entries

| Class         | Count | Examples                                                             |
|---------------|------:|----------------------------------------------------------------------|
| `OPERATIONAL` |    19 | Kuramoto, Ott–Antonsen, Lyapunov, Serotonin, Dopamine, GABA, Ricci, Cryptobiosis, Free Energy, Kelly, SignalBus, GVS, DRO-ARA, AC-κ, Explosive sync, HPC bridge, Ricci flow, Serotonin ODE |
| `PARTIAL`     |     6 | Dopamine execution adapter, Neuro optimizer balance metrics, `_validation` bounds, Coherence-bridge adapter, Hebbian plasticity, Homeostatic stabilizer |
| `DECORATIVE`  |     3 | `neuro_orchestrator` scenario builder, `adaptive_calibrator`, legacy `BasalGangliaPolicy` |
| `OVERCLAIM`   |     2 | `docs/neuro_optimization_guide.md`, `docs/HPC_AI_V4.md`              |
| `LEGACY`      |     2 | Two `docs/archive/LEGACY_*` artifacts                                |
| `REJECTED`    |     1 | `docs/exocortex/RESEARCH_TIMELINE.md` "mycelium" mention             |

(Counts will drift as remediation PRs land.)

---

## Remediation queue

After this audit PR merges, one PR per mechanism, in this order:

| PR  | Target                                  | Lie blocked                                                | Goal                                                                     |
|-----|-----------------------------------------|------------------------------------------------------------|--------------------------------------------------------------------------|
| A   | `serotonin-controller`                  | "Serotonin = neuroscience validity"                        | Add explicit non-claim block; confirm INV-5HT1..7 coverage matrix.       |
| B   | `dopamine-execution-adapter-tanh`       | "Adapter is raw TD-error"                                  | Add bounds test; pin scope outside `INV-DA7`.                            |
| C   | `gaba-position-gate`                    | "GABA = generic brake"                                     | Add STDP-monotonicity test (`INV-GABA2`-style).                          |
| D   | `kuramoto-order-parameter`              | "Phase coherence = market truth"                           | Add surrogate/null comparison witness.                                   |
| E   | `ricci-flow-engine`                     | "Curvature = graph intelligence"                           | Integration invariant test combining INV-K1, INV-OA1, INV-RC1.           |
| F   | `hebbian-plasticity-update`             | "Plasticity = parameter update"                            | Stability criterion + bounded-input test.                                |
| G   | `cryptobiosis-state-machine`            | "Cryptobiosis = mystical freeze"                           | Already operational — extend to neuroeconomics protective state.         |
| H   | `neuro-optimization-guide-overclaim`, `docs-hpc-ai-v4-overclaim` | "Docs claim verified neuroscience"   | Add per-claim source/test references; explicit non-claim preamble.       |
| I   | `neuro-orchestrator-scenario-builder`, `adaptive-calibrator-annealing`, `basal-ganglia-policy-legacy` | "Naming-only neuroscience on runtime"           | Rename to neutral terms; add non-claim block.                            |

Every remediation PR must follow §11 of the audit protocol and be CLOSED
only when:

- The mechanism has explicit input.
- The mechanism has explicit output witness.
- The mechanism has a falsifier.
- All tests pass.
- No biological-equivalence claim remains.
- The ledger entry is upgraded or downgraded honestly.
- `git diff` is clean after a falsifier round-trip (poisoned entry → red,
  restore → green).

---

## Local commands

```bash
# Validate the ledger.
python tools/audit/neuro_symbolic_audit.py

# Run the audit tests.
python -m pytest tests/audit/test_neuro_symbolic_audit.py -v

# Static analysis.
python -m ruff check tools/audit/neuro_symbolic_audit.py tests/audit/test_neuro_symbolic_audit.py
python -m ruff format --check tools/audit/neuro_symbolic_audit.py tests/audit/test_neuro_symbolic_audit.py
python -m black --check tools/audit/neuro_symbolic_audit.py tests/audit/test_neuro_symbolic_audit.py
python -m mypy --strict tools/audit/neuro_symbolic_audit.py tests/audit/test_neuro_symbolic_audit.py
```

---

## Final law

> Neuroscience is not decoration.
> Neuroscience is an algorithmic constraint source.
>
> If the concept does not change behavior, remove it from runtime naming.
> If it changes behavior but cannot be falsified, downgrade it.
> If it is falsifiable and tested, keep it.
> If it claims biology, prove only the engineering analog.
