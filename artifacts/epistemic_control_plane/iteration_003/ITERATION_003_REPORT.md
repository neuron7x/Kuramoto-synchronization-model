# ECP-AS Iteration 003 — Verification Report

## Objective
Replay real 2026 external scientific adjudication events and test whether ECP-AS distinguishes evidence retirement, uncertainty, conflict, falsification, and benign corrections.

## Result
- External cases: **14**
- Material challenges: **9**
- Benign controls: **5**
- ECP-AS external action agreement: **14/14**
- False degradations: **0**
- Missed degradations: **0**
- False falsifications: **0**
- Typed-transition conformance: **14/14**
- Naive retraction=falsification false falsifications: **7**
- Over-conservative all-editorial baseline false degradations: **5**

## Evidence boundary
The DEGRADE/PRESERVE action label is externally grounded. The exact ECP-AS terminal state is an internal policy conformance target, not externally labeled scientific truth.

## Verification
- 49 targeted epistemic-kernel unit tests: PASS
- historical replay runner: PASS
- compileall: PASS
- git diff check: PASS
- source manifest deterministic digest checks: PASS

## Remaining proof obligation
Run against externally labeled or blinded soundness/discovery tasks whose labels are not authored by the ECP-AS implementation team.
