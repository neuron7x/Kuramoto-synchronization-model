# ADR-0017 · Dual-Tree Consolidation: `core/` → `src/geosync/`

* **Status**: Superseded by [ADR 0024](0024-import-architecture-canonicalization.md)
* **Date**: 2026-04-18
* **Deciders**: neuron7xLab
* **Supersedes**: —
* **Superseded by**: ADR 0024 (2026-06-09)

> **Superseded.** This ADR made `src/geosync/` the canonical src-layout target.
> ADR 0024 reversed that decision: the canonical install root is now top-level
> `geosync/`, and `src/geosync/` is the **retired fork** being migrated out. The
> historical reasoning below is kept for the record only.

## Context

The repository carries two parallel Python package trees:

| Tree | Role | Size | Status |
|------|------|------|--------|
| `core/` | Legacy namespace, predates the canonical src-layout | ~6.3 MB, ~1 500 files | Frozen for new code, kept for backward compatibility |
| `src/geosync/` | Canonical src-layout for the ``geosync`` distribution (this ADR's now-superseded decision) | ~2.1 MB, growing | **Retired fork** per ADR 0024 — do not add new code |

`core/` exists because the project predates PEP 660 / modern src-layout
tooling, and it continued to accumulate modules during the period when
refactoring it was more expensive than adding to it. `src/geosync/` is
the target tree for the `geosync` installable distribution published
via `pyproject.toml`.

A subset of modules already has a thin shim pattern
(`core/compat.py` → `geosync.core.compat`, PR #310). The rest do not
yet — imports like `from core.events.sourcing import ...` resolve
against the legacy tree directly, which means that in principle the
same logic could diverge between `core/events/sourcing.py` and
`src/geosync/core/events/sourcing.py` if both ever existed.

## Decision

Migrate every module in `core/` to `src/geosync/core/` over a bounded
set of releases, in three canonical stages:

1. **Shim pass.** Every `core/<sub>/**.py` gets a canonical home at
   `src/geosync/core/<sub>/**.py` and `core/<sub>/**.py` becomes a
   thin re-export shim (like `core/compat.py`). Zero behavioural
   change; every existing import keeps working.
2. **Import rewrite.** All first-party code and tests migrate their
   `from core.X import ...` → `from geosync.core.X import ...`. The
   shims continue to serve third-party or lagging callers.
3. **Shim removal.** Once the import-rewrite window has elapsed
   (≥ one release cycle) and no first-party code imports from `core.X`,
   the `core/` tree is removed.

Before and during the migration, **`core/` is frozen**: no new module
may be added there, no behavioural change may land there except as
part of an explicit shim step. Stage 1 closes this freeze.

## Acceptance criteria (per stage)

### Stage 1 · Shim pass

* Every `core/<sub>/**.py` file is either
  (a) already a shim (imports from `geosync.core.<sub>.*`), or
  (b) has an accompanying `src/geosync/core/<sub>/**.py` with identical
      behaviour and a shim replacing the original.
* `import-linter` gains a rule disallowing new content in `core/` that
  is not a shim.
* `mypy --strict core/ src/geosync/` passes.
* Regression tests under `tests/` continue to pass under both the
  legacy and canonical import paths.

### Stage 2 · Import rewrite

* `grep -rn "from core\." --include="*.py" src/ tests/ cortex_service/ application/ execution/ observability/` returns 0 rows.
* `ruff` / `black` / `mypy` remain green across the whole tree.
* The physics-kernel gate still passes.

### Stage 3 · Shim removal

* All shim files in `core/` have been deleted.
* The `core/` top-level package is removed.
* `pyproject.toml` no longer declares `core` as a package.
* `import-linter` rule flips: `core.*` imports are forbidden from
  everywhere.

## Out of scope

* Moving non-Python artefacts (`.claude/physics/`, `docs/`, `tools/`,
  `tests/`). These already live outside the dual-tree problem.
* Renaming the distribution. The package stays `geosync`.

## Risk & rollback

| Risk | Mitigation | Rollback |
|------|------------|----------|
| Hidden import-order dependency between `core.X` and `geosync.core.X` during Stage 1 | Every shim is generated, not hand-written, and the test suite runs under both legacy and canonical paths before merge | Delete the shim, restore the original module, reopen the freeze |
| External callers pinned to `core.X` | Shims preserve the surface for the full grace window; the removal PR carries a migration table in its description | Revert the shim-removal commit; `core.X` is back |
| Accidental behavioural drift inside a shim | Shims are single-line re-exports by construction; a review rule blocks anything more | Fix the shim or revert |

## Tracking

The migration has its own checklist under
[`reports/CORE_MIGRATION_PROGRESS.md`](0024-import-architecture-canonicalization.md)
(created once Stage 1 begins). Each stage closes with a merged PR and
a paragraph recorded there.
