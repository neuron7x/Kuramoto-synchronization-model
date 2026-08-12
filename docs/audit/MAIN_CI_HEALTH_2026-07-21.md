# Main CI Health — latent red gates hidden by quota (2026-07-21)

Running the full `tests/ci` suite locally (main CI is blocked by `ci_quota_exceeded`,
so these never surface) revealed **7 red gates on the canonical line**, all pre-existing
(reproduced on a 0-change pristine `main` tree). This branch fixes the safe/clearly-correct
ones and documents the rest, which need an owner decision (ratchet-bump vs refactor) or
touch frozen evidence.

## Fixed on this branch
| gate | root cause | fix |
|---|---|---|
| `test_manifest_scope` (×2) | MR !22 landed recovered files without updating root `MANIFEST.sha256` → 24 tracked-but-unlisted + 6 mismatch | regenerated deterministically (`generate_manifest.py`), diff = exactly the !22 + this branch files |
| `test_verify_claims` (claim-boundary) | `docs/research/OPERATIONAL_DEFINITIONS.md:138` "not a live-trading or alpha product" flagged as a product claim — it is an **honest negation** | added a reasoned entry to `.github/claim_boundary_allow.json` (the file's documented mechanism for honest negations) |
| `test_config_references`, `test_gate_standalone_import`, `test_coverage_surface_paths_exist` | the 3 governance holes the recovered gates exposed | fixed in `cf6841de` (see ORPHANED_WORK_RECOVERY ledger) |

## Documented — pre-existing, need owner decision (NOT fixed here)
1. **`test_architecture_debt_inference` — debt over budget.** `type_ignore_suppressions`
   709 > 704 (+5); `noqa_suppressions` 534 > 510 (+24). Accumulated on main while CI
   was quota-blocked; ~9 noqa are from the !22 research files (legitimate numeric code).
   Even removing all !22 contributions leaves it over the frozen budget from pre-existing
   growth. **Decision needed:** re-freeze the ratchet at current counts (reflect reality,
   catch future growth) vs a suppression-reduction sweep. Not bumped unilaterally — a
   ratchet ceiling is a governance decision.
2. **`test_ratchets_enforced[check_import_architecture]` — import-architecture ratchet.**
   ✅ **FIXED (2026-07-21, this branch).** 6 sys.path hacks (the head-truncated view
   showed 5; the full set added `scripts/ci/check_terminology.py`) converted to
   importlib file-location loads — no sys.path mutation:
   `run_comparison.py`, `check_baselines.py`, `check_numerical_stability.py`
   (`_ensure_pkg` for core+geosync), `check_physics_score.py`, `check_state_ontology.py`,
   `check_terminology.py` (`_text_normalize` fallback). Each verified runnable standalone
   from a foreign cwd; the two `baselines.py` loaders register the module in `sys.modules`
   before `exec_module` (dataclasses needs it). Ratchet: no new debt (55 baseline hacks
   remain, target 0). Their own gate tests: 116 passed.
3. **`test_artifact_freshness_gate` (×2) — provenance/evidence.**
   `artifacts/physics_v2/REL-004_readiness_receipt.json` (committed by remediation wave-2,
   `68d12f2f`) is an **unclassified evidence artifact** — not in the provenance contract —
   plus deterministic-artifact regen drift. Touches release evidence; **not recomputed**
   here per the frozen-calibration discipline (never recompute frozen evidence). Needs the
   evidence owner to classify REL-004 in the provenance contract.

## Net
`tests/ci`: 1024 → **1029 passing** on this branch (5 gates fixed); 3 gates (debt,
import-arch, artifact-freshness) remain red pending owner decisions, each with root cause
above. This branch introduces **no new red** and touches no frozen evidence.
