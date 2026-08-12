<!-- SPDX-License-Identifier: MIT -->
# Integration debt — evidence and staged migration (2026-07-23)

## Why this document exists

The ten-axis composition gate names the two weakest *integration* axes with numbers, so the
next change cycle is driven by those numbers rather than by intuition:

| axis | probe | score | what it measures |
|---|---|---|---|
| simplicity | `namespace_singularity` | **0.2353** | 13 of 17 wheel packages are outside the `geosync` namespace |
| adaptability | `import_architecture` | **0.8870** | 19 `src.*` production imports + 53 `sys.path` hacks |

Coherence-of-parts is already high (0.72; RTM traceability 1.0, 83/87 gates green). The gap is
**integration into one artifact**: the repository still ships ~7 top-level runtime packages plus a
193-file `src/` shadow tree.

## Measured shape of the `src/` shadow tree

An AST dependency graph over every tracked `.py` file (importers classified by location):

- **193** modules under `src/`.
- **142 are dead** — imported by nothing tracked (not production, not tests, not each other).
- **4 live leaves** carry the entire production coupling, all consumed by `application/`:
  - `src.admin.remote_control` — `AdminIdentity` + kill-switch admin API + rate limiter (5 importers)
  - `src.audit.audit_logger` — `AuditLogger` (8 importers)
  - `src.risk.risk_manager` — risk facade (2 static importers **+ 1 dynamic** `importlib.import_module("src.risk.risk_manager")` in `application/api/risk_factory.py:53`)
  - `src.security.access_control`
- The cluster is tangled: `remote_control` itself imports `src.audit.audit_logger`.
- `tests/packaging/test_namespace.py:59` asserts `importlib.import_module("src")` — `src` is a
  *declared, tested* package, so it cannot simply be renamed out from under that contract.

**Consequence for sequencing:** mass-deleting the 142 dead modules does **not** move either headline
probe (the debt is driven by the live coupling, not the dead files) and touches nothing on the auth
path — it is a safe later hygiene step, not the lever. The lever is relocating the 4 live leaves out
of `src/` so `application/` stops importing `src.*` and `src` can leave the wheel surface.

## Staged plan (each stage independently verifiable, ratchet-enforced)

0. **This cycle — bounded proof of method.** Retired 2 vestigial `sys.path` hacks in
   `core/neuro/tests/` (both use `spec_from_file_location`, so the hack was dead); the
   import-architecture ratchet is tightened 55 → 53 path-hacks, `adaptability` 0.8838 → 0.8870.
   The load-bearing script hacks (`hyperdirect_veto_falsifier`, `coherence_bridge/test_runner`,
   the two `coherence_bridge` external-`GEOSYNC_PATH` inserts) are **kept** — they support
   `python <file>.py` execution and are a separate console-scripts cycle, not free deletions.
1. **Relocate `src.audit.audit_logger`** to a canonical root (e.g. `application/audit/`), leave a
   thin re-export shim at the old path, re-point the 8 `application/` importers. Verify: full-tree
   import, `application/` + secrets + RBAC tests, gates, `test_namespace`. Ratchet `src_imports` down.
2. **Relocate `src.admin.remote_control`** (AdminIdentity/kill-switch) once its `audit_logger`
   dependency is canonical. This touches the RBAC surface hardened in the mutation batches, so it
   ships with its own destruction stage.
3. **Relocate `src.risk.risk_manager`** and convert the dynamic `importlib.import_module` in
   `risk_factory.py` to a direct canonical import.
4. **Relocate `src.security.access_control`**, then delete the 142 dead modules (now provably
   orphaned) and drop `src` from `tool.setuptools.packages.find` — `namespace_singularity` moves.

Each stage is a graph relocation, never a blanket rewrite: move body → shim old path → re-point
named importers → verify → tighten the ratchet. No stage is merged without the import gate green.
