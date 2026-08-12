# Determinism Policy

GeoSync is a verification-first system: every gate, artifact and runtime
simulation must be replayable from a declared substrate. Ambient time and
randomness silently break replay, fabricate PASS states, and make evidence
non-reproducible. This policy defines the contract; `check_code_hygiene.py`
enforces a **monotone-down ratchet** on ambient calls in the runtime roots
(`docs/CODE_QUALITY_MANIFEST.json`), so the debt frozen in
`docs/CODE_DEBT_BASELINE.json` can only shrink and never grow.

## Ambient sources under ratchet

The `ambient_nondeterminism` dimension flags direct, un-injected calls to:

- clocks — `datetime.now` / `utcnow` / `today`, `time.time` / `time_ns` /
  `monotonic` / `perf_counter`
- sleeps — `time.sleep`, `asyncio.sleep`
- RNG — `random.*`, `numpy.random.*` (`default_rng`, `seed`, `rand`, …)

A new such call in a runtime root, or a higher count in an already-flagged
file, fails the build. Paying one down requires `--write` to tighten the
ledger, keeping it honest.

## Required substrate

Runtime and research code that needs time or randomness must take it from an
injected context rather than the ambient process:

```python
@dataclass(frozen=True)
class Clock:
    now_ns: Callable[[], int]

@dataclass(frozen=True)
class SeedContext:
    seed: int
    rng: np.random.Generator
    source: Literal["fixed", "artifact", "external", "test"]

@dataclass(frozen=True)
class DeterminismContext:
    run_id: str
    git_sha: str
    clock: Clock
    seed: SeedContext
```

## Evidence-artifact requirements

Every runtime/research artifact must declare:

- clock source
- RNG source and seed
- input data hash
- config hash
- replay command
- nondeterminism class (`deterministic` | `seeded` | `wall-clock` | `external`)

## Allowed ambient use

Ambient time/randomness is acceptable only outside the runtime roots — tests
(with fixed seeds), benchmarks, demos and one-off dev tools — or behind an
explicit, reviewed entry already recorded in the baseline. New ambient debt in
runtime code is not accepted; inject a `DeterminismContext` instead.

See also: `docs/adr/0025-code-hygiene-ratchet.md`,
`scripts/ci/check_code_hygiene.py`.
