# Fast-lane backlog ledger

## Context

`python-fast-shard` (the fast/default pytest lane, ~17.6k tests) had been
passing **vacuously** on `main` and every PR: `pytest.ini` already carries `-q`,
and the shard added a second `-q` to `--collect-only`, flipping node-id output
to a per-file summary so the `grep '::'` matched nothing and every shard logged
`0/0 selected tests — shard passes`. The lane ran **zero tests** for its entire
history.

PR #1153 restored the oracle (real node-id collection + a fail-closed guard:
zero total collection after the test-surface filter is now FATAL). Restoring it
surfaced the latent backlog the vacuum had hidden.

## Measured backlog shape (PR #1153, `--maxfail=20`)

- total collected: **~17,617** fast node ids
- selected per shard: 4494 / 4373 / 4302 / 4448
- failure clusters: **9**
- enumeration method: full kept set run locally in one pass per layer
  (`--ignore` the quarantined files), `--maxfail` **not** hit — so the
  quarantined set below is the *complete* known backlog at each layer, not a
  prefix. Re-enumerated on main @ 04798776 after #1182: exactly 1 remaining
  failure (the D-002G lock, layer 3).

| cluster | files | issue | lane | status |
|---|---|---|---|---|
| `cli_import_shadowing` | 4 | [#1158](https://github.com/neuron7xLab/GeoSync/issues/1158) | ci-import-architecture | **drained** |
| `acceptor_corpus_legacy_mapping` | 1 | [#1170](https://github.com/neuron7xLab/GeoSync/issues/1170) | governance-schema | **drained** |
| `analytics_import_shadowing` | 1 | [#1171](https://github.com/neuron7xLab/GeoSync/issues/1171) | ci-import-architecture | **drained** |
| `adversarial_invariant_count` | 1 | [#1172](https://github.com/neuron7xLab/GeoSync/issues/1172) | governance-registry | **drained** |
| `numerical_policy_unregistered_clamps` | 1 | [#1173](https://github.com/neuron7xLab/GeoSync/issues/1173) | physics-numerical-policy | **drained** |
| `tools_import_shadowing` | 1 (20 tests) | [#1178](https://github.com/neuron7xLab/GeoSync/issues/1178) | ci-import-architecture | **drained** |
| `namespace_canonical_policy` | 2 | [#1179](https://github.com/neuron7xLab/GeoSync/issues/1179) | ci-import-architecture | **drained** |
| `contradiction_ledger_stale` | 1 | [#1180](https://github.com/neuron7xLab/GeoSync/issues/1180) | governance-ledger | **drained** |
| `d002g_lock_anchor_stale` | 1 | [#1183](https://github.com/neuron7xLab/GeoSync/issues/1183) | governance-lock | **drained** |

**Cluster-count correction (was "1").** The original measurement reported a
single cluster because the four `cli_import_shadowing` import errors aborted
collection before the rest of the fast surface was reached. Once those files
were quarantined, the oracle ran further and surfaced four more deterministic
clusters that the import failures (and, before them, the vacuum) had hidden.
They were latent, not absent — exactly the backlog the restored oracle exists
to expose. None is a flaky/env failure; each is tracked and drained per cluster.

### cli_import_shadowing — RESOLVED (#1158)

`cli/` (repo root, held `amm_cli.py` / `geosync_cli.py`) was not declared in
`[tool.setuptools.packages.find]`, while `scripts`/`scripts.*` was. Because no
top-level `cli` package was emitted into the editable-install finder, the
explicit-node-id run step resolved top-level `cli` against `scripts/cli.py`
(`scripts.cli`), and four test modules failed to import. `--collect-only`
resolved `cli` correctly; the node-id run step did not — an invocation-dependent
`sys.path`/rootdir difference. Adding `cli/__init__.py` alone did not fix CI
because the package was still not packaged.

**Why not "declare `cli` in `packages.find`":** that would add `cli` as a NEW
non-`geosync` top-level package in the distributable wheel, which both the
package-boundary ratchet (`.github/package_boundary_baseline.json`,
`tests/ci/test_package_boundary.py`) and the wheel-contract ratchet
(`.github/bwheel_baseline.json`) forbid — the non-`geosync` leak set may only
shrink (ADR-0024). Patching the baselines to grow that set would weaken the gate.

**Fix (#1158):** re-home the package into the canonical wheel namespace —
`cli/` → `geosync/cli/`. As `geosync.cli` it is packaged by the existing
`geosync`/`geosync.*` `packages.find` entry with **zero** package-boundary debt,
and the public import path `geosync.cli` cannot be shadowed by `scripts.cli`
(different dotted root). Importers updated to
`from geosync.cli[.geosync_cli] import ...` (4 quarantined tests, the e2e
pipeline test, and the CLI-docs generator).

Formerly quarantined files (now un-quarantined, collecting + green):
- `tests/unit/cli/test_amm_cli.py`
- `tests/unit/cli/test_cli_golden.py`
- `tests/unit/cli/test_fete_backtest_cli.py`
- `tests/unit/test_geosync_cli.py`

**Expiry met:** the CLI package is importable under a clean editable install as
`geosync.cli` (`from geosync.cli import amm_cli` → `geosync/cli/amm_cli.py`); the
four entries were removed from `tests/ci/fast_quarantine.txt` and the tests
re-enabled. The post-subtraction collection stays non-empty and every remaining
quarantine entry carries an issue ref.

### acceptor_corpus_legacy_mapping

`tests/governance/test_typed_models.py` loads every commit acceptor. Several
`.claude/commit_acceptors/*.yaml` still declare `required_python_symbols` in the
legacy mapping form `[{file, symbol}]` instead of the canonical
`"<module>::<symbol>"` string — the same schema drift fixed in the root
`commit_acceptors/` by #1160, with stragglers left under `.claude/`. Confirmed
offenders: `forman-ricci-margin-onset-honesty.yaml`,
`governance-verification-protocol-binding.yaml`,
`import-arch-geosync-risk-consolidation.yaml` (+`calibration-contract.yaml` in
CI). **Expiry:** all `.claude/commit_acceptors` use the `module::symbol` string
form; drained in #1170.

### analytics_import_shadowing

`tests/unit/analytics/test_descriptor_capsule.py::test_cli_smoke` runs the
descriptor-capsule CLI in a subprocess, which fails with
`ModuleNotFoundError: No module named 'analytics'`. Same import-architecture
class as `cli_import_shadowing`: the `analytics` package is not declared in
`[tool.setuptools.packages.find]`, so it is absent under the CI editable install
in a fresh subprocess. **Expiry:** `analytics` imports in a fresh subprocess
under the CI editable install; drained in #1171.

### adversarial_invariant_count

`tests/adversarial_invariants/test_invariant_fail_closed.py:34` asserts
`len(invariant_ids) == 97`, but `.claude/physics/INVARIANTS.yaml` registers
**106** (canonical per CLAUDE.md). The hardcoded count is stale. The drain must
not merely bump the number: it must confirm all 106 registered invariants carry
a negative vector that fails closed under 50ms (the test's real purpose).
**Expiry:** the count assertion matches the canonical registry size; drained in
#1172.

### numerical_policy_unregistered_clamps

`tests/tools/test_numerical_policy.py::test_physics_tree_has_zero_unregistered_clamps`
reports four clamps in the scoped physics tree not declared in the
numerical-policy registry: `core/kuramoto/engine.py:295` (`saturate_clip`) and
`core/physics/forman_ricci.py:175/269/375`. Some originate from #1150/#1152
Forman-Ricci work that merged under the vacuous oracle. **Expiry:** the physics
tree has zero unregistered clamps (each registered with a declared bound, or
refactored if unjustified); drained in #1173.

### tools_import_shadowing

All 14 tests in `tests/ci/test_pr_preflight_engine.py` fail at **collection**
with `ModuleNotFoundError: No module named 'tools'` (`from tools.ci import
pr_preflight`). Same import-architecture class as `cli_import_shadowing` /
`analytics_import_shadowing`: the `tools` package is not declared in
`[tool.setuptools.packages.find]`, so it is absent under the CI editable
install. **Expiry:** `tools.ci.pr_preflight` imports under the CI editable
install; drained in #1178.

### namespace_canonical_policy

`tests/test_architecture_guards.py::test_namespace_integrity_has_no_violations`
reports 23 violations (e.g. `src/geosync/risk/__init__.py` missing
`__CANONICAL__ = True`) and
`tests/unit/scripts/test_namespace_shims_importable.py::test_namespace_policy_gate_passes`
fails because `scripts/check_namespace_policy.py` `main()` returns 1 (legacy
`src.*` imports outside the curated allowlist). Canonical namespace is
`geosync.*`. Likely subsumed by the in-flight import-architecture consolidation
(#1159) — cross-reference before draining. **Expiry:** namespace policy gate
returns 0 and architecture-guards reports zero violations; drained in #1179.

### contradiction_ledger_stale

`tests/audit/test_contradiction_ledger.py::test_every_falsifier_confirms_its_claim_against_live_source`
had failed: entry **C-NEURO-003**'s old falsifier
`[ "$(grep -c dopamine_serotonin_correlation_min core/validation/neuro_integrity.py)" -le 2 ]`
returned 1 (expected 0) — the field had been wired into a `validate_*` path
(>2 mentions), so the ledger's "still dead" position was no longer true and the
crown invariant correctly demanded the entry flip to RESOLVED. This was the
contradiction ledger working as designed, not a test bug. **DRAINED:**
C-NEURO-003 is now `RESOLVED` with a `resolution_ref` (the enforcement at
`core/validation/neuro_integrity.py:412,433` + the correlation-witness acceptor),
and its falsifier was rewritten to the anti-regression form
`[ "$(grep -c ... )" -ge 3 ]` (expect_exit 0) which matches live source. The
quarantine line is removed and the full ledger suite (17 tests) is green
unquarantined.

### d002g_lock_anchor_stale

`tests/systemic_risk/test_d002g_m2_locked_governance_untouched.py::test_locked_governance_files_unchanged_at_m2_anchor`
fails: #1174 ('repair 139 corrupted commands') rewrote inline commands in the
D-002G/M2 **locked** acceptor `x10r-d002g-p1-strike-scaffolding.yaml` to satisfy
the new acceptor-command-syntax gate, but the M2 lock anchor SHA was not updated.
The lock test correctly caught a locked-file mutation. This is **not** a silent
quarantine target — the resolution (re-anchor the M2 manifest to the repaired
SHA, or revert the file and exempt it) is a governance decision tracked in #1183.
This quarantine only keeps main real-green while that decision is pending.
**Expiry:** `x10r-d002g-p1-strike-scaffolding.yaml` re-anchored or reverted;
drained in #1183.

## Invariant

The fast gate is now **real-green, not fake-green**: it runs ~17.6k tests,
subtracts only the explicitly-quarantined-with-issue files, fails if collection
collapses to zero, and fails on any new unquarantined failure.
