# Fractal Health Map of `main` — full gate X-ray (2026-07-21)

Ran **every** gate (81 `scripts/ci/check_*.py` + 12 `scripts/check_*.py`) against the full
`main` tree — not the 26-gate CI `integrity` subset, and not `make verify` (changeset-only).
CI is `ci_quota_exceeded`, so this whole-tree view had never been taken. Result: **78 GREEN,
13 non-green, 2 need-args**. The non-green are not 13 unrelated bugs — they collapse into
**five self-similar generating functions** that recur at every scale of the system.

## The generating functions (why the same defect keeps appearing)

**G1 — registry desync.** A file-set change must ripple to *every* parallel registry, but a
change syncs only some. The registries are self-similar: root `MANIFEST.sha256`, `INVENTORY.json`,
`examples_manifest.yaml`, dataset manifests, the evidence-provenance contract, the import-arch
baseline, the debt budget. MR !22 (recovery) updated the tree but not all registries → root
manifest drifted (fixed in !23), then **INVENTORY.json** drifted (fixed here), and fixing
INVENTORY re-drifts the manifest — the ripple is the function itself.

**G2 — dangling reference.** A config/manifest names a path that (dis)appeared. Same shape at
every scale: connectome `import_roots` → non-existent `geosync/*` (fixed in !23); config
templates → missing modules; coverage surfaces → empty dirs (fixed in !23); examples manifest →
resolution mismatch.

**G3 — standalone / packaging binding.** First-party code not importable without repo-root on
`sys.path`. Fixed for 6 gates via `_ensure_pkg` file-location loads (!24). Still latent:
`check_governance_kernel_binding` (`import governance` fails standalone though `governance/` is a
valid package with `__init__.py`).

**G4 — fail-closed catch (gate working as designed).** Not a gate defect — the gate refusing
ungoverned input. `check_dataset_manifests`: `askar-instruments-v1`, `askar-market-panel-v1`
carry `license=UNKNOWN` → UNLICENSED, fail-closed. Correct behaviour; needs a licensing decision,
not a code fix.

**G5 — environmental / frozen evidence.** Gate needs a CI-produced receipt or reads frozen
calibration. `check_release_evidence` (missing coverage/mutation/sbom/tests/wheel receipts —
produced by CI lanes), `check_artifact_freshness` (REL-004 provenance), dopamine contract/promotion
state. Must not be recomputed locally (frozen-calibration discipline).

## Disposition
| gate(s) | G | status |
|---|---|---|
| root `MANIFEST.sha256` | G1 | ✅ !23 |
| connectome roots, coverage surfaces, config refs | G2 | ✅ !23 |
| 6 sys.path gates → `_ensure_pkg` | G3 | ✅ !24 |
| `check_inventory_sync` (INVENTORY.json ← !22 residue) | G1 | ✅ this branch |
| `check_examples_manifest` (6 unregistered `examples/*.py` + 4 mis-filed `docs/examples/*.md`) | G1/G2 | ✅ 2026-07-21 — registered the 6 demos (real seed/deps), removed the 4 doc entries (manifest governs `examples/*.py` only) |
| `check_governance_kernel_binding` | G3 | ✅ 2026-07-21 — `_ensure_pkg('governance')` file-location bootstrap; PASS standalone |
| `check_dataset_manifests` (askar-*/binance-* UNKNOWN/PUBLIC_NO_LICENSE) | G4 | ⏳ licensing decision (P5) |
| `check_artifact_freshness` | G5 | ✅ 2026-07-21 (P6) — classified REL-004 receipt as `generated-but-excluded` (timestamped verdict-gate output, same as law_witness_index); regenerated artifacts/manifest.json bookkeeping (no deterministic/frozen artifact recomputed) |
| `check_release_evidence` (coverage/mutation/sbom/wheel receipts) | G5 | ⏳ produced by CI release lanes — release-context/env, not faked |
| dopamine contract / claim_promotion | G5/gov | ⏳ 2026-07-21: ran the recovered `generate_dopamine_component_artifacts.py` (fail-closed, real checks). config/schema/properties/backtest/slo/performance = **PASS**; claim_promotion = **FAIL** on `docs/CLAIMS.yaml` 'tested/anchored' wording for geosync.dopamine lacking a formal promotion manifest -> security **BLOCKED** (depends on claim_promotion). A genuine claims-promotion governance state, not a bug; the gate checks verdict CONTENT so BLOCKED artifacts cannot false-green it. Owner decision: soften the claim wording to P2_RESEARCH level, or complete the promotion evidence chain. Generating fake PASS evidence would have hidden this. |
| debt-ratchet | — | ⬇️ 2026-07-21: **noqa reduced 534→338** (197 dead directives removed via `ruff --extend-select RUF100 --fix`, ruff error count unchanged at 20 = proven dead; budget tightened 510→338). **type_ignore 709→703 (P1, 2026-07-21)**: 6 real mypy-verified fixes — `message: Any` on 2 event_bus broker handlers, `func: Any` on 2 no-op njit-fallback decorators (kuramoto/ricci), `cast()` on 2 cli return-narrowings. All runtime no-ops (annotations/casts); mypy 'Success' each. **Debt gate GREEN** (both classes under budget; budgets tightened noqa 510→338, type_ignore 704→703). |

