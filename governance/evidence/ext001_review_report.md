# EXT-001 — Independent Review → Remediation Report

**Readiness entry:** EXT-001 ("Independent review should map findings to remediation evidence.")
**Independent reviewer:** GitHub CodeQL code-scanning (automated, external to the change author).
**Snapshot:** 2026-06-10. **Open alerts at review:** 21 (5 error / 3 warning / 13 note).
**Machine-readable map:** [`ext001_remediation_map.json`](ext001_remediation_map.json).

## Method

Every open CodeQL alert was pulled via the code-scanning API and assigned exactly
one disposition, each carrying its own evidence pointer (a dismissal reason, a merged
PR, or a tracked-scope justification). No finding is left unmapped — the gap EXT-001
names is precisely "findings not mapped to remediation evidence."

## Error-tier (5/5 resolved)

| Alert | Rule | Path | Disposition | Evidence |
|-------|------|------|-------------|----------|
| #870 | `py/unsafe-cyclic-import` | `core/indicators/multiscale_kuramoto.py` | **Dismissed — false positive** | `cache.py:44` imports `TimeFrame` only under `if TYPE_CHECKING`; no runtime cycle (`import core.indicators` succeeds). Dismissed via API. |
| #871 | `py/unsafe-cyclic-import` | `core/indicators/multiscale_kuramoto.py` | **Dismissed — false positive** | Same TYPE_CHECKING-guarded import as #870. |
| #221 | `py/unreachable-except` | `execution/live_loop.py` | **Remediated** | PR #900 (merged). |
| #285 | `py/call/wrong-named-argument` | `bench/bench_indicators.py` | **Remediated** | PR #900 (merged). |
| #286 | `py/call/wrong-named-argument` | `examples/integrated_risk_management_example.py` | **Remediated** | PR #900 (merged). |

Two error findings were verified false positives (TYPE_CHECKING-only static cycle,
no runtime effect) and dismissed with an auditable reason on the alert; the other
three were genuine and fixed in PR #900 "fix(execution): unreachable transient-error
handler + 4 call/return defects (CodeQL tail)".

## Lower tiers (16 tracked, not promoted)

- **13 × `js/unused-local-variable` + 3 × `js/superfluous-trailing-arguments`** — confined to
  `ui/dashboard/demo.html`, a non-shipping demo asset; no runtime or financial path. Tracked, non-gating.
- **`py/mixed-returns`, `py/import-and-import-from` (note)** — stylistic, outside production execution; accepted.

## Honest boundary

This report closes the EXT-001 *evidence* gap (findings → remediation are now mapped
and retained). It is **not** a clean-bill security claim: 16 note/warning-tier findings
remain open in non-shipping scope and are explicitly tracked above, not silently cleared.
