# Correctness-Debt Wave 2 — CodeQL board, PR #2

Date: 2026-06-10 · Branch: `fix/correctness-debt-wave2`

Second pass over the CodeQL `security-and-quality` board, after the
security-board triage (PR #895). This wave targets the **high-confidence real
defects** in source — not lint noise — each verified before fixing.

## Fixed (real defects)

| Defect | File | CodeQL | Fix |
|--------|------|--------|-----|
| Strategy emitted the wrong `SignalEvent` (mock-only kwargs) → `TypeError` whenever the backtest package was importable | `geosync_hpc/hpc_real_data_backtest.py` | py/call/wrong-named-class-argument #346/#347 | Dedicated `StrategySignal` dataclass, decoupled from `backtest.events.SignalEvent`. 3 regression tests. |
| Leaked file descriptors from `yaml.safe_load(open(...))` | `scripts/validate.py` (×3), `scripts/run_backtest.py` | py/file-not-closed #265/#270/#271/#272 | `with open(...)` / `_load_yaml` helper. |
| `except BaseException` swallowed `KeyboardInterrupt`/`SystemExit` into a result/error map | `core/agent/evaluator.py`, `core/agent/orchestrator.py` (gather) | py/catch-base-exception #222/#225 | Re-raise interrupts, catch `Exception` for the rest. Non-interrupt behaviour unchanged. |

## Verified false positives (left as-is)

- **`for x in <Enum>:`** (`infra/datacenter/manager.py:388`, `examples/...:343`) —
  `DataCenterRegion`/`ModulePhase` are `enum.Enum` subclasses, which are
  iterable. `py/non-iterable-in-for-loop` #477/#478 — FP.
- **`OperationalTag`** (`src/data/versioning.py:184`) — `@dataclass(frozen=True)`
  with a custom `__hash__` over the same fields its dataclass `__eq__` compares;
  consistent. `py/equals-hash-mismatch` #351 — FP.
- **`except BaseException` that forwards** (`core/agent/orchestrator.py:276`
  `future.set_exception`, `core/agent/sandbox.py:182` subprocess pipe,
  `cli/geosync_cli.py:580` worker→main) — the CPython `concurrent.futures`
  `_WorkItem.run` idiom: forwarding (not swallowing) every exception across a
  thread/process boundary is intentional. Dismissed as by-design.
- **Guarded `uninitialized-local`** (`signal_filter.py:728` path-correlated
  `if`, `profiler/cli.py:127` argparse `choices`) — unreachable unbound path.

## Verification

`ruff` · `black --check` · `mypy --strict` clean on every changed module;
new regression tests + full `core/agent` suite green.