## The actual root cause (the function above the functions)
**Gates exist but do not run.** CI is quota-blocked, `make verify` is changeset-only, and no
local target runs the full gate set against the whole tree. So every ratchet silently slips and
every registry silently desyncs — invisibly. The highest-leverage fix is not any single gate; it
is **restoring a whole-tree gate run** (self-hosted runner, or a `make gates-all` target that
executes this X-ray) so drift is caught the moment it appears, at every scale, instead of
accumulating unseen. Until then, this map is the manual X-ray; re-run it after any file-set change.

## P2/P3/P4 (2026-07-21)
- **check_governance_kernel_binding** ✅ bootstrap fix (G3).
- **check_feature_debt_lock**: now fails *clean* (exit 2, guidance) when base-ref shares no merge-base with HEAD — a stale/unrelated `origin` (github) instead of a raw traceback; classified NEEDS_ARGS. In CI `origin/main`=gitlab resolves normally.
- **check_audit_report_paths**: an INVERTED tripwire (exit 1 = healthy). run_all_gates now models `_INVERTED` gates. Baseline 9→6.

## CI-parity verification (2026-07-21) — main is CI-green modulo release-gates
Ran the exact `.gitlab-ci.yml` job commands locally (CI is quota-blocked, so this is
the only way to know its real verdict):

| CI job step | command | result |
|---|---|---|
| lint | `ruff check .` | ✅ All checks passed (0) |
| lint | `mypy --config-file=mypy.ini .` | ✅ **Success: no issues found in 4126 source files** |
| integrity-gates | 26 `scripts/ci/check_*` gates | ✅ all green |
| integrity-gates | 29-file scoped pytest list | **355 passed, 3 failed** |

The only failures are `test_release_evidence.py` (present-digests / regen-deterministic /
sha256sums). These are **release-gate semantics**, not a defect: the reproducible-build
report archives `--ref HEAD`, and on a dev branch HEAD ≠ the release commit the committed
report was cut for, so the committed bundle correctly differs from a fresh dev-HEAD regen.
They go green at a release commit (HEAD = release). MR!30 already made the report
deterministic *within* a ref (was wall-clock `now()`).

Net: the whole 10-MR consolidation has brought `main` to CI-health — ruff, full-tree
mypy (4126 files), every integrity gate, and 355/358 integrity tests pass. The residual
is release-context (release-gate tests) or owner-decision (dataset licensing, dopamine
claims-promotion) — none is a latent code defect.

## Destruction battery — the session's gates have TEETH (2026-07-21)
Per the mandatory-destruction discipline (a gate that cannot fail is not a gate),
each recovered/fixed gate was adversarially probed by injecting the exact violation
it exists to catch, then reverting. All 9 FIRED (or proved deterministic):

| gate | injected violation | verdict |
|---|---|---|
| check_config_references | dangling `geosync/FAKE_ROOT` in connectome | 🦷 FIRED |
| check_attribute_existence | `getattr(geosync.risk.kill_switch, "fake_zzz", None)` | 🦷 FIRED |
| import_architecture ratchet | new `sys.path.insert` in a gate | 🦷 FIRED |
| run_all_gates meta-ratchet | a new always-red `check_*` gate | 🦷 FIRED (NEW red) |
| check_reproducible_archive | two regens (post-MR!30 fix) | ✅ byte-identical |
| coverage_surface | surface pointing at a non-existent dir | 🦷 FIRED |
| check_silent_procedures | broad silent `except: pass` in a capital-surface procedure | 🦷 FIRED |
| debt-ratchet | a new `# noqa` over the 338 budget | 🦷 FIRED (+2) |
| check_inventory_sync | a tracked in-scope file absent from INVENTORY | 🦷 FIRED |

Two gates (attribute_existence, silent_procedures) required a *correctly-scoped* probe to
fire — they are deliberately narrow (first-party modules only; procedures on capital
surfaces only). A wrong-shaped probe left them GREEN, which is correct: they do not
over-fire on non-violations. Precise teeth, not loose or hollow. The 11-MR consolidation's
gate work is verified real — not fake-green.


## Governance-decision round (2026-07-21) — narrowed, not forced
- **l2_collector**: ✅ excluded from the whole-tree gate sweep — its own docstring says
  "cron every ~60s, or systemd watchdog sidecar"; it probes a LIVE collector, not repo state.
- **dopamine claims-promotion**: NARROWED to a precise owner question. Ran the REAL evaluator
  (`scripts/evaluate_dopamine_rpe_extension.py`) — genuine PASS (config/schema/properties/
  backtest/slo/performance all PASS + EVAL_SUMMARY PASS); the cited test
  `test_td_error_is_linear_in_reward` passes, so the **"tested" wording is truthful** and
  resolvable by committing the real EVAL evidence. Sole residual: the claim carries
  `tier: ANCHORED`, and the gate models ANCHORED as requiring *rollback* evidence — but this
  is an **algebraic** invariant (INV-DA7, ∂δ/∂r=1 to float precision), anchored mathematically,
  not deployment-anchored. Whether an algebraic claim should carry a tier the gate reads as
  deployment-grade is a governance/epistemic call — NOT a code defect, and not softened,
  fabricated, or gate-edited here.
- **dataset licensing**: unchanged — binance PUBLIC_NO_LICENSE (ToS) / askar UNKNOWN provenance;
  a legal grant cannot be fabricated. Owner/legal decision.
