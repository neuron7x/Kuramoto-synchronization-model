# D-002H Gate D — Forbidden-Claim Scan (declaration, not authorisation)

**Study:** D-002H
**Gate:** D — forbidden-claim scan clean
**Status:** PASS (zero leaks across scanned D-002H/D-002G surface)
**Machine artifact:** [`artifacts/d002h/scans/d002h_forbidden_claim_scan.json`](../../artifacts/d002h/scans/d002h_forbidden_claim_scan.json)
**Schema:** `D002H-GATE-D-v1`
**Scanner:** [`scripts/x10r_d002h_gate_d_scan.py`](../../scripts/x10r_d002h_gate_d_scan.py)
**Tests:** [`tests/systemic_risk/test_d002h_gate_d_forbidden_claims.py`](../../tests/systemic_risk/test_d002h_gate_d_forbidden_claims.py)

---

## 1. Scope

This artifact closes Gate D of the locked D-002H authorisation conjunction
described in [`D002H_CANONICAL_RUN_AUTHORIZATION_GATES.md`](D002H_CANONICAL_RUN_AUTHORIZATION_GATES.md) §D.

Gate D is **automated scan**: it walks the D-002H / D-002G governance
docs, artifacts, commit acceptors and tests, and verifies that every
occurrence of a forbidden phrase from the locked D-002H prereg
`forbidden_claims` list (sha256
`44b18b5a40ce9d188a9c3bd49339621f81a65a15f97a683247902450dd54acec`)
sits inside an explicit denial context (`❌`, `NOT`, `MUST NOT`,
`forbidden`, `excluded`, `cannot`, `never`, `out of scope`, …).

Gate D **does not execute** any canonical run, **does not produce**
scientific results, and **does not authorise** the D-002H canonical
run. The 7-gate conjunction A ∧ B ∧ C ∧ D ∧ E ∧ F ∧ G is the
authorisation contract; this PR addresses Gate D only.

Gates A, B, C are already closed on `main`:

| Gate | Artifact | Anchor PR |
|------|----------|-----------|
| A    | [`docs/governance/D002H_PREREGISTRATION.yaml`](D002H_PREREGISTRATION.yaml) | #683 |
| B    | [`artifacts/d002h/eligibility/d002h_ricci_eligibility.json`](../../artifacts/d002h/eligibility/d002h_ricci_eligibility.json) | #684 |
| C    | [`artifacts/d002h/canonical/d002h_canonical_grid.json`](../../artifacts/d002h/canonical/d002h_canonical_grid.json) | #685 |

Gates **E, F, G** remain open after this PR.

---

## 2. Forbidden phrases (enumerated)

The scanner pins the 9 `forbidden_claims` from the locked D-002H prereg
verbatim plus the two §D extras (`canonical run authorised /
authorized`):

| # | Phrase | Source |
|---|--------|--------|
| 1 | `cross-substrate robustness` | D002H prereg `forbidden_claims[0]` |
| 2 | `general topology robustness` | D002H prereg `forbidden_claims[1]` |
| 3 | `D-002G rescue` | D002H prereg `forbidden_claims[2]` |
| 4 | `D-002C rescue` | D002H prereg `forbidden_claims[3]` |
| 5 | `global systemic-risk conclusion` | D002H prereg `forbidden_claims[4]` |
| 6 | `scientific PASS before canonical run` | D002H prereg `forbidden_claims[5]` |
| 7 | `M4 inside D-002G` | D002H prereg `forbidden_claims[6]` |
| 8 | `block_structured remains in scope` | D002H prereg `forbidden_claims[7]` |
| 9 | `temporal_coupling remains in scope` | D002H prereg `forbidden_claims[8]` |
| 10 | `canonical run authorized` | Gates doc §D — never as present-state claim |
| 11 | `canonical run authorised` | Gates doc §D — never as present-state claim |

The forbidden-phrase tuple is referenced verbatim by every Gate D test
(`tests/systemic_risk/test_d002h_gate_d_forbidden_claims.py`). Any drift
between the prereg list and the scanner tuple fails the corresponding
phrase-specific test.

