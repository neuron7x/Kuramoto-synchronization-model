# 09 — Threats to Validity

Each threat is stated to *weaken overclaiming*, with a mitigation or an explicit
unresolved status. None is decorative.

## 1. Internal validity

| Threat | Mitigation / status |
|---|---|
| gate bugs (a gate passes a bad state) | gates are tested (`tests/ci/test_wheel_contract.py`, `test_package_boundary.py`, `test_falsifier_ledger.py`, `test_wrapper_laziness.py`); adversarial self-tests included |
| stale artifacts (e.g. stale `build/` re-ships packages) | clean-room `git archive` build in `scripts/ci/check_wheel_contract.py` |
| CI flakiness / false negatives | CI is the oracle but necessary-not-sufficient; ratchets fail closed |
| false positives | claim/forbidden scanners deliberately narrow (see `01` RQ1) — UNRESOLVED tension, documented |

## 2. Construct validity

- **Admissibility is not truth.** A bound, falsifier-backed claim is *admissible*,
  not empirically validated. Enforced as a non-claim throughout.
- **Package integrity is not scientific validity.** A clean wheel
  (`artifacts/wheel_contract.json`) says nothing about market structure.
- **Reproducibility debt is not market evidence.** The 70 latent imports (M3) are
  a software metric, not a finding about markets.

## 3. External validity

One repository, one domain (market-structure research), finance-specific
constraints, and limited independent replication. Generalization beyond GeoSync
is **NOT** established. The governance pattern is *proposed* as transferable; that
transfer is unproven.

## 4. Conclusion validity

The metrics may measure *governance strength*, not *research truth*. CI success
is necessary but insufficient for any empirical conclusion. No causal claim is
made that the governance improves market understanding.

## 5. Mitigations (cross-cutting)

- independent replay (the reproducibility package, `docs/phd/10_artifact_reproducibility_package.md`);
- frozen artifacts + monotone ledgers (`.github/bwheel_baseline.json`);
- strict non-claims, enforced by `scripts/ci/check_phd_traceability.py`;
- negative-result reporting (`governance/NEGATIVE_EVIDENCE.yaml`);
- public, exercisable artifact package.

Unresolved (no full mitigation yet): external validity, falsifier *adequacy*
(power), and the narrow-scanner false-positive/negative tradeoff. These are
carried openly in `docs/phd/04_limitation_ledger.md`.
