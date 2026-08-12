# WP-03 — Physics Release Scorecard as a Gate

**Research question.** Can partial physics evidence silently become release-ready?

**Hypothesis.** A scorecard without enforcement decays into a decorative badge.

**Failure mode.** A human (or a release bot) sets "ready" while a required
dimension is still `PARTIAL` / `UNTESTED` / `FALSE`. The release ships on an
incomplete evidence chain.

## Mechanism

[`physics_release_scorecard.yml`](../../physics_release_scorecard.yml) declares,
per dimension, a discrete state on a strict ordering:

```
FALSE < UNTESTED < PARTIAL < LOCAL_VERIFIED < CI_VERIFIED < EVIDENCE_BEARING
```

[`tools/release/check_physics_release_scorecard.py`](../../tools/release/check_physics_release_scorecard.py)
**recomputes** readiness from the dimension states and fails closed when:

- `claimed_ready: true` while any **required** dimension is below
  `min_state_for_ready` (default `CI_VERIFIED`) — **PARTIAL != READY**, the core lie;
- a dimension claims a verified state (`>= LOCAL_VERIFIED`) with **empty
  `evidence`** — a claim with no proof;
- an unknown state, a malformed scorecard, or a gate with **no required
  dimension** (decorative).

Readiness is never trusted from a hand-set flag; it is derived. Under-claiming
(`computed_ready=true`, `claimed_ready=false`) is safe and passes.

## Current state (honest)

The shipped scorecard is **NOT release-ready** and says so. Verified dimensions
(`dependency_security_gate`, `CodeQL_gate`, `claim_boundary_gate`,
`SecondOrderStabilityAudit`, `descriptor_promotion_firewall`) are `CI_VERIFIED`.
The blocking dimensions double as the remaining roadmap:

| Dimension | State | Closes under |
|-----------|-------|--------------|
| `same_SHA_CI_proof` | PARTIAL | WP-07 |
| `negative_evidence_ledger` | UNTESTED | WP-07 |
| `artifact_replayability` | PARTIAL | WP-07 |
| `Scorecard_gate` (OpenSSF) | FALSE | supply-chain lane |

## Running

```bash
python tools/release/check_physics_release_scorecard.py        # human report
python tools/release/check_physics_release_scorecard.py --json # machine report
pytest -q tests/release/test_physics_release_scorecard.py
```

The CI gate `physics-release-scorecard-gate` runs the detector + the
deterministic suite fail-closed: the scorecard cannot drift into a self-flattering
"ready" without the evidence chain.
