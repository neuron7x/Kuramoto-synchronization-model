# REL-011 Release-Evidence Gate — Destruction Findings (mandatory pre-integration)

Target: `scripts/ci/check_release_evidence.py` (REL-011 single release evidence bundle
aggregator + integrity gate) attacked at base 80fd48496 (wave-14 branch). 1 destroyer,
7 attack classes. All attacks isolated in /tmp, worktree left clean.

A release-evidence gate that fail-opens is catastrophic — it would certify a release as
carrying evidence it does not have. Attacked as an adversary shipping an unqualified release.

## CONFIRMED FAIL-OPEN

| ID | Sev | Defect | Repro | Fix |
|----|-----|--------|-------|-----|
| RD-F1 | CRITICAL | content/verdict-BLIND readiness: category "satisfied" == `Path.is_file()`; bytes never inspected | plant `{"verdict":"FAIL"}` / 0-byte / non-JSON-garbage / `{}` at the 5 missing mandatory receipt paths + `--emit` -> release_readiness=READY, GATE GREEN, **exit 0** | per-category receipt-content contract: parse JSON + validate shape + verdict PASSING + numeric floor (coverage/mutation); garbage/empty/FAIL/below-floor -> NOT satisfied -> NOT_READY |
| RD-F1b | CRITICAL | verdict-bearing categories (security_scan->verdict, cleanroom->match) surface value as decorative metadata, never gate | flip receipts to verdict:"FAIL" / match:false, re-emit -> still GATE GREEN exit 0 | gate on verdict==PASS / match==true |

## LOW (fail-CLOSED but off-contract)

| ID | Sev | Defect | Fix |
|----|-----|--------|-----|
| RD-L1 | LOW | malformed committed bundle JSON / non-dict payload / malformed provenance -> uncaught traceback + exit 1 (docstring promises clean exit 2) | try/except around committed-load + build_bundle/_source_ref -> clean exit 2 |
| RD-L2 | LOW | schema `patternProperties` w/o effective additionalProperties:false -> an extra `backdoor` category is schema-accepted (determinism-covered, not exploitable alone) | constrain categories to enumerated required set |

## HELD (attacked, did not break — non-vacuous)
- byte-flip MANIFEST.sha256/VERSION/ledger without regen -> RED exit 1 (digest + determinism anchor)
- committed bundle: flip category PRESENT->MISSING / verdict NOT_READY->READY / recorded sha bogus -> RED
- tamper VERSION + forge SHA256SUMS to match -> RED (committed release_evidence.json is independent anchor)
- drop SHA256SUMS line -> RED (recomputed != committed)
- schema gate real: missing-required / wrong-type / extra-top-prop / bad-enum / PRESENT+null-sha / short-commit -> rejected
- tampered bundle -> nonzero exit (never 0); missing bundle dir -> clean exit 2; receipt path is a dir -> NOT_READY

## Closure
RD-F1/F1b/L1/L2 fixed in wave-14 before integration (regression tests replay each repro).
Gate remains RED-by-design (release honestly NOT_READY — real coverage/mutation/sbom/tests/wheel
absent = downstream TST-003/TST-010/…); the fix makes it content-AWARE so a planted fake receipt
also correctly fails. Re-attack evidence: reattack_rel011.txt.
