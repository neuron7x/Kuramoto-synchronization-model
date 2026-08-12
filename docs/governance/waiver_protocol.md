# Gate Waiver Protocol

**Readiness entry:** GOV-001 ("Report-only review surfaces need explicit closure rules
before stronger readiness claims.")
**Status:** binding. **Owner:** repository maintainer (neuron7xLab).

A *gate* is any CI check, branch-protection required status check, or governance
validator (`commit-acceptor-validation`, `readiness-register`, `repo-policy`,
`research-integrity-gate`, `secrets-supply-chain`, `python-quality`, …). This
protocol defines the only admissible ways a gate may be bypassed, so a red or
report-only surface can never silently become a merge.

## 1. Default — gates are fail-closed

- A **required** (blocking) check that is red blocks merge. No override by re-running
  until green-by-luck: a flaky failure must be root-caused or quarantined with an issue.
- A **report-only** check that is red does **not** block merge, but MUST be either
  (a) remediated, (b) waived per §3, or (c) escalated to blocking per §4 before its
  associated readiness claim is strengthened. Ignoring it is not a closure.

## 2. Classification

Every gate is exactly one of:

| Class | Meaning | Bypass |
|-------|---------|--------|
| `blocking` | required status check on `main` | only via §3 waiver |
| `report-only` | runs but does not block | remediate, §3 waiver, or §4 escalate |
| `advisory` | informational, no readiness claim depends on it | no waiver needed |

The current blocking set is recorded in
[`governance/evidence/gov001_blocking_check.json`](../../governance/evidence/gov001_blocking_check.json).

## 3. Waiver (the only admissible bypass)

A waiver is granted only when ALL hold:

1. **Written justification** — the specific finding, why it is non-blocking *for this
   change*, and the residual-risk argument.
2. **Scope** — the exact files / alert IDs / check name the waiver covers. No blanket waivers.
3. **Expiry** — an explicit date or a tracking issue. A waiver without an expiry is invalid.
4. **Auditability** — recorded in the PR body and, for security findings, as a dismissal
   reason on the alert (so the bypass is attributable and revocable).
5. **No verdict-flip** — a waiver may accept a *known* finding; it may NOT be used to flip
   a fail-closed verdict (sign flip, threshold retune) without the maintainer's explicit
   sign-off and a fail-closed re-audit.

Severity floor: `error`-severity security findings and any P0 invariant violation are
**not waivable** — they block until remediated or verified false-positive with evidence.

## 4. Escalation (report-only → blocking)

A report-only gate is escalated to a required status check when it has run green on
`main` for a sustained period and a readiness claim now depends on it. Escalation is a
branch-protection change, recorded in `gov001_blocking_check.json` with before/after
required sets and a one-line rollback. Escalation is reversible by the same mechanism.

## 5. De-escalation / rollback

Removing a blocking check (e.g., a gate proven chronically flaky) is itself a waiver
under §3: it needs written justification, scope, an expiry/replacement plan, and is
recorded with the before/after required set. Branch protection is never edited silently.
