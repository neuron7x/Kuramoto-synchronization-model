# ADR-0001: Architectural Connectome Gate

## Status

Accepted for PR-level enforcement.

## Context

GeoSync contains multiple logical substrates with different operational value functions: sensing, memory, governance, risk, admission, and execution. Without a machine-checkable boundary, Python imports can silently create reverse dependencies that collapse the intended information-flow topology. Once that happens, architecture becomes folklore with nicer indentation.

The repository needs a small, deterministic, reviewable gate that prevents accidental domain leakage without requiring runtime execution.

## Decision

Introduce a connectome contract at `docs/architecture/connectome.yaml` and enforce it with an AST-based validator at `tools/architecture/check_connectome.py`.

The contract declares:

- governed domains;
- source paths owned by each domain;
- import roots belonging to each domain;
- explicit cross-domain `allowed_imports`;
- hard-veto `forbidden_imports`;
- active versus reserved domain state.

The GitHub Actions workflow `.github/workflows/connectome-gate.yml` runs the validator and the connectome regression tests on pull requests, merge queue events, and pushes to `main`.

## Consequences

Positive consequences:

- cross-domain import leakage becomes a CI-visible violation;
- domain ownership is reviewable as a contract, not inferred from directory names;
- negative controls document bypass classes;
- schema and shape tests constrain the contract itself;
- the architecture now has a reproducible evidence surface.

Trade-offs:

- non-literal dynamic imports remain outside this static gate;
- the gate does not prove runtime behavior;
- broad import roots must be reviewed carefully;
- changing a domain edge now requires explicit contract modification.

## Invariants

The decision preserves these invariants:

1. A governed file has exactly one owning domain.
2. Cross-domain imports are denied unless explicitly allowed.
3. Forbidden imports override broad allowances.
4. Active domains do not depend on reserved execution substrate.
5. Tests must include negative controls for every claimed bypass class.

## Evidence

Minimum evidence for this ADR:

```bash
python tools/architecture/check_connectome.py
python tools/architecture/check_connectome.py --format json
python -m pytest tests/tools/architecture/test_check_connectome.py tests/tools/architecture/test_connectome_contract_shape.py -q
```

## Claim boundary

This ADR governs static Python import topology only. It does not claim algorithmic correctness, execution safety, biological fidelity, market validity, or full dynamic-loader coverage. Those claims require separate gates. Yes, the universe still insists on separate evidence for separate claims.
