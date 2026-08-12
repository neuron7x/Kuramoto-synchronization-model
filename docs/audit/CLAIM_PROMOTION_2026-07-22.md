# Tier-promotion gate — the right to assert ANCHORED is machine-earned (RES-020, roadmap step 4)

`claims/promotion_policy.yaml` + `scripts/ci/check_claim_promotion.py` close the last unbound
link in the executable claims-governance kernel: a claim's self-declared `tier` in
`docs/CLAIMS.yaml` (22 ANCHORED / 5 EXTRAPOLATED) must have **earned** the EXECUTED audit verdict
its tier demands. Designed + adversarially hardened by a 10-agent orchestrated workflow; the
adversary found a real hole (below), which was fixed before merge.

## The binding
- **ANCHORED requires SUPPORTED** — the falsifier ran and HELD. NOT_TESTED (parked), DANGLING
  (cannot-fire), REFUTED (fired) all fall short → gate RED.
- **EXTRAPOLATED requires ≥ NOT_TESTED** — must not be actively broken (REFUTED/DANGLING excluded);
  an honestly-parked or by-design-untested claim is admissible.
- Strength ordering is imported verbatim from `geosync.proof.audit._SEVERITY` — the gate never
  re-implements verdict logic and never re-runs a falsifier; it is a THIN CONSUMER of the audit
  report and verifies that report's `content_digest` (tamper/staleness) before trusting it.
- **Hard contract minimums live in CODE** (`_CONTRACT_MIN`): the editable policy YAML may make a
  tier STRICTER but can never weaken ANCHORED below SUPPORTED — the data file can't become a
  laundering vector (instrument-invariant split).

## Result on the real 27 claims (executed / default mode)
`ok=True checked=27 violations=0 allowlisted=1`. **21/22 ANCHORED earned SUPPORTED**; 5
EXTRAPOLATED satisfy their floor; the one exception — `api-contract-openapi-coverage` — is
NOT_TESTED because its falsifier needs the optional `schemathesis` dependency, so it is
**allowlisted with a mandatory reason** that the gate marks STALE (→ RED) the moment the node
earns SUPPORTED. No silent pardon.

## Adversarial hardening (a real hole, caught + fixed)
The skeptic found that `require_evidence_paths_exist` was a data-file knob that could be flipped
`false` (or deleted) to silently disable the "a claim resting on deleted evidence is
over-promotion" check. Fixed: it is now a hard contract minimum — `validate_policy` rejects a
policy that disables it, and the enforcement defaults it True on absence. Both the set-false and
delete-the-line laundering vectors are closed (verified).

## CI
`claim-promotion` job (fail-closed): runs the audit in default mode (executes non-heavy
falsifiers — resolve-only cannot prove SUPPORTED) then enforces the policy. 33 teeth pass
(over-promotion → RED, refuted/dangling under a floor → RED, stale allowlist → RED). This is
roadmap step 4; step 5 (external-reviewer packet) partially landed (console entry points, MR!47).
