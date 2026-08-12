# PR Audit Packet: Architectural Connectome Gate

## Motivation

This change promotes GeoSync architecture boundaries from informal directory intent to a machine-checkable connectome contract. The goal is to prevent accidental cross-domain leakage between sensing, memory, governance, risk, admission, and reserved execution substrates before that leakage reaches runtime or production.

## Architecture decision

This PR adds a contract-driven architecture gate:

- ADR: `docs/architecture/ADR-0001-connectome-gate.md`
- Contract: `docs/architecture/connectome.yaml`
- Schema: `docs/architecture/connectome.schema.json`
- Validator: `tools/architecture/check_connectome.py`
- CI: `.github/workflows/connectome-gate.yml`
- Protocol: `docs/architecture/CONNECTOME_GATE.md`

The enforced flow is:

```text
perception -> memory / governance / risk -> admission -> reserved execution
```

## Implementation surface

The validator resolves domain ownership from the contract and detects static imports, relative imports, package child imports, literal dynamic imports, aliased importlib usage, and `__import__` calls with string literals.

The schema constrains the structural shape of the contract: required fields, domain states, owner format, path lists, import roots, allowed imports, and forbidden imports.

## Negative controls

The regression suite covers:

- direct forbidden import;
- allowed cross-domain import;
- unlisted cross-domain import;
- relative import boundary crossing;
- package child import boundary crossing;
- literal dynamic import;
- aliased literal dynamic import;
- machine-readable JSON violation output;
- canonical contract shape and registered-domain resolution.

## Evidence commands

```bash
python tools/architecture/check_connectome.py
python tools/architecture/check_connectome.py --format json
python -m pytest tests/tools/architecture/test_check_connectome.py tests/tools/architecture/test_connectome_contract_shape.py -q
```

## Review checklist

- Confirm every governed path has one domain owner.
- Confirm every new cross-domain edge is explicit in `allowed_imports`.
- Confirm every hard boundary is explicit in `forbidden_imports`.
- Confirm active domains do not depend on reserved execution substrate.
- Confirm every newly claimed bypass class has a negative test.
- Confirm the PR claim boundary does not exceed static import topology.

## Claim boundary

This PR proves static Python import-boundary compliance against the declared connectome contract. It does not claim runtime behavior, market validity, causal safety, biological fidelity, or full dynamic-loader coverage. Those require separate gates and separate evidence.
