# D-002H Gate F — Canonical-Run Authorisation Artifact (intermediate)

**Schema:** `D002H-CANONICAL-RUN-AUTHORISATION-v1`
**Artifact:** `artifacts/d002h/authorization/d002h_canonical_run_authorisation.json`
**Status:** AUTHORISED (intermediate; Gate G required for absolute final)
**Scope:** `ricci_flow` only (per D-002H prereg)

---

## 1. Scope

Gate F is term 6 of the 7-gate canonical-run authorisation conjunction
defined in `docs/governance/D002H_CANONICAL_RUN_AUTHORIZATION_GATES.md`
§F:

> Gate F — explicit authorization artifact created.
> `artifacts/d002h/authorization/d002h_canonical_run_authorisation.json`
> exists with schema `D002H-CANONICAL-RUN-AUTHORISATION-v1`,
> status="AUTHORISED", listing Gate A..G verdicts and the pinned sha
> of `D002H_PREREGISTRATION.yaml`. Authorization artifact is a SEPARATE
> PR; it CANNOT be this prereg PR.

This PR delivers exactly that artifact, plus its 13 verification tests
and the append-only blockers ledger update. It is governance-only — no
substrate code, no mechanism code, no canonical sweep is touched.

## 2. Prior gate chain

| Gate | Name                                         | Anchor SHA                                 | Verdict |
|------|----------------------------------------------|--------------------------------------------|---------|
| A    | D-002H prereg lock                           | `1b59ce5326a8e8bd8aaaf9666a06075d34b4f6a5` | PASS    |
| B    | ricci_flow M1/M3 eligibility reverification  | `b97daae8b554ab9960510564e19263adcc1fe71b` | PASS    |
| C    | canonical parameter grid declaration         | `a9d852d34258861809325df81bd7cba6d0e557ec` | PASS    |
| D    | forbidden-claim scanner                      | `077073ee801c434840d64f911e7b1f39ce2ac0fa` | PASS    |
| E    | locked-ledger verification                   | `e1d3ae304274e8b8f509edeb83b0a9adfeb43a77` | PASS    |

Conjunction satisfied at Gate F: `A AND B AND C AND D AND E AND F`.
Conjunction still open: `G`.

## 3. Anchor verification method

For each of the 5 prior-gate anchors, the verification probe is

```
git merge-base --is-ancestor <anchor_sha> origin/main
```

Exit code 0 = ancestor (PASS); exit code 1 = not an ancestor (FAIL).
The probe is executed both at PR creation time (manually, on a fresh
checkout of `origin/main`) and inside the test suite via
`subprocess.run(...)` in
`tests/systemic_risk/test_d002h_gate_f_authorization.py::test_gate_f_all_5_anchors_are_ancestors_of_main`
and the parametrised
`test_gate_f_each_anchor_is_ancestor_of_main` (one case per gate).

The D-002C claim ledger byte-exact pin
(`f96ba9b5a2057d2e0bff84afc28578ab316cff73f6dc6673fb0d6d543b8bd6dd`)
and the D-002H prereg byte-exact pin
(`44b18b5a40ce9d188a9c3bd49339621f81a65a15f97a683247902450dd54acec`)
are double-locked: once in the artifact JSON, once inline in the test
module with a `# pragma: allowlist secret` comment, matching the
pattern established by the Gate D and Gate E acceptors.

## 4. Status

- `status` = `"AUTHORISED"` (string literal).
- `canonical_run_authorized_at_gate_f` = `true`.
- `canonical_run_authorized_final` = `false`.
- `final_authorisation_pending_gate` = `"G"`.
- `downstream_gates_remaining` = `["G"]`.

Gate F PASS is intermediate. Absolute final authorisation requires
Gate G (final CI lock on a separate PR) AND a separate canonical-sweep
PR. Even after Gate G, canonical-run authorisation is scoped to
`ricci_flow` only per the D-002H prereg.

## 5. Claim boundary

> Gate F certifies that prior gates A through E PASS on main and
> snapshots the conjunction A ∧ B ∧ C ∧ D ∧ E ∧ F. It does NOT itself
> authorise canonical run execution — Gate G (final CI lock) is required
> for absolute authorisation. Even after Gate G, canonical run
> authorisation is SCOPED to ricci_flow only per D-002H prereg.

## 6. Forbidden interpretations

- ❌ "Gate F status=AUTHORISED means the canonical sweep is starting."
  It does not. Gate G + a separate sweep PR are still required.
- ❌ "Gate F closes B1." B1 was closed structurally by D-002G; D-002H
  operates on the ricci_flow-narrowed grid.
- ❌ "Gate F applies to block_structured or temporal_coupling."
  Explicitly excluded; the D-002H prereg narrows scope to `ricci_flow`
  alone.
- ❌ "Gate F rescues D-002C or D-002G." It does not. Gate F is a
  declaration-and-snapshot gate; no result, no claim, no rescue.
- ❌ "Gate F closes the 7-gate conjunction." It closes term 6 only;
  term 7 (Gate G) remains open.

## 7. Reproduce

```
git checkout origin/main
git merge-base --is-ancestor 1b59ce5326a8e8bd8aaaf9666a06075d34b4f6a5 origin/main && echo "A PASS"
git merge-base --is-ancestor b97daae8b554ab9960510564e19263adcc1fe71b origin/main && echo "B PASS"
git merge-base --is-ancestor a9d852d34258861809325df81bd7cba6d0e557ec origin/main && echo "C PASS"
git merge-base --is-ancestor 077073ee801c434840d64f911e7b1f39ce2ac0fa origin/main && echo "D PASS"
git merge-base --is-ancestor e1d3ae304274e8b8f509edeb83b0a9adfeb43a77 origin/main && echo "E PASS"

PYTHONPATH=. python -m pytest tests/systemic_risk/test_d002h_gate_f_authorization.py -q
```

Expected: all 5 ancestry probes print "PASS"; pytest reports all Gate F
tests passing (10 base contract tests + 5 parametrised ancestor cases
+ 2 additional integrity tests).

## 8. Downstream

| Gate | Status   | Required for canonical run             |
|------|----------|----------------------------------------|
| A    | CLOSED   | yes                                    |
| B    | CLOSED   | yes                                    |
| C    | CLOSED   | yes                                    |
| D    | CLOSED   | yes                                    |
| E    | CLOSED   | yes                                    |
| F    | CLOSED (this PR) | yes                            |
| G    | OPEN     | yes (final CI lock; separate PR)       |

Canonical sweep on the D-002H ricci_flow grid remains BLOCKED until
`A ∧ B ∧ C ∧ D ∧ E ∧ F ∧ G` AND a separate sweep PR. This artifact
does not initiate, schedule, or pre-authorise that sweep.
