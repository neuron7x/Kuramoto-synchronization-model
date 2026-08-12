# GeoSync Architecture Map (Canonical Code Root)

> **Source of truth:** [ADR 0024 — Import-Architecture Canonicalization](adr/0024-import-architecture-canonicalization.md)
> (Accepted 2026-06-09). This map describes that decision and the in-flight
> transitional state. Where this document and any older note disagree, ADR 0024
> wins.

## Canonical package
- **Root:** `geosync/` (repository top level — `import geosync` resolves here).
- **Import prefix:** `import geosync...`
- **Purpose:** Single canonical, wheel-installable source of truth for runtime,
  controllers, SDKs, and services.

## Retired / legacy packages
- **`src/geosync/` (retired fork):** The stale parallel tree ADR 0024 retires
  (last meaningfully diverged 2026-05-06; only 2 filenames in common with the
  canonical top-level tree). It still carries legacy `__CANONICAL__ = True`
  namespace markers and several modules with no top-level twin
  (`src/data`, `src/audit`, `src/system`, `src/risk`, `src/security`); these are
  migrated under the staged plan, not in one sweep. **Do not add new code here
  and do not add new `src.*` imports.**
- **`core/` (deprecated):** Thin shims that forward to `geosync.core.*`. Kept for
  backward compatibility only.

## Migration state (transitional, two layers)
ADR 0024's target and the older `__CANONICAL__` flag regime currently disagree,
by design, during migration:

1. **Import-architecture target (authoritative):** the canonical install root is
   `geosync/`; `src/geosync/` is the fork being retired. Enforced by the
   fail-closed, monotone-down ratchet
   [`scripts/ci/check_import_architecture.py`](../scripts/ci/check_import_architecture.py)
   over [`.github/import_architecture_baseline.json`](../.github/import_architecture_baseline.json):
   no new `src.*` import and no new runtime `sys.path` mutation may enter.
2. **Legacy `__CANONICAL__` markers (transitional):** packages under
   `src/geosync/*` still declare `__CANONICAL__ = True` and the top-level
   `geosync/` shim declares `__CANONICAL__ = False`. These markers predate
   ADR 0024 and are migrated as the code collapse proceeds; until then they are
   tracked, not trusted as the architectural decision.

## Subsystem map
- **Serotonin (TACL/5-HT):** `geosync/core/neuro/serotonin/` (legacy mirror: `core/neuro/serotonin/`)
- **Thermo / TACL:** `runtime/` (API + controller), bridged through canonical runtime entrypoint
- **TACL Behavior Contracts:** `tacl/` (unchanged)
- **NAK controller:** `nak_controller/`
- **Neural Controller / Cortex:** `cortex_service/` and `geosync/neural_controller/`
- **Risk/Execution:** `application/`, `execution/`, `runtime/`
- **Observability:** `observability/`
- **Experimental/Sandbox:** `sandbox/`, `examples/`

## Guidance
- New code MUST import from `geosync...`.
- Never add a new `src.*` import or a runtime `sys.path` mutation — the
  import-architecture gate fails the build.
- Legacy imports under `core...` are deprecated and emit warnings; they resolve
  to the canonical modules where possible.
- See README for the canonical run command and import examples.
