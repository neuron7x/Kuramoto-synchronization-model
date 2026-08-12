# Epistemic Validation — Fail-Closed Sustainer

Acceptor: `.claude/commit_acceptors/epistemic-validation-fail-closed.yaml`
Module: `core.neuro.epistemic_validation`
Tests: `tests/unit/neuro/test_epistemic_validation.py` (49 cases)

## Promise

The module supplies a Layer 2 *sustainer* — per CLAUDE.md §0
*Ontology of Gradient* — that maintains an information-cost budget
while accumulating windowed evidence on signal/fact agreement.
`ACTIVE → HALTED` is one-way. Halt is sticky inside this module.
Recovery requires an external reset — by construction this composes
with `runtime.rebus_gate.RebusGate` via `RebusBridge.maybe_escalate`,
which forwards a halted state as `stressed_state=True` to
`RebusGate.apply_external_safety_signal` and triggers the existing
`emergency_exit` path. Cryptobiosis remains the Layer 3 last-resort.

## Invariants enforced

| Invariant | Coverage |
|---|---|
| INV-FE2 (universal, P0) — components non-negative; `budget ≥ 0`, `weight ∈ [0, 1]`, surprise cost `c(Δ) ≥ 0` | Hypothesis property tests `test_property_budget_non_negative`, `test_property_weight_bounded` |
| INV-HPC1 (universal, P0) — seeded reproducibility, identical input ⟹ identical chain hash | `test_genesis_is_pure`, `test_state_hash_format_pinned` |
| INV-HPC2 (universal, P0) — finite-input ⟹ finite-output | `test_update_rejects_non_finite_inputs`, `test_verify_stream_rejects_non_finite` |

The composite `(weight, budget)` is **not** aggregated into a quantity
that pretends to be Helmholtz `F = U − T·S`. Helmholtz F can be
negative per INV-FE2 — collapsing the two would abuse the contract.
The `budget` register is therefore distinct, named explicitly as an
information capacity in nats, and clamped at zero from below.

## What this module is NOT

* Not a Landauer cost model. The cost function
  `c(Δ) = T·log1p(|fact − signal|)` is information-theoretic surprise
  (nats), not `kB·T·ln 2` per erased bit. The multiplier is a
  dimensionless `temperature`, not `kT`.
* Not a Bayesian posterior. The evidence weight is a windowed
  exponential moving average; the variable name reflects the
  semantics.
* Not an active-inference implementation. It composes with — but
  does not replace — `geosync_hpc.hpc_active_inference_v4`. An
  exhausted budget on this gate signals that the active-inference
  layer has accumulated more surprise than the configured tolerance
  admits.

## Chronology discipline

* `EpistemicState.seq` — monotonic 64-bit step counter; advances by
  exactly 1 per accepted update; frozen on halt.
* `EpistemicState.state_hash` — hex-encoded SHA-256 chain over the
  prior hash and a deterministic 65-byte packing (32-byte prior
  digest, 8-byte big-endian `seq`, three IEEE-754 little-endian
  doubles for `weight` / `budget` / `invariant_floor`, one halt
  byte). Pinned by `test_state_hash_format_pinned` — any future
  refactor that changes the packing breaks persisted lineages and
  must be migrated explicitly.
* Halt flag is *derived* from `(budget, weight, floor)`, not a
  trust-me boolean. Halt reason is one of `"budget_exhausted"` or
  `"weight_collapse"` — empty string for active states.
* Inside this module the transition is one-way; there is no
  `REENTRY` path. Composition with `RebusGate` provides the
  external-reset semantics the contract requires.

## Falsifier coverage

The acceptor's `falsifier.command` filter selects four halt-axis
tests:

* `test_sticky_halt_returns_state_unchanged` — any post-halt
  `update(...)` returns the original halted state by identity.
* `test_budget_exhaustion_halts_with_reason` — the first step that
  would overspend the budget halts with `halt_reason ==
  "budget_exhausted"`.
* `test_weight_collapse_halts_with_reason` — a step that drives the
  EMA below the configured floor halts with `halt_reason ==
  "weight_collapse"`.
* `test_property_halt_is_sticky` — Hypothesis fuzz of randomised
  post-halt streams; the snapshot identity holds for every example.

Together these four cases cover both halt-trigger axes (budget and
weight) and the stickiness invariant. A regression that left any
post-halt path mutating state, or any halt path tagging the wrong
reason, would surface here without depending on stochastic timing.

## Quality gates

| Gate | Status |
|---|---|
| `black --check` | clean |
| `ruff check` + `ruff format --check` | clean |
| `mypy --strict` (module + tests + `__init__.py`) | clean |
| `pytest tests/unit/neuro/` | 145 passed (49 new + 96 prior) |
| `.claude/physics/validate_tests.py` | no issues (87 invariants loaded) |

## Public surface

Wired into `core.neuro` lazy exports:

* `EpistemicConfig` — frozen configuration; bounds-checked at
  construction.
* `EpistemicState` — frozen per-step state; identified by chain
  hash.
* `EpistemicPhase` — `ACTIVE` | `HALTED`.
* `EpistemicError` — subclass of `ValueError`; raised at every
  contract boundary with an INV-tagged message.
* `RebusBridge` — composition primitive; forwards halted states as
  `stressed_state=True` to a `RebusGate`.

The per-step functions (`initial_state`, `update`, `verify_stream`)
remain submodule-only to avoid generic-name collisions. Import them
directly from `core.neuro.epistemic_validation`.
