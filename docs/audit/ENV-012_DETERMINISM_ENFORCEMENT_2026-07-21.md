# ENV-012 — deterministic execution policy: enforced, with live teeth (2026-07-21)

**Deliverable status: satisfied by existing + newly-proven enforcement.** ENV-012 asks for a
deterministic execution policy. It exists AND is gated:

1. **Policy** — `docs/DETERMINISM_POLICY.md` defines the contract: no ambient clocks
   (`datetime.now`/`time.time`/…), sleeps, or RNG in the runtime roots; time/randomness must come
   from an injected `DeterminismContext` (Clock + SeedContext); every runtime/research artifact
   declares its substrate.

2. **Enforcement (fail-closed ratchet)** — `scripts/ci/check_code_hygiene.py` runs the
   `ambient_nondeterminism` dimension as a **monotone-down ratchet** over the runtime roots
   (`geosync`, `execution`, `application`, `runtime`, `core`, `coherence_bridge`,
   `physics_contracts`), frozen in `docs/CODE_DEBT_BASELINE.json`. A new ambient call, or a higher
   count in a flagged file, fails the build; paying down requires `--write`.

3. **Reproducibility proof** — `core/physics/determinism_kit.py` (Law T6, INV-DET1..3) +
   `scripts/ci/check_reproducible_archive.py` (REL-010) prove bit-identical replay of sealed
   artifacts.

## Live teeth demonstration (this is why ENV-012 is closeable now, not just documented)
The ratchet was found **RED on `main`**: `geosync/risk/kill_switch.py` had risen 3→4 ambient
calls — MR!34 added a `datetime.now()` in the corrupt-load HALTED fallback, uncaught because CI
quota is exhausted and the gate is not in the slim integrity subset. The violation was **removed**
(the fallback is not a trading event; forensic timing stays in the log), restoring 4→3 and GREEN.
A policy that catches a real, freshly-introduced violation in safety-critical code is enforced,
not decorative.

## Honest residual
The ratchet freezes existing ambient-nondeterminism debt (339 over-budget symbols / 824 flagged
call-sites) for monotone paydown — it forbids GROWTH, not yet zero. That debt is ARC-008's
workstream; ENV-012's deliverable is the *policy + fail-closed enforcement + reproducibility
proof*, all present and demonstrated. This document is the ENV-012 evidence artifact.
