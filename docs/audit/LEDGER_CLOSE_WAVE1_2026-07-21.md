# Remediation-ledger closure — Wave 1 (2026-07-21)

Two OPEN items closed against real, independently-verified evidence. Each was checked by a
SEPARATE adversarial reviewer agent (not the implementer) that ran the gates/tests, read the
sources for teeth, and defaulted to FAIL on weak evidence — the two-signature / COI discipline.
Two further candidates (ARC-016, OPS-003) were **held OPEN** because their declared dependencies
(TST-015 fault-injection, TST-012 property tests) are not yet closed; closing them now would
violate the ledger's own dependency semantics. They close after the TST-015 build.

## RES-014 — Preserve negative evidence and tombstones → CLOSED
- Evidence: `scripts/ci/check_tombstone_preservation.py` — GREEN: 7 tombstones sha-anchored,
  7 negative artifacts confirmed on disk.
- Teeth (verifier-confirmed): `_validate` fails on a missing 40-hex SHA or a non-existent
  artifact path — a deleted/tampered tombstone flips the gate RED. Not vacuous.
- Independent verdict: PASS.

## REL-013 — Forbid stale generated artifacts → CLOSED
- Evidence: `scripts/ci/check_artifact_freshness.py` — GREEN: 6 deterministic artifacts fresh.
- Teeth (verifier-confirmed): `check()` recomputes each generator's sha256 and flags STALE on
  mismatch vs the committed digest. Now runs on live CI — picked up by the `gates-all-meta`
  job (`run_all_gates.py` globs every `scripts/ci/check_*.py`, this gate is not excluded).
- Independent verdict: PASS.

## Held OPEN (dependency-honest)
- **ARC-016** (OMS idempotency/conservation) — core claim independently verified PASS
  (two same-cid concurrent submits → exactly one queued order; INV-OMS1 E_kinetic≥0 witnessed),
  but deps TST-012 + TST-015 are open. Closes after TST-015.
- **OPS-003** (kill-switch/recovery) — independently verified PASS (raising protective callback
  → KillSwitchCallbackError + still-active; corrupt persisted state → HALTED fail-closed), but
  deps ARC-016 + TST-015 open. Closes after the chain TST-015 → ARC-016.

Ledger status: 100 OPEN → 98 OPEN. Honest closure only; no dependency-order violation.
