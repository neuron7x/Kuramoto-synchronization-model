# ADR 0024 — Import-Architecture Canonicalization (single `geosync` package)

**Status.** Accepted, 2026-06-09.
**Related.**
- [`scripts/ci/release_gate.py`](../../scripts/ci/release_gate.py) (Section B probes report the totals)
- [`scripts/ci/check_import_architecture.py`](../../scripts/ci/check_import_architecture.py) (the ratchet this ADR governs)
- [`.github/import_architecture_baseline.json`](../../.github/import_architecture_baseline.json) (the debt ledger)

---

## Context — machine-verified topology (2026-06-09, commit on `main`)

The release gate reports Section B (package/import architecture) as **RED**.
Root-cause investigation establishes *why*, with reproducible evidence:

1. **Three divergent roots merged into one namespace.** `import geosync`
   resolves to top-level `geosync/__init__.py`, but `geosync.core.digital_governance`
   resolves to **`src/geosync/core/digital_governance.py`**. The `geosync`
   package is a runtime *namespace merge* of top-level `geosync/` (84 files),
   `src/geosync/` (112 files — only **2** filenames in common with the
   top-level, i.e. a genuine fork), and top-level legacy mirrors (`core/`,
   `audit/`-style). The merge only assembles because **82 first-party files
   mutate `sys.path`** at import time.

2. **The fork is stale.** Top-level `geosync/` was last touched 2026-06-09;
   `src/geosync/` last 2026-05-06. `import geosync` (144 first-party imports)
   vs `import src.geosync` (5). **Canonical decision: top-level `geosync/`
   wins; `src/geosync/` is the abandoned fork to be retired.**

3. **24 first-party files import `src.*`** (`src.data` ×17, `src.audit` ×23
   occurrences, `src.risk`, `src.security`, `src.system`, `src.geosync`).
   Several `src.*` modules (`src/data` 34 files, `src/system`, `src/audit`)
   have **no top-level twin** — they are real modules stranded under `src/`.

4. **Circular-import fragility.** `geosync.core.neuro.serotonin.serotonin_controller`
   raises `ImportError: cannot import name 'SEROTONIN_ALERTS' from partially
   initialized module 'core.neuro...'` outside `conftest.py`'s import ordering.
   `tests/.../test_import_canonicality.py` enforces `core.X is geosync.X`
   single-source identity — a deliberate, in-flight canonicalization with its
   own invariants.

5. **Consequence at release time.** A clean-room wheel ships **16 top-level
   packages** (14 outside `geosync*`: `core`, `domain`, `execution`, `tools`,
   `markets`, `src`, …) — generic-name squatting of global `site-packages` —
   and **2 of 8 CLI entrypoints fail** from a clean install (`geosync-sync`,
   `geosync-db` reference an unpackaged `scripts.*`).

## Decision

**Target state:** one canonical `geosync` package, no first-party `src.*`
imports, no runtime `sys.path` mutation, wheel-installable without namespace
squatting and with all entrypoints runnable from a clean install.

Because the namespace is fragile (path-hack-dependent, circular-import-laden,
test-governed), the migration is **staged and gated by the full test suite**,
not done in one sweep. To make that safe and monotone:

- **Ratchet now (this ADR).** `check_import_architecture.py` freezes the exact
  debt set (`24` `src.*` importers + `82` path-hacks) in
  `import_architecture_baseline.json`. The set may only **shrink**: any new
  violator fails CI; paying down debt must tighten the ledger (`--write`). No
  fresh architectural debt can enter while the migration proceeds.
- **Stage order (each gated by the suite):**
  1. Move `src/{data,audit,risk,security,system}` (no top-level twin) under
     `geosync.<pkg>`; rewrite importers; delete the `sys.path` hack that
     exposed them.
  2. Retire `src/geosync/` fork: reroute its 5 importers (esp.
     `geosync/risk/__init__.py → src.geosync.risk.automated_testing`) to
     canonical modules, then delete the fork.
  3. Collapse `core/`-style legacy mirrors into `geosync.core` re-export shims
     with the canonicality test still green; remove their path hacks.
  4. Restrict `[tool.setuptools.packages.find]` to `geosync*`; repoint or
     re-home the broken `scripts.*` entrypoints; verify clean-room wheel +
     entrypoint smoke (release gate `B.wheel`, `E.clean_clone`).

## Verification

Each stage flips its release-gate probe and lowers the ratchet count —
verifiable, not asserted. The migration is **done** when
`check_import_architecture.py` reports both lists empty and `release_gate.py`
Section B is all GREEN.

## Consequences

- Short term: the ratchet adds one fast CI gate; it does not change runtime.
- The fork retirement (`src/geosync/`) is the highest-value single stage but
  must not precede stage 1, or stranded `src.*` modules break.
- No claim is promoted by this ADR; it records structure and a plan, both
  grounded in reproducible probes.
