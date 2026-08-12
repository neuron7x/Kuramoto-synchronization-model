# PromptOps Validator PR1

## Purpose

This PR turns prompt artifacts into deterministic CI contracts. The target is not
better wording. The target is a merge gate where prompt intent is parsed,
validated, tested, and shadow-checked before the branch is allowed to move.

## Implemented control plane

- `schemas/promptops/system_prompt_contract.schema.json` defines the public
  system-prompt artifact shape.
- `tools/promptops_validate.py` validates YAML and JSON artifacts fail-closed.
- `tools/promptops_shadow_runner.py` executes deterministic local shadow cases
  without provider calls.
- `examples/promptops/system_prompt_contract.example.yaml` provides a canonical
  contract.
- `tests/promptops/` locks validator and shadow-runner behavior.
- `.github/workflows/promptops-validator.yml` adds the PR gate.

## Deterministic gates

The validator enforces:

- required root keys: `artifact_type`, `id`, `version`, `messages`,
  `unit_tests`, `shadow_tests`
- strict artifact ID and semver format
- at least one authoritative `system` or `developer` message
- declared `<ref:...>` closure
- HTTP(S) reference validation
- sensitive-token pattern detection
- unsafe override phrase detection
- duplicate test IDs inside collections
- duplicate artifact IDs across scanned files
- JSON report emission with source SHA-256 fingerprints

## Shadow runner boundary

The local shadow runner is intentionally provider-free. It evaluates declared
`shadow_tests` through deterministic issue-code simulation and quality gates.
This gives CI a stable regression surface before any real model judge is wired
behind cost controls and provider-specific nondeterminism.

Supported PR1 expectations:

- `must_fail: true|false`
- `expected_issue: <issue-code>`
- `forbidden_issue: <issue-code>`

Supported PR1 quality gate semantics:

- `no credential leakage`
- `deterministic issue code emitted`
- `latency budget recorded`

Unknown gate labels are preserved and treated as non-blocking in PR1 so the
contract vocabulary can evolve without breaking every experimental prompt. PR2
can convert stabilized labels into strict handlers.

## Acceptance command

```bash
python -m pip install pytest pyyaml
python -m json.tool schemas/promptops/system_prompt_contract.schema.json >/tmp/promptops_schema.json
python tools/promptops_validate.py examples/promptops --report artifacts/promptops/validation_report.json
python tools/promptops_shadow_runner.py examples/promptops --report artifacts/promptops/shadow_report.json
python -m pytest tests/promptops -q
```

Expected local result for this PR:

```text
8 passed
```

## Next integration

PR2 should add provider-backed optional shadow inference:

1. default CI remains local-mock and deterministic
2. provider CI is opt-in via explicit runtime configuration
3. model outputs are compared through bounded metrics
4. failures produce issue codes, not prose confetti
5. token spend, latency, and provider version are captured in the report
