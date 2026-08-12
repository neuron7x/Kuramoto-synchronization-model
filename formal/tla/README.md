# TLA⁺ Formal Specifications

This directory carries machine-checked formal specifications of GeoSync
control-plane protocols. Today there is one: the four-barrier admission
gate shipped in PR #322 / PR #323 (``core/events/admission.py``).

## AdmissionGate

| Artefact | Purpose |
|---|---|
| [`AdmissionGate.tla`](AdmissionGate.tla) | State-machine specification of the admission gate, three safety invariants encoded as TLC-checkable predicates |
| [`MC.cfg`](MC.cfg) | TLC model configuration — small but exhaustive state space covering every barrier permutation |

### Invariants proved

| Invariant | Statement |
|---|---|
| `TypeOK` | Every emitted verdict is well-formed — barrier ∈ {B1, B2, B3, B4, NONE}, code ∈ canonical code set |
| `SafeFirstRejectionWins` | An accepted verdict carries barrier = NONE and code = OK; no barrier bypass is possible |
| `RejectCodeMatchesBarrier` | Every rejection cites the canonical code for its triggering barrier (no mis-labelling) |

### Running the model checker locally

```bash
# one-time: fetch TLA+ tools
wget -q https://github.com/tlaplus/tlaplus/releases/latest/download/tla2tools.jar -O /tmp/tla2tools.jar

# model-check the spec
java -cp /tmp/tla2tools.jar tlc2.TLC -config MC.cfg AdmissionGate.tla
```

Expected output tail on a clean repo checkout:

```
Model checking completed. No error has been found.
  Estimates of the probability that TLC did not check all reachable states
  because two distinct states had the same fingerprint:
  ...
853 states generated, 547 distinct states found, 80 states left on queue.
The depth of the complete state graph search is 9.
Finished in 00s at ...
```

Runs in well under two seconds. No external services, no network, no
randomness — a hermetic formal artefact.

### Why a TLA⁺ spec of the admission gate specifically

Unit tests probe ``∃t`` correctness — "here is one input sequence that
triggers this barrier". The CNS alignment law (see
[`docs/CNS_ALIGNMENT_DEEP_TASKS.md`](../../docs/CNS_ALIGNMENT_DEEP_TASKS.md))
demands ``∀t`` coherence — "no admissible input sequence produces an
accepted contradiction". TLA⁺ + TLC checks that universally on the
state space the constants carve out; a failing barrier ordering, a
mis-labelled reject, or a silent bypass would surface as a
counterexample trace.

### Refinement obligation

Any change to ``core/events/admission.py`` that alters the barrier
ordering, adds / removes a reject code, or changes the structural
contract of ``AdmissionVerdict`` MUST include a corresponding update
to ``AdmissionGate.tla`` and a fresh TLC run showing the invariants
still hold. The CI workflow at
``.github/workflows/formal-verification.yml`` enforces this.