---

## 3. Exempt files (enumerated)

The following files **intentionally** enumerate the forbidden phrases and
are exempt from the scan. Each exemption has a load-bearing reason
documented inline in `SCANNER_EXEMPT_PATHS`.

| Path | Reason |
|------|--------|
| `scripts/x10r_d002h_gate_d_scan.py` | The scanner — defines `FORBIDDEN_CLAIMS` as guard literals. |
| `tests/systemic_risk/test_d002h_gate_d_forbidden_claims.py` | The scanner's own tests — mention every phrase to scan FOR them. |
| `artifacts/d002h/scans/d002h_forbidden_claim_scan.json` | The scanner's output — embeds the phrase list for audit reproducibility. |
| `docs/governance/D002H_GATE_D_FORBIDDEN_CLAIM_SCAN.md` | This report — enumerates phrases in the §2 table. |
| `docs/governance/D002H_PREREGISTRATION.yaml` | The list source (sha-locked at PR #683). |
| `docs/governance/D002H_CLAIM_BOUNDARY.md` | The ❌-block doc that enumerates forbidden interpretations. |
| `docs/governance/D002H_CANONICAL_RUN_AUTHORIZATION_GATES.md` | The §gates doc that references "canonical run authorised" as the artifact-to-be-created. |
| `docs/governance/D002H_SCOPE_RATIONALE.md` | The scope-rationale doc explaining substrate exclusions. |
| `.claude/commit_acceptors/x10r-d002g-*.yaml` (7 files) | D-002G acceptors that pin forbidden phrases inside falsifier `grep -vE` guards. |
| `.claude/commit_acceptors/x10r-d002h-*.yaml` (4 files) | D-002H acceptors that pin forbidden phrases inside falsifier `grep -vE` guards (including this PR's acceptor). |
| `tests/systemic_risk/test_d002g_m3_traps.py` | Adversarial M3 trap test with `_FORBIDDEN_PHRASES` guard literal list. |
| `tests/systemic_risk/test_d002g_m3_no_promotion.py` | No-promotion guard test. |
| `tests/systemic_risk/test_d002g_p3_traps.py` | Adversarial P3 trap test. |
| `tests/systemic_risk/test_d002g_p3_no_canonical_promotion.py` | No-canonical-promotion guard test. |
| `tests/systemic_risk/test_d002g_structural_closure.py` | Structural-closure guard test. |
| `tests/systemic_risk/test_d002h_gate_b_eligibility.py` | Gate B test with `_FORBIDDEN_CROSS_SUBSTRATE_PHRASES` list. |
| `tests/systemic_risk/test_d002h_preregistration.py` | Pre-registration round-trip test that mentions phrases. |

Exempt-set discipline (per the operating law of this brief):

> If a leak is found, do NOT silence it by widening the exempt set —
> fix the leaking phrase OR explicitly add ❌-denial framing. Exempt
> set is bounded by design intent, not convenience.

The 24 exempt files in the artifact are exactly the files whose **stated
purpose** is to enumerate or pin the forbidden phrases.

---

## 4. Scanner method

The scanner (`scripts/x10r_d002h_gate_d_scan.py`) walks the following
globs and treats every match that is not in `SCANNER_EXEMPT_PATHS` as
in-scope:

```
docs/governance/D002*.md
docs/governance/D002*.yaml
artifacts/d002g/**/*
artifacts/d002h/**/*
.claude/commit_acceptors/x10r-d002*.yaml
tests/systemic_risk/test_d002*.py
scripts/x10r_d002*.py
```

For each line of every in-scope file, the scanner does a
case-insensitive substring match against every entry in
`FORBIDDEN_CLAIMS`. A hit is **demoted to denial-context** iff any
`ALLOWED_DENIAL_MARKERS` token (`❌`, `NOT`, `MUST NOT`, `forbidden`,
`excluded`, `cannot`, `never`, `out of scope`, …) appears in a context
window of `CONTEXT_LINES_BEFORE=8` lines above and
`CONTEXT_LINES_AFTER=2` lines below the hit. Otherwise the line is
recorded as a `LeakRecord`.

The window is asymmetric because denial framing in this corpus is
typically introduced by a heading or list header above the bulleted
forbidden phrase (e.g. `NO null-domain admissibility verdict may promote
to:` followed by a bulleted `* D-002C rescue claim.`). The small forward
window catches inline trailing denials.

Verdict logic:

```
gate_d_verdict = "PASS" iff n_leaks == 0
gate_d_verdict = "FAIL" otherwise
canonical_run_authorized = false   # always, regardless of verdict
downstream_gates_remaining = ["E","F","G"]
```

The verdict literal is the only verdict the scanner produces; it does
**not** introduce a new mechanism, a new substrate, a new tier, or a
new ledger entry.

---

## 5. Verdict

```
schema_version              D002H-GATE-D-v1
study_id                    D-002H
gate                        D
gate_d_verdict              PASS
n_leaks                     0
scanned_files_count         76
exempt_files_count          24
canonical_run_authorized    false
downstream_gates_remaining  ["E", "F", "G"]
```

No file in the scanned set contains a forbidden phrase outside the
denial context. The full scanned/exempt enumeration and the (empty)
`leaks` list are pinned in
`artifacts/d002h/scans/d002h_forbidden_claim_scan.json`.

The artifact is reproducible from a clean working tree by running:

```
PYTHONPATH=. python scripts/x10r_d002h_gate_d_scan.py
```

This is a side-effecting CLI: it writes the artifact JSON and returns
exit code 0 on PASS, 12 on FAIL (mirroring the falsifier's exit-code
convention).

---

## 6. Claim boundary (verbatim, locked)

> Gate D verifies the scoped no-promotion property of D-002H
> docs/artifacts. PASS does NOT authorise canonical run. Conjunction
> A ∧ B ∧ C ∧ D ∧ E ∧ F ∧ G is the contract.

This boundary is also pinned inside the JSON artifact at the
`claim_boundary` field, byte-equivalent to the above.

---

## 7. Forbidden interpretations (❌ list)

- ❌ "Gate D PASS authorises the D-002H canonical run." It does not;
  Gates E, F, G remain open and the conjunction is the contract.
- ❌ "Gate D rescues D-002G or D-002C." It does not; the D-002C ledger
  sha (`f96ba9b5a2057d2e0bff84afc28578ab316cff73f6dc6673fb0d6d543b8bd6dd`)
  is byte-exact unchanged across this PR; the D-002H prereg sha is also
  byte-exact unchanged.
- ❌ "Gate D widens the exempt set to silence a real leak." It does not;
  every exempt file is exempt because its stated purpose is to enumerate
  forbidden phrases as guard literals.
- ❌ "Gate D introduces a new verdict literal." It does not; the only
  literal is `PASS` / `FAIL`, mirroring the binary all-or-nothing
  contract of the §D gates doc.
- ❌ "Gate D PASS implies block_structured or temporal_coupling
  substrates are back in scope." It does not; both are excluded by the
  locked D-002H prereg and the scanner enforces the exclusion as two
  distinct phrase guards.

---

## 8. Reproduce

```
# from a clean working tree synced to this PR's merge sha:
PYTHONPATH=. python scripts/x10r_d002h_gate_d_scan.py
# -> exit 0, "Gate D PASS: scanned=76 exempt=24 leaks=0"

# tests:
PYTHONPATH=. python -m pytest \
  tests/systemic_risk/test_d002h_gate_d_forbidden_claims.py -q
# -> 10 passed
```

Per `D002H_CANONICAL_RUN_AUTHORIZATION_GATES.md`, Gate D PASS is
**necessary but NOT sufficient** for canonical D-002H run authorisation.
Gates A, B, C, D closed. Gates E, F, G remain open. Canonical run
remains BLOCKED.
