# Micro-Scale Dynamic Bug Fractal Audit (Reverse/Falsification Oriented)

## 1) Problem statement (one sentence)
Hidden micro-instabilities in time, randomness, state transitions, and observability can compound in long-running dynamic environments and become visible only after delayed feedback cycles.

## 2) Falsifiable hypothesis
If we isolate temporal, stochastic, and stateful pathways and force deterministic replay under adversarial perturbations, then delayed divergence classes can be reproduced in under controlled horizons; otherwise the hypothesis is rejected.

**Refutation condition:** with fixed seeds, frozen clocks, and replayed input streams, output trajectories remain within tolerance envelope for all monitored invariants over a 10^4-step horizon.

## 3) Invariants (defined before code changes)
1. **Clock monotonicity invariant:** event timestamps used for ordering must be non-decreasing per stream.
2. **Replay determinism invariant:** fixed seed + identical input => identical outputs.
3. **State serialization invariant:** persisted state reloaded at `t+n` preserves risk/kill-switch semantics.
4. **Fail-closed invariant:** any invariant breach drives safe fallback, not permissive continuation.
5. **Metric integrity invariant:** telemetry timestamps reflect the same clock model as domain events.

## 4) Contract framing (I/O, bounds)
- Input: market/event stream, config, clock source, stochastic seed.
- Output: decisions, risk states, telemetry tuples, persisted snapshots.
- Bounds: bounded memory growth, bounded latency under normal load, deterministic replay mode.

## 5) Fractal bug map (micro -> meso -> macro)

### Class A — Time-domain drift and dual-clock mismatch
**Micro trigger:** mixed use of `datetime.now(timezone.utc)` and `time.time()` across subsystems.

**Observed signal locations:**
- Risk engine and kill-switch use wall-clock datetime UTC.
- Neural telemetry metric buffer records float epoch seconds.

**Potential delayed effect:** ordering ambiguity and reconciliation skew during replay/cross-service joins.

### Class B — Entropy governance inconsistencies
**Micro trigger:** mixed patterns of seeded RNG, hardcoded seeds, and implicit randomness usage.

**Potential delayed effect:** flaky regime boundary behavior, irreproducible backtest/live discrepancy.

### Class C — Silent exception absorption / no-op branches
**Micro trigger:** `pass` pathways in core modules where telemetry or escalated handling may be expected.

**Potential delayed effect:** low-signal fault accumulation that manifests as late-stage state divergence.

### Class D — Stateful lifecycle edges
**Micro trigger:** daily reset, kill-switch timestamping, and state persistence using runtime wall-clock.

**Potential delayed effect:** reset race windows and inconsistent recovery semantics after restart.

## 6) Reverse-analysis protocol (how to break our own assumptions)
1. Freeze clock and replay same stream with/without restarts.
2. Inject clock skew (+/- 500ms, +/- 5s) at subsystem boundaries.
3. Run dual-seed and fixed-seed matrix for stochastic components.
4. Force persistence corruption / stale snapshot restoration.
5. Compare decisions and risk states with null-model baseline.

## 7) Priority bug backlog (actionable)
1. Introduce unified clock adapter for domain + telemetry paths.
2. Enforce explicit RNG injection in critical code paths (no implicit global RNG).
3. Replace silent `pass` with structured warning/error telemetry in non-test code.
4. Add long-horizon determinism test suite (10^4 steps, restart checkpoints).
5. Add metric join audit to detect cross-clock skew.

## 8) Validation matrix (red -> green expectation)
- Deterministic replay test fails before clock unification; passes after.
- Seed reproducibility test fails where implicit RNG exists; passes after explicit injection.
- Restart equivalence test fails on stale timestamp assumptions; passes after state contract hardening.

## 9) What gets discarded if hypothesis fails
If deterministic replay cannot expose delayed divergence classes, we discard the fractal-compounding model and prioritize non-stationary exogenous factors as primary explanation.

## 10) Artifact governance
- Success criterion: reproducible detection and elimination of at least one delayed divergence class without increased false positives.
- Completion criterion: report, tests, and rollback plan present.
- Owner: platform reliability + quantitative runtime team.

---

## 11) Closure ledger (this audit cycle)

> Tier labels follow `feedback_inference_discipline_v1`: **ANCHORED** = verified in
> code; **EXTRAPOLATED** = inferred from contract.

### A. Class B (Entropy governance) — ANCHORED CLOSED
- Status: `0` bare `random.` / `np.random.` violations in priority paths
  (`risk/`, `core/`, `engine/`, `kuramoto/`, `controllers/`, `policy/`,
  `runtime/`, `kernel/`, `pncc/`, `live/`, `governance/`, `compat/`).
- Production entropy already routes through `np.random.default_rng(seed)` or
  injected `Generator` objects; `core/utils/determinism.py::seed_numpy` is the
  single entry point.
- Action: no patch required.

### B. Class C (Silent exception absorption) — ANCHORED CLOSED
- Status: `0` bare `except: pass` or `except Exception: pass` in non-test code.
- All handlers either log via `logger.error/warning`, re-raise, or document
  intent. Sampling done on priority paths.
- Action: no patch required.

### C. Class A (Time-domain drift) — ACTIVE
- Status: ~79 direct `datetime.now(...)` / `time.time()` / `time.monotonic()`
  sites in priority paths bypass `geosync.core.compat.default_clock`.
- Action: migrate the high-impact fail-closed and lifecycle sites to the
  injected `Clock` API (`utc_now`, `default_clock().epoch_ns()`,
  `default_clock().monotonic_ns()`). The full list is finite; this pass
  closes the top-N most impactful sites and leaves a CI guard against
  regression in those modules.

### D. Class D (Stateful lifecycle edges) — ACTIVE
- Files: `runtime/kill_switch.py`, `runtime/rebus_gate.py`,
  `runtime/adaptive_system_manager.py`, `runtime/thermo_controller.py`,
  `core/neuro/cryptobiosis.py`, `core/engine/core.py`.
- Action: in the same patch as Class A — every wall-clock read in these
  files routes through `Clock`. A determinism replay test (`FrozenClock`)
  exercises the lifecycle edges with a 1e4-step horizon to lock the
  refutation condition from §2.

### E. Acceptance for this branch
- ANCHORED tests for Class A/D migration pass under `FrozenClock`.
- mypy `--strict` for the canonical compat module and the migrated
  call sites stays green.
- `ruff format` + `ruff check` clean on touched files.
- New audit doc + per-module replay tests committed; no push, awaiting
  user-side merge to GitHub.
