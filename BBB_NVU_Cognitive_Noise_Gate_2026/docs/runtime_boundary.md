# Runtime Boundary

The runtime boundary is the integration-facing API for deterministic inference. It separates library/service invocation from CLI file-system adapters.

## API surface

- `DeterministicInferenceEngine.from_rules(rules, engine_hash=None)` builds an engine from already-loaded rules without rule-file I/O.
- `RuntimeBoundary(rules, engine_hash=None)` wraps the engine for integration callers.
- `RuntimeBoundary.evaluate_run(..., created_at=..., profile=...)` requires an explicit timestamp and supports `full`, `risk`, and `actions` output profiles.
- `RuntimeBoundary.evaluate_batch(...)` validates each request with `RuntimeRequest` and preserves deterministic batch ordering.

## Contract

The boundary does not change risk logic. It only fixes the API surface:

```text
loaded rules + input document + explicit created_at + engine_hash -> deterministic output profile
```

CLI execution remains available for examples, but integration code should use `RuntimeBoundary` or `DeterministicInferenceEngine.from_rules`.
