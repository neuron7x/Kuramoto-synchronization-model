# D-002H Canonical Run Authorisation Gates (locked)

Canonical D-002H run is allowed if and only if ALL of the following gates evaluate to PASS:

## Gate A — D-002H prereg locked
- D002H_PREREGISTRATION.yaml exists on main with sha256 pinned at this PR's merge commit.
- Subsequent edits constitute fresh D002J pre-registration.

## Gate B — ricci_flow M1/M3 eligibility reverified
- run verify_m1_eligibility on ricci_flow × {50, 100, 200} at canonical lambda grid; expect all cells ELIGIBLE_M1.
- run verify_m3_eligibility on the same grid; expect all cells ELIGIBLE_M3 (with match_report within locked tolerances).
- emit machine-readable verdict artifact under artifacts/d002h/eligibility/d002h_ricci_eligibility.json.

## Gate C — canonical parameter grid declared
- emit artifacts/d002h/canonical/d002h_canonical_grid.json with:
    substrates = [ricci_flow]
    N = [50, 100, 200]
    lambda_values = [0.0, 0.05, 0.10, 0.20, 0.40, 1.0]
    n_seeds = 20
    n_bootstrap = 16
- pinned at separate PR's merge commit. No silent drift.

## Gate D — forbidden-claim scan clean
- automated grep over all D-002H docs + reports for the forbidden_claims list in D002H_PREREGISTRATION.yaml.
- zero hits outside ❌/forbidden-list/D-002C-reference context.

## Gate E — D002C ledger untouched
- byte-exact sha256 of docs/governance/D002C_CLAIM_LEDGER.yaml at the authorisation artifact's commit must equal f96ba9b5a2057d2e0bff84afc28578ab316cff73f6dc6673fb0d6d543b8bd6dd.

## Gate F — explicit authorization artifact created
- artifacts/d002h/authorization/d002h_canonical_run_authorisation.json exists with schema D002H-CANONICAL-RUN-AUTHORISATION-v1, status="AUTHORISED", listing Gate A..G verdicts and the pinned sha of D002H_PREREGISTRATION.yaml.
- authorization artifact is a SEPARATE PR; it CANNOT be this prereg PR.

## Gate G — CI terminal green
- all required CI checks on the authorisation PR PASS.
- no commit-acceptor-validation failure, no secrets-supply-chain failure, no test failure.

## Conjunction
Canonical run allowed iff: A ∧ B ∧ C ∧ D ∧ E ∧ F ∧ G

This PR (D-002H pre-registration) PASSES Gate A only. Gates B–G are downstream artifacts.
