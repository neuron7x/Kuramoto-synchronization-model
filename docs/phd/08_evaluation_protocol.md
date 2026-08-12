# 08 — Evaluation Protocol

## 1. Evaluation goal

Test whether machine-enforced claim governance (a) reduces false empirical
promotion and (b) exposes reproducibility debt before release. The goal is about
the *governance*, not about market returns.

## 2. Evaluation units

claim records · artifacts · CI gates · PRs · falsifier witnesses
(`governance/FALSIFIER_LEDGER.yaml`) · non-claim-boundary violations.

## 3. Metrics

| ID | Metric | Source command / artifact |
|---|---|---|
| M1 | dead entrypoints | `artifacts/wheel_contract.json::script_failures` (0) |
| M2 | non-geosync packaged namespaces | `artifacts/wheel_contract.json::non_geosync_packages` (13) |
| M3 | latent import failures | `artifacts/wheel_contract.json::import_failures` (70) |
| M4 | new import debt | `scripts/ci/check_import_architecture.py` (0) |
| M5 | forbidden-term findings | `scripts/ci/lint_forbidden_terms.py` |
| M6 | falsifier coverage | `scripts/ci/check_falsifier_ledger.py` (6/6) |
| M7 | claim-to-artifact traceability | `scripts/ci/check_phd_traceability.py` → `artifacts/phd_traceability.json` |
| M8 | CI-caught defect count | PR check-run history (#1302/#1303/#1304) |
| M9 | claim downgrade events | `governance/NEGATIVE_EVIDENCE.yaml` |
| M10 | strict-vs-ratchet delta | `check_wheel_contract.py` vs `--strict` |

Every metric has a command or artifact source; no unverifiable metric is listed.

## 4. Experimental design

Before/after repository state, PR-level intervention, CI-gated acceptance. Each
governance mechanism was introduced in a PR (`docs/phd/03_evidence_matrix.md`)
and its effect measured by the metric above. No success is claimed outside a
gate's verdict.

## 5. Falsification rules (the methodology FAILS if)

- a claim exists without an artifact (caught by `check_phd_traceability.py`);
- synthetic evidence is promoted to measured real-world truth;
- docs assert `B.wheel=0` while `check_wheel_contract.py --strict` fails;
- an entrypoint resolves to a missing module (`script_failures > 0`);
- CI accepts a forbidden claim (`check_claim_boundary.py` regression);
- an empirical claim lacks a replay path.

Any one of these failing is a refutation of the governance, not a tuning knob.

## 6. Real-L2 chapter pre-registration

Dataset requirements, replay command, and null baselines are pre-registered in
`docs/phd/05_next_empirical_chapter.md`. There is **no** profitability objective;
success is defined as *falsification discipline and reproducibility of the
verdict*, never as trading return. The study has not been run (no dataset).
