# Validation Commands

Reference card for the five gates declared in [`METHODOLOGY.md`](./METHODOLOGY.md).
Run them in this order. Each gate must exit `0` before moving to the next.

The same gates run in CI (`.github/workflows/pr-gate.yml` and friends); these
local commands are the canonical regeneration recipes.

## 1. AST validator — invariant references in tests

```bash
python .claude/physics/validate_tests.py
```

Walks every `tests/**/test_*.py`, parses it, and rejects:

- assertions whose tolerance is a magic literal (no formula reference);
- tests whose docstring or marker omits the `INV-*` token they witness;
- tests that mutate global physics constants without a `# physics-override`
  marker plus a justification comment.

The validator also emits a per-category coverage table so a contributor can
see which `INV-*` IDs still lack a witness.

## 2. `mypy --strict`

```bash
mypy --strict src/
```

Required for every `.py` file under `src/`. The PostToolUse hook in
`.claude/settings.json` runs this on every edit, so violations should
never reach commit time. CI runs it again as a backstop.

## 3. `ruff format --check` + `ruff check`

```bash
ruff format --check .
ruff check .
```

Together these enforce the lockstep style policy. `ruff format --write` is the
canonical formatter — do not run `black` or `isort` separately.

## 4. `pytest`

Run the gate that matches the change:

```bash
# Fast gate — runs on every PR
make test-fast

# Heavy gate — runs when src/, tests/, core/, formal/, scripts/, or Makefile change
make test-heavy

# Full gate — for release tags
make test-ci-full
```

Hypothesis property suites are inside the heavy gate. Locally you can also
run them directly:

```bash
pytest tests/ -m "slow or heavy_math or nightly" --maxfail=3 -q
```

## 5. `MANIFEST.sha256`

```bash
make release
sha256sum -c MANIFEST.sha256
```

Reproducible build seal. A clean checkout plus a fresh `make release` must
produce a `MANIFEST.sha256` whose contents match the committed copy line for
line. If they diverge, find the source of nondeterminism (timestamps,
unsorted iteration, random seed) and fix it before merging.

## Convenience aggregates

```bash
make audit         # runs gates 1–3 plus dep audits
make test-ci-full  # runs all unit + property + integration suites
make formal-verify # invokes formal/proof_invariant.py for invariants with proof obligations
```

## When CI fails but the local run passes

The most common cause is shallow-fetch divergence on dependabot branches:
the `python-heavy-tests` job uses `git fetch --depth=1 origin main` and then
`git diff main...HEAD` to decide whether to skip. If the PR branch was
created before recent merges to `main`, the diff has no merge base and the
job exits with `fatal: ... no merge base`.

Fix: rebase the PR branch onto current `origin/main` and force-push with
`--force-with-lease`. Do not bypass the gate.
