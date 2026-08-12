# Adversarial Orchestration Methodology

GeoSync development uses an **adversarial multi-role workflow**. Every change
passes through four roles before it can land. No role has autonomous authority:
the human contributor is the central decision node and the only signer.

## Roles

| Role | Responsibility | Concrete artifact |
| --- | --- | --- |
| **Creator** | Proposes the change — code, test, doc | The diff |
| **Critic** | Challenges the change against physical and architectural constraints | Inline review comments + the embedded physics kernel (see below) |
| **Auditor** | Verifies that the change does not break invariants or contracts | CI gate output, `validate_tests.py` report |
| **Verifier** | Confirms the artifact is reproducible bit-for-bit | `MANIFEST.sha256` diff + signed tag |

The Critic role is partially **embedded in the repository**, not in the
contributor's head: [`CLAUDE.md`](../../CLAUDE.md) and the documents under
[`.claude/physics/`](../../.claude/physics/) state the rules a Critic must apply,
so any reviewer (human or automated) reaches the same verdict.

## The five validation gates

Every PR must pass these gates **in this order**. Failure at any gate halts the
pipeline; the failure does not get masked or skipped.

1. **AST validator** — `python .claude/physics/validate_tests.py`
   - Parses every test, checks that assertions reference an `INV-*` ID, and
     that numeric tolerances derive from a documented formula rather than a
     magic literal.
2. **`mypy --strict`** — type-level soundness on the entire `src/` tree.
3. **`ruff format --check` + `ruff check`** — style and lint determinism.
4. **`pytest`** — runtime correctness, including the property-based
     (Hypothesis) suites.
5. **`MANIFEST.sha256`** — reproducibility seal: regeneration must produce
     byte-identical artifacts.

The exact commands for each gate live in [`VALIDATION.md`](./VALIDATION.md).

## Invariant references in tests

Each test is required to declare which invariant it witnesses. The minimum form is:

```python
def test_kuramoto_order_parameter_bounded() -> None:
    """Witness for INV-K1: 0 ≤ R(t) ≤ 1 for all t."""
    ...
```

The AST validator (gate 1) rejects tests whose docstring or marker does not
contain an `INV-*` token from [`INVARIANTS_INDEX.md`](./INVARIANTS_INDEX.md).
This makes coverage of the physics layer **structurally measurable**, not a
matter of opinion.

## Escalation

A failing gate is never "patched around" by relaxing the invariant. If a test
genuinely cannot pass:

1. Document the falsification attempt (input, observed output, expected bound).
2. Open an issue tagged `physics-falsification`.
3. Either the implementation is wrong (fix the code) or the invariant was
   wrong (amend `INVARIANTS.yaml` with a dated changelog entry and a citation).

Both branches produce a permanent audit trail; neither lets the failing test
silently pass.

## Why adversarial, not consensus

A consensus workflow optimizes for agreement; an adversarial workflow optimizes
for finding the case that breaks the claim. Physical systems do not care about
agreement, so neither does this codebase.
